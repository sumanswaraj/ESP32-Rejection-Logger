"""Private JSON bridge for the Windows launcher; existing firmware APIs stay intact.

Read one UTF-8 JSON object on stdin. Write one {ok, result, error} object on
stdout. Diagnostic output goes to stderr with supplied credentials redacted.
No request data is passed through command-line arguments or written to disk.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# The embedded interpreter is not itself frozen. Keep flash backups outside
# the downloaded application directory in the existing durable data location.
os.environ["QC_DESKTOP_PACKAGED"] = "1"

import qc_core

MAX_REQUEST_BYTES = 64 * 1024
SECRET_FIELDS = {"password", "api_key", "token", "passkey", "secret", "ca"}
OPERATIONS = {
    "ports": {"operation"},
    "detect": {"operation", "port"},
    "flash": {"operation", "port", "new_install", "confirm"},
    "info": {"operation", "port", "reset"},
    "configure": {"operation", "port", "network", "profile", "pins", "touch_active_low", "device_id"},
    "initialize_storage": {"operation", "port", "confirm"},
}


class Redactor:
    def __init__(self, request: Any):
        values: set[str] = set()

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if str(key).lower() in SECRET_FIELDS and isinstance(item, str) and item:
                        values.add(item)
                        values.update(part for part in item.splitlines() if part)
                    else:
                        collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(request)
        self.values = sorted(values, key=len, reverse=True)

    def text(self, value: Any) -> str:
        value = str(value)
        for secret in self.values:
            value = value.replace(secret, "[redacted]")
        # Libraries can include an endpoint in errors. Suppress complete URLs
        # in diagnostics because their query strings may contain credentials.
        return re.sub(r"https?://[^\s<>\"']+", "[URL omitted]", value)

    def result(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[redacted]" if str(key).lower() in SECRET_FIELDS else self.result(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.result(item) for item in value]
        if isinstance(value, tuple):
            return [self.result(item) for item in value]
        if isinstance(value, str):
            for secret in self.values:
                value = value.replace(secret, "[redacted]")
        return value


class DiagnosticStream(io.TextIOBase):
    """Buffer complete lines so secrets split across writes remain redacted."""

    def __init__(self, destination, redactor: Redactor):
        self.destination = destination
        self.redactor = redactor
        self.pending = ""
        self.omitted = False

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        for part in value.splitlines(keepends=True):
            if not self.omitted:
                self.pending += part
                if len(self.pending) > MAX_REQUEST_BYTES:
                    self.pending = ""
                    self.omitted = True
            if part.endswith(("\n", "\r")):
                self._emit()
        return len(value)

    def _emit(self) -> None:
        if self.omitted:
            self.destination.write("Diagnostic line omitted (too long).\n")
        elif self.pending:
            self.destination.write(self.redactor.text(self.pending))
        self.pending = ""
        self.omitted = False
        self.destination.flush()

    def flush(self) -> None:
        # Preserve partial lines until completion or finish(), even if a
        # library flushes between pieces of a credential.
        self.destination.flush()

    def finish(self) -> None:
        self._emit()


def _port(request: dict) -> str:
    port = request.get("port")
    if not isinstance(port, str) or not port or len(port) > 256 or any(ord(c) < 32 for c in port):
        raise qc_core.QCError("Select a valid serial port.")
    return port


def _validate(request: Any) -> str:
    if not isinstance(request, dict):
        raise qc_core.QCError("The request must be a JSON object.")
    operation = request.get("operation")
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise qc_core.QCError("Unknown operation.")
    if set(request) - OPERATIONS[operation]:
        raise qc_core.QCError("Unexpected request fields.")
    if operation != "ports":
        _port(request)
    return operation


def _bundle_for(device: dict) -> Path:
    chip, mb, physical = device.get("chip"), device.get("layout_mb"), device.get("flash_mb")
    if chip not in qc_core.CHIPS or type(mb) is not int or mb not in qc_core.FLASH_MB:
        raise qc_core.QCError("The detected board has no supported firmware target.")
    if type(physical) is not int or physical < mb:
        raise qc_core.QCError("The detected flash size is invalid.")
    bundle = ROOT / "firmware" / f"{chip}-{mb}MB"
    if not (bundle / "manifest.json").is_file():
        raise qc_core.QCError("Matching firmware is missing. Download and extract the complete Windows package.")
    # Check the packaged images before connecting a second time to flash.
    qc_core.validate_bundle(bundle, chip, physical)
    return bundle


def dispatch(request: dict, log=lambda message: None) -> Any:
    operation = _validate(request)
    if operation == "ports":
        from serial.tools import list_ports
        return [
            {"port": port.device, "description": port.description or "Serial port", "manufacturer": port.manufacturer,
             "vid": port.vid, "pid": port.pid, "serial_number": port.serial_number}
            for port in sorted(list_ports.comports(), key=lambda item: item.device)
        ]
    port = _port(request)
    if operation == "detect":
        return qc_core.detect(port)
    if operation == "info":
        reset = request.get("reset", False)
        if type(reset) is not bool:
            raise qc_core.QCError("Reset must be true or false.")
        if reset:
            return qc_core.read_device(port, reset=True)
        return qc_core.read_device(port)
    if operation == "flash":
        new_install = request.get("new_install", False)
        if type(new_install) is not bool:
            raise qc_core.QCError("New installation must be true or false.")
        if new_install and request.get("confirm") != "CHANGE PARTITION LAYOUT":
            raise qc_core.QCError("Confirm CHANGE PARTITION LAYOUT before permitting a different layout.")
        device = qc_core.detect(port)
        bundle = _bundle_for(device)
        return qc_core.flash(port, new_install=new_install, bundle=bundle, log=log)
    if operation == "initialize_storage":
        if request.get("confirm") != "FORMAT EMPTY STORAGE":
            raise qc_core.QCError("Confirm FORMAT EMPTY STORAGE to initialize a new device.")
        device = qc_core.read_device(port)
        if (type(device.get("sequence")) is not int or device["sequence"] != 0
                or type(device.get("pending_events")) is not int or device["pending_events"] != 0
                or device.get("storage_fault") is not True):
            raise qc_core.QCError("Only unformatted devices without capture history can be initialized.")
        return qc_core.serial_request(port, "initialize_storage", {"confirm": "FORMAT EMPTY STORAGE"})
    if "device_id" in request:
        qc_core.validate_device_id(request["device_id"])
    network = request.get("network")
    if network is not None:
        if not isinstance(network, dict):
            raise qc_core.QCError("Network settings must be an object.")
        qc_core.validate_network(network)
    if "pins" in request and "profile" in request:
        raise qc_core.QCError("Choose a GPIO profile or a custom pin map, not both.")
    pins = request.get("pins")
    if "pins" in request and not isinstance(pins, dict):
        raise qc_core.QCError("The pin map must be an object.")
    if "profile" in request:
        profile_id = request["profile"]
        if not isinstance(profile_id, str):
            raise qc_core.QCError("Choose a valid GPIO profile.")
        profile = next((item for item in qc_core.profiles() if item["id"] == profile_id), None)
        if not profile:
            raise qc_core.QCError("Unknown GPIO profile.")
        device = qc_core.read_device(port)
        if profile["chip"] != device.get("chip"):
            raise qc_core.QCError("The GPIO profile belongs to a different chip.")
        pins = qc_core.pin_map(profile)
        qc_core.validate_pins(profile["chip"], pins)
    polarity = request.get("touch_active_low")
    if "touch_active_low" in request and type(polarity) is not bool:
        raise qc_core.QCError("Touch polarity must be true or false.")
    if not network and pins is None and polarity is None and "device_id" not in request:
        raise qc_core.QCError("Enter settings, a Logger ID or choose a GPIO profile to apply.")
    # Missing credential fields are deliberately left missing, preserving the
    # values already on the device. Explicit empty fields still clear values.
    options = {"network": network, "pins": pins, "touch_active_low": polarity}
    if "device_id" in request:
        options["device_id"] = request["device_id"]
    return qc_core.configure(port, **options)


def handle(request: Any, log=lambda message: None) -> dict:
    redactor = Redactor(request)
    try:
        result = dispatch(request, log=lambda message: log(redactor.text(message)))
        return {"ok": True, "result": redactor.result(result), "error": None}
    except Exception as error:
        message = redactor.text(str(error)) or "Operation failed."
        return {"ok": False, "result": None, "error": message}


def main() -> int:
    output, diagnostics = sys.stdout, sys.stderr
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("oversized")
        request = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        response = {"ok": False, "result": None, "error": "Send one UTF-8 JSON request smaller than 64 KiB."}
    else:
        stream = DiagnosticStream(diagnostics, Redactor(request))
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            response = handle(request, log=lambda message: print(message, file=stream))
        stream.finish()
    output.write(json.dumps(response, ensure_ascii=True, separators=(",", ":")) + "\n")
    output.flush()
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
