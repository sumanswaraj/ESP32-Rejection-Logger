// Real production headers plus ArduinoJson; only hardware APIs are stubbed.
#include "SerialConfigurator.h"
#include "AssignmentManager.h"
#include <iostream>
#include <stdexcept>

static unsigned checks=0;
static void expect(bool condition,const char* message){
  checks++;if(!condition)throw std::runtime_error(message);
}
struct Journal {size_t count=0;bool fault=false;size_t length()const{return count;}};
struct Response {bool restart=false;JsonDocument json;};
static JsonDocument request(const char* command="configure"){
  JsonDocument d;d["protocol"]=1;d["id"]="test-request";d["command"]=command;return d;
}
static Response exchange(DeviceSettings& settings,Journal& journal,const JsonDocument& req){
  String encoded;serializeJson(req,encoded);CaptureStream channel;SerialConfigurator configurator;
  Response result;result.restart=configurator.handle(encoded,settings,journal,channel);
  expect(channel.output.rfind("QC_RPC ",0)==0,"Reply must use the real commissioning prefix");
  expect(!deserializeJson(result.json,channel.output.substr(7)),"Reply must be valid JSON");
  expect(result.json["id"]=="test-request","Reply must preserve request correlation");
  return result;
}
static DeviceSettings seed(uint64_t sequence=0){
  FakeNVS::reset();FakeNVS::strings["id"]="LEGACY_ID";FakeNVS::strings["generation"]="original-generation";
  FakeNVS::integers["sequence"]=sequence;
  DeviceSettings settings;expect(settings.begin(),"Legacy settings should load");
  settings.ssid="Factory";settings.password="original-password";settings.token="original-token";
  settings.ingestUrl="https://example.com/exec";
  expect(settings.save(),"Initial config should save");FakeNVS::writes.clear();return settings;
}
static String assignment(const String& deviceId,bool valid=true){
  JsonDocument d;d["success"]=true;d["device_id"]=deviceId;d["active"]=true;
  d["assignment_id"]="job-1";d["assignment_version"]=1;d["machine_id"]="machine-1";
  if(valid)d["part_id"]="part-1";
  String raw;serializeJson(d,raw);return raw;
}
static void testRenameAndPersistence(){
  auto settings=seed();Journal journal;FakeNVS::strings["assignment"]=assignment("LEGACY_ID");
  auto req=request();req["device_id"]="LOGGER_001-A";auto response=exchange(settings,journal,req);
  expect(response.restart && response.json["ok"].as<bool>(),"ID-only configure should succeed and restart");
  expect(FakeNVS::writes==std::vector<std::string>{"config"},"Rename must perform exactly one config write");
  expect(FakeNVS::strings["id"]=="LEGACY_ID","Legacy identity key must stay untouched");
  expect(FakeNVS::strings["generation"]=="original-generation" && FakeNVS::integers["sequence"]==0,"Rename must preserve capture identity history");
  expect(FakeNVS::strings["assignment"]==assignment("LEGACY_ID"),"Cached assignment must not be deleted in a second write");
  DeviceSettings rebooted;expect(rebooted.begin(),"Renamed config should load after reboot");
  expect(rebooted.deviceId=="LOGGER_001-A","Canonical config ID must override legacy ID after reboot");
  expect(rebooted.password==settings.password && rebooted.token==settings.token && rebooted.ssid==settings.ssid,"ID-only configure must preserve network credentials");
  expect(rebooted.pins.buzzer==settings.pins.buzzer && rebooted.generation==settings.generation,"ID-only configure must preserve GPIO and generation");
  AssignmentManager restored;expect(restored.restore(rebooted) && !restored.active && restored.id.isEmpty(),"Unused renamed logger must ignore its previous valid cached assignment");
  expect(!restored.install(assignment("LEGACY_ID"),rebooted),"A fresh assignment for another logger must still be rejected");
}
static void testIdentityLocks(){
  for(bool pending:{false,true}){
    auto settings=seed(pending?0:7);Journal journal;journal.count=pending?3:0;
    auto changed=request();changed["device_id"]="RENAMED";auto rejected=exchange(settings,journal,changed);
    expect(!rejected.restart && !rejected.json["ok"].as<bool>(),"Captured or pending history must prevent a rename");
    expect(FakeNVS::writes.empty(),"Rejected rename must not write config");
    auto unchanged=request();unchanged["device_id"]="LEGACY_ID";auto accepted=exchange(settings,journal,unchanged);
    expect(accepted.restart && accepted.json["ok"].as<bool>(),"Unchanged identity must remain allowed with history");
    DeviceSettings rebooted;expect(rebooted.begin() && rebooted.deviceId=="LEGACY_ID" && rebooted.sequence==settings.sequence,"Unchanged ID must preserve history on reboot");
  }
}
static void testCombinedConfiguration(){
  auto settings=seed();Journal journal;auto req=request();req["device_id"]="COMBINED_ID";
  req["network"]["name"]="Changed display name";req["network"]["ssid"]="Changed network";
  settings.pins.toJson(req["pins"].to<JsonObject>());req["pins"]["buzzer"]=4;
  auto response=exchange(settings,journal,req);
  expect(response.restart && response.json["ok"].as<bool>(),"Combined ID, network and pin configuration should succeed");
  expect(FakeNVS::writes==std::vector<std::string>{"config"},"Combined identity and settings must commit in one config write");
  DeviceSettings rebooted;expect(rebooted.begin(),"Combined configuration should reload");
  expect(rebooted.deviceId=="COMBINED_ID" && rebooted.name=="Changed display name" && rebooted.ssid=="Changed network" && rebooted.pins.buzzer==4,"Combined settings must survive reboot together");
  expect(rebooted.password==settings.password && rebooted.token==settings.token,"Omitted combined credentials must remain unchanged");
}
static void testValidation(){
  for(const std::string& invalid:std::vector<std::string>{"",std::string(81,'A'),"contains space","contains.dot","with/slash","caf\xc3\xa9",std::string("A\0B",3)}){
    auto settings=seed();Journal journal;auto req=request();req["device_id"]=invalid;
    auto response=exchange(settings,journal,req);
    expect(!response.restart && !response.json["ok"].as<bool>(),"Invalid logger IDs must be rejected");
    expect(FakeNVS::writes.empty(),"Invalid logger ID must not write config");
  }
  for(const char* encoded:{"null","true","123","[]","{}"}){
    auto settings=seed();Journal journal;auto req=request();JsonDocument value;
    expect(!deserializeJson(value,encoded),"Test input must parse");req["device_id"]=value.as<JsonVariant>();
    auto response=exchange(settings,journal,req);
    expect(!response.restart && !response.json["ok"].as<bool>() && FakeNVS::writes.empty(),"Non-text logger IDs must be rejected before writes");
  }
  auto settings=seed();Journal journal;auto req=request();req["device_id"]=std::string(80,'A');
  auto response=exchange(settings,journal,req);
  expect(response.restart && response.json["ok"].as<bool>(),"The 80-byte ASCII boundary must be accepted");
}
static void testWriteFailure(){
  for(auto failure:{FakeNVS::REFUSE_WRITE,FakeNVS::SHORT_WRITE,FakeNVS::CORRUPT_READBACK}){
    auto settings=seed();Journal journal;FakeNVS::failure=failure;auto req=request();req["device_id"]="NEW_ID";
    auto response=exchange(settings,journal,req);
    expect(!response.restart && !response.json["ok"].as<bool>(),"Failed or unverified config writes must never report success");
    expect(settings.deviceId=="LEGACY_ID" && settings.sequence==0,"Failed configure must not mutate in-memory identity/history");
    expect(settings.configurationFault,"Unverified config write must latch a capture fault until restart");
    expect(FakeNVS::writes==std::vector<std::string>{"config"},"Failure handling must avoid multi-key identity writes");
    auto readback=exchange(settings,journal,request("info"));
    expect(readback.json["device"]["configuration_fault"].as<bool>(),"Info must report the latched configuration fault");
    if(failure==FakeNVS::SHORT_WRITE){
      FakeNVS::failure=FakeNVS::NONE;DeviceSettings rebooted;
      expect(rebooted.begin() && rebooted.deviceId=="NEW_ID" && rebooted.sequence==0,"A write may commit despite an unverified result; capture must stay paused before reboot");
    }
  }
}
static void testBootMigrationAndMalformedConfig(){
  auto settings=seed(8);JsonDocument oldConfig;settings.toJson(oldConfig);oldConfig.remove("device_id");
  String raw;serializeJson(oldConfig,raw);FakeNVS::strings["config"]=raw;DeviceSettings legacy;
  expect(legacy.begin() && legacy.deviceId=="LEGACY_ID" && legacy.sequence==8,"Old config without device_id must retain legacy identity/history");
  FakeNVS::strings["config"]="broken-json";DeviceSettings broken;
  expect(!broken.begin() && broken.sequence==8,"Malformed config must fail closed while retaining the identity lock");
  oldConfig["device_id"]="invalid.id";serializeJson(oldConfig,raw);FakeNVS::strings["config"]=raw;DeviceSettings invalid;
  expect(!invalid.begin() && invalid.sequence==8,"Invalid canonical identity must fail closed while retaining capture history");
  FakeNVS::reset();DeviceSettings fresh;expect(fresh.begin(),"A fresh logger should initialize");
  expect(fresh.deviceId=="ESP32_123456789ABC","A fresh logger must keep the deterministic MAC default");
  expect(FakeNVS::strings.count("id")==0,"Fresh startup must not separately persist the identity key");
}
static void testAssignmentRestore(){
  auto settings=seed(9);FakeNVS::strings["assignment"]=assignment("OTHER_ID");AssignmentManager previous;
  expect(!previous.restore(settings),"Mismatched cached assignment with captured history must fail closed");
  settings.sequence=0;FakeNVS::strings["assignment"]=assignment("OTHER_ID",false);
  expect(!previous.restore(settings),"Malformed mismatched cached assignment must not be ignored");
  FakeNVS::strings["assignment"]=assignment("LEGACY_ID");FakeNVS::writes.clear();
  expect(previous.restore(settings) && previous.active && previous.id=="job-1","Matching valid assignment should restore normally");
  expect(FakeNVS::writes.empty(),"Assignment restore must not alter NVS");
}
static void testInfoAndOldConfiguration(){
  auto settings=seed();Journal journal;auto info=request("info");auto response=exchange(settings,journal,info);
  expect(response.json["device"]["logger_id_edit_supported"].as<bool>(),"Info must advertise Logger ID support");
  expect(!response.json["device"]["identity_locked"].as<bool>(),"Fresh identity must be editable");
  journal.count=1;response=exchange(settings,journal,info);
  expect(response.json["device"]["identity_locked"].as<bool>(),"Pending events must lock identity in info");
  journal.count=0;settings.sequence=5;response=exchange(settings,journal,info);
  FakeNVS::integers["sequence"]=5;
  expect(response.json["device"]["identity_locked"].as<bool>(),"Captured sequence must lock identity in info");
  auto network=request();network["network"]["name"]="Updated display name";response=exchange(settings,journal,network);
  expect(response.restart && response.json["ok"].as<bool>(),"Network-only configure must remain supported with history");
  DeviceSettings rebooted;expect(rebooted.begin() && rebooted.deviceId=="LEGACY_ID" && rebooted.name=="Updated display name","Network configure must preserve ID and apply the existing fields");
  auto pins=request();rebooted.pins.toJson(pins["pins"].to<JsonObject>());pins["pins"]["buzzer"]=4;
  response=exchange(rebooted,journal,pins);
  expect(response.restart && response.json["ok"].as<bool>(),"Pin-only configure must remain supported with captured history");
  DeviceSettings repinned;expect(repinned.begin() && repinned.deviceId=="LEGACY_ID" && repinned.sequence==5 && repinned.pins.buzzer==4 && repinned.name=="Updated display name","Pin-only configure must preserve identity, sequence and network settings");
}
int main(){
  try{testRenameAndPersistence();testIdentityLocks();testCombinedConfiguration();testValidation();testWriteFailure();testBootMigrationAndMalformedConfig();testAssignmentRestore();testInfoAndOldConfiguration();}
  catch(const std::exception& error){std::cerr<<"Firmware Logger ID test failed: "<<error.what()<<'\n';return 1;}
  std::cout<<"Passed "<<checks<<" firmware Logger ID assertions against real headers and ArduinoJson; hardware APIs were stubbed.\n";
}
