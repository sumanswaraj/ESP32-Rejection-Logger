"""Hardware-free tests of the desktop bridge's preservation boundaries."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backend


class BackendTests(unittest.TestCase):
    def test_bad_request_shape_returns_complete_error_object(self):
        for request in ([], None, {}, {"operation": "erase_everything"}, {"operation": "info", "port": "COM3", "unexpected": 1}):
            with self.subTest(request=request):
                response = backend.handle(request)
                self.assertFalse(response["ok"])
                self.assertIsNone(response["result"])
                self.assertIsInstance(response["error"], str)

    def test_info_defaults_to_reading_without_reset(self):
        device = {"chip": "esp32", "pending_events": 3, "sequence": 7}
        for fields in ({}, {"reset": False}):
            with self.subTest(fields=fields), \
                 patch.object(backend.qc_core, "read_device", return_value=device) as read:
                response = backend.handle({"operation": "info", "port": "COM6", **fields})
                self.assertTrue(response["ok"])
                self.assertEqual(response["result"], device)
                read.assert_called_once_with("COM6")

    def test_info_forwards_explicit_reset_request(self):
        device = {"chip": "esp32", "storage_fault": True}
        with patch.object(backend.qc_core, "read_device", return_value=device) as read:
            response = backend.handle({"operation": "info", "port": "COM6", "reset": True})
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"], device)
        read.assert_called_once_with("COM6", reset=True)

    def test_info_rejects_non_boolean_reset_before_touching_hardware(self):
        with patch.object(backend.qc_core, "read_device") as read, \
             patch.object(backend.qc_core, "detect") as detect, \
             patch.object(backend.qc_core, "serial_request") as serial:
            for reset in (None, 0, 1, "false", "true", [], {}):
                with self.subTest(reset=reset):
                    response = backend.handle({"operation": "info", "port": "COM6", "reset": reset})
                    self.assertFalse(response["ok"])
                    self.assertIsNone(response["result"])
                    self.assertIsInstance(response["error"], str)
            read.assert_not_called()
            detect.assert_not_called()
            serial.assert_not_called()

    def test_flash_defaults_preserve_and_validates_explicit_bundle(self):
        device = {"chip": "esp32s3", "layout_mb": 16, "flash_mb": 16}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "firmware/esp32s3-16MB"
            bundle.mkdir(parents=True)
            (bundle / "manifest.json").write_text("{}")
            with patch.object(backend, "ROOT", root), patch.object(backend.qc_core, "detect", return_value=device), \
                 patch.object(backend.qc_core, "validate_bundle") as validate, patch.object(backend.qc_core, "flash", return_value=device) as flash:
                response = backend.handle({"operation": "flash", "port": "COM3"})
                self.assertTrue(response["ok"])
                validate.assert_called_once_with(bundle, "esp32s3", 16)
                self.assertFalse(flash.call_args.kwargs["new_install"])
                self.assertEqual(flash.call_args.kwargs["bundle"], bundle)

    def test_layout_consent_required_before_hardware_is_touched(self):
        with patch.object(backend.qc_core, "detect") as detect:
            for value in (True, "yes", 1):
                response = backend.handle({"operation": "flash", "port": "COM3", "new_install": value})
                self.assertFalse(response["ok"])
            detect.assert_not_called()

    def test_missing_firmware_prevents_flash(self):
        device = {"chip": "esp32", "layout_mb": 4, "flash_mb": 4}
        with tempfile.TemporaryDirectory() as temporary, patch.object(backend, "ROOT", Path(temporary)), \
             patch.object(backend.qc_core, "detect", return_value=device), patch.object(backend.qc_core, "flash") as flash:
            response = backend.handle({"operation": "flash", "port": "COM3"})
            self.assertFalse(response["ok"])
            flash.assert_not_called()

    def test_invalid_packaged_manifest_prevents_flash(self):
        device = {"chip": "esp32", "layout_mb": 4, "flash_mb": 4}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "firmware/esp32-4MB"
            bundle.mkdir(parents=True)
            (bundle / "manifest.json").write_text('{"schema_version":1,"chip":"esp32s3"}')
            with patch.object(backend, "ROOT", root), patch.object(backend.qc_core, "detect", return_value=device), \
                 patch.object(backend.qc_core, "flash") as flash:
                response = backend.handle({"operation": "flash", "port": "COM3"})
                self.assertFalse(response["ok"])
                self.assertIn("different chip", response["error"])
                flash.assert_not_called()

    def test_credential_omissions_are_preserved(self):
        with patch.object(backend.qc_core, "configure", return_value={"message": "saved"}) as configure:
            response = backend.handle({"operation": "configure", "port": "COM3", "network": {"ssid": "Factory"}})
            self.assertTrue(response["ok"])
            self.assertEqual(configure.call_args.kwargs["network"], {"ssid": "Factory"})
            self.assertNotIn("password", configure.call_args.kwargs["network"])
            self.assertNotIn("api_key", configure.call_args.kwargs["network"])

    def test_explicit_empty_credentials_are_not_silently_dropped(self):
        with patch.object(backend.qc_core, "configure", return_value={}) as configure:
            response = backend.handle({"operation": "configure", "port": "COM3", "network": {"password": "", "api_key": ""}})
            self.assertTrue(response["ok"])
            self.assertEqual(configure.call_args.kwargs["network"], {"password": "", "api_key": ""})

    def test_wrong_chip_gpio_profile_is_rejected(self):
        with patch.object(backend.qc_core, "read_device", return_value={"chip": "esp32c3"}), \
             patch.object(backend.qc_core, "configure") as configure:
            response = backend.handle({"operation": "configure", "port": "COM3", "profile": "esp32s3-existing"})
            self.assertFalse(response["ok"])
            configure.assert_not_called()

    def test_initialize_requires_consent_and_no_capture_history(self):
        clean = {"sequence": 0, "pending_events": 0, "storage_fault": True}
        with patch.object(backend.qc_core, "read_device", return_value=clean) as read, \
             patch.object(backend.qc_core, "serial_request", return_value={"message": "initialized"}) as serial:
            self.assertFalse(backend.handle({"operation": "initialize_storage", "port": "COM3"})["ok"])
            read.assert_not_called()
            request = {"operation": "initialize_storage", "port": "COM3", "confirm": "FORMAT EMPTY STORAGE"}
            for device in ({**clean, "sequence": 1}, {**clean, "pending_events": 1}, {**clean, "storage_fault": False}, {"storage_fault": True}):
                read.return_value = device
                self.assertFalse(backend.handle(request)["ok"])
                serial.assert_not_called()
            read.return_value = clean
            self.assertTrue(backend.handle(request)["ok"])
            serial.assert_called_once_with("COM3", "initialize_storage", {"confirm": "FORMAT EMPTY STORAGE"})

    def test_credentials_are_redacted_in_logs_errors_and_result(self):
        request = {"operation": "configure", "port": "COM3", "network": {"password": "secret-password", "api_key": "private-key"}}
        logs = []

        def fail(*args, **kwargs):
            raise RuntimeError("secret-password private-key https://example.com?token=another-secret")

        with patch.object(backend.qc_core, "configure", side_effect=fail):
            response = backend.handle(request, log=logs.append)
        self.assertNotIn("secret-password", json.dumps(response))
        self.assertNotIn("private-key", json.dumps(response))
        self.assertNotIn("another-secret", json.dumps(response))
        with patch.object(backend.qc_core, "configure", return_value={"password": "old-secret", "message": "saved private-key"}):
            response = backend.handle(request)
        self.assertEqual(response["result"]["password"], "[redacted]")
        self.assertNotIn("private-key", json.dumps(response))

    def test_stream_redacts_secret_split_across_writes(self):
        destination = io.StringIO()
        stream = backend.DiagnosticStream(destination, backend.Redactor({"password": "split-secret"}))
        stream.write("split-")
        stream.flush()
        stream.write("secret\n")
        stream.finish()
        self.assertNotIn("split-secret", destination.getvalue())
        self.assertIn("[redacted]", destination.getvalue())

    def test_stream_redacts_multiline_supplied_credentials(self):
        destination = io.StringIO()
        stream = backend.DiagnosticStream(destination, backend.Redactor({"password": "first-secret\nsecond-secret"}))
        stream.write("first-secret\nsecond-secret\n")
        stream.finish()
        self.assertNotIn("first-secret", destination.getvalue())
        self.assertNotIn("second-secret", destination.getvalue())

    def test_cli_outputs_single_json_line_without_traceback(self):
        for value in (b"invalid", b"[]", b'{"operation":"info","port":"COM3","password":"secret"}'):
            completed = subprocess.run([sys.executable, str(Path(backend.__file__))], input=value, capture_output=True)
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(len(completed.stdout.splitlines()), 1)
            response = json.loads(completed.stdout)
            self.assertFalse(response["ok"])
            self.assertEqual(completed.stderr, b"")


if __name__ == "__main__":
    unittest.main()
