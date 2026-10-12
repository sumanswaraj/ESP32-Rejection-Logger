#pragma once
#include <LittleFS.h>
#include "EventCodec.h"
class OfflineQueue {
  uint64_t ids[MAX_PENDING];size_t used=0;
  String path(uint64_t seq,const char* ext="json"){char p[56];snprintf(p,sizeof(p),"/pending/%020llu.%s",(unsigned long long)seq,ext);return p;}
public:
  bool fault=false;
  size_t length()const{return used;}
  uint64_t highest()const{return used?ids[used-1]:0;}
  bool begin(){
    // Never auto-format: a failed mount must not erase production records.
    if(!LittleFS.begin(false)){fault=true;return false;}
    if(!LittleFS.exists("/pending") && !LittleFS.mkdir("/pending")){fault=true;return false;}
    File dir=LittleFS.open("/pending");if(!dir || !dir.isDirectory()){fault=true;return false;}
    File f=dir.openNextFile();
    while(f){String n=f.name();bool temp=n.endsWith(".tmp");bool record=n.endsWith(".json");f.close();
      if(temp){String p=n.startsWith("/")?n:String("/pending/")+n;if(!LittleFS.remove(p))fault=true;}
      else if(record){String base=n.substring(n.lastIndexOf('/')+1);char* end=nullptr;
        uint64_t id=strtoull(base.c_str(),&end,10);
        if(!end || String(end)!=".json" || !id || used>=MAX_PENDING)fault=true;
        else ids[used++]=id;}
      else fault=true;
      f=dir.openNextFile();
    }
    for(size_t i=1;i<used;i++){uint64_t v=ids[i];size_t j=i;while(j && ids[j-1]>v){ids[j]=ids[j-1];j--;}ids[j]=v;}
    String b,h,e;
    for(size_t i=0;i<used;i++)if(!read(ids[i],b,h,e))fault=true;
    return !fault;
  }
  bool read(uint64_t id,String& body,String& hash,String& event){
    File f=LittleFS.open(path(id),"r");if(!f || f.size()>MAX_BODY+1024)return false;
    JsonDocument d;auto err=deserializeJson(d,f);f.close();if(err)return false;
    body=d["body"].as<String>();hash=d["hash"].as<String>();event=d["event_id"].as<String>();
    if(body.length()>MAX_BODY || hash.length()!=64 || hash!=sha256(body) || event.isEmpty())return false;
    JsonDocument p;if(deserializeJson(p,body))return false;
    return p["sequence"].as<uint64_t>()==id && p["event_id"].as<String>()==event;
  }
  bool push(uint64_t id,const String& body,const String& event){
    if(fault || used>=MAX_PENDING || (used && id<=highest()) || body.length()>MAX_BODY || LittleFS.totalBytes()-LittleFS.usedBytes()<16384)return false;
    String hash=sha256(body);if(hash.isEmpty())return false;
    JsonDocument d;d["body"]=body;d["hash"]=hash;d["event_id"]=event;
    File f=LittleFS.open(path(id,"tmp"),"w");if(!f){fault=true;return false;}
    size_t expected=measureJson(d),actual=serializeJson(d,f);f.flush();f.close();
    if(actual!=expected || !LittleFS.rename(path(id,"tmp"),path(id))){fault=true;return false;}
    ids[used++]=id;String b,h,e;
    if(!read(id,b,h,e)){fault=true;return false;}return true;
  }
  bool peek(uint64_t& id,String& body,String& hash,String& event){
    if(!used || fault)return false;id=ids[0];if(!read(id,body,hash,event)){fault=true;return false;}return true;
  }
  bool acknowledge(uint64_t id){
    if(!used || ids[0]!=id)return false;
    // Delete only after a matching committed receipt. Power-cut retry remains idempotent.
    if(!LittleFS.remove(path(id))){fault=true;return false;}
    for(size_t i=1;i<used;i++)ids[i-1]=ids[i];used--;return true;
  }
};
