#pragma once
#include "Arduino.h"
#include <map>
#include <vector>

namespace FakeNVS {
enum Failure {NONE, REFUSE_WRITE, SHORT_WRITE, CORRUPT_READBACK};
inline std::map<std::string,String> strings;
inline std::map<std::string,uint64_t> integers;
inline std::vector<std::string> writes;
inline Failure failure=NONE;
inline void reset(){strings.clear();integers.clear();writes.clear();failure=NONE;}
}
class Preferences {
public:
  bool begin(const char*,bool){return true;}
  String getString(const char* name,const char* fallback="")const{
    auto found=FakeNVS::strings.find(name);return found==FakeNVS::strings.end()?String(fallback):found->second;
  }
  size_t putString(const char* name,const String& value){
    FakeNVS::writes.emplace_back(name);
    if(FakeNVS::failure==FakeNVS::REFUSE_WRITE)return 0;
    FakeNVS::strings[name]=FakeNVS::failure==FakeNVS::CORRUPT_READBACK?String("corrupted"):value;
    return FakeNVS::failure==FakeNVS::SHORT_WRITE?value.length()-1:value.length();
  }
  uint64_t getULong64(const char* name,uint64_t fallback=0)const{
    auto found=FakeNVS::integers.find(name);return found==FakeNVS::integers.end()?fallback:found->second;
  }
  size_t putULong64(const char* name,uint64_t value){
    FakeNVS::writes.emplace_back(name);FakeNVS::integers[name]=value;return sizeof(value);
  }
};
