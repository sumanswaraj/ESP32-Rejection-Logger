ESP32 REJECTION LOGGER - WINDOWS USB FLASHER

For Windows 10 or 11, 64-bit. This EXE cannot run on a phone.

1. Download the ZIP and use Extract All. Keep the complete folder together.
2. Connect the ESP32 using a USB DATA cable.
3. Double-click "ESP32 Logger Flasher.exe". Your default browser opens the local app.
4. Choose the COM port, click Detect ESP32, then Flash matching firmware.
5. Wait for verification. Release BOOT; press RESET if necessary.
6. Read device settings. Save the Wi-Fi name/password, existing Apps Script
   /exec server URL, and API key. Blank password/API key fields keep stored values.
7. Read settings again after reboot to check them. Register the displayed Logger
   ID in the existing Shop Floor Control system if this is a new device.
8. On a fresh unformatted logger, review the Initialize empty storage action
   when offered. It refuses devices with capture history or pending events.
9. Click Close app when finished, then close the browser tab.

No Arduino IDE, Python installation, compiler, or internet download is required
for flashing. The existing deployed server is required to send rejection events.

NORMAL UPGRADE
The existing project's flashing core validates chip, flash capacity, image
checksums and partition layout before writing. It verifies the written images.
Compatible NVS settings and event storage are excluded from normal flash writes.
A different existing partition layout stops the operation. The optional New
installation action makes a full flash backup before a confirmed layout change;
the old data may be inaccessible afterward. Backups are stored in:
%LOCALAPPDATA%\QC_ESP32\backups

SUPPORTED HARDWARE
ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6. Includes 4/8/16 MB layouts.
The utility detects physical capacity. Octal flash is not supported by this build.
GPIO profiles must match actual wiring; leave the map unchanged unless needed.
The compiled firmware is version 2.1.0-multiboard-pilot from your unchanged
source commit 740eb1c55a86e38200005f63a23681766942bd1b.

IF THE BOARD DOES NOT CONNECT
Use Refresh after reconnecting. Close Arduino Serial Monitor or other serial
tools. Hold BOOT while starting detection/flashing, then release when it connects.
After reboot, native USB boards may use a different COM number; refresh and select
the port running the logger firmware before reading settings.
If Windows shows no COM port, install the USB driver supplied by the board maker
(commonly CP210x or CH340). Drivers are not bundled or installed by this app.

VALIDATION LIMITS
All 15 real CI-built firmware bundles pass the original validator. The Python
bridge and HTTP adapter pass 20 tests without a connected ESP32. Browser controls
pass a JavaScript syntax check; browser interaction testing was unavailable here.
The EXE is cross-compiled for Windows x64. It has not been executed on a Windows
computer or used to flash a physical ESP32 in this environment.

This app does not edit Google Sheets or change Apps Script deployment.
The activity log omits passwords and API keys. App source, dependency licenses,
firmware build metadata and a SHA-256 file manifest are included in this folder.
