"""Build, flash and commission QC loggers. Serial credentials are never logged."""
from __future__ import annotations
import contextlib
import csv
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit
from qc_paths import user_data_dir

ROOT = Path(__file__).resolve().parent
CHIPS = {"esp32": 0, "esp32s2": 2, "esp32s3": 9, "esp32c3": 5, "esp32c6": 13}
FLASH_MB = (4, 8, 16)
CORE_VERSION = "3.3.2"
PIN_FIELDS = ("touch_scl", "touch_sdo", "buzzer", "led_wifi", "led_error", "led_ack", "led_quantity", "led_pending", "setup")
RPC_PREFIX = b"QC_RPC "

class QCError(RuntimeError):
    pass

def profiles():
    data = json.loads((ROOT / "profiles/boards.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise QCError("Unsupported board profile format")
    return data["profiles"]

def pin_map(profile):
    return {key: profile[key] for key in ("keypad", "rows", "cols", *PIN_FIELDS)} | {"touch": profile["touch_scl"] >= 0}

def chip_name(name):
    value = name.lower().replace("-", "").split(" ")[0]
    if value not in CHIPS:
        raise QCError(f"Unsupported chip {name}; supported: ESP32, S2, S3, C3, C6")
    return value

def validate_pins(chip, pins):
    chip = chip_name(chip)
    if type(pins.get("keypad")) is not bool or type(pins.get("touch")) is not bool:
        raise QCError("Enable flags must be true or false")
    if not pins["keypad"] and not pins["touch"]:
        raise QCError("Enable the keypad or touch panel")
    used = set()
    valid = {
        "esp32": set(range(0, 20)) | set(range(21, 24)) | set(range(25, 28)) | set(range(32, 40)),
        "esp32s2": set(range(0, 22)) | set(range(26, 47)),
        "esp32s3": set(range(0, 22)) | set(range(26, 49)),
        "esp32c3": set(range(22)), "esp32c6": set(range(31))
    }[chip]
    reserved = {
        "esp32": set(range(6, 12)) | {1, 3, 16, 17, 2, 5, 12, 15},
        "esp32s2": set(range(26, 38)) | {19, 20, 43, 44, 45, 46},
        "esp32s3": set(range(26, 38)) | {19, 20, 43, 44, 45, 46},
        "esp32c3": set(range(11, 22)) | {2, 8},
        "esp32c6": set(range(24, 31)) | {12, 13, 14, 16, 17, 4, 5, 8, 15}
    }[chip]
    strap = 9 if chip in ("esp32c3", "esp32c6") else 0
    def check(pin, label, output=True):
        if type(pin) is not int:
            raise QCError(f"{label}: enter a GPIO number")
        if pin == -1:
            return
        if pin not in valid or pin in reserved or (pin == strap and label != "setup"):
            raise QCError(f"{label}: GPIO {pin} is unavailable or reserved")
        if output and chip == "esp32" and pin >= 34:
            raise QCError(f"{label}: GPIO {pin} is input-only")
        if pin in used:
            raise QCError(f"GPIO {pin} is assigned more than once")
        used.add(pin)
    for group in ("rows", "cols"):
        array = pins.get(group)
        if not isinstance(array, list) or len(array) != 4 or any(type(p) is not int or not 0 <= p <= 48 for p in array):
            raise QCError("Keypad rows/columns need four GPIO numbers")
        if pins["keypad"]:
            for index, pin in enumerate(array):
                check(pin, f"{group}{index+1}")
    for name in PIN_FIELDS:
        if name not in pins:
            raise QCError(f"Missing GPIO field: {name}")
        if name.startswith("touch_"):
            if not pins["touch"]:
                continue
            if pins[name] < 0:
                raise QCError("Touch requires SCL and SDO GPIOs")
        check(pins[name], name, name not in ("touch_sdo", "setup"))
    return pins

def validate_network(network):
    lengths = {"ssid": 32, "password": 63, "name": 60, "endpoint": 512, "api_key": 200, "ca": 2048}
    for name, value in network.items():
        if name not in lengths or not isinstance(value, str):
            raise QCError("Unknown or invalid network field")
        if len(value.encode("utf-8")) > lengths[name]:
            raise QCError(f"{name}: value is too long")
    if "password" in network and network["password"] and len(network["password"].encode("utf-8")) < 8:
        raise QCError("Wi-Fi password must be empty or 8–63 bytes")
    if "name" in network and not network["name"]:
        raise QCError("Display name cannot be empty")
    if network.get("endpoint"):
        url = network["endpoint"]
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or any(ord(c) <= 32 for c in url):
            raise QCError("Use an HTTPS server URL without user credentials or fragments")
    if network.get("ca") and ("-----BEGIN CERTIFICATE-----" not in network["ca"] or "-----END CERTIFICATE-----" not in network["ca"]):
        raise QCError("Trusted CA must be a PEM certificate")

def generate_board_header():
    lines = ['#pragma once', '// Generated from profiles/boards.json by qc_flash.py profiles.', '#include "UserBoard.h"', '#if QC_BOARD_PROFILE == 0']
    for index, chip in enumerate(CHIPS):
        default = next(p for p in profiles() if p["chip"] == chip and p["default"])
        lines += [f'{"#if" if index == 0 else "#elif"} defined(CONFIG_IDF_TARGET_{chip.upper()})', f'#undef QC_BOARD_PROFILE\n#define QC_BOARD_PROFILE {default["number"]}']
    lines += ['#else', '#error "Supported targets: ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6."', '#endif', '#endif']
    for index, profile in enumerate(profiles()):
        validate_pins(profile["chip"], pin_map(profile))
        lines += [f'{"#if" if index == 0 else "#elif"} QC_BOARD_PROFILE == {profile["number"]}', f'#if !defined(CONFIG_IDF_TARGET_{profile["chip"].upper()})', '#error "Pin profile does not match the selected chip."', '#endif', f'constexpr char BOARD_PROFILE_NAME[] = "{profile["id"]}";', f'constexpr bool KEYPAD_AVAILABLE={str(profile["keypad"]).lower()}, TOUCH_AVAILABLE={str(profile["touch_scl"] >= 0).lower()};']
        lines.append(f'constexpr char BOARD_CHIP_NAME[] = "{profile["chip"]}";')
        for group in ("rows", "cols"):
            lines.append(f'constexpr uint8_t {"ROW" if group == "rows" else "COL"}_PINS[4] = {{{",".join(map(str, profile[group]))}}};')
        for name in PIN_FIELDS:
            lines.append(f'constexpr int PIN_{name.upper()} = {profile[name]};')
    lines += ['#else', '#error "Unknown QC_BOARD_PROFILE."', '#endif', '']
    return "\n".join(lines)

def write_partition_tables():
    for mb, app_size in [(4, 0x180000), (8, 0x300000), (16, 0x400000)]:
        second = 0x10000 + app_size
        fs = second + app_size
        text = '# Name,Type,SubType,Offset,Size,Flags\nnvs,data,nvs,0x9000,0x5000,\notadata,data,ota,0xE000,0x2000,\n'
        text += f'app0,app,ota_0,0x10000,0x{app_size:X},\napp1,app,ota_1,0x{second:X},0x{app_size:X},\nspiffs,data,spiffs,0x{fs:X},0x{mb*1024*1024-fs:X},\n'
        (ROOT / "partitions" / f"{mb}MB.csv").write_text(text)

def partition_entries(data):
    entries, md5_seen = [], False
    for offset in range(0, min(len(data), 0xC00), 32):
        item = data[offset:offset+32]
        if len(item) != 32:
            raise QCError("Truncated partition table")
        magic = struct.unpack_from("<H", item)[0]
        if magic == 0xFFFF:
            break
        if magic == 0xEBEB:
            if item[16:] != hashlib.md5(data[:offset]).digest():
                raise QCError("Partition checksum mismatch")
            md5_seen = True
            break
        if magic != 0x50AA:
            raise QCError("Invalid partition table")
        _, kind, subtype, start, size, label, flags = struct.unpack("<HBBII16sI", item)
        entries.append((kind, subtype, start, size, label.rstrip(b"\0"), flags))
    if not entries:
        raise QCError("Empty partition table")
    end = 0x9000
    for kind, _, start, size, _, _ in sorted(entries, key=lambda row: row[2]):
        if start < end or start % 4096 or size % 4096 or (kind == 0 and start % 65536):
            raise QCError("Overlapping or unaligned partitions")
        end = start + size
    return tuple(entries)

def sha256(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(source.read()).hexdigest()

def fqbn(chip, flash_mb):
    if chip not in CHIPS or flash_mb not in FLASH_MB:
        raise QCError("Choose a supported chip and 4, 8 or 16 MB flash")
    options = ["FlashMode=dio", f"FlashSize={flash_mb}M"]
    if chip != "esp32s3":
        options += ["FlashFreq=40"]
    if chip in ("esp32", "esp32s2", "esp32s3"):
        options += ["PSRAM=disabled"]
    if chip != "esp32":
        options += ["CDCOnBoot=cdc"]
    if chip == "esp32s3":
        options += ["USBMode=hwcdc"]
    return f'esp32:esp32:{chip}:' + ",".join(options)

def run(command, log=print):
    # A list of arguments is passed directly; no shell interpolation.
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") as process:
        for line in process.stdout:
            log(line.rstrip())
        if process.wait():
            raise QCError("Build tool failed; see the preceding output")

def build(chip, flash_mb, cli="arduino-cli", config=None, log=print):
    target = fqbn(chip, flash_mb)
    base = [str(cli)] + (["--config-file", str(config)] if config else [])
    work = ROOT / ".build" / f"{chip}-{flash_mb}MB"
    sketch = work / "ESP32_QC_Terminal"
    sketch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "ESP32_QC_Terminal", sketch, dirs_exist_ok=True)
    (sketch / "BoardProfile.h").write_text(generate_board_header())
    (sketch / "UserBoard.h").write_text('#pragma once\n#define QC_BOARD_PROFILE 0\n')
    shutil.copyfile(ROOT / "partitions" / f"{flash_mb}MB.csv", sketch / "partitions.csv")
    output = work / "output"
    log(f"Building {chip}, {flash_mb} MB")
    maximum = {4: 0x180000, 8: 0x300000, 16: 0x400000}[flash_mb]
    run(base + ["compile", "--fqbn", target, "--build-path", str(output), "--build-property", f"upload.maximum_size={maximum}", "--jobs", "2", str(sketch)], log)
    properties = subprocess.run(base + ["compile", "--fqbn", target, "--show-properties=expanded", str(sketch)], capture_output=True, text=True, check=True).stdout
    props = dict(line.split("=", 1) for line in properties.splitlines() if "=" in line)
    boot_offset = int(props["build.bootloader_addr"], 0)
    platform = Path(props["runtime.platform.path"])
    bundle = ROOT / "firmware" / f"{chip}-{flash_mb}MB"
    bundle.mkdir(parents=True, exist_ok=True)
    source_name = "ESP32_QC_Terminal.ino"
    inputs = [("bootloader", boot_offset, output / f"{source_name}.bootloader.bin"), ("partitions", 0x8000, output / f"{source_name}.partitions.bin"), ("ota_data", 0xE000, platform / "tools/partitions/boot_app0.bin"), ("application", 0x10000, output / f"{source_name}.bin")]
    images = []
    for kind, offset, file in inputs:
        dest = bundle / f"{kind}.bin"
        shutil.copyfile(file, dest)
        images.append({"kind": kind, "offset": offset, "file": dest.name, "size": dest.stat().st_size, "sha256": sha256(dest)})
    manifest = {"schema_version": 1, "chip": chip, "flash_mb": flash_mb, "core_version": CORE_VERSION, "fqbn": target, "psram": "disabled", "serial_config_protocol": 1, "images": images}
    version = re.search(r'FIRMWARE_VERSION\[\]\s*=\s*"([^"]+)"', (ROOT / "ESP32_QC_Terminal/Config.h").read_text())
    if version:
        manifest["firmware_version"] = version.group(1)
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    validate_bundle(bundle, chip, flash_mb)
    log(f"Firmware ready: {bundle.name}")
    return bundle

def validate_bundle(bundle, chip, physical_mb):
    bundle = Path(bundle)
    manifest = json.loads((bundle / "manifest.json").read_text())
    if manifest.get("schema_version") != 1 or manifest.get("chip") != chip:
        raise QCError("Firmware was built for a different chip")
    mb = manifest.get("flash_mb")
    if mb not in FLASH_MB or mb > physical_mb:
        raise QCError("Firmware partition layout does not fit detected flash")
    entries = {}
    expected = {"bootloader": 0x1000 if chip in ("esp32", "esp32s2") else 0, "partitions": 0x8000, "ota_data": 0xE000, "application": 0x10000}
    if len(manifest.get("images", [])) != 4:
        raise QCError("Firmware bundle needs exactly four images")
    for image in manifest["images"]:
        kind = image["kind"]
        if kind not in expected or kind in entries or image["offset"] != expected[kind]:
            raise QCError("Unexpected image or flash address")
        name = image["file"]
        if Path(name).name != name or name != f"{kind}.bin":
            raise QCError("Invalid firmware filename")
        file = bundle / name
        if file.stat().st_size != image["size"] or sha256(file) != image["sha256"]:
            raise QCError("Firmware checksum mismatch; rebuild or restore the package")
        data = file.read_bytes()
        if kind in ("bootloader", "application"):
            if len(data) < 24 or data[0] != 0xE9 or struct.unpack_from("<H", data, 12)[0] != CHIPS[chip]:
                raise QCError("Binary image is for a different chip")
            if data[3] >> 4 != {4: 2, 8: 3, 16: 4}[mb]:
                raise QCError("Binary flash-size header does not match the layout")
        entries[kind] = (image["offset"], file, len(data))
    table = partition_entries(entries["partitions"][1].read_bytes())
    if max(row[2] + row[3] for row in table) > mb * 1024 * 1024:
        raise QCError("Partitions exceed the configured flash")
    app0 = next((row for row in table if row[0:2] == (0, 0x10)), None)
    if not app0 or app0[2] != 0x10000 or entries["application"][2] > app0[3]:
        raise QCError("Application exceeds its partition")
    limits = {"bootloader": 0x8000, "partitions": 0x9000, "ota_data": 0x10000, "application": app0[2] + app0[3]}
    for kind, (offset, _, length) in entries.items():
        if offset + ((length + 4095) // 4096) * 4096 > limits[kind]:
            raise QCError("Image would overwrite configuration or queue storage")
    return manifest, sorted([(offset, str(file)) for offset, file, _ in entries.values()]), table

def esptool_api():
    try:
        import esptool
        from esptool import cmds
    except ImportError as error:
        raise QCError("Run START_WINDOWS.bat or install requirements.txt first") from error
    if esptool.__version__ != "5.1.0":
        raise QCError("This application requires esptool 5.1.0; install requirements.txt")
    return cmds

@contextlib.contextmanager
def connected(port):
    cmds = esptool_api()
    with cmds.detect_chip(port=port, connect_attempts=3) as rom:
        esp = cmds.run_stub(rom)
        cmds.attach_flash(esp)
        try:
            yield esp
        finally:
            try:
                cmds.reset_chip(esp, "hard-reset")
            except Exception:
                pass

def describe(esp):
    cmds = esptool_api()
    chip = chip_name(esp.CHIP_NAME)
    jedec = esp.flash_id()
    label = cmds.DETECTED_FLASH_SIZES.get((jedec >> 16) & 255)
    if not label or not label.endswith("MB"):
        raise QCError("Cannot safely identify flash capacity")
    mb = int(label[:-2])
    if mb < 4:
        raise QCError("This logger requires at least 4 MB flash")
    if chip == "esp32s3" and esp.flash_type() == 1:
        raise QCError("Octal flash requires a dedicated boot build; this release supports quad flash")
    return {"chip": chip, "flash_mb": mb, "layout_mb": max(x for x in FLASH_MB if x <= mb), "description": esp.get_chip_description(), "mac": ":".join(f"{b:02x}" for b in esp.read_mac())}

def detect(port):
    with connected(port) as esp:
        return describe(esp)

def flash(port, new_install=False, bundle=None, log=print):
    cmds = esptool_api()
    with connected(port) as esp:
        device = describe(esp)
        if bundle:
            bundle = Path(bundle)
        else:
            from qc_firmware import selected_bundle
            bundle = selected_bundle(device["chip"], device["layout_mb"], ROOT)
        if not (bundle / "manifest.json").exists():
            raise QCError("Matching firmware is missing. Use qc_flash.py build to build this target")
        manifest, images, wanted = validate_bundle(bundle, device["chip"], device["flash_mb"])
        existing = cmds.read_flash(esp, 0x8000, 0x1000, no_progress=True)
        blank = all(value == 255 for value in existing)
        compatible = False
        if not blank:
            try:
                compatible = partition_entries(existing) == wanted
            except QCError:
                pass
        if not blank and not compatible:
            if not new_install:
                raise QCError("Different partition layout. Back up/review the device, then choose New installation. Existing storage may become inaccessible")
            folder = user_data_dir(ROOT) / "backups"
            folder.mkdir(parents=True, exist_ok=True)
            backup = folder / f'{device["chip"]}-{device["mac"].replace(":", "")}-{time.time_ns()}.bin'
            log("Backing up the existing flash before changing its layout")
            cmds.read_flash(esp, 0, device["flash_mb"] * 1024 * 1024, output=str(backup))
            if backup.stat().st_size != device["flash_mb"] * 1024 * 1024:
                raise QCError("Backup was incomplete; flashing cancelled")
            log(f"Backup saved: {backup.name}")
        log(f'Flashing {device["chip"]}, {manifest["flash_mb"]} MB layout. NVS and event storage are excluded from the writes')
        cmds.write_flash(esp, images, flash_size="keep", flash_mode="keep", flash_freq="keep", compress=True, erase_all=False, force=False)
        cmds.verify_flash(esp, images)
        log("Flash verified. Device restarting")
        device["blank_partition_table"] = blank
        return device

@contextlib.contextmanager
def commissioning_link(port):
    try:
        import serial
    except ImportError as error:
        raise QCError("Install requirements.txt first") from error
    with serial.Serial(port=None, baudrate=115200, timeout=0.25, write_timeout=5) as link:
        link.dtr = False
        link.rts = False
        link.port = port
        link.open()
        # TinyUSB CDC on S2 requires DTR for transmission. Keep RTS inactive
        # and release DTR before the device's delayed restart.
        link.dtr = True
        try:
            yield link
        finally:
            try:
                link.dtr = False
                link.rts = False
            except (OSError, serial.SerialException):
                pass

def serial_request(port, command, payload=None, timeout=18):
    request = {"protocol": 1, "id": uuid.uuid4().hex, "command": command}
    if payload:
        request.update(payload)
    if len(json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) >= 4096:
        raise QCError("Configuration request is too large")
    with commissioning_link(port) as link:
        time.sleep(1.8)  # Some USB/UART drivers briefly reset the chip on open.
        link.reset_input_buffer()
        def exchange(packet):
            encoded = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            link.write(encoded)
            link.flush()
            deadline = time.monotonic() + timeout
            buffer = b""
            while time.monotonic() < deadline:
                buffer += link.read(max(1, min(link.in_waiting, 4096)))
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.startswith(RPC_PREFIX):
                        continue  # Boot text, including setup passwords, is not exposed.
                    try:
                        response = json.loads(line[len(RPC_PREFIX):])
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if response.get("id") != packet["id"]:
                        continue
                    if not response.get("ok"):
                        raise QCError(response.get("message", "Device refused the configuration"))
                    return response
                if len(buffer) > 8192:
                    buffer = b""
            raise QCError("No configuration response. Use the port running the new firmware, close Serial Monitor, and release BOOT. Old pilot firmware needs one upgrade first")
        if command != "info":
            # Wait for a full boot before sending a longer configuration frame.
            exchange({"protocol": 1, "id": uuid.uuid4().hex, "command": "info"})
        return exchange(request)

def read_device(port):
    return serial_request(port, "info")["device"]

def configure(port, network=None, pins=None, touch_active_low=None):
    payload = {}
    if network:
        validate_network(network)
        payload["network"] = network
    if pins is not None:
        device = read_device(port)
        validate_pins(device["chip"], pins)
        payload["pins"] = pins
    if touch_active_low is not None:
        if not payload:
            payload["pins"] = read_device(port)["pins"]
        payload["touch_active_low"] = bool(touch_active_low)
    if not payload:
        raise QCError("Enter network settings or select Apply GPIO map")
    return serial_request(port, "configure", payload)
