#pragma once
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "DeviceSettings.h"
#include "GoogleRoots.h"
#include "Endpoint.h"
struct NetworkJob {uint8_t kind=0;uint64_t seq=0;char body[MAX_BODY+1]={0},hash[65]={0};};
struct NetworkResult {uint8_t kind=0;uint64_t seq=0;int code=0;char reply[MAX_REPLY+1]={0};};
class QCNetworkManager {
public:
  QueueHandle_t jobs=nullptr,results=nullptr;
  String endpoint,token,ca,deviceId;
  bool begin(const DeviceSettings& s){
    endpoint=s.ingestUrl;token=s.token;ca=s.ca.isEmpty()?String(GOOGLE_ROOT_CA):s.ca;deviceId=s.deviceId;
    jobs=xQueueCreate(1,sizeof(NetworkJob));results=xQueueCreate(1,sizeof(NetworkResult));if(!jobs || !results)return false;
    WiFi.mode(WIFI_STA);WiFi.setSleep(false);WiFi.setAutoReconnect(true);
    if(s.ssid.length())WiFi.begin(s.ssid.c_str(),s.password.c_str());
    configTime(0,0,"pool.ntp.org","time.google.com");
    return xTaskCreate(worker,"qc-google",12288,this,1,nullptr)==pdPASS;
  }
  // Google's one-time ContentService redirect must be fetched with GET.
  // Only the original /exec URL receives the POST body/API key.
  static int fetch(const String& url,const String* body,const String& ca,String& output,String& redirect){
    WiFiClientSecure secure;secure.setCACert(ca.c_str());secure.setHandshakeTimeout(8);
    HTTPClient http;if(!http.begin(secure,url))return -101;
    http.setTimeout(HTTP_TIMEOUT_MS);http.setConnectTimeout(HTTP_TIMEOUT_MS);
    http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
    const char* headers[]={"Location"};http.collectHeaders(headers,1);
    http.addHeader("Accept","application/json");int code;
    if(body){http.addHeader("Content-Type","application/json");code=http.POST((uint8_t*)body->c_str(),body->length());}else code=http.GET();
    redirect=http.header("Location");
    if(code==200){
      class BoundedStream:public Stream {public:String data;bool overflow=false;
        int available()override{return 0;}int read()override{return -1;}int peek()override{return -1;}void flush()override{}
        size_t write(uint8_t c)override{if(data.length()>=MAX_REPLY){overflow=true;return 0;}data+=(char)c;return 1;}
        size_t write(const uint8_t* b,size_t n)override{if(data.length()+n>MAX_REPLY){overflow=true;return 0;}data.concat((const char*)b,n);return n;}
      }sink;
      int size=http.getSize();if(size>int(MAX_REPLY))code=-102;
      else if(http.writeToStream(&sink)<0 || sink.overflow)code=-102;else output=sink.data;
    }
    http.end();return code;
  }
  static void worker(void* arg){auto& self=*static_cast<QCNetworkManager*>(arg);
    auto* job=new NetworkJob;auto* res=new NetworkResult;
    if(!job || !res){delete job;delete res;vTaskDelete(nullptr);return;}
    for(;;){if(xQueueReceive(self.jobs,job,portMAX_DELAY)!=pdTRUE)continue;
      *res=NetworkResult();res->kind=job->kind;res->seq=job->seq;
      if(WiFi.status()==WL_CONNECTED && validEndpoint(self.endpoint) && self.ca.length() && time(nullptr)>1700000000){
        JsonDocument d;
        if(job->kind==1){deserializeJson(d,job->body);d["action"]="qc_ingest_v2";d["record_json"]=job->body;d["payload_hash"]=job->hash;}
        else {d["action"]="qc_get_assignment_v2";d["device_id"]=self.deviceId;}
        d["api_key"]=self.token;String body;serializeJson(d,body);
        String reply,location;res->code=fetch(self.endpoint,&body,self.ca,reply,location);
        if(self.endpoint.startsWith("https://script.google.com/macros/s/") && (res->code==302 || res->code==303) && location.startsWith("https://script.googleusercontent.com/")){
          String ignored;res->code=fetch(location,nullptr,self.ca,reply,ignored);
        }
        if(res->code==200)strlcpy(res->reply,reply.c_str(),sizeof(res->reply));
      }else res->code=-100;
      xQueueSend(self.results,res,portMAX_DELAY);
    }
  }
};
