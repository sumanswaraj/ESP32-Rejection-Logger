#pragma once
#include <WebServer.h>
#include "DeviceSettings.h"
static const char PORTAL_HTML[] PROGMEM=R"HTML(<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><title>QC Terminal</title>
<style>body{font:16px system-ui;background:#eef2f6;color:#182539;max-width:760px;margin:auto;padding:20px}section{background:white;padding:20px;margin:16px 0;border-radius:14px}input,textarea,button{box-sizing:border-box;font:inherit;padding:12px;margin:5px 0;width:100%}button{background:#1458ae;color:white;border:0;border-radius:8px;cursor:pointer}label{display:block}input[type=checkbox]{width:auto}pre{white-space:pre-wrap}</style>
<h1>QC Rejection Terminal</h1><section><h2>Device status</h2><pre id="status">Loading…</pre><button onclick="refresh()">Refresh</button></section>
<section><h2>Quantity mode</h2><p>Default: 1 piece. Set quantity, then press a defect on either keypad. It resets to 1 after local save.</p>
<form action="/quantity" method="post"><input name="csrf" class="csrf" type="hidden"><input name="quantity" type="number" min="1" max="9999" value="1" required><button>Set quantity</button></form>
<form action="/cancel" method="post"><input name="csrf" class="csrf" type="hidden"><button>Cancel quantity — restore 1</button></form></section>
<section><h2>Device setup</h2><p>Hold BOOT for 5 seconds after startup to unlock setup for 10 minutes. Enter the deployed Apps Script /exec URL. Machine and part remain managed by the shop-floor dashboard.</p>
<form action="/save" method="post"><input name="csrf" class="csrf" type="hidden">
<label>Logger ID (must match QR_Master; locked after first event)<input id="device_id" name="device_id" maxlength="80" required></label>
<label>Device display name<input id="name" name="name" maxlength="60" required></label>
<label>Wi-Fi SSID<input id="ssid" name="ssid" maxlength="32" required></label>
<label>Wi-Fi password (blank keeps existing)<input name="password" type="password" maxlength="63"></label>
<label>Apps Script web-app /exec URL<input id="endpoint" name="endpoint" type="url" required></label>
<label>Device API key (blank keeps existing)<input name="token" type="password" maxlength="200"></label>
<label>Trusted root CA PEM (blank uses bundled Google roots unless a custom CA is already saved)<textarea name="ca" rows="6" maxlength="2048"></textarea></label>
<label><input id="touch" type="checkbox" name="touch" value="1">Enable 16-key SCL/SDO touch board</label><p id="touch_note"></p>
<label><input id="active_low" type="checkbox" name="active_low" value="1">Active-low serial mode (usual board setting)</label>
<button>Save and restart</button></form>
<form action="/reset" method="post"><input name="csrf" class="csrf" type="hidden"><p>Network reset preserves logger identity and queued events.</p><input name="confirm" placeholder="Type RESET NETWORK" required><button>Reset network and server settings</button></form></section>
<script>async function refresh(){try{let r=await fetch('/status');let s=await r.json();document.getElementById('status').textContent=JSON.stringify(s,null,2);for(let e of document.querySelectorAll('.csrf'))e.value=s.csrf;for(let k of ['device_id','name','ssid','endpoint'])document.getElementById(k).value=s[k];document.getElementById('device_id').readOnly=s.identity_locked;document.getElementById('touch').checked=s.touch;document.getElementById('active_low').checked=s.active_low;}catch(e){document.getElementById('status').textContent='Reconnect and refresh.'}}refresh();</script></html>)HTML";
class SetupPortal {
public:
  WebServer server{80};String pass,csrf;uint32_t opened=0;bool open=false,ap=false;
  bool unlocked()const{return open && millis()-opened<SETUP_WINDOW_MS;}
  bool authorized(bool mutation=false){
    if(!server.authenticate("admin",pass.c_str())){server.requestAuthentication();return false;}
    if(mutation && server.arg("csrf")!=csrf){server.send(403,"text/plain","Invalid form token; refresh the page.");return false;}
    return true;
  }
  void openWindow(const String& id){opened=millis();open=true;
    if(!ap){String label="QC-Setup-"+id.substring(id.length()>6?id.length()-6:0);
      WiFi.mode(WIFI_AP_STA);ap=WiFi.softAP(label.c_str(),pass.c_str());
      Serial.printf("Setup AP: %s | URL http://192.168.4.1 | user admin | password %s\n",label.c_str(),pass.c_str());}
  }
  void begin(){char b[24];snprintf(b,sizeof(b),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());pass=b;
    snprintf(b,sizeof(b),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());csrf=b;
    Serial.printf("Local control login: admin | password %s (changes each restart)\n",pass.c_str());
    server.on("/",HTTP_GET,[this](){if(authorized())server.send_P(200,"text/html",PORTAL_HTML);});
  }
  void tick(){server.handleClient();if(open && !unlocked()){open=false;if(ap){WiFi.softAPdisconnect(true);ap=false;WiFi.mode(WIFI_STA);}}}
};
