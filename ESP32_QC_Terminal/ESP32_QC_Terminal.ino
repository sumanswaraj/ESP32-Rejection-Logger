#include "Config.h"
#include "GoogleRoots.h"
#include "DeviceSettings.h"
#include "InputState.h"
#include "FeedbackManager.h"
#include "KeypadHandler.h"
#include "TouchpadHandler.h"
#include "OfflineQueue.h"
#include "AssignmentManager.h"
#include "QCNetworkManager.h"
#include "SetupPortal.h"
#include "SerialConfigurator.h"
DeviceSettings settings;InputState input;FeedbackManager feedback;
KeypadHandler keypad;TouchpadHandler touch;OfflineQueue journal;
AssignmentManager assignment;QCNetworkManager network;SetupPortal portal;
SerialConfigurator serialConfig;
bool ready=false,inflight=false,serverFault=false,assignmentFresh=false,bootTriggered=false;
uint64_t sentSequence=0;String sentEvent,sentHash;
uint32_t nextSend=0,lastAssignment=0,lastWifi=0,held=0,restartAt=0,retry=2000,lastEntry=0;
String lastMessage="Starting",lastAcknowledged;
void reply(int code,const String& message){portal.server.send(code,"text/plain",message);}
bool setupAllowed(){if(!portal.authorized(true))return false;
  if(!portal.unlocked()){reply(403,"Hold BOOT for 5 seconds after startup to unlock device setup.");return false;}
  if(inflight){reply(409,"Request in flight. Retry after a few seconds.");return false;}return true;}
