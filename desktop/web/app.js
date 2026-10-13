/* Local desktop frontend. Secrets are sent only to the authenticated localhost utility. */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const token = document.querySelector('meta[name="app-token"]').content;
  const state = { busy: false, ports: [], detected: null, info: null, infoPort: "", profiles: [], closed: false, started: 0, timer: null, confirmation: null, logs: [] };
  const port = () => $("port").value;
  const text = (id, value) => { $(id).textContent = value == null || value === "" ? "—" : String(value); };
  function log(message) {
    const stamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    state.logs.push(`[${stamp}] ${String(message)}`);
    if (state.logs.length > 160) state.logs.splice(0, state.logs.length - 160);
    $("activity-log").textContent = state.logs.join("\n");
    $("activity-log").scrollTop = $("activity-log").scrollHeight;
  }
  function status(message, error = false) {
    text("status-text", message);
    $("status").classList.toggle("error", error);
  }
  function updateControls() {
    const unavailable = state.busy || state.closed;
    document.querySelectorAll("button, input, select, summary").forEach((element) => {
      if (element.tagName === "SUMMARY") { element.setAttribute("aria-disabled", String(unavailable)); return; }
      element.disabled = unavailable;
    });
    $("detect").disabled = unavailable || !port();
    $("read-settings").disabled = unavailable || !port();
    const selectedPort = state.ports.find((item) => item.port === port());
    $("reset-read-settings").disabled = unavailable || !port() || (selectedPort && selectedPort.vid === 0x303A);
    $("flash").disabled = unavailable || !state.detected;
    $("new-install").disabled = unavailable || !state.detected;
    $("save-settings").disabled = unavailable || !state.info || state.infoPort !== port();
    $("initialize-storage").disabled = unavailable || !storageEligible();
    $("confirm-proceed").disabled = unavailable || !state.confirmation || $("confirm-input").value !== state.confirmation.phrase;
  }
  function setBusy(value, message) {
    state.busy = value;
    $("status").classList.toggle("busy", value);
    $("status").setAttribute("aria-busy", String(value));
    if (state.timer) clearInterval(state.timer);
    state.timer = null;
    text("status-time", "");
    if (value) {
      state.started = Date.now();
      status(message);
      state.timer = setInterval(() => { text("status-time", `${Math.floor((Date.now() - state.started) / 1000)}s`); }, 1000);
    }
    updateControls();
  }
  async function api(operation, extra = {}) {
    const response = await fetch("/api/operation", {
      method: "POST", credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-App-Token": token },
      body: JSON.stringify({ operation, ...(operation === "ports" ? {} : { port: port() }), ...extra }),
    });
    let reply;
    try { reply = await response.json(); }
    catch (_) { throw new Error("The local utility did not return a valid response. Keep the app window open and try again."); }
    if (reply.logs) {
      const lines = Array.isArray(reply.logs) ? reply.logs : String(reply.logs).split("\n");
      lines.filter(Boolean).forEach(log);
    }
    if (!response.ok || !reply.ok) throw new Error(reply.error || `Request failed (${response.status}).`);
    return reply.result;
  }
  async function run(message, callback) {
    if (state.busy || state.closed) return;
    setBusy(true, message);
    log(message);
    try { await callback(); }
    catch (error) {
      const message = error instanceof TypeError ? "The local app is unreachable. Reopen the Windows executable if it was closed." : error.message;
      status(message, true);
      log(`Error: ${message}`);
    } finally { setBusy(false); }
  }
  function clearDevice() {
    state.detected = null;
    state.info = null;
    state.infoPort = "";
    $("detected-device").hidden = true;
    $("device-settings").hidden = true;
    $("storage-panel").hidden = true;
    $("password").value = "";
    $("api-key").value = "";
    text("flash-hint", "Detect your ESP32 first.");
    updateControls();
  }
  async function refreshPorts() {
    const previous = port();
    const ports = await api("ports");
    state.ports = ports;
    $("port").replaceChildren(new Option(ports.length ? "Choose a port" : "No serial ports found", ""));
    ports.forEach((item) => $("port").add(new Option(`${item.port}${item.description ? ` · ${item.description}` : ""}`, item.port)));
    if (ports.some((item) => item.port === previous)) $("port").value = previous;
    else if (ports.length === 1) $("port").value = ports[0].port;
    if (port() !== previous) clearDevice();
    const message = ports.length ? `${ports.length} serial port${ports.length === 1 ? "" : "s"} found. Select your ESP32 and click Detect.` : "No serial ports found. Check your USB data cable and driver, then click Refresh.";
    status(message);
    log(message);
  }
  async function detect() {
    // A failed probe must never leave a previous device available for flashing.
    clearDevice();
    const device = await api("detect");
    state.detected = device;
    $("detected-device").hidden = false;
    text("detected-chip", device.description || String(device.chip).toUpperCase());
    text("detected-flash", `${device.flash_mb} MB`);
    text("detected-layout", device.layout_mb ? `${device.layout_mb} MB` : `${device.flash_mb} MB`);
    text("detected-mac", device.mac);
    text("flash-hint", "Ready. Keep the USB cable connected until verification finishes.");
    status(`${String(device.chip).toUpperCase()} detected. You can flash matching firmware or read existing settings.`);
    log(`Detected ${String(device.chip).toUpperCase()} · ${device.flash_mb} MB · ${port()}`);
  }
  function storageEligible() {
    return Boolean(state.info && state.infoPort === port() && state.info.storage_fault === true && state.info.sequence === 0 && state.info.pending_events === 0);
  }
  function loggerIdLockReason(device) {
    if (!device || device.logger_id_edit_supported !== true) return "This firmware cannot edit the Logger ID. Install current firmware, then read settings again.";
    if (![device.sequence, device.pending_events].every((count) => Number.isSafeInteger(count) && count >= 0)) return "Logger ID is read-only because the event history could not be verified. Read settings again before changing it.";
    if (device.identity_locked === true || device.sequence > 0 || device.pending_events > 0) return "Logger ID is locked because this logger has captured or queued events. You can still change its display name.";
    return "Choose the Logger ID before the first event is captured. Use 1–80 letters, digits, underscores or hyphens. The firmware verifies that the ID can still be changed when saving.";
  }
  function loggerIdEditable(device) {
    return Boolean(device && device.logger_id_edit_supported === true && device.identity_locked !== true && [device.sequence, device.pending_events].every((count) => Number.isSafeInteger(count) && count === 0));
  }
  function addDetail(label, value) {
    const group = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = label; dd.textContent = value == null ? "—" : String(value);
    group.append(dt, dd); $("device-details").append(group);
  }
  function refreshProfileOptions() {
    const chip = (state.info && state.info.chip) || (state.detected && state.detected.chip);
    $("profile").replaceChildren(new Option("Keep the current GPIO mapping", ""));
    state.profiles.filter((profile) => profile.chip === chip).forEach((profile) => {
      $("profile").add(new Option(profile.label, profile.id));
    });
    text("profile-note", "Choose a profile only if your physical wiring matches it.");
  }
  function displaySettings(device) {
    state.info = device;
    state.infoPort = port();
    $("device-settings").hidden = false;
    text("device-id", device.device_id);
    $("logger-id").value = device.device_id || "";
    $("logger-id").readOnly = !loggerIdEditable(device);
    text("logger-id-help", loggerIdLockReason(device));
    $("name").value = device.name || "";
    $("ssid").value = device.ssid || "";
    $("endpoint").value = device.endpoint || "";
    $("password").value = "";
    $("api-key").value = "";
    document.querySelectorAll("[data-secret]").forEach((button) => {
      const input = $(button.dataset.secret); input.type = "password";
      button.textContent = "Show"; button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-label", `Show ${input.id === "password" ? "Wi-Fi password" : "API key"}`);
    });
    text("password-state", device.wifi_password_set ? "A Wi-Fi password is stored. Leave blank to keep it." : "No Wi-Fi password is stored.");
    text("api-key-state", device.api_key_set ? "An API key is stored. Leave blank to keep it." : "No API key is stored.");
    const storageFault = device.storage_fault === true;
    text("device-state", storageFault ? "Storage needs attention" : "Device settings loaded");
    $("device-state").classList.toggle("fault", storageFault);
    $("device-details").replaceChildren();
    addDetail("Chip", device.chip ? String(device.chip).toUpperCase() : "—");
    addDetail("Captured event sequence", device.sequence);
    addDetail("Pending events", device.pending_events);
    addDetail("Event storage", storageFault ? "Fault reported" : "Available");
    const pins = device.pins || {};
    const lines = Object.entries(pins).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : String(value)}`);
    text("pin-map", lines.length ? lines.join("\n") : "No GPIO mapping returned.");
    refreshProfileOptions();
    $("storage-panel").hidden = !storageEligible();
  }
  async function readSettings(reset = false) {
    displaySettings(await api("info", reset ? { reset: true } : {}));
    status(storageEligible() ? "Device settings loaded. This fresh logger needs empty storage initialization." : "Device settings loaded. Edit the fields you want to change, then save.");
    log("Device settings loaded. Stored passwords and API keys are not displayed.");
  }
  async function flash(newInstall = false) {
    await api("flash", newInstall ? { new_install: true, confirm: "CHANGE PARTITION LAYOUT" } : { new_install: false });
    state.info = null;
    state.infoPort = "";
    $("device-settings").hidden = true;
    $("storage-panel").hidden = true;
    status("Firmware flash verified. Release BOOT. After the logger restarts, refresh ports if needed and read device settings.");
    log("Firmware installed and verified. Read device settings next.");
  }
  function networkChanges() {
    const network = {};
    ["name", "ssid", "endpoint"].forEach((key) => {
      const value = $(key).value;
      if (value !== (state.info[key] || "")) network[key] = value;
    });
    if ($("password").value) network.password = $("password").value;
    if ($("api-key").value) network.api_key = $("api-key").value;
    return network;
  }
  async function saveSettings() {
    const network = networkChanges(), profile = $("profile").value;
    const deviceId = $("logger-id").value, idChanged = deviceId !== (state.info.device_id || "");
    if (!Object.keys(network).length && !profile && !idChanged) { status("No settings have changed."); return; }
    if (idChanged) {
      if (!loggerIdEditable(state.info)) throw new Error(loggerIdLockReason(state.info));
      if (deviceId.length < 1 || deviceId.length > 80 || /[^A-Za-z0-9_-]/.test(deviceId)) throw new Error("Logger ID must contain 1–80 letters, digits, underscores or hyphens.");
    }
    const byteLength = (value) => new TextEncoder().encode(value).length;
    if (network.password && (byteLength(network.password) < 8 || byteLength(network.password) > 63)) throw new Error("Wi-Fi password must be 8–63 bytes. Leave it blank to keep the stored password.");
    if (network.name === "") throw new Error("Display name cannot be empty.");
    if (network.endpoint) {
      let url; try { url = new URL(network.endpoint); } catch (_) { throw new Error("Enter a valid HTTPS server URL."); }
      if (url.protocol !== "https:" || url.username || url.password || url.hash || /\s/.test(network.endpoint)) throw new Error("Use an HTTPS server URL without user credentials, spaces or fragments.");
    }
    const request = {};
    if (idChanged) request.device_id = deviceId;
    if (Object.keys(network).length) request.network = network;
    if (profile) request.profile = profile;
    await api("configure", request);
    $("password").value = ""; $("api-key").value = "";
    // Read settings explicitly after the device restarts. Some USB devices re-enumerate.
    state.info = null;
    state.infoPort = "";
    $("device-settings").hidden = true;
    $("storage-panel").hidden = true;
    status("Settings saved. Allow the device to restart, then read settings again. Refresh ports if the COM number changes.");
    log("Settings saved. Secrets were not logged. Read settings after the restart to verify.");
  }
  function askConfirmation({ title, message, phrase, action }) {
    if (state.busy || state.closed) return;
    state.confirmation = { phrase, action };
    text("confirm-title", title); text("confirm-message", message); text("confirm-phrase", phrase);
    $("confirm-input").value = "";
    $("confirm-proceed").disabled = true;
    $("confirm-dialog").showModal();
    $("confirm-input").focus();
  }
  $("refresh-ports").addEventListener("click", () => run("Refreshing USB serial ports…", refreshPorts));
  $("port").addEventListener("change", () => { clearDevice(); status(port() ? `${port()} selected. Detect the ESP32 or read existing settings.` : "Select your ESP32 serial port."); });
  $("detect").addEventListener("click", () => run("Connecting to ESP32 and detecting its flash size…", detect));
  $("flash").addEventListener("click", () => run("Flashing and verifying matching firmware. Keep USB connected…", () => flash(false)));
  $("read-settings").addEventListener("click", () => run("Reading device settings over USB…", () => readSettings()));
  $("reset-read-settings").addEventListener("click", () => run("Restarting the board and reading settings. Release BOOT…", () => readSettings(true)));
  $("settings-form").addEventListener("submit", (event) => { event.preventDefault(); if (!state.info || state.infoPort !== port()) return; run("Saving device settings…", saveSettings); });
  $("profile").addEventListener("change", () => { const profile = state.profiles.find((p) => p.id === $("profile").value); text("profile-note", profile ? profile.notes : "Choose a profile only if your physical wiring matches it."); });
  $("new-install").addEventListener("click", () => askConfirmation({ title: "Change the partition layout?", message: "Use this only after a different layout prevented a normal flash. A full flash backup will be created first. Existing settings and queued events may become inaccessible with the new layout.", phrase: "CHANGE PARTITION LAYOUT", action: () => run("Backing up the ESP32 and installing the matching partition layout…", () => flash(true)) }));
  $("initialize-storage").addEventListener("click", () => {
    if (!storageEligible()) return;
    askConfirmation({ title: "Initialize empty event storage?", message: "The connected logger reports a storage fault with zero captured events and no pending events. This formats its event-storage partition. The device will reject the request if it has captured or queued any events.", phrase: "FORMAT EMPTY STORAGE", action: () => run("Initializing empty logger storage…", async () => { await api("initialize_storage", { confirm: "FORMAT EMPTY STORAGE" }); state.info = null; state.infoPort = ""; $("device-settings").hidden = true; $("storage-panel").hidden = true; status("Empty storage initialized. After the logger restarts, read settings to verify its status."); log("Storage initialized. Read settings after the restart to verify."); }) });
  });
  $("confirm-input").addEventListener("input", updateControls);
  $("confirm-cancel").addEventListener("click", () => $("confirm-dialog").close());
  $("confirm-proceed").addEventListener("click", () => {
    if (!state.confirmation || $("confirm-input").value !== state.confirmation.phrase) return;
    const action = state.confirmation.action; $("confirm-dialog").close(); action();
  });
  $("confirm-dialog").addEventListener("close", () => { state.confirmation = null; $("confirm-input").value = ""; updateControls(); });
  document.querySelectorAll("[data-secret]").forEach((button) => button.addEventListener("click", () => {
    const input = $(button.dataset.secret), show = input.type === "password";
    input.type = show ? "text" : "password"; button.textContent = show ? "Hide" : "Show";
    button.setAttribute("aria-pressed", String(show)); button.setAttribute("aria-label", `${show ? "Hide" : "Show"} ${input.id === "password" ? "Wi-Fi password" : "API key"}`);
  }));
  $("clear-log").addEventListener("click", () => { state.logs = []; $("activity-log").textContent = "Activity cleared."; });
  $("close-app").addEventListener("click", () => run("Closing the local utility…", async () => {
    const response = await fetch("/api/close", { method: "POST", credentials: "same-origin", headers: { "X-App-Token": token } });
    if (!response.ok) throw new Error("The utility could not close. You can close its Windows window after any operation finishes.");
    state.closed = true;
    $("password").value = ""; $("api-key").value = "";
    status("Local utility closed. You can close this browser tab."); log("Local utility closed.");
  }));
  // Profiles never contain credentials. A failure keeps existing GPIO mapping available.
  async function loadProfiles() {
    try {
      const response = await fetch("/api/profiles", { credentials: "same-origin", cache: "no-store", headers: { "X-App-Token": token } });
      if (!response.ok) return;
      const reply = await response.json();
      const profiles = Array.isArray(reply) ? reply : (Array.isArray(reply.result) ? reply.result : reply.profiles);
      state.profiles = Array.isArray(profiles) ? profiles : [];
      if (state.info) refreshProfileOptions();
    } catch (_) { /* GPIO profile selection is optional. */ }
  }
  updateControls();
  loadProfiles();
  run("Looking for USB serial ports…", refreshPorts);
})();
