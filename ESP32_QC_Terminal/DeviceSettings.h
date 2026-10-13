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
  bool configurationFault=false;
  String generation; uint64_t sequence=0; Preferences prefs;
  static bool validDeviceIdBytes(const char* id,size_t length){
    if(!id || !length || length>80)return false;
    for(size_t i=0;i<length;i++){unsigned char c=id[i];
      if(!((c>='A' && c<='Z') || (c>='a' && c<='z') || (c>='0' && c<='9') || c=='_' || c=='-'))return false;}
    return true;
  }
  static bool validDeviceId(const String& id){return validDeviceIdBytes(id.c_str(),id.length());}
  static bool readDeviceId(JsonVariantConst value,String& id){
    if(!value.is<const char*>())return false;
    JsonString raw=value.as<JsonString>();if(!validDeviceIdBytes(raw.c_str(),raw.size()))return false;
    id=value.as<String>();return raw.size()==id.length();
  }
  bool begin(){
    if(!prefs.begin("qc-terminal",false))return false;
    sequence=prefs.getULong64("sequence",0);deviceId=prefs.getString("id","");
    String raw=prefs.getString("config","");JsonDocument d;
    if(!raw.isEmpty() && deserializeJson(d,raw))return false;
    if(d.containsKey("device_id")){
      String configuredId;if(!readDeviceId(d["device_id"],configuredId))return false;deviceId=configuredId;
    }
    if(deviceId.isEmpty()){uint64_t mac=ESP.getEfuseMac();char id[40];snprintf(id,sizeof(id),"ESP32_%012llX",(unsigned long long)mac);deviceId=id;}
    generation=prefs.getString("generation","");
    if(generation.isEmpty()){char g[24];snprintf(g,sizeof(g),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());generation=g;
      if(!prefs.putString("generation",generation))return false;}
    if(raw.isEmpty())return true;
    ssid=d["ssid"].as<String>();password=d["password"].as<String>();name=d["name"]|"QC Terminal";
    ingestUrl=d["ingest_url"].as<String>();assignmentUrl=d["assignment_url"].as<String>();
    token=d["token"].as<String>();ca=d["ca"].as<String>();
    String pinError;if(d.containsKey("pins") && (!d["pins"].is<JsonObject>() || !pins.fromJson(d["pins"],pinError)))return false;
    touchEnabled=pins.touch && (d["touch_enabled"]|true);pins.touch=touchEnabled;touchActiveLow=d["touch_active_low"]|true;
    if(!pins.validate(pinError))return false;
    allowHttp=d["allow_http"]|false;legacyUnbound=d["legacy_unbound"]|false;return true;
  }
  void toJson(JsonDocument& d)const{d["device_id"]=deviceId;d["ssid"]=ssid;d["password"]=password;d["name"]=name;
    d["ingest_url"]=ingestUrl;d["assignment_url"]=assignmentUrl;d["token"]=token;d["ca"]=ca;
    d["touch_enabled"]=touchEnabled;d["touch_active_low"]=touchActiveLow;
    d["allow_http"]=allowHttp;d["legacy_unbound"]=legacyUnbound;pins.toJson(d["pins"].to<JsonObject>());}
  bool saveConfig(const JsonDocument& d){
    size_t expected=d.overflowed()?0:measureJson(d);String s;
    size_t written=expected>0 && expected<=3900?serializeJson(d,s):0;
    bool saved=expected>0 && expected<=3900 && written==expected && s.length()==expected &&
      prefs.putString("config",s)==expected && prefs.getString("config","")==s;
    // An unverified write may have committed. Pause capture until reboot so
    // old in-memory identity cannot acquire history under a new stored ID.
    if(!saved)configurationFault=true;return saved;}
  bool save(){JsonDocument d;toJson(d);return saveConfig(d);}
  bool nextSequence(uint64_t& out){if(sequence>=9007199254740991ULL)return false;
    uint64_t next=sequence+1;if(prefs.putULong64("sequence",next)!=sizeof(next))return false;
    sequence=next;out=next;return true;}
};
