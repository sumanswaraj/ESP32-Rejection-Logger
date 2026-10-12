#pragma once
#include "Config.h"
#include "PinConfig.h"
class TouchpadHandler {
  uint16_t previous=0,candidate=0; uint32_t changed=0,last=0,boot=0;
  bool enabled=false,activeLow=true;int scl=-1,sdo=-1;
public:
  void begin(const PinConfig& pins,bool on,bool low){enabled=on && pins.touch;activeLow=low;boot=millis();scl=pins.touchScl;sdo=pins.touchSdo;
    if(!enabled)return;
    pinMode(scl,OUTPUT);digitalWrite(scl,activeLow?HIGH:LOW);
    pinMode(sdo,INPUT_PULLUP);}
  uint8_t poll(){
    if(!enabled || millis()-boot<1000 || millis()-last<20)return 0;
    last=millis();uint16_t bits=0;
    // Idle gap > 2 ms is provided by the 20 ms scan interval.
    // Clock asserted LOW in default active-low serial mode; sample after deassertion.
    for(uint8_t i=0;i<16;i++){
      digitalWrite(scl,activeLow?LOW:HIGH);delayMicroseconds(10);
      digitalWrite(scl,activeLow?HIGH:LOW);delayMicroseconds(10);
      bool value=digitalRead(sdo);
      if(activeLow?!value:value)bits|=uint16_t(1)<<i;
    }
    if(bits!=candidate){candidate=bits;changed=millis();return 0;}
    if(millis()-changed<40 || bits==previous)return 0;
    uint16_t old=previous;previous=bits;
    // Require full release between touches; reject ambiguous multiple keys.
    if(old!=0 || bits==0 || (bits & (bits-1)))return 0;
    for(uint8_t i=0;i<16;i++)if(bits & (uint16_t(1)<<i))return i+1;
    return 0;
  }
};
