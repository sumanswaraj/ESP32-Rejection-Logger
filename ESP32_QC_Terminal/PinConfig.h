#pragma once
#include <ArduinoJson.h>
#include <driver/gpio.h>
#include "BoardProfile.h"

// Pin numbers are runtime settings. The board profile supplies first-boot defaults.
struct PinConfig {
  bool keypad=KEYPAD_AVAILABLE, touch=TOUCH_AVAILABLE;
  uint8_t rows[4]={ROW_PINS[0],ROW_PINS[1],ROW_PINS[2],ROW_PINS[3]};
  uint8_t cols[4]={COL_PINS[0],COL_PINS[1],COL_PINS[2],COL_PINS[3]};
  int touchScl=PIN_TOUCH_SCL,touchSdo=PIN_TOUCH_SDO,buzzer=PIN_BUZZER;
  int wifi=PIN_LED_WIFI,error=PIN_LED_ERROR,ack=PIN_LED_ACK;
  int quantity=PIN_LED_QUANTITY,pending=PIN_LED_PENDING,setup=PIN_SETUP;

  static bool reserved(int pin,bool setupPin=false){
    if(pin<0)return false;
#if defined(CONFIG_IDF_TARGET_ESP32)
    // Keep flash, PSRAM-capable pins, UART, and straps free.
    if((pin>=6 && pin<=11)||pin==16||pin==17||pin==1||pin==3)return true;
    if(pin==0)return !setupPin;
    return pin==2||pin==5||pin==12||pin==15;
#elif defined(CONFIG_IDF_TARGET_ESP32S2) || defined(CONFIG_IDF_TARGET_ESP32S3)
    if((pin>=26 && pin<=37)||pin==19||pin==20||pin==43||pin==44||pin==45||pin==46)return true;
    return pin==0 && !setupPin;
#elif defined(CONFIG_IDF_TARGET_ESP32C3)
    if((pin>=11 && pin<=21)||pin==2||pin==8)return true;
    return pin==9 && !setupPin;
#elif defined(CONFIG_IDF_TARGET_ESP32C6)
    if(pin>=24||pin==12||pin==13||pin==14||pin==16||pin==17||pin==4||pin==5||pin==8||pin==15)return true;
    return pin==9 && !setupPin;
#else
    return true;
#endif
  }
  bool validate(String& reason)const{
    uint64_t used=0;
    auto check=[&](int pin,bool output,bool isSetup=false){
      if(pin==-1)return true;
      if(pin<0||pin>48||!GPIO_IS_VALID_GPIO(pin)||(output && !GPIO_IS_VALID_OUTPUT_GPIO(pin))||reserved(pin,isSetup)){
        reason=String("Unavailable/reserved GPIO ")+pin;return false;}
      uint64_t bit=1ULL<<pin;
      if(used & bit){reason=String("GPIO assigned twice: ")+pin;return false;}
      used|=bit;return true;
    };
    if(keypad)for(uint8_t i=0;i<4;i++)if(!check(rows[i],true)||!check(cols[i],true))return false;
    if(touch){if(touchScl<0||touchSdo<0){reason="Touch needs SCL and SDO GPIOs";return false;}
      if(!check(touchScl,true)||!check(touchSdo,false))return false;}
    for(int p:{buzzer,wifi,error,ack,quantity,pending})if(!check(p,true))return false;
    if(!check(setup,false,true))return false;
    if(!keypad && !touch){reason="Enable at least one defect input";return false;}
    return true;
  }
  void toJson(JsonObject object)const{
    object["keypad"]=keypad;object["touch"]=touch;
    JsonArray r=object["rows"].to<JsonArray>(),c=object["cols"].to<JsonArray>();
    for(uint8_t i=0;i<4;i++){r.add(rows[i]);c.add(cols[i]);}
    object["touch_scl"]=touchScl;object["touch_sdo"]=touchSdo;object["buzzer"]=buzzer;
    object["led_wifi"]=wifi;object["led_error"]=error;object["led_ack"]=ack;
    object["led_quantity"]=quantity;object["led_pending"]=pending;object["setup"]=setup;
  }
  bool fromJson(JsonObjectConst object,String& reason){
    if(!object["keypad"].is<bool>()||!object["touch"].is<bool>()){
      reason="Pin map needs keypad/touch enable flags";return false;}
    PinConfig candidate=*this;candidate.keypad=object["keypad"];candidate.touch=object["touch"];
    for(const char* name:{"rows","cols"}){
      JsonArrayConst array=object[name].as<JsonArrayConst>();
      if(array.size()!=4){reason="Keypad row/column arrays must contain four GPIOs";return false;}
      for(uint8_t i=0;i<4;i++){
        if(!array[i].is<int>()||array[i].as<int>()<0||array[i].as<int>()>48){reason="Invalid keypad GPIO";return false;}
        (name[0]=='r'?candidate.rows:candidate.cols)[i]=array[i];
      }
    }
    const char* names[]={"touch_scl","touch_sdo","buzzer","led_wifi","led_error","led_ack","led_quantity","led_pending","setup"};
    int* values[]={&candidate.touchScl,&candidate.touchSdo,&candidate.buzzer,&candidate.wifi,&candidate.error,&candidate.ack,&candidate.quantity,&candidate.pending,&candidate.setup};
    for(uint8_t i=0;i<9;i++){
      if(!object[names[i]].is<int>()){reason=String("Missing/invalid GPIO field: ")+names[i];return false;}
      *values[i]=object[names[i]].as<int>();
    }
    if(!candidate.validate(reason))return false;
    *this=candidate;return true;
  }
};
