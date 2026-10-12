#pragma once
#include "DeviceSettings.h"
struct AssignmentManager {
  bool active=false;String id,machine,part,lot,operatorId;uint32_t version=0,catalogVersion=0;
  bool restore(DeviceSettings& s){String raw=s.prefs.getString("assignment","");
    if(raw.isEmpty())return true;return install(raw,s,false);}
  bool install(const String& raw,DeviceSettings& s,bool persist=true){
    JsonDocument d;if(deserializeJson(d,raw) || !d["success"].is<bool>() || !d["success"].as<bool>() || d["device_id"].as<String>()!=s.deviceId || !d["active"].is<bool>())return false;
    bool next=d["active"];String newId=d["assignment_id"].as<String>();uint32_t v=d["assignment_version"]|0U;
    if(next && (newId.isEmpty() || !v || d["machine_id"].as<String>().isEmpty() || d["part_id"].as<String>().isEmpty()))return false;
    if(raw.length()>2048)return false;
    if(persist && !s.prefs.putString("assignment",raw))return false;
    active=next;id=newId;version=v;machine=d["machine_id"].as<String>();part=d["part_id"].as<String>();
    lot=d["lot_id"].as<String>();operatorId=d["operator_id"].as<String>();catalogVersion=d["defect_catalog_version"]|1U;return true;
  }
  void append(JsonDocument& d){d["assignment_id"]=id;d["assignment_version"]=version;d["machine_id"]=machine;
    d["part_id"]=part;d["lot_id"]=lot;d["operator_id"]=operatorId;d["defect_catalog_version"]=catalogVersion;}
};
