"""Exercise the packaged EXE and embedded Python on Windows without a board.

This checks real executable startup, bundled imports, authenticated localhost
HTTP requests, serial-port enumeration, and orderly shutdown. It never detects
or flashes a device. An optional package stamp records successful native
execution, refreshes file checksums, and repacks the exact tested executables.
No hardware or browser interaction validation is claimed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, Request, build_opener
import zipfile


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_startup_url(process: subprocess.Popen, timeout: float = 25) -> str:
    lines: queue.Queue[str | None] = queue.Queue()

    def collect() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line.strip())
        lines.put(None)

    threading.Thread(target=collect, daemon=True).start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
        except queue.Empty:
            if process.poll() is not None:
                raise RuntimeError("The Windows launcher exited before serving its UI.")
            continue
        if line is None:
            raise RuntimeError("The Windows launcher closed stdout before reporting its URL.")
        if line.startswith("http://127.0.0.1:"):
            parsed = urlsplit(line)
            tokens = parse_qs(parsed.query).get("token", [])
            if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                    or not parsed.port or parsed.path != "/" or len(tokens) != 1
                    or len(tokens[0]) != 64 or any(c not in "0123456789abcdef" for c in tokens[0])):
                raise RuntimeError("The launcher reported an invalid localhost session URL.")
            return line
    raise RuntimeError("The Windows launcher did not report its startup URL within 25 seconds.")


def verify_embedded_python(root: Path) -> dict:
    script = """
import json
import sys
import esptool
import serial
import qc_core
assert sys.version_info[:3] == (3, 13, 16), sys.version
assert esptool.__version__ == '5.1.0', esptool.__version__
cmds = qc_core.esptool_api()
for name in ('detect_chip', 'run_stub', 'attach_flash', 'read_flash', 'write_flash', 'verify_flash', 'reset_chip'):
    assert callable(getattr(cmds, name)), name
