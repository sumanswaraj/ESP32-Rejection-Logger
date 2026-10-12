#pragma once
#include <Keypad.h>
#include "Config.h"
#include "InputState.h"
#include "PinConfig.h"
class KeypadHandler {
  char keys[4][4]={{'1','2','3','A'},{'4','5','6','B'},{'7','8','9','C'},{'*','0','#','D'}};
  byte rows[4]={ROW_PINS[0],ROW_PINS[1],ROW_PINS[2],ROW_PINS[3]};
  byte cols[4]={COL_PINS[0],COL_PINS[1],COL_PINS[2],COL_PINS[3]};
  Keypad* pad=nullptr;
public:
  void begin(const PinConfig& pins){if(!pins.keypad)return;
    for(uint8_t i=0;i<4;i++){rows[i]=pins.rows[i];cols[i]=pins.cols[i];}
    pad=new Keypad(makeKeymap(keys),rows,cols,4,4);if(pad)pad->setDebounceTime(30);}
  uint8_t poll(){return pad?InputState::defect(pad->getKey()):0;}
};
