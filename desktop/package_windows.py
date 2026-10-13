"""Assemble the portable Windows app using verified firmware and a bundled runtime.

Run after dependencies have been installed for Windows into the package's
runtime/Lib/site-packages. No firmware source or production backend is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import qc_core

NAME = "ESP32-Logger-Flasher-Windows-x64"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def windows_x64(path: Path) -> None:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError(f"Not a Windows executable: {path.name}")
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[offset:offset+4] != b"PE\0\0" or struct.unpack_from("<H", data, offset+4)[0] != 0x8664:
        raise ValueError(f"Not a Windows x64 executable: {path.name}")


def verify_firmware_source(info: dict) -> None:
    hashes = {}
    for folder in ("ESP32_QC_Terminal", "profiles", "partitions"):
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file():
                continue
            name = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            if name == "ESP32_QC_Terminal/BoardProfile.h":
                data = qc_core.generate_board_header().encode()
            elif name == "ESP32_QC_Terminal/UserBoard.h":
                data = b"#pragma once\n#define QC_BOARD_PROFILE 0\n"
            elif name == "ESP32_QC_Terminal/Config.h":
                data = re.sub(r'(FIRMWARE_VERSION\[\]\s*=\s*")[^"\n]+(")',
                              lambda m: m.group(1)+info["firmware_version"]+m.group(2), data.decode()).encode()
            hashes[name] = hashlib.sha256(data).hexdigest()
    if hashes != info.get("source_sha256"):
        raise RuntimeError("The compiled firmware does not match the project's firmware source.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-archive", required=True, type=Path)
    parser.add_argument("--firmware-root", required=True, type=Path)
    parser.add_argument("--go", required=True, type=Path)
    args = parser.parse_args()
    package = ROOT / "dist" / NAME
    runtime = package / "runtime"
    if not (runtime / "Lib/site-packages/esptool").is_dir():
        raise RuntimeError("Install Windows-target esptool 5.1.0 and pyserial into runtime/Lib/site-packages first.")
    info = json.loads((args.firmware_root / "build_info.json").read_text())
    verify_firmware_source(info)
    source_commit = info["source_commit"]
    with zipfile.ZipFile(args.runtime_archive) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            relative = Path(entry.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe runtime archive path")
            target = runtime / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(entry))
    paths = list(runtime.glob("python*._pth"))
    if len(paths) != 1:
        raise ValueError("Expected one embedded interpreter path file")
    original = paths[0].read_text()
    standard = next(line for line in original.splitlines() if line.endswith(".zip"))
    paths[0].write_text(f"{standard}\n.\nLib/site-packages\n..\n", encoding="utf-8")
    for name in ("qc_core.py", "qc_paths.py"):
        shutil.copy2(ROOT / name, package / name)
    shutil.copytree(ROOT / "profiles", package / "profiles", dirs_exist_ok=True)
    (package / "desktop").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "desktop/backend.py", package / "desktop/backend.py")
    shutil.copytree(args.firmware_root / "firmware", package / "firmware", dirs_exist_ok=True)
    shutil.copy2(args.firmware_root / "build_info.json", package / "firmware-build-info.json")
    for chip in qc_core.CHIPS:
        for mb in qc_core.FLASH_MB:
            qc_core.validate_bundle(package / "firmware" / f"{chip}-{mb}MB", chip, mb)
    env = dict(os.environ, GOOS="windows", GOARCH="amd64", CGO_ENABLED="0", GOTOOLCHAIN="local")
    env["GOCACHE"] = str(ROOT / ".build/desktop-go-cache")
    env["GOMODCACHE"] = str(ROOT / ".build/desktop-go-modcache")
    executable = package / "ESP32 Logger Flasher.exe"
    subprocess.run([str(args.go), "build", "-trimpath", "-ldflags", "-s -w -H=windowsgui", "-o", str(executable), "."], cwd=ROOT / "desktop", env=env, check=True)
    windows_x64(executable)
    windows_x64(runtime / "python.exe")
    shutil.copy2(ROOT / "desktop/WINDOWS_README.txt", package / "START HERE.txt")
    # Include launcher source and tests so this executable remains reviewable.
    shutil.copytree(ROOT / "desktop", package / "source/desktop", ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    license_dir = package / "licenses"
    license_dir.mkdir(exist_ok=True)
    shutil.copy2(args.go.parents[1] / "LICENSE", license_dir / "Go-LICENSE.txt")
    (license_dir / "THIRD-PARTY.txt").write_text(
        "Bundled Python: runtime/LICENSE.txt (Python Software Foundation license).\n"
        "esptool 5.1.0: runtime/Lib/site-packages/esptool-5.1.0.dist-info/licenses/LICENSE (GPL-2.0-or-later).\n"
        "esptool Python source and stub resources are bundled under runtime/Lib/site-packages/esptool.\n"
        "Other dependency licenses are preserved inside their *.dist-info directories.\n"
        "Go runtime: Go-LICENSE.txt.\n", encoding="utf-8")
    # Host-generated bytecode cannot be used by the Windows interpreter.
    for folder in list(package.rglob("__pycache__")):
        shutil.rmtree(folder)
    dependencies = {}
    for metadata in (runtime / "Lib/site-packages").glob("*.dist-info/METADATA"):
        fields = dict(line.split(": ", 1) for line in metadata.read_text().splitlines() if line.startswith(("Name: ", "Version: ")))
        dependencies[fields["Name"]] = fields["Version"]
    app_info = {"source_repository": "https://github.com/sumanswaraj/ESP32-Rejection-Logger", "firmware_source_commit": source_commit,
                "firmware_version": info["firmware_version"], "firmware_target_count": 15, "runtime_archive_sha256": digest(args.runtime_archive),
                "dependencies": dependencies, "windows_target": "Windows 10/11 x64", "hardware_flash_tested": False,
                "windows_execution_tested": False, "browser_interaction_tested": False}
    (package / "app-build-info.json").write_text(json.dumps(app_info, indent=2)+"\n")
    manifest = {p.relative_to(package).as_posix(): digest(p) for p in sorted(package.rglob("*"))
                if p.is_file() and p.name != "SHA256-MANIFEST.json"}
    (package / "SHA256-MANIFEST.json").write_text(json.dumps(manifest, indent=2)+"\n")
    archive_path = ROOT / "dist" / (NAME+".zip")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                archive.write(path, NAME+"/"+path.relative_to(package).as_posix())
    archive_path.with_suffix(".zip.sha256").write_text(digest(archive_path)+"  "+archive_path.name+"\n")
    print(json.dumps({"zip": str(archive_path), "bytes": archive_path.stat().st_size, "files": len(manifest), "firmware_targets": 15}))


if __name__ == "__main__":
    main()
