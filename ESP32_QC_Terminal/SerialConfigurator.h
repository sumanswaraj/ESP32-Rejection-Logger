#pragma once
#include "DeviceSettings.h"
#include "Endpoint.h"

// Physical USB/UART is the local administration channel. Requests are never echoed.
// Network/HTTP access continues to require the existing admin login and CSRF token.
class SerialConfigurator {
  Stream* channel=&Serial;
  void reply(const String& id,bool ok,const String& message,JsonDocument* info=nullptr){
    JsonDocument out;out["protocol"]=1;out["id"]=id;out["ok"]=ok;out["message"]=message;
    if(info)out["device"]=info->as<JsonObject>();
    channel->print("QC_RPC ");serializeJson(out,*channel);channel->println();channel->flush();
  }
public:
  template<class Journal>
  bool handle(const String& line,DeviceSettings& settings,Journal& journal,Stream& transport){
    channel=&transport;
    if(line.isEmpty())return false;
    bool legacyFormat=line=="FORMAT EMPTY STORAGE";
    JsonDocument req;
    if(legacyFormat){req["protocol"]=1;req["id"]="serial";req["command"]="initialize_storage";req["confirm"]=line;}
    else if(deserializeJson(req,line)){reply("",false,"Invalid configuration request");return false;}
    String id=req["id"]|"",command=req["command"]|"";
    if(req["protocol"].as<int>()!=1||id.length()>64){reply("",false,"Unsupported protocol");return false;}
    if(command=="info"){
      JsonDocument info;info["firmware"]=FIRMWARE_VERSION;info["chip"]=BOARD_CHIP_NAME;info["chip_model"]=ESP.getChipModel();
      info["board_profile"]=BOARD_PROFILE_NAME;info["device_id"]=settings.deviceId;info["name"]=settings.name;info["mac"]=WiFi.macAddress();
      info["flash_bytes"]=ESP.getFlashChipSize();info["psram_bytes"]=ESP.getPsramSize();
      info["ssid"]=settings.ssid;info["endpoint"]=settings.ingestUrl;
      info["wifi_password_set"]=!settings.password.isEmpty();info["api_key_set"]=!settings.token.isEmpty();
      info["custom_ca_set"]=!settings.ca.isEmpty();info["touch_active_low"]=settings.touchActiveLow;
      info["pending_events"]=journal.length();info["sequence"]=settings.sequence;info["storage_fault"]=journal.fault;
      info["wifi_connected"]=WiFi.status()==WL_CONNECTED;info["ip"]=WiFi.localIP().toString();
      settings.pins.toJson(info["pins"].to<JsonObject>());
      reply(id,true,"Device settings read; credentials hidden",&info);return false;
    }
    if(command=="initialize_storage"){
      if(req["confirm"]!="FORMAT EMPTY STORAGE"||settings.sequence!=0||journal.length()!=0||!journal.fault){
        reply(id,false,"Refused: only unformatted devices without capture history can be initialized");return false;}
      if(!LittleFS.format()){reply(id,false,"Storage initialization failed");return false;}
      reply(id,true,"Storage initialized; restarting");return true;
    }
    if(command!="configure"){reply(id,false,"Unknown command");return false;}
    if(!req["network"].is<JsonObject>()&&!req["pins"].is<JsonObject>()){
      reply(id,false,"Provide network settings or a GPIO map");return false;}
    JsonDocument draft;settings.toJson(draft);
    if(req["network"].is<JsonObject>()){
      JsonObjectConst network=req["network"];
      const char* input[]={"ssid","password","name","endpoint","api_key","ca"};
      const char* stored[]={"ssid","password","name","ingest_url","token","ca"};
      for(JsonPairConst field:network){
        bool known=false;for(const char* name:input)if(strcmp(field.key().c_str(),name)==0)known=true;
        if(!known||!field.value().is<const char*>()){reply(id,false,"Unknown/invalid network field");return false;}
      }
      for(uint8_t i=0;i<6;i++)if(network[input[i]].is<const char*>())draft[stored[i]]=network[input[i]];
    }
    PinConfig pins=settings.pins;String error;
    if(req["pins"].is<JsonObject>() && !pins.fromJson(req["pins"],error)){reply(id,false,error);return false;}
    if(!pins.validate(error)){reply(id,false,error);return false;}
    pins.toJson(draft["pins"].to<JsonObject>());draft["touch_enabled"]=pins.touch;
    if(req.containsKey("touch_active_low")){
      if(!req["touch_active_low"].is<bool>()){reply(id,false,"Invalid touch polarity");return false;}
      draft["touch_active_low"]=req["touch_active_low"];}
    String ssid=draft["ssid"]|"",password=draft["password"]|"",name=draft["name"]|"";
    String endpoint=draft["ingest_url"]|"",token=draft["token"]|"",ca=draft["ca"]|"";
    if(ssid.length()>32||password.length()>63||(password.length()>0&&password.length()<8)||name.isEmpty()||name.length()>60||token.length()>200||ca.length()>2048){
      reply(id,false,"Check SSID, password, display name, API key or CA length");return false;}
    if(endpoint.length()>0 && !validEndpoint(endpoint)){reply(id,false,"Use a valid HTTPS server URL");return false;}
    if(ca.length()>0 && (ca.indexOf("-----BEGIN CERTIFICATE-----")<0||ca.indexOf("-----END CERTIFICATE-----")<0)){
      reply(id,false,"Custom CA must be a PEM certificate");return false;}
    // Pin-only changes are allowed before Wi-Fi/server commissioning.
    draft["allow_http"]=false;draft["legacy_unbound"]=false;
    String stored;serializeJson(draft,stored);
    if(stored.length()>3900||settings.prefs.putString("config",stored)!=stored.length()||settings.prefs.getString("config","")!=stored){
      reply(id,false,"Configuration save failed");return false;}
    reply(id,true,"Configuration saved; restarting");return true;
  }
};
