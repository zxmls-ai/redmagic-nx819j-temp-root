import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

import nx819j_root as root


class DeviceSelectionTests(unittest.TestCase):
    def test_single_authorized(self):
        self.assertEqual(root.select_device("List of devices attached\nTEST-A\tdevice\n"), "TEST-A")

    def test_multiple_rejected(self):
        with self.assertRaises(RuntimeError):
            root.select_device("TEST-A\tdevice\nTEST-B\tdevice")

    def test_explicit_device(self):
        self.assertEqual(root.select_device("TEST-A\tdevice\nTEST-B\tdevice", "TEST-B"), "TEST-B")

    def test_unauthorized_rejected(self):
        with self.assertRaises(RuntimeError):
            root.select_device("TEST-A\tunauthorized", "TEST-A")

    def test_no_devices_rejected(self):
        with self.assertRaises(RuntimeError):
            root.select_device("List of devices attached\n")

    def test_offline_companion_requires_selection(self):
        with self.assertRaises(RuntimeError):
            root.select_device("TEST-A\tdevice\nTEST-B\toffline")


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.expected = {"model": "TEST", "kernel": "1-full-string", "incremental": "build-A"}
        self.actual = dict(self.expected, boot_completed="1", locked="1")

    def test_exact_match(self):
        root.validate_device(self.actual, self.expected)

    def test_wrong_kernel(self):
        self.actual["kernel"] = "1-different-string"
        with self.assertRaises(RuntimeError):
            root.validate_device(self.actual, self.expected)

    def test_wrong_build(self):
        self.actual["incremental"] = "build-B"
        with self.assertRaises(RuntimeError):
            root.validate_device(self.actual, self.expected)

    def test_unlocked_rejected(self):
        self.actual["locked"] = "0"
        with self.assertRaises(RuntimeError):
            root.validate_device(self.actual, self.expected)


class AssetTests(unittest.TestCase):
    def test_tampered_content_same_length(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / "sample").write_bytes(b"abc")
            manifest = {"sample": {"size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}}
            root.verify_assets(directory, manifest)
            (directory / "sample").write_bytes(b"abd")
            with self.assertRaises(RuntimeError):
                root.verify_assets(directory, manifest)

    def test_cleanup_is_scoped(self):
        original = "cleanup() {\n  rm -rf /data/local/tmp/nx819j-*\n}\n"
        self.assertIn('rm -rf "$D"', root.scoped_run_script(original))
        with self.assertRaises(RuntimeError):
            root.scoped_run_script(original + original)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.capture = Path(self.temp.name)
        # Synthetic small values: no real device addresses or boot identifiers.
        (self.capture / "symbols.txt").write_text(
            "1000 T first\n2000 T second\n3000 T third\n4000 D selinux_state\n")
        (self.capture / "bl_text.txt").write_text(
            "caller=first+0x4/0x20\ncaller=second+0x4/0x20\ncaller=third+0x4/0x20\n")
        (self.capture / "slide.txt").write_text("0x100")
        (self.capture / "target.txt").write_text(hex(0x4000 + 0x100 - 7))
        (self.capture / "boot_id.txt").write_text("synthetic-boot-A")
        (self.capture / "bl_0.bin").write_bytes(struct.pack("<QQQ", 0x1104, 0x2104, 0x3104))

    def verify(self, boot="synthetic-boot-A"):
        return root.verify_capture(self.capture, self.capture / "symbols.txt", boot)

    def test_three_distinct_matches(self):
        self.assertEqual(self.verify()["matching_symbol_count"], 3)

    def test_stale_boot_rejected(self):
        with self.assertRaises(RuntimeError):
            self.verify("synthetic-boot-B")

    def test_wrong_target_rejected(self):
        (self.capture / "target.txt").write_text("0x1234")
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_too_few_matches_rejected(self):
        (self.capture / "bl_0.bin").write_bytes(struct.pack("<QQ", 0x1104, 0x2104))
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_repeated_symbol_not_three_votes(self):
        (self.capture / "bl_text.txt").write_text("caller=first+0x4/0x20\n" * 10)
        with self.assertRaises(RuntimeError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
