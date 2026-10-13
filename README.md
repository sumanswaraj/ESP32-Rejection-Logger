# ESP32 Rejection Logger

## Windows USB flasher

Download the **Windows flasher ZIP** from
[Download Windows flasher](https://github.com/sumanswaraj/ESP32-Rejection-Logger/raw/refs/heads/main/downloads/ESP32-Logger-Flasher-Windows-x64.zip).
The same download is linked from [Releases](https://github.com/sumanswaraj/ESP32-Rejection-Logger/releases/latest).
It includes the desktop app, Python runtime and all 15 matching firmware bundles.
Use a **Windows 10 or 11 PC, 64-bit**; this `.exe` cannot run on a phone.
No Arduino IDE, compiler or separate Python installation is needed to flash.

1. Right-click the downloaded ZIP and choose **Extract All**. Keep the complete
   extracted folder together; the `.exe` needs its accompanying files.
2. Connect the ESP32 to the PC with a **USB data cable**.
3. Double-click **ESP32 Logger Flasher.exe**. The setup screen opens in your
   browser and communicates with the local app on your PC.
4. Select the COM port, click **Detect ESP32**, then **Flash matching firmware**.
   Keep USB connected until verification finishes.
5. Release BOOT after flashing. Press RESET if needed. If the COM number changes
   after reboot, click **Refresh** and select the logger's new port.
6. Click **Read device settings**. Save its Wi-Fi name/password, your existing
   deployed Apps Script `/exec` server URL, and API key. Blank password and API
   key fields keep the stored values. Read settings again after reboot to verify.
7. For a fresh logger, register the displayed Logger ID in your existing Shop
   Floor Control system. Initialize empty storage only when the app offers the
   guarded action for a logger with no captured or pending events.
8. Click **Close app** when finished, then close the browser tab.

Normal upgrades preserve the existing logger ID, compatible stored settings and
queued rejection events. A different partition layout stops the flash. The
optional **New installation** action creates a full flash backup before a
confirmed layout change; existing data can become inaccessible afterward.
Leave the GPIO mapping unchanged unless your physical wiring matches the
selected board profile. Use a board-maker USB driver if Windows shows no port.

This app does not edit the Google Sheet or change its Apps Script deployment.
It uses the existing firmware and existing server URL. The original Shop Floor
Control login, QR assignment and Sheet workflow still require review of the
bound Apps Script; this flasher does not establish that those features are
complete or tested.

All 15 firmware bundles were validated, and 20 Python/HTTP adapter tests passed.
The EXE was cross-compiled for Windows x64. It has not yet been executed on a
Windows PC or used with a physical ESP32 here; browser interaction testing was
unavailable. JavaScript syntax checks passed. A Windows build/startup workflow
provides additional validation without substituting for a real USB flash test.

Run [Build and test Windows flasher](../../actions/workflows/build-windows-flasher.yml) in Actions to build and test the actual Windows executable.

See [the complete Windows instructions](desktop/WINDOWS_README.txt) for connection
help, backup location and validation limits. Firmware build instructions from
the existing project follow below.

# ESP32 logger: build all firmware on GitHub

This package adds a **Build All Firmware** button. GitHub downloads the saved
compiler and libraries, builds all 15 chip/flash combinations, validates the
images, and provides one firmware update ZIP for the existing flashing app.

The included firmware source comes from **ESP32_Flash_Configure_v2_1.zip**.
Building does not connect to a board. This setup does not create a GitHub
repository or upload anything automatically.

## One-time setup in your browser

1. Sign in to GitHub. If needed, create an account at https://github.com/signup.
2. Open https://github.com/new. Name the repository `ESP32-Rejection-Logger`,
   choose **Private**, tick **Add a README file**, and create the repository.
3. Extract `ESP32_GitHub_Build_Setup.zip` on your PC. Open the extracted
   `ESP32_GitHub_Build` folder.
4. In GitHub, choose **Add file > Upload files**. Drag the **contents** of
   `ESP32_GitHub_Build` into the upload area. Upload the source folders and root
   files directly into the repository root, then commit the changes.
   Do not upload the setup ZIP or wrap everything in an extra folder.
5. Check the repository for `.github/workflows/build-firmware.yml`. If that file
   was uploaded, continue to the next step. If the browser skipped the `.github`
   folder, use **Add file > Create new file**. For the filename, enter:

   ```text
   .github/workflows/build-firmware.yml
   ```

   Open `WORKFLOW_TO_COPY.txt` from the extracted folder in Notepad, copy its
   entire contents into the new file, and commit it to the default branch.
6. Open the **Actions** tab. The workflow **Build All Firmware** should appear.
   If GitHub asks to enable Actions for this repository, enable it.

The following files/folders must be at the repository root: `build_all.py`,
`qc_core.py`, `qc_paths.py`, `toolchain.json`, `ESP32_QC_Terminal`, `profiles`,
and `partitions`. The workflow must be at the exact path above.

## Get compiled firmware

1. Open **Actions > Build All Firmware > Run workflow**.
2. Choose the default branch. In **Firmware version**, enter a label such as
   `2.1.1`. Leaving it blank uses the version in `ESP32_QC_Terminal/Config.h`.
3. Click the green **Run workflow** button. Open the new run to watch progress.
4. Wait for the run to show a green check. If any target fails, no complete
   firmware update is published. The failed step contains the error.
5. Scroll to **Artifacts** and download `ESP32-Firmware-<run number>`.
6. Extract that downloaded artifact ZIP once. Inside it are:
   - `ESP32_Firmware_<version>.zip`: the firmware package to import.
   - `ESP32_Firmware_<version>.zip.sha256`: its integrity checksum.
7. Open your existing flashing app, choose **Import firmware**, and select
   `ESP32_Firmware_<version>.zip`. Then use **Flash matching firmware** for the
   connected board.

Keep the inner firmware ZIP intact for the app. GitHub's outer artifact ZIP is
just a download wrapper. Artifacts are retained for 30 days by this workflow;
download and keep the firmware ZIP for future use.

## After the firmware is updated

Upload the changed `.ino`/`.h` files into the same `ESP32_QC_Terminal` folder in
GitHub and commit them. Preserve their folder paths. Run **Build All Firmware**
again with a new version label, download the result, and import it into the app.

The version input is written into a temporary source copy for compilation and
into every target manifest. It does not commit a change to `Config.h`.
You can also edit `Config.h` yourself and leave the input blank.

Each released ZIP includes the source commit, toolchain versions, source file
hashes, and per-image checksums. A matching compiled package can be reused for
any number of boards with that hardware configuration.

Wi-Fi, server and GPIO changes that the flashing app supports can be saved
through configuration; they do not require a new build.

## Saved build settings

| Setting | Value |
| --- | --- |
| Arduino CLI | 1.3.1 |
| ESP32 Arduino core | 3.3.2 |
| ArduinoJson | 7.4.2 |
| Keypad | 3.1.1 |
| Chip families | ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6 |
| Flash layouts per family | 4 MB, 8 MB, 16 MB |
| Output | 15 validated bundles in one importable ZIP |

The board, flash, USB and PSRAM options are the same as the existing firmware
package. These portable builds use quad flash and leave PSRAM disabled.
`profiles/boards.json` supplies the first-boot GPIO defaults; the original
builder regenerates `BoardProfile.h` for compilation.

The first build downloads tools and libraries. Later builds can reuse the
download cache. The workflow runs only when you click **Run workflow**.

## If something does not appear or fails

- **No Build All Firmware workflow:** confirm the workflow file's exact path,
  and that it is committed to the repository's default branch.
- **No Run workflow button:** open the workflow itself, check the default branch,
  and ensure your GitHub account has write access to the repository.
- **Source files not found:** the upload added an extra parent folder; put the
  contents of `ESP32_GitHub_Build` at the repository root.
- **Compilation error:** open the red build step and inspect the first compiler
  error. The workflow stops before producing a complete package.
- **App cannot find manifests:** extract GitHub's downloaded artifact ZIP and
  select the inner `ESP32_Firmware_<version>.zip`.

## Optional use on a PC with the compiler already installed

With Python 3.10+ and Arduino CLI 1.3.1 on PATH, run from this folder:

```text
python build_all.py --setup --version 2.1.1
```

The first run requires internet access. Tools are kept in this folder's
`.toolchain` directory. The result is saved in `dist`.

## Official instructions

- Create a repository: https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository
- Upload files: https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository
- Run a workflow: https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow
- Download the result: https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts
- Arduino CLI setup action: https://github.com/arduino/setup-arduino-cli

See `VALIDATION.md` for what was checked before this setup package was delivered.

## Flash verifies, but reading settings times out

Use the updated Windows package, close other serial tools and release BOOT.
The settings reader now leaves the USB/UART adapter's BOOT control line
released. Native USB CDC ports retain the signaling they need to transmit.
Select the board's COM port and try **Read device settings**. If a USB/UART
board still does not reply, choose **Reset and read** to restart it with BOOT
released; stored settings and events are retained. Native USB ports use the
board's physical RESET button instead.

The reader identifies known download-mode, crash and power-failure messages
without displaying boot passwords. A silent response after a verified flash
still requires checking application startup; it does not mean storage should
be erased. If the new reader remains silent, capture the 115200-baud boot log
and remove setup credentials before sharing it.
