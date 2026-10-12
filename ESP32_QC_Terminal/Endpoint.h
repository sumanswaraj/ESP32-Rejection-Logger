#pragma once
#include <Arduino.h>
inline bool validEndpoint(const String& url){
  if(url.length()>512||!url.startsWith("https://"))return false;
  for(char c:url)if((unsigned char)c<=32||c=='#')return false;
  int end=url.indexOf('/',8);if(end<0)end=url.length();
  String host=url.substring(8,end);
  return host.length()>0 && host.indexOf('@')<0 && host.indexOf('?')<0;
}
