"""Compile/run production identity and RPC headers against real ArduinoJson.

The Preferences/ESP/WiFi/GPIO boundaries are fakes. These tests verify the
firmware's decisions and write protocol, not physical NVS power-loss behavior.
Requires a host C++17 compiler and the repository's installed ArduinoJson.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class FirmwareLoggerIdTests(unittest.TestCase):
    def test_actual_firmware_identity_and_rpc_headers(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which("g++") or shutil.which("clang++")
        self.assertIsNotNone(compiler, "Install a host C++17 compiler for the firmware regression tests")
        library = root / ".toolchain/user/libraries/ArduinoJson/src"
        self.assertTrue((library / "ArduinoJson.h").is_file(), "Install the pinned toolchain with build_all.py --setup first")
        with tempfile.TemporaryDirectory(prefix="firmware-identity-") as temporary:
            binary = Path(temporary) / "firmware_logger_id"
            command = [
                compiler, "-std=c++17", "-DCONFIG_IDF_TARGET_ESP32",
                "-DARDUINOJSON_ENABLE_ARDUINO_STRING=1", "-DARDUINOJSON_ENABLE_ARDUINO_STREAM=0",
                "-DARDUINOJSON_ENABLE_ARDUINO_PRINT=0", "-DARDUINOJSON_ENABLE_PROGMEM=0",
                "-Wno-deprecated-declarations", "-I", str(root / "tests/firmware_stubs"),
                "-I", str(root / "ESP32_QC_Terminal"), "-I", str(library),
                str(root / "tests/firmware_logger_id.cpp"), "-o", str(binary),
            ]
            compiled = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            tested = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(tested.returncode, 0, tested.stdout + tested.stderr)
            self.assertIn("firmware Logger ID assertions", tested.stdout)


if __name__ == "__main__":
    unittest.main()
