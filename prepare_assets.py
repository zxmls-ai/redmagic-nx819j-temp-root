"""Verify the tested upstream APK and extract only the required local assets."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

BASE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(apk, output):
    manifest = json.loads((BASE / 'materials.json').read_text(encoding='utf-8'))
    if digest(apk.read_bytes()) != manifest['apk']['sha256']:
        raise ValueError('APK SHA-256 不匹配；只接受已实测的上游文件。')
    checked = {}
    with zipfile.ZipFile(apk) as archive:
        for name, expected in manifest['assets'].items():
            data = archive.read('assets/nx819j/' + name)
            if len(data) != expected['size'] or digest(data) != expected['sha256']:
                raise ValueError('物料校验失败：' + name)
            checked[name] = data
    output.mkdir(parents=True, exist_ok=True)
    for name, data in checked.items():
        (output / name).write_bytes(data)
    print(f'已校验并提取 {len(checked)} 个文件：{output}')
    print('这些第三方文件仅保存在本地 vendor/，不属于仓库的 MIT 授权内容。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=BASE / 'vendor' / 'assets')
    args = parser.parse_args()
    prepare(args.apk, args.output)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error))
