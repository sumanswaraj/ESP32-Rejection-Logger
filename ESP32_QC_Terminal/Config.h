#pragma once
#include <Arduino.h>
#include "BoardProfile.h"
constexpr char FIRMWARE_VERSION[] = "2.1.0-multiboard-pilot";
constexpr size_t MAX_PENDING=1024, MAX_BODY=2048, MAX_REPLY=4096;
constexpr uint32_t SETUP_WINDOW_MS=600000, HTTP_TIMEOUT_MS=6000;
constexpr uint16_t MAX_QUANTITY=9999;
// Active buzzer through transistor. All GPIO signals are 3.3 V.
// SCL/SDO board is TTP229-BSF-style serial, NOT I2C.
