"""Build all 15 logger targets and produce a ZIP for Import firmware.

Uses the original flasher's builder and validator. No board is contacted.
Requires Python 3.10+ and the Arduino CLI version in toolchain.json.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import qc_core

ROOT = Path(__file__).resolve().parent
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
IMAGE_NAMES = ("manifest.json", "bootloader.bin", "partitions.bin", "ota_data.bin", "application.bin")


def version_label(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,79}", value):
        raise qc_core.QCError("Use a version such as 2.1.1: letters, numbers, dots, underscores, + or -; maximum 80 characters.")
    return value


def source_version(source_root: Path) -> str:
    text = (source_root / "ESP32_QC_Terminal" / "Config.h").read_text(encoding="utf-8")
    match = re.search(r'FIRMWARE_VERSION\[\]\s*=\s*"([^"\n]+)"', text)
    if not match:
        raise qc_core.QCError("Config.h is missing FIRMWARE_VERSION.")
    return version_label(match.group(1))


def write_version(source_root: Path, version: str) -> None:
    path = source_root / "ESP32_QC_Terminal" / "Config.h"
    text, count = re.subn(r'(FIRMWARE_VERSION\[\]\s*=\s*")[^"\n]+(")', lambda m: m.group(1) + version + m.group(2), path.read_text(encoding="utf-8"))
    if count != 1:
        raise qc_core.QCError("Expected exactly one firmware version in Config.h.")
    path.write_text(text, encoding="utf-8")


def commit_id() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True) if shutil.which("git") else None
    return result.stdout.strip() if result and result.returncode == 0 else "local-uncommitted"


def prepare_toolchain(cli: str, settings: dict, setup: bool) -> None:
    # Isolate dependencies from the user's Arduino IDE installation.
    for suffix, subfolder in (("DATA", "data"), ("DOWNLOADS", "downloads"), ("USER", "user")):
        path = ROOT / ".toolchain" / subfolder
        path.mkdir(parents=True, exist_ok=True)
        os.environ["ARDUINO_DIRECTORIES_" + suffix] = str(path)
    result = subprocess.run([cli, "version"], capture_output=True, text=True, check=True)
    found = re.search(r"\bVersion:\s*(\S+)", result.stdout)
    if not found or found.group(1) != settings["arduino_cli"]:
        raise qc_core.QCError("Install Arduino CLI " + settings["arduino_cli"] + " to use the saved toolchain.")
    if qc_core.CORE_VERSION != settings["esp32_core"]:
        raise qc_core.QCError("toolchain.json and qc_core.py specify different ESP32 core versions.")
    if setup:
        extra = ["--additional-urls", settings["board_index"]]
        qc_core.run([cli, "core", "update-index", *extra])
        qc_core.run([cli, "core", "install", "esp32:esp32@" + settings["esp32_core"], *extra])
        qc_core.run([cli, "lib", "update-index"])
        qc_core.run([cli, "lib", "install", *[name + "@" + version for name, version in settings["libraries"].items()]])


def source_hashes(root: Path) -> dict:
    files = []
    for name in ("ESP32_QC_Terminal", "profiles", "partitions"):
        files.extend(p for p in (root / name).rglob("*") if p.is_file())
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def package_firmware(bundles: list[Path], output: Path, version: str, metadata: dict) -> None:
    expected = {(chip, mb) for chip in qc_core.CHIPS for mb in qc_core.FLASH_MB}
    found = set()
    expanded_bytes = 0
    for folder in bundles:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        key = (manifest.get("chip"), manifest.get("flash_mb"))
        if key not in expected or key in found:
            raise qc_core.QCError("Unexpected or duplicate firmware target.")
        if manifest.get("firmware_version") != version or manifest.get("serial_config_protocol") != 1:
            raise qc_core.QCError("Firmware version or configuration protocol mismatch.")
        qc_core.validate_bundle(folder, *key)
        found.add(key)
        expanded_bytes += sum((folder / name).stat().st_size for name in IMAGE_NAMES)
    if found != expected:
        raise qc_core.QCError("All 15 targets must pass before a complete update ZIP is created.")
    info = (json.dumps(metadata, indent=2) + "\n").encode("utf-8")
    if expanded_bytes + len(info) > MAX_PACKAGE_BYTES:
        raise qc_core.QCError("The update exceeds the flashing app's 64 MiB expanded limit.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-", dir=output.parent) as temporary:
        archive_path = Path(temporary) / "firmware.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for folder in sorted(bundles):
                for name in IMAGE_NAMES:
                    archive.write(folder / name, "firmware/" + folder.name + "/" + name)
            archive.writestr("build_info.json", info)
        if archive_path.stat().st_size > MAX_PACKAGE_BYTES:
            raise qc_core.QCError("The ZIP exceeds the flashing app's 64 MiB limit.")
        archive_path.replace(output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(digest + "  " + output.name + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", action="store_true", help="Download the pinned core and libraries into an isolated toolchain.")
    parser.add_argument("--version", default="", help="Release label; blank uses Config.h. Changes only the temporary build copy.")
    parser.add_argument("--arduino-cli", default="arduino-cli", help="Path to Arduino CLI.")
    args = parser.parse_args()
    version = version_label(args.version) if args.version else source_version(ROOT)
    cli = shutil.which(args.arduino_cli)
    if not cli:
        raise qc_core.QCError("Arduino CLI was not found. The GitHub workflow installs it automatically.")
    settings = json.loads((ROOT / "toolchain.json").read_text(encoding="utf-8"))
    output = ROOT / "dist" / ("ESP32_Firmware_" + version + ".zip")
    # A failed rebuild must never leave an earlier ZIP with the same label.
    output.unlink(missing_ok=True)
    output.with_suffix(".zip.sha256").unlink(missing_ok=True)
    prepare_toolchain(cli, settings, args.setup)
    work = ROOT / ".build"
    work.mkdir(exist_ok=True)
    original_root = qc_core.ROOT
    with tempfile.TemporaryDirectory(prefix="release-", dir=work) as temporary:
        stage = Path(temporary)
        for name in ("ESP32_QC_Terminal", "profiles", "partitions"):
            shutil.copytree(ROOT / name, stage / name)
        write_version(stage, version)
        # The original builder regenerates chip-specific GPIO defaults.
        qc_core.ROOT = stage
        try:
            (stage / "ESP32_QC_Terminal" / "BoardProfile.h").write_text(qc_core.generate_board_header(), encoding="utf-8")
            (stage / "ESP32_QC_Terminal" / "UserBoard.h").write_text("#pragma once\n#define QC_BOARD_PROFILE 0\n", encoding="utf-8")
            inputs = source_hashes(stage)
            bundles = []
            for chip in qc_core.CHIPS:
                for mb in qc_core.FLASH_MB:
                    bundles.append(qc_core.build(chip, mb, cli=cli))
            metadata = {"schema_version": 1, "firmware_version": version, "source_commit": commit_id(), "built_at_utc": datetime.now(timezone.utc).isoformat(), "target_count": len(bundles), "toolchain": settings, "source_sha256": inputs}
            package_firmware(bundles, output, version, metadata)
        finally:
            qc_core.ROOT = original_root
    print("\nSUCCESS: all 15 targets passed validation.")
    print("Import this ZIP in the flashing app: " + str(output))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (qc_core.QCError, OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as error:
        print("BUILD FAILED: " + str(error), file=sys.stderr)
        sys.exit(1)
