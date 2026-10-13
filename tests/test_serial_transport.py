"""Exercise commissioning control lines and RPC framing without a physical board.

Run with: python -m unittest discover -s tests -p 'test_serial_transport.py' -v
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qc_core


class FakeSerial:
    """Record observable pyserial operations; generate replies from sent frames."""

    def __init__(self, on_write=None, **kwargs):
        self.options = kwargs
        self.port = kwargs.get("port")
        self._dtr = True
        self._rts = True
        self.is_open = False
        self.events = []
        self.pending = bytearray()
        self.requests = []
        self.on_write = on_write
        self.read_limit = None

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, value):
        self._dtr = value
        self.events.append(("dtr", value, self.is_open))

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, value):
        self._rts = value
        self.events.append(("rts", value, self._dtr, self.is_open))

    def open(self):
        self.events.append(("open", self._dtr, self._rts))
        self.is_open = True

    def close(self):
        self.events.append(("close", self._dtr, self._rts))
        self.is_open = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @property
    def in_waiting(self):
        return len(self.pending)

    def read(self, size=1):
        if self.read_limit is not None:
            size = min(size, self.read_limit)
        chunk = bytes(self.pending[:size])
        del self.pending[:size]
        return chunk

    def write(self, data):
        self.events.append(("write", bytes(data)))
        request = json.loads(data.decode("utf-8"))
        self.requests.append(request)
        if self.on_write:
            self.pending.extend(self.on_write(request))
        return len(data)

    def flush(self):
        self.events.append(("flush",))

    def reset_input_buffer(self):
        self.events.append(("reset_input_buffer",))
        self.pending.clear()


def rpc(request, *, id_override=None, device=None):
    response = {
        "protocol": 1,
        "id": request["id"] if id_override is None else id_override,
        "ok": True,
        "message": "Credentials hidden",
    }
    if device is not None:
        response["device"] = device
    return b"QC_RPC " + json.dumps(response).encode("utf-8") + b"\n"


class SerialTransportTests(unittest.TestCase):
    def setUp(self):
        self.links = []
        self.on_write = None
        self.initial_boot_output = b""
        self.read_limit = None
        self.ports = [SimpleNamespace(device="COM6", vid=0x10C4)]

        def construct(**kwargs):
            link = FakeSerial(on_write=self.on_write, **kwargs)
            link.pending.extend(self.initial_boot_output)
            link.read_limit = self.read_limit
            self.links.append(link)
            return link

        self.serial_patch = patch("serial.Serial", side_effect=construct)
        self.ports_patch = patch("serial.tools.list_ports.comports", side_effect=lambda: self.ports)
        self.sleep_patch = patch.object(qc_core.time, "sleep", return_value=None)
        self.clock_patch = patch.object(qc_core.time, "monotonic", side_effect=itertools.count(0.0, 0.1))
        for mocked in (self.serial_patch, self.ports_patch, self.sleep_patch, self.clock_patch):
            mocked.start()
            self.addCleanup(mocked.stop)

    def link(self):
        self.assertEqual(len(self.links), 1)
        return self.links[0]

    def assert_dtr_never_asserted(self, link):
        self.assertFalse(any(event[:2] == ("dtr", True) for event in link.events), link.events)

    def test_uart_port_releases_boot_and_reset_before_open_and_close(self):
        with qc_core.commissioning_link("COM6") as link:
            self.assertFalse(link.dtr)
            self.assertFalse(link.rts)
        link = self.link()
        self.assertIn(("open", False, False), link.events)
        self.assertEqual(link.events[-1], ("close", False, False))
        self.assert_dtr_never_asserted(link)

    def test_unknown_port_defaults_to_uart_without_asserting_boot(self):
        self.ports = [SimpleNamespace(device="COM99", vid=0x303A)]
        with qc_core.commissioning_link("COM6"):
            pass
        self.assert_dtr_never_asserted(self.link())

    def test_missing_vid_defaults_to_uart_without_asserting_boot(self):
        self.ports = [SimpleNamespace(device="COM6", vid=None)]
        with qc_core.commissioning_link("COM6"):
            pass
        self.assert_dtr_never_asserted(self.link())

    def test_native_usb_enables_cdc_only_after_open_and_releases_before_close(self):
        self.ports = [SimpleNamespace(device="COM6", vid=0x303A)]
        with qc_core.commissioning_link("COM6") as link:
            self.assertTrue(link.dtr)
            self.assertFalse(link.rts)
        events = self.link().events
        self.assertIn(("open", False, False), events)
        self.assertIn(("dtr", True, True), events)
        self.assertGreater(events.index(("dtr", True, True)), events.index(("open", False, False)))
        self.assertEqual(events[-1], ("close", False, False))
        self.assertFalse(any(event[0] == "rts" and event[1] for event in events))

    def test_explicit_uart_override_works_for_native_usb_vid(self):
        self.ports = [SimpleNamespace(device="COM6", vid=0x303A)]
        with qc_core.commissioning_link("COM6", native_usb=False):
            pass
        self.assert_dtr_never_asserted(self.link())

    def test_explicit_native_override_enables_cdc_on_unlisted_port(self):
        self.ports = []
        with qc_core.commissioning_link("COM6", native_usb=True) as link:
            self.assertTrue(link.dtr)
        self.assertEqual(self.link().events[-1], ("close", False, False))

    def test_uart_reset_pulses_en_while_boot_stays_released(self):
        with qc_core.commissioning_link("COM6", native_usb=False, reset=True):
            pass
        link = self.link()
        self.assert_dtr_never_asserted(link)
        pulses = [event for event in link.events if event[0] == "rts" and event[1] is True]
        self.assertEqual(len(pulses), 1, link.events)
        self.assertEqual(pulses[0], ("rts", True, False, True))
        pulse_index = link.events.index(pulses[0])
        self.assertTrue(any(event[:3] == ("rts", False, False)
                            for event in link.events[pulse_index + 1:]), link.events)
        self.assertEqual(link.events[-1], ("close", False, False))

    def test_native_usb_reset_is_rejected_without_reset_pulse_or_transmission(self):
        with self.assertRaises(qc_core.QCError) as caught:
            with qc_core.commissioning_link("COM6", native_usb=True, reset=True):
                self.fail("Native USB reset must not enter the context")
        self.assertRegex(str(caught.exception).lower(), r"reset")
        for link in self.links:
            self.assertFalse(any(event[0] == "rts" and event[1] for event in link.events))
            self.assertFalse(link.requests)

    def test_control_lines_are_released_when_request_raises(self):
        with self.assertRaisesRegex(RuntimeError, "simulated failure"):
            with qc_core.commissioning_link("COM6", native_usb=True):
                raise RuntimeError("simulated failure")
        self.assertEqual(self.link().events[-1], ("close", False, False))

    def test_read_device_filters_malformed_and_other_request_id_replies(self):
        device = {"chip": "esp32", "device_id": "TEST_DEVICE", "pending_events": 0}
        self.on_write = lambda request: (
            b"QC_RPC invalid-json\n"
            + rpc(request, id_override="unrelated-request", device={"chip": "wrong"})
            + b"ordinary boot output\n"
            + rpc(request, device=device)
        )
        self.assertEqual(qc_core.read_device("COM6", native_usb=False), device)
        self.assertEqual(self.link().requests[0]["command"], "info")
        self.assert_dtr_never_asserted(self.link())

    def test_read_device_forwards_uart_reset_option(self):
        self.on_write = lambda request: rpc(request, device={"chip": "esp32"})
        self.assertEqual(qc_core.read_device("COM6", native_usb=False, reset=True), {"chip": "esp32"})
        self.assertIn(("rts", True, False, True), self.link().events)
        self.assert_dtr_never_asserted(self.link())

    def test_rpc_reply_can_arrive_split_across_serial_reads(self):
        self.read_limit = 7
        self.on_write = lambda request: rpc(request, device={"chip": "esp32"})
        self.assertEqual(qc_core.read_device("COM6", native_usb=False), {"chip": "esp32"})

    def test_configure_handshake_does_not_transmit_configuration_until_info_replies(self):
        self.on_write = lambda request: rpc(request, device={"chip": "esp32"})
        payload = {"network": {"ssid": "TEST_SSID", "password": "TEST_PASSWORD_123"}}
        reply = qc_core.serial_request("COM6", "configure", payload, native_usb=False)
        self.assertTrue(reply["ok"])
        requests = self.link().requests
        self.assertEqual([request["command"] for request in requests], ["info", "configure"])
        self.assertNotIn("network", requests[0])
        self.assertEqual(requests[1]["network"], payload["network"])
        self.assertNotEqual(requests[0]["id"], requests[1]["id"])

    def test_timeout_diagnostics_classify_boot_failure_without_exposing_boot_secrets(self):
        diagnostic_cases = (
            ("DOWNLOAD_BOOT waiting for download", r"download"),
            ("Guru Meditation Error: Core 1 panic'ed; Backtrace: 0x400", r"crash|panic|backtrace|reset"),
            ("Stack canary watchpoint triggered", r"crash|panic|stack|reset"),
            ("Brownout detector was triggered", r"brownout|power"),
            ("invalid header: 0xffffffff", r"invalid|header|firmware|boot"),
        )
        sentinels = ("PRIVATE_TEST_SSID", "PRIVATE_TEST_PASSWORD", "PRIVATE_TEST_API_KEY")
        for diagnostic, expected_category in diagnostic_cases:
            with self.subTest(diagnostic=diagnostic):
                self.links.clear()
                private_output = (
                    "Setup AP: " + sentinels[0] + " | password " + sentinels[1] + "\n"
                    + diagnostic + " api_key=" + sentinels[2] + "\n"
                ).encode("utf-8")
                self.on_write = lambda _request, text=private_output: text
                with self.assertRaises(qc_core.QCError) as caught:
                    qc_core.serial_request("COM6", "info", timeout=0.5, native_usb=False)
                message = str(caught.exception)
                self.assertRegex(message.lower(), expected_category)
                for sentinel in sentinels:
                    self.assertNotIn(sentinel, message)
                self.assertNotIn("Setup AP:", message)
                self.assert_dtr_never_asserted(self.link())

    def test_plain_timeout_does_not_invent_a_boot_failure_or_leak_setup_password(self):
        self.on_write = lambda _request: b"Local control login: admin | password PRIVATE_BOOT_PASSWORD\n"
        with self.assertRaises(qc_core.QCError) as caught:
            qc_core.serial_request("COM6", "info", timeout=0.5, native_usb=False)
        message = str(caught.exception)
        self.assertIn("No configuration response", message)
        self.assertNotIn("PRIVATE_BOOT_PASSWORD", message)
        self.assertNotIn("Local control login", message)

    def test_startup_download_diagnostic_survives_input_buffer_reset(self):
        self.initial_boot_output = (
            b"Setup AP: PRIVATE_STARTUP_SSID password PRIVATE_STARTUP_PASSWORD\n"
            b"DOWNLOAD_BOOT waiting for download api_key=PRIVATE_STARTUP_KEY\n"
        )
        with self.assertRaises(qc_core.QCError) as caught:
            qc_core.serial_request("COM6", "info", timeout=0.5, native_usb=False)
        message = str(caught.exception)
        self.assertIn("download", message.lower())
        self.assertNotIn("PRIVATE_STARTUP_", message)
        self.assertIn(("reset_input_buffer",), self.link().events)


if __name__ == "__main__":
    unittest.main()
