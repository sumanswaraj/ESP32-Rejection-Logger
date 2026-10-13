#pragma once
// Host-only hardware boundary: firmware headers and ArduinoJson remain real.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <type_traits>

class String {
  std::string value;
public:
  String() = default;
  String(const char* text):value(text?text:""){}
  String(const std::string& text):value(text){}
  template<class T,typename std::enable_if<std::is_arithmetic<T>::value,int>::type=0>
  String(T number):value(std::to_string(number)){}
  const char* c_str()const{return value.c_str();}
  size_t length()const{return value.size();}
  bool isEmpty()const{return value.empty();}
  bool concat(const char* text){if(text)value+=text;return true;}
  bool concat(const char* text,size_t length){value.append(text,length);return true;}
  auto begin()const{return value.begin();}
  auto end()const{return value.end();}
  bool startsWith(const char* prefix)const{return value.rfind(prefix,0)==0;}
  int indexOf(char c,size_t start=0)const{auto position=value.find(c,start);return position==std::string::npos?-1:static_cast<int>(position);}
  int indexOf(const char* text)const{auto position=value.find(text);return position==std::string::npos?-1:static_cast<int>(position);}
  String substring(size_t start,size_t finish)const{return value.substr(start,finish-start);}
  String substring(size_t start)const{return value.substr(start);}
  friend bool operator==(const String& left,const String& right){return left.value==right.value;}
  friend bool operator!=(const String& left,const String& right){return !(left==right);}
  friend String operator+(const String& left,const String& right){return left.value+right.value;}
};

class Stream {
public:
  virtual ~Stream() = default;
  virtual size_t write(uint8_t)=0;
  virtual size_t write(const uint8_t* data,size_t length){for(size_t i=0;i<length;i++)write(data[i]);return length;}
  size_t print(const String& value){return write(reinterpret_cast<const uint8_t*>(value.c_str()),value.length());}
  size_t println(){return write(static_cast<uint8_t>('\n'));}
  virtual void flush(){}
};
class CaptureStream:public Stream {
public:
  std::string output;
  size_t write(uint8_t byte)override{output+=static_cast<char>(byte);return 1;}
};
inline CaptureStream Serial;
struct FakeESP {
  uint64_t getEfuseMac()const{return 0x123456789ABCULL;}
  const char* getChipModel()const{return "ESP32";}
  uint32_t getFlashChipSize()const{return 4*1024*1024;}
  uint32_t getPsramSize()const{return 0;}
};
inline FakeESP ESP;
constexpr int WL_CONNECTED=3;
struct FakeIP {String toString()const{return "192.0.2.1";}};
struct FakeWiFi {
  String macAddress()const{return "12:34:56:78:9A:BC";}
  int status()const{return WL_CONNECTED;}
  FakeIP localIP()const{return {};}
};
inline FakeWiFi WiFi;
struct FakeLittleFS {bool format(){return true;}};
inline FakeLittleFS LittleFS;
