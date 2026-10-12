#pragma once
#include <mbedtls/sha256.h>
#include <ArduinoJson.h>
#include "Config.h"
inline String sha256(const String& s){unsigned char bytes[32];char hex[65];
  if(mbedtls_sha256((const unsigned char*)s.c_str(),s.length(),bytes,0)!=0)return "";
  for(int i=0;i<32;i++)snprintf(hex+i*2,3,"%02x",bytes[i]);hex[64]=0;return hex;}
inline bool receiptMatches(const String& reply,const String& event,const String& hash){
  JsonDocument d;if(deserializeJson(d,reply))return false;
  String status=d["status"].as<String>();
  return d["success"].is<bool>() && d["success"].as<bool>() && (status=="committed" || status=="duplicate") && d["event_id"].as<String>()==event && d["payload_hash"].as<String>()==hash;
}
