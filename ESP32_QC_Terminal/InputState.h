#pragma once
#include <stdint.h>
struct InputState {
  bool editing=false; uint16_t quantity=1;
  bool setQuantity(uint16_t q) { if(q<1 || q>9999) return false; quantity=q; editing=false; return true; }
  void accepted() { quantity=1; editing=false; }
  static uint8_t defect(char k) {
    if(k>='1' && k<='9') return k-'0';
    switch(k){case '0':return 10;case 'A':return 11;case 'B':return 12;
      case 'C':return 13;case 'D':return 14;case '*':return 15;case '#':return 16;default:return 0;}
  }
};
