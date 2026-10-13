"""Verify commissioning identity edits cannot rewrite a captured logger."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qc_core


def fresh_device(**changes):
    return {
        "device_id": "LOGGER_ORIGINAL", "chip": "esp32",
        "logger_id_edit_supported": True, "identity_locked": False,
        "sequence": 0, "pending_events": 0, **changes,
    }


class LoggerIdentityTests(unittest.TestCase):
    def test_ascii_identifiers_accept_single_character_and_maximum_length(self):
        for value in ("A", "0", "_", "-", "Factory_Line-02", "a" * 80):
            with self.subTest(value=value):
                self.assertEqual(qc_core.validate_device_id(value), value)

    def test_invalid_ids_fail_before_any_hardware_access(self):
        for value in ("", "a" * 81, "with space", " x", "x ", "x.y", "x/y",
                      "x\n", "x\x00", "é", "Ａ", "汉字", 1, True, [], {}):
            with self.subTest(value=value), \
                 patch.object(qc_core, "read_device") as read, \
                 patch.object(qc_core, "serial_request") as write:
                with self.assertRaisesRegex(qc_core.QCError, "Logger ID"):
                    qc_core.configure("COM6", device_id=value)
                read.assert_not_called()
                write.assert_not_called()

    def test_id_only_change_reads_current_settings_then_sends_top_level_id(self):
        calls = []
        def read(port):
            calls.append(("read", port))
            return fresh_device()
        def write(port, command, payload):
            calls.append(("write", port, command, payload))
            return {"ok": True, "message": "saved"}
        with patch.object(qc_core, "read_device", side_effect=read), \
             patch.object(qc_core, "serial_request", side_effect=write):
            result = qc_core.configure("COM6", device_id="Factory_Line-02")
        self.assertTrue(result["ok"])
        self.assertEqual(calls, [("read", "COM6"),
                                 ("write", "COM6", "configure", {"device_id": "Factory_Line-02"})])

    def test_identity_and_network_changes_preserve_omitted_credentials(self):
        network = {"name": "Packing Line", "ssid": "Factory"}
        with patch.object(qc_core, "read_device", return_value=fresh_device()), \
             patch.object(qc_core, "serial_request", return_value={"ok": True}) as write:
            qc_core.configure("COM6", network=network, device_id="PACKING_01")
        payload = write.call_args.args[2]
        self.assertEqual(payload, {"network": network, "device_id": "PACKING_01"})
        self.assertNotIn("device_id", payload["network"])
        self.assertNotIn("password", payload["network"])
        self.assertNotIn("api_key", payload["network"])
        self.assertEqual(network, {"name": "Packing Line", "ssid": "Factory"})

    def test_changed_id_requires_explicit_firmware_capability(self):
        for capability in (None, False, 0, 1, "true"):
            device = fresh_device(logger_id_edit_supported=capability)
            with self.subTest(capability=capability), \
                 patch.object(qc_core, "read_device", return_value=device), \
                 patch.object(qc_core, "serial_request") as write:
                with self.assertRaisesRegex(qc_core.QCError, "upgrade"):
                    qc_core.configure("COM6", device_id="NEW_ID")
                write.assert_not_called()

    def test_captured_or_pending_events_refuse_the_whole_configuration(self):
        for history in ({"sequence": 1}, {"sequence": 500, "pending_events": 0},
                        {"pending_events": 1}, {"identity_locked": True}):
            with self.subTest(history=history), \
                 patch.object(qc_core, "read_device", return_value=fresh_device(**history)), \
                 patch.object(qc_core, "serial_request") as write:
                with self.assertRaisesRegex(qc_core.QCError, "locked.*display name"):
                    qc_core.configure("COM6", network={"name": "New display"}, device_id="NEW_ID")
                write.assert_not_called()

    def test_malformed_capture_history_cannot_authorize_an_edit(self):
        for field in ("sequence", "pending_events"):
            for value in (None, False, True, -1, 0.0, "0", [], {}):
                with self.subTest(field=field, value=value), \
                     patch.object(qc_core, "read_device", return_value=fresh_device(**{field: value})), \
                     patch.object(qc_core, "serial_request") as write:
                    with self.assertRaisesRegex(qc_core.QCError, "history.*invalid"):
                        qc_core.configure("COM6", device_id="NEW_ID")
                    write.assert_not_called()

    def test_missing_current_id_or_history_cannot_authorize_an_edit(self):
        for field in ("device_id", "sequence", "pending_events"):
            device = fresh_device()
            del device[field]
            with self.subTest(field=field), \
                 patch.object(qc_core, "read_device", return_value=device), \
                 patch.object(qc_core, "serial_request") as write:
                with self.assertRaises(qc_core.QCError):
                    qc_core.configure("COM6", device_id="NEW_ID")
                write.assert_not_called()

    def test_unchanged_id_is_a_no_op_even_with_older_or_captured_firmware(self):
        for device in (fresh_device(),
                       {"device_id": "LOGGER_ORIGINAL"},
                       fresh_device(sequence=10, identity_locked=True)):
            with self.subTest(device=device), \
                 patch.object(qc_core, "read_device", return_value=device) as read, \
                 patch.object(qc_core, "serial_request") as write:
                response = qc_core.configure("COM6", device_id="LOGGER_ORIGINAL")
                self.assertTrue(response["ok"])
                self.assertEqual(response["device"], device)
                read.assert_called_once_with("COM6")
                write.assert_not_called()

    def test_unchanged_id_retains_normal_network_flow_on_older_or_locked_firmware(self):
        for device in ({"device_id": "LOGGER_ORIGINAL"},
                       fresh_device(sequence=10, pending_events=3, identity_locked=True)):
            with self.subTest(device=device), \
                 patch.object(qc_core, "read_device", return_value=device), \
                 patch.object(qc_core, "serial_request", return_value={"ok": True}) as write:
                qc_core.configure("COM6", network={"name": "New display", "password": ""},
                                  device_id="LOGGER_ORIGINAL")
                write.assert_called_once_with("COM6", "configure", {"network": {"name": "New display", "password": ""}})

    def test_omitted_id_keeps_existing_network_only_behavior(self):
        with patch.object(qc_core, "read_device") as read, \
             patch.object(qc_core, "serial_request", return_value={"ok": True}) as write:
            qc_core.configure("COM6", network={"ssid": "Factory"})
        read.assert_not_called()
        write.assert_called_once_with("COM6", "configure", {"network": {"ssid": "Factory"}})

    def test_device_refusal_remains_authoritative_after_host_preflight(self):
        with patch.object(qc_core, "read_device", return_value=fresh_device()), \
             patch.object(qc_core, "serial_request", side_effect=qc_core.QCError("Logger ID became locked")):
            with self.assertRaisesRegex(qc_core.QCError, "became locked"):
                qc_core.configure("COM6", device_id="NEW_ID")


if __name__ == "__main__":
    unittest.main()
