#pragma once
#include <Preferences.h>
#include <ArduinoJson.h>
#include <esp_system.h>
#include <time.h>
#include "Config.h"
#include "PinConfig.h"
struct DeviceSettings {
  PinConfig pins;
  String ssid,password,name="QC Terminal",deviceId,ingestUrl,assignmentUrl,token,ca;
  bool touchEnabled=TOUCH_AVAILABLE,touchActiveLow=true,allowHttp=false,legacyUnbound=false;
  String generation; uint64_t sequence=0; Preferences prefs;
  bool begin(){
    if(!prefs.begin("qc-terminal",false))return false;
    deviceId=prefs.getString("id","");
    if(deviceId.isEmpty()){uint64_t mac=ESP.getEfuseMac();char id[40];snprintf(id,sizeof(id),"ESP32_%012llX",(unsigned long long)mac);deviceId=id;
      if(!prefs.putString("id",deviceId))return false;}
    generation=prefs.getString("generation","");
    if(generation.isEmpty()){char g[24];snprintf(g,sizeof(g),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());generation=g;
      if(!prefs.putString("generation",generation))return false;}
    sequence=prefs.getULong64("sequence",0);
    String raw=prefs.getString("config","");if(raw.isEmpty())return true;
    JsonDocument d;if(deserializeJson(d,raw))return false;
    ssid=d["ssid"].as<String>();password=d["password"].as<String>();name=d["name"]|"QC Terminal";
    ingestUrl=d["ingest_url"].as<String>();assignmentUrl=d["assignment_url"].as<String>();
    token=d["token"].as<String>();ca=d["ca"].as<String>();
    String pinError;if(d.containsKey("pins") && (!d["pins"].is<JsonObject>() || !pins.fromJson(d["pins"],pinError)))return false;
    touchEnabled=pins.touch && (d["touch_enabled"]|true);pins.touch=touchEnabled;touchActiveLow=d["touch_active_low"]|true;
    if(!pins.validate(pinError))return false;
    allowHttp=d["allow_http"]|false;legacyUnbound=d["legacy_unbound"]|false;return true;
  }
  void toJson(JsonDocument& d)const{d["ssid"]=ssid;d["password"]=password;d["name"]=name;
    d["ingest_url"]=ingestUrl;d["assignment_url"]=assignmentUrl;d["token"]=token;d["ca"]=ca;
    d["touch_enabled"]=touchEnabled;d["touch_active_low"]=touchActiveLow;
    d["allow_http"]=allowHttp;d["legacy_unbound"]=legacyUnbound;pins.toJson(d["pins"].to<JsonObject>());}
  bool save(){JsonDocument d;toJson(d);
    String s;serializeJson(d,s);return s.length()<=3900 && prefs.putString("config",s)>0;}
  bool nextSequence(uint64_t& out){if(sequence>=9007199254740991ULL)return false;
    uint64_t next=sequence+1;if(prefs.putULong64("sequence",next)!=sizeof(next))return false;
    sequence=next;out=next;return true;}
};
