"""NX819J temporary Root workflow. Default: inspect only; --activate opts in.

External payloads are not distributed here. See materials.json and THIRD_PARTY.md.
"""
from pathlib import Path
import argparse
import collections
import datetime
import hashlib
import json
import queue
import re
import shlex
import struct
import subprocess
import sys
import threading
import time
import uuid

BASE = Path(__file__).resolve().parent


def select_device(output, requested=None):
    devices = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] in {"device", "unauthorized", "offline"}:
            devices.append((fields[0], fields[1]))
    if requested:
        if (requested, "device") not in devices:
            raise RuntimeError("指定设备未连接或未授权 USB 调试。")
        return requested
    if len(devices) != 1 or devices[0][1] != "device":
        raise RuntimeError("请只连接一台已授权的手机，或用 --serial 明确选择设备。")
    return devices[0][0]


def validate_device(actual, expected):
    for key in ("model", "kernel", "incremental"):
        if actual[key] != expected[key]:
            raise RuntimeError("设备条件不匹配：" + key + "。不要修改检查值强行继续。")
    if actual["boot_completed"] != "1" or actual["locked"] != "1":
        raise RuntimeError("手机尚未完成启动，或 BL 状态不符合本次测试条件。")


def verify_assets(directory, manifest):
    for name, expected in manifest.items():
        data = (directory / name).read_bytes()
        if len(data) != expected["size"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise RuntimeError("物料校验失败：" + name)


def scoped_run_script(original):
    # Patch only the upstream cleanup scope, after verifying the original hash.
    old = '  rm -rf /data/local/tmp/nx819j-*'
    if original.count(old) != 1:
        raise RuntimeError("上游清理逻辑与预期不同，已停止。")
    return original.replace(old, '  rm -rf "$D"')


def verify_capture(capture, symbols_path, current_boot):
    symbols = {}
    for line in symbols_path.read_text(encoding="utf-8").splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    anchors = collections.Counter(re.findall(
        r"caller=([A-Za-z_][A-Za-z0-9_.]*)\+0x([0-9a-fA-F]+)/0x[0-9a-fA-F]+",
        (capture / "bl_text.txt").read_text(encoding="utf-8")))
    slide = int((capture / "slide.txt").read_text().strip(), 0)
    target = int((capture / "target.txt").read_text().strip(), 0)
    raw = b"".join(p.read_bytes() for p in sorted(capture.glob("bl_*.bin")))
    matching = set()
    for (name, offset), _ in anchors.most_common(40):
        if name in symbols:
            address = symbols[name] + int(offset, 16) + slide
            if 0 <= address < 2**64 and struct.pack("<Q", address) in raw:
                matching.add(name)
    boot = (capture / "boot_id.txt").read_text().strip()
    if not boot or boot != current_boot:
        raise RuntimeError("手机已经重启，或启动标识无效；采样不能复用。")
    if target != symbols["selinux_state"] + slide - 7 or len(matching) < 3:
        raise RuntimeError("独立地址校验未通过，已停止。")
    return {"matching_symbol_count": len(matching), "same_boot": True, "target_match": True}


class Device:
    def __init__(self, adb, serial):
        self.prefix = [adb, "-s", serial]

    def call(self, *args, timeout=60, check=True):
        result = subprocess.run(self.prefix + list(args), capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout)
        if check and result.returncode:
            raise RuntimeError("ADB 操作失败：" + result.stdout.strip() + " " + result.stderr.strip())
        return result.stdout.strip()

    def shell(self, command, **kwargs):
        return self.call("shell", command, **kwargs)

    def verify_root(self):
        result = self.shell("su -c 'id; getenforce; grep kernelsu /proc/modules'", timeout=30)
        if ("uid=0(root)" not in result or "\nEnforcing\n" not in result
                or not re.search(r"^kernelsu\s.*\sLive\s", result, re.M)):
            raise RuntimeError("Root、KernelSU 模块或 SELinux 校验未通过。")
        if self.shell("getprop ro.boot.flash.locked") != "1":
            raise RuntimeError("BL 状态与已验证条件不一致。")
        return "Root=uid0; KernelSU=Live; SELinux=Enforcing; BL=locked"


def run_payload(device, remote, logdir, timeout=4500):
    command = f"NX819J_DIR={remote} sh {remote}/run.sh 2>&1"
    process = subprocess.Popen(device.prefix + ["shell", command], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                               errors="replace", bufsize=1)
    lines = queue.Queue()

    def reader():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + timeout
    try:
        with (logdir / "root.log").open("w", encoding="utf-8") as log:
            while time.monotonic() < deadline:
                try:
                    line = lines.get(timeout=1)
                except queue.Empty:
                    continue
                if line is None:
                    raise RuntimeError("上游流程在 DONE 前结束，请保留本地日志。")
                log.write(line)
                log.flush()
                # Raw addresses remain in ignored local logs, not normal console output.
                if line.startswith("[") or line.strip() in {
                    "MODULE_LOADED", "SELINUX_RESTORED", "KSU_MANAGER_LAUNCHED", "DONE"
                }:
                    print(line, end="", flush=True)
                if line.strip() == "DONE":
                    result = device.verify_root()
                    (logdir / "verification.txt").write_text(result + "\n", encoding="utf-8")
                    return result
            raise RuntimeError("等待超过 75 分钟，未确认成功。设备端进程可能仍在运行。")
    finally:
        # Close this host-side client only. Do not kill the device's loader worker.
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb", help="adb executable path")
    parser.add_argument("--serial", help="explicit ADB device identifier; never stored in reports")
    parser.add_argument("--assets", type=Path, default=BASE / "vendor" / "assets")
    parser.add_argument("--activate", action="store_true", help="run the temporary Root workflow")
    args = parser.parse_args()
    manifest = json.loads((BASE / "materials.json").read_text(encoding="utf-8"))
    listing = subprocess.run([args.adb, "devices"], check=True, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=30)
    device = Device(args.adb, select_device(listing.stdout, args.serial))
    commands = {"model": "getprop ro.product.model", "kernel": "uname -r",
                "incremental": "getprop ro.build.version.incremental",
                "boot_completed": "getprop sys.boot_completed",
                "locked": "getprop ro.boot.flash.locked"}
    info = {key: device.shell(cmd) for key, cmd in commands.items()}
    validate_device(info, manifest["device"])
    print(json.dumps(info, ensure_ascii=False, indent=2), flush=True)
    modules = device.shell("cat /proc/modules")
    if re.search(r"^kernelsu\s", modules, re.M):
        print(device.verify_root())
        print("临时 Root 已生效；没有再次执行提权。")
        return
    if device.shell("getenforce") != "Enforcing":
        raise RuntimeError("起始 SELinux 状态异常；请先正常重启，再重新检查。")
    if device.shell("pidof t64560_loader2 t64560_v36 t64560_w2", check=False):
        raise RuntimeError("检测到残留提权进程；请先正常重启，不能叠加运行。")
    manager = device.shell("pm path me.weishu.kernelsu", check=False)
    print("KernelSU 管理器：" + ("已安装" if manager.startswith("package:") else "未安装"))
    if not args.activate:
        print("只读检查完成，尚未运行采样或提权。实际成功仍需 --activate 验证。")
        return
    if not manager.startswith("package:"):
        raise RuntimeError("请先安装材料清单指定的 KernelSU.apk。")
    verify_assets(args.assets, manifest["assets"])
    run_script = scoped_run_script((args.assets / "run.sh").read_text(encoding="utf-8"))
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    logdir = BASE / "logs" / stamp
    logdir.mkdir(parents=True)
    remote = "/data/local/tmp/nx819j-publish-" + uuid.uuid4().hex
    print("本地私有日志：" + str(logdir), flush=True)
    # The installed base APK must match the tested manager, not just its package name.
    package_paths = [line[8:] for line in manager.splitlines() if line.startswith("package:")]
    if len(package_paths) != 1:
        raise RuntimeError("管理器安装形式与测试不一致；预期为单个 APK。")
    installed_manager = logdir / "manager.apk"
    device.call("pull", package_paths[0], str(installed_manager))
    if hashlib.sha256(installed_manager.read_bytes()).hexdigest() != manifest["manager"]["sha256"]:
        raise RuntimeError("已安装 KernelSU.apk 的哈希与测试版本不一致。")
    installed_manager.unlink()
    runtime = logdir / "run.sh"
    runtime.write_text(run_script, encoding="utf-8", newline="\n")
    print("部署已校验物料并采样……", flush=True)
    device.shell("mkdir " + shlex.quote(remote))
    for name in manifest["assets"]:
        path = runtime if name == "run.sh" else args.assets / name
        device.call("push", str(path), remote + "/" + name)
    device.call("push", str(BASE / "scripts" / "capture.sh"), remote + "/capture.sh")
    captured = device.shell(f"sh {remote}/capture.sh {remote} 2>&1", timeout=120)
    (logdir / "capture.log").write_text(captured, encoding="utf-8")
    device.call("pull", remote + "/bl", str(logdir / "capture"))
    evidence = verify_capture(logdir / "capture", args.assets / "syms.txt",
                              device.shell("cat /proc/sys/kernel/random/boot_id"))
    (logdir / "independent-check.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    device.call("push", str(BASE / "scripts" / "use_capture.sh"), remote + "/take_slide.sh")
    print("当前启动采样校验通过；运行上游流程。请保持 USB 连接。", flush=True)
    print(run_payload(device, remote, logdir))
    print("临时 Root 已验证。重启会失效；更新后必须重新评估，不能照搬旧物料。")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print("已停止：" + str(error), file=sys.stderr)
        print("如已进入提权阶段，请保留日志并正常重启后再评估；程序不会自动回滚或反复重试。", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("已中断电脑端等待；设备端操作可能尚未结束，请勿立即重复运行。", file=sys.stderr)
        sys.exit(130)