void setup(){
  Serial.begin(115200);delay(100);
#if ARDUINO_USB_CDC_ON_BOOT
  Serial0.begin(115200); // Serve commissioning commands over USB or a UART bridge.
#endif
  bool cfg=settings.begin(),fs=journal.begin();
  if(cfg){feedback.begin(settings.pins);keypad.begin(settings.pins);touch.begin(settings.pins,settings.touchEnabled,settings.touchActiveLow);}
  if(settings.pins.setup>=0)pinMode(settings.pins.setup,INPUT_PULLUP);
  if(cfg && journal.highest()>settings.sequence){settings.sequence=journal.highest();if(settings.prefs.putULong64("sequence",settings.sequence)!=8)cfg=false;}
  bool restored=cfg && assignment.restore(settings);
  ready=cfg && fs && restored;
  ready=network.begin(settings) && ready;
  portal.begin();
  portal.server.on("/status",HTTP_GET,[](){if(!portal.authorized())return;
    JsonDocument d;d["firmware"]=FIRMWARE_VERSION;d["board_profile"]=BOARD_PROFILE_NAME;
    d["chip"]=ESP.getChipModel();d["flash_bytes"]=ESP.getFlashChipSize();d["psram_bytes"]=ESP.getPsramSize();
    d["keypad_available"]=settings.pins.keypad;d["touch_available"]=settings.pins.touchScl>=0 && settings.pins.touchSdo>=0;
    settings.pins.toJson(d["pins"].to<JsonObject>());
    d["device_id"]=settings.deviceId;d["name"]=settings.name;
    d["ssid"]=settings.ssid;d["endpoint"]=settings.ingestUrl;d["touch"]=settings.touchEnabled;d["active_low"]=settings.touchActiveLow;
    d["identity_locked"]=settings.sequence>0;d["csrf"]=portal.csrf;d["setup_unlocked"]=portal.unlocked();
    d["wifi"]=WiFi.status()==WL_CONNECTED;d["ip"]=WiFi.localIP().toString();d["rssi"]=WiFi.RSSI();
    d["pending_events"]=journal.length();d["storage_fault"]=journal.fault;d["ready"]=ready;
    d["quantity"]=input.quantity;d["job_id"]=assignment.id;d["machine"]=assignment.machine;d["part"]=assignment.part;
    d["job_active"]=assignment.active;d["assignment_verified_this_boot"]=assignmentFresh;d["last_ack"]=lastAcknowledged;d["message"]=lastMessage;
    String body;serializeJson(d,body);portal.server.send(200,"application/json",body);
  });
  portal.server.on("/quantity",HTTP_POST,[](){if(!portal.authorized(true))return;
    String text=portal.server.arg("quantity");if(text.isEmpty()){reply(400,"Enter a quantity.");return;}
    for(char c:text)if(c<'0'||c>'9'){reply(400,"Use a positive whole number.");return;}
    long q=text.toInt();if(q<1||q>MAX_QUANTITY){reply(400,"Quantity must be 1 to 9999.");return;}
    input.setQuantity(q);reply(200,"Quantity set. Press a defect key. Back to return to controls.");
  });
  portal.server.on("/cancel",HTTP_POST,[](){if(!portal.authorized(true))return;input.accepted();reply(200,"Quantity restored to 1.");});
  portal.server.on("/save",HTTP_POST,[](){if(!setupAllowed())return;
    String id=portal.server.arg("device_id"),url=portal.server.arg("endpoint"),ssid=portal.server.arg("ssid"),name=portal.server.arg("name");
    if(id.isEmpty()||id.length()>80||ssid.isEmpty()||ssid.length()>32||name.isEmpty()||name.length()>60||!validEndpoint(url)){reply(400,"Check ID, name, SSID and HTTPS server URL.");return;}
    for(char c:id)if(!(isalnum((unsigned char)c)||c=='_'||c=='-')){reply(400,"Logger ID: letters, numbers, underscore or hyphen only.");return;}
    if(id!=settings.deviceId && (settings.sequence || journal.length())){reply(409,"Logger ID is locked after capture. Change display name instead.");return;}
    String pw=portal.server.arg("password"),token=portal.server.arg("token"),ca=portal.server.arg("ca");
    if((pw.length() && pw.length()<8)||pw.length()>63||token.length()>200||ca.length()>2048){reply(400,"Invalid credential length.");return;}
    if(ca.length() && (ca.indexOf("-----BEGIN CERTIFICATE-----")<0||ca.indexOf("-----END CERTIFICATE-----")<0)){reply(400,"Use a PEM CA certificate.");return;}
    if(token.isEmpty()&&settings.token.isEmpty()){reply(400,"Enter the device API key from Config.");return;}
    PinConfig pins=settings.pins;pins.touch=portal.server.hasArg("touch");String pinError;
    if(!pins.validate(pinError)){reply(400,pinError);return;}
    if(id!=settings.deviceId){if(!settings.prefs.putString("id",id)){reply(500,"ID save failed.");return;}settings.deviceId=id;settings.prefs.remove("assignment");}
    settings.ssid=ssid;settings.name=name;settings.ingestUrl=url;settings.assignmentUrl="";settings.allowHttp=false;settings.legacyUnbound=false;
    if(pw.length())settings.password=pw;if(token.length())settings.token=token;if(ca.length())settings.ca=ca;
    settings.pins=pins;settings.touchEnabled=pins.touch;settings.touchActiveLow=portal.server.hasArg("active_low");
    if(!settings.save()){ready=false;reply(500,"Settings save failed; capture paused.");return;}
    ready=false;reply(200,"Settings saved. Restarting. Setup password changes; read USB Serial.");restartAt=millis()+1500;
  });
  portal.server.on("/reset",HTTP_POST,[](){if(!setupAllowed())return;
    if(portal.server.arg("confirm")!="RESET NETWORK"){reply(400,"Type RESET NETWORK exactly.");return;}
    settings.ssid="";settings.password="";settings.ingestUrl="";settings.token="";settings.name="QC Terminal";
    if(!settings.save()){ready=false;reply(500,"Reset save failed.");return;}
    ready=false;reply(200,"Network settings reset. Pending events and logger ID retained. Restarting.");restartAt=millis()+1500;
  });
  portal.server.begin();
  if(settings.ssid.isEmpty() || settings.ingestUrl.isEmpty())portal.openWindow(settings.deviceId);
  lastMessage=ready?"Ready; awaiting current job from Apps Script":"Storage/configuration error: capture paused";
  Serial.printf("QC %s | Logger %s | pending %u\n",FIRMWARE_VERSION,settings.deviceId.c_str(),unsigned(journal.length()));
  Serial.printf("Profile %s | Chip %s | Flash %u | PSRAM %u | keypad %d | touch %d\n",
    BOARD_PROFILE_NAME,ESP.getChipModel(),unsigned(ESP.getFlashChipSize()),unsigned(ESP.getPsramSize()),settings.pins.keypad,settings.pins.touch);
}
void capture(uint8_t code,const char* source){
  if(!ready||journal.fault||input.editing||!assignmentFresh||!assignment.active){feedback.error();lastMessage="Capture blocked: configure device and start/verify dashboard job";return;}
  uint64_t seq;if(!settings.nextSequence(seq)){ready=false;feedback.error();lastMessage="Persistent sequence save failed";return;}
  String id=settings.deviceId+"-"+settings.generation+"-"+String((unsigned long long)seq);
  JsonDocument d;d["schema_version"]=2;d["device_id"]=settings.deviceId;d["device_name"]=settings.name;
  d["event_id"]=id;d["generation"]=settings.generation;d["sequence"]=seq;
  d["rejection_code"]=code;d["quantity"]=input.quantity;d["client_ms"]=millis();d["source"]=source;d["firmware"]=FIRMWARE_VERSION;
  time_t now=time(nullptr);if(now>1700000000){char utc[28];struct tm tm;gmtime_r(&now,&tm);strftime(utc,sizeof(utc),"%Y-%m-%dT%H:%M:%SZ",&tm);d["occurred_at"]=utc;d["time_quality"]="sntp";}
  else {d["occurred_at"]=nullptr;d["time_quality"]="unsynchronized";}
  assignment.append(d);String body;serializeJson(d,body);
  if(journal.push(seq,body,id)){input.accepted();feedback.localSaved();lastMessage="Locally saved; awaiting Google Sheet confirmation";Serial.printf("SAVED %s code=%u\n",id.c_str(),code);}
  else {feedback.error();lastMessage="Storage full/failure: event NOT accepted; quantity retained";}
}
void loop(){
  // Explicit first-use formatting only. Never auto-format after a mount error.
  static String serialLine[2];static bool serialOverflow[2]={false,false};
  auto serialTick=[&](Stream& transport,uint8_t index){
  uint16_t budget=128;
  while(transport.available() && budget--){
    char c=transport.read();
    if(c=='\n'){
      serialLine[index].trim();
      if(!serialOverflow[index] && serialConfig.handle(serialLine[index],settings,journal,transport)){ready=false;restartAt=millis()+1500;}
      serialLine[index]="";serialOverflow[index]=false;
    }else if(serialLine[index].length()<4096)serialLine[index]+=c;else serialOverflow[index]=true;
  }};
  serialTick(Serial,0);
#if ARDUINO_USB_CDC_ON_BOOT
  serialTick(Serial0,1);
#endif
  portal.tick();uint32_t n=millis();if(restartAt && int32_t(n-restartAt)>=0)ESP.restart();
  if(settings.pins.setup>=0 && digitalRead(settings.pins.setup)==LOW){if(!held)held=n;if(!bootTriggered && n-held>=5000){portal.openWindow(settings.deviceId);bootTriggered=true;}}
  else {held=0;bootTriggered=false;}
  if(WiFi.status()!=WL_CONNECTED && settings.ssid.length() && n-lastWifi>=15000){lastWifi=n;WiFi.reconnect();}
  uint8_t k=keypad.poll(),t=touch.poll();
  // One physical action must use one interface. Simultaneous inputs are rejected.
  if(k && t){feedback.error();lastMessage="Ambiguous simultaneous keypad/touch input: retry";}
  else if((k||t) && n-lastEntry>=120){lastEntry=n;capture(k?k:t,k?"keypad":"touch");}
  static NetworkResult result;
  if(network.results && xQueueReceive(network.results,&result,0)==pdTRUE){
    inflight=false;
    if(result.kind==1){if(result.code==200 && result.seq==sentSequence && receiptMatches(result.reply,sentEvent,sentHash)){
        if(journal.acknowledge(sentSequence)){feedback.success();lastAcknowledged=sentEvent;serverFault=false;retry=2000;nextSend=n+250;lastMessage="Confirmed saved in Google Sheet";}
        else {ready=false;feedback.error();lastMessage="Receipt matched but local acknowledgement failed";}
      }else {serverFault=true;nextSend=n+retry+(esp_random()%500);retry=retry<30000?retry*2:60000;JsonDocument errorDoc;deserializeJson(errorDoc,result.reply);String reason=errorDoc["error"].as<String>();
        lastMessage=String("Event retained: ")+(reason.length()?reason:String("HTTP/receipt error ")+String(result.code));Serial.printf("UPLOAD waiting: HTTP %d\n",result.code);}
    }else if(result.kind==2){if(result.code==200 && assignment.install(result.reply,settings)){
        assignmentFresh=true;serverFault=false;lastMessage=assignment.active?"Dashboard job synchronized":"No active dashboard job: capture paused";
      }else{serverFault=true;lastMessage="Assignment sync failed; cached job retained";}
    }
  }
  if(ready && !inflight && !restartAt && WiFi.status()==WL_CONNECTED && !settings.ingestUrl.isEmpty()){
    static NetworkJob job;
    // Snapshot new assignments even while old events remain queued. Each queued body is immutable.
    if(lastAssignment==0 || n-lastAssignment>=20000){
      job=NetworkJob();job.kind=2;if(xQueueSend(network.jobs,&job,0)==pdTRUE){inflight=true;lastAssignment=n;}
    }else if(journal.length() && int32_t(n-nextSend)>=0){
      String body,hash,event;uint64_t seq;
      if(journal.peek(seq,body,hash,event)){job=NetworkJob();job.kind=1;job.seq=seq;
        strlcpy(job.body,body.c_str(),sizeof(job.body));strlcpy(job.hash,hash.c_str(),sizeof(job.hash));
        if(xQueueSend(network.jobs,&job,0)==pdTRUE){inflight=true;sentSequence=seq;sentEvent=event;sentHash=hash;}}
    }
  }
  feedback.tick(WiFi.status()==WL_CONNECTED,journal.length()>0,input.quantity!=1||input.editing,!ready||journal.fault||serverFault||!assignment.active);
  delay(1);
}