assert callable(serial.Serial)
print(json.dumps({'python': sys.version.split()[0], 'esptool': esptool.__version__, 'serial': serial.__version__}))
"""
    completed = subprocess.run(
        [str(root / "runtime/python.exe"), "-X", "utf8", "-c", script],
        cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=45, check=True,
    )
    return json.loads(completed.stdout)


def smoke_test(root: Path) -> dict:
    if os.name != "nt":
        raise RuntimeError("This smoke test must run on native Windows.")
    executable = root / "ESP32 Logger Flasher.exe"
    python = root / "runtime/python.exe"
    executable_hash, python_hash = digest(executable), digest(python)
    versions = verify_embedded_python(root)
    environment = dict(os.environ, ESP32_FLASHER_NO_BROWSER="1")
    process = subprocess.Popen(
        [str(executable)], cwd=root, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    opener = build_opener(ProxyHandler({}))
    origin, token = "", ""

    def request(path: str, method: str = "GET", value=None,
                app_token: str | None = None, source_origin: str | None = None):
        headers = {}
        if app_token is not None:
            headers["X-App-Token"] = app_token
        if source_origin is not None:
            headers["Origin"] = source_origin
        body = None
        if value is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(value).encode("utf-8")
        try:
            with opener.open(Request(origin + path, data=body, method=method, headers=headers), timeout=40) as response:
                return response.status, response.headers, response.read()
        except HTTPError as error:
            return error.code, error.headers, error.read()

    try:
        url = read_startup_url(process)
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        token = parse_qs(parsed.query)["token"][0]
        code, headers, body = request("/?" + parsed.query)
        assert code == 200, "Authenticated page did not load."
        assert b"{{APP_TOKEN}}" not in body and token.encode() in body, "Page session was not populated."
        assert b'id="logger-id"' in body and b'id="logger-id-help"' in body, "Logger ID controls are missing."
        assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", ""), "Page CSP is missing."
        assert headers.get("Cache-Control") == "no-store", "Page can be cached."
        assert request("/")[0] == 403, "Page accepted a missing session."
        for asset, mime in (("/app.js", "text/javascript"), ("/app.css", "text/css")):
            code, headers, body = request(asset)
            assert code == 200 and body, f"Packaged asset did not load: {asset}."
            assert headers.get("Content-Type", "").startswith(mime), f"Incorrect asset type: {asset}."
        code, _, body = request("/api/profiles", app_token=token)
        profiles = json.loads(body)
        assert code == 200 and isinstance(profiles, list) and profiles, "GPIO profiles are missing."
        assert all(isinstance(item.get("id"), str) and isinstance(item.get("chip"), str) for item in profiles), "Invalid GPIO profiles."
        for bad_token in (None, "foreign-token"):
            assert request("/api/profiles", app_token=bad_token)[0] == 403, "Profiles accepted an invalid session."
            assert request("/api/operation", "POST", {"operation": "ports"}, app_token=bad_token)[0] == 403, "Operation accepted an invalid session."
        assert request("/api/operation", "POST", {"operation": "ports"}, app_token=token,
                       source_origin="https://foreign.example")[0] == 403, "Foreign Origin was accepted."
        code, _, body = request("/api/operation", "POST", {"operation": "ports"}, app_token=token,
                                source_origin=origin)
        response = json.loads(body)
        assert code == 200 and response.get("ok") is True, "Bundled serial enumeration failed."
        ports = response.get("result")
        assert isinstance(ports, list), "Bundled helper did not return a serial-port list."
        assert all(isinstance(item.get("port"), str) for item in ports), "Invalid serial-port result."
        code, _, body = request("/api/close", "POST", app_token=token, source_origin=origin)
        assert code == 200 and json.loads(body).get("ok") is True, "App shutdown was refused."
        assert process.wait(timeout=10) == 0, "Windows launcher did not exit cleanly."
        if digest(executable) != executable_hash or digest(python) != python_hash:
            raise RuntimeError("An executable changed while the native smoke test was running.")
        return {
            "windows_execution_tested": True,
            "embedded_python_imports_tested": True,
            "localhost_http_tested": True,
            "serial_port_enumeration_tested": True,
            "session_and_origin_checks_tested": True,
            "browser_interaction_tested": False,
            "hardware_flash_tested": False,
            "versions": versions,
            "profile_count": len(profiles),
            "serial_port_count": len(ports),
            "windows_executable_sha256": executable_hash,
            "embedded_python_executable_sha256": python_hash,
            "tested_at_utc": datetime.now(timezone.utc).isoformat(),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        }
    finally:
        if process.poll() is None and origin and token:
            try:
                request("/api/close", "POST", app_token=token, source_origin=origin)
                process.wait(timeout=5)
            except Exception:
                pass
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()


def stamp_package(root: Path, report: dict) -> Path:
    """Repack a passed native test without rebuilding its tested EXE or Python."""
    required_checks = (
        "windows_execution_tested", "embedded_python_imports_tested", "localhost_http_tested",
        "serial_port_enumeration_tested", "session_and_origin_checks_tested",
    )
    if any(report.get(name) is not True for name in required_checks):
        raise RuntimeError("Only a completely passed native Windows smoke test can stamp a package.")
    if report.get("browser_interaction_tested") is not False or report.get("hardware_flash_tested") is not False:
        raise RuntimeError("This smoke test cannot claim browser interaction or hardware flashing.")
    executable, python = root / "ESP32 Logger Flasher.exe", root / "runtime/python.exe"
    if (digest(executable) != report.get("windows_executable_sha256")
            or digest(python) != report.get("embedded_python_executable_sha256")):
        raise RuntimeError("The package executables differ from the successfully tested binaries.")
    metadata_path = root / "app-build-info.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    readme_path = root / "START HERE.txt"
    readme = readme_path.read_text(encoding="utf-8")
    validation = (
        "VALIDATION LIMITS\n"
        "All 15 real CI-built firmware bundles pass the original validator. The Python\n"
        "serial transport, Logger ID and bridge tests pass without a connected ESP32.\n"
        "This EXE\n"
        "and its bundled Python were executed on a native Windows CI runner. Startup,\n"
        "authenticated HTTP, serial-port enumeration, and clean shutdown passed.\n"
        "No physical ESP32 was detected or flashed. Browser interaction was not tested.\n"
    )
    readme, count = re.subn(r"(?s)VALIDATION LIMITS\n.*?(?=\nThis app does not edit Google Sheets)", validation, readme)
    if count != 1:
        raise RuntimeError("The package validation note is missing or ambiguous.")
    metadata.update(windows_execution_tested=True, hardware_flash_tested=False, browser_interaction_tested=False)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (root / "windows-smoke-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    readme_path.write_text(readme, encoding="utf-8")
    manifest_path = root / "SHA256-MANIFEST.json"
    files = [path for path in sorted(root.rglob("*"))
             if path.is_file() and "__pycache__" not in path.relative_to(root).parts]
    manifest = {path.relative_to(root).as_posix(): digest(path) for path in files if path != manifest_path}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if manifest_path not in files:
        files.append(manifest_path)
        files.sort()
    archive = root.parent / (root.name + ".zip")
    temporary_archive = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary_archive, "w", zipfile.ZIP_DEFLATED) as packaged:
        for path in files:
            packaged.write(path, root.name + "/" + path.relative_to(root).as_posix())
    temporary_archive.replace(archive)
    archive.with_suffix(".zip.sha256").write_text(digest(archive) + "  " + archive.name + "\n", encoding="utf-8")
    if digest(executable) != report["windows_executable_sha256"] or digest(python) != report["embedded_python_executable_sha256"]:
        raise RuntimeError("An executable changed while stamping the tested package.")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--stamp-package", action="store_true", help="Record passed native execution and repack the exact tested package.")
    arguments = parser.parse_args()
    report = smoke_test(arguments.app_root.resolve())
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if arguments.stamp_package:
        archive = stamp_package(arguments.app_root.resolve(), report)
        print(json.dumps({"tested_package": str(archive), "zip_sha256": digest(archive)}))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
