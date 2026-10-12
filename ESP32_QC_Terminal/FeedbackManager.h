#pragma once
#include "Config.h"
#include "PinConfig.h"
class FeedbackManager {
  uint32_t soundUntil=0,ackUntil=0,errorUntil=0;
  int buzzer=-1,wifiPin=-1,errorPin=-1,ack=-1,quantityPin=-1,pendingPin=-1;
public:
  static void write(int pin,bool value){if(pin>=0)digitalWrite(pin,value);}
  void begin(const PinConfig& pins){buzzer=pins.buzzer;wifiPin=pins.wifi;errorPin=pins.error;ack=pins.ack;quantityPin=pins.quantity;pendingPin=pins.pending;
    for(int p:{buzzer,wifiPin,errorPin,ack,quantityPin,pendingPin})if(p>=0){pinMode(p,OUTPUT);write(p,LOW);}}
  void localSaved(){soundUntil=millis()+30;}
  void success(){soundUntil=millis()+90;ackUntil=millis()+800;}
  void error(){soundUntil=millis()+250;errorUntil=millis()+2000;}
  void tick(bool wifi,bool pending,bool quantity,bool fault){
    uint32_t n=millis();
    auto active=[n](uint32_t until){return until && int32_t(until-n)>0;};
    write(buzzer,active(soundUntil));write(wifiPin,wifi);
    write(ack,active(ackUntil));write(quantityPin,quantity);
    write(pendingPin,pending && ((n/350)%2));
    write(errorPin,!wifi || fault || active(errorUntil));
  }
};
