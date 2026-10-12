#pragma once
// Generated from profiles/boards.json by qc_flash.py profiles.
#include "UserBoard.h"
#if QC_BOARD_PROFILE == 0
#if defined(CONFIG_IDF_TARGET_ESP32)
#undef QC_BOARD_PROFILE
#define QC_BOARD_PROFILE 1
#elif defined(CONFIG_IDF_TARGET_ESP32S2)
#undef QC_BOARD_PROFILE
#define QC_BOARD_PROFILE 2
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
#undef QC_BOARD_PROFILE
#define QC_BOARD_PROFILE 3
#elif defined(CONFIG_IDF_TARGET_ESP32C3)
#undef QC_BOARD_PROFILE
#define QC_BOARD_PROFILE 4
#elif defined(CONFIG_IDF_TARGET_ESP32C6)
#undef QC_BOARD_PROFILE
#define QC_BOARD_PROFILE 6
#else
#error "Supported targets: ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6."
#endif
#endif
#if QC_BOARD_PROFILE == 1
#if !defined(CONFIG_IDF_TARGET_ESP32)
#error "Pin profile does not match the selected chip."
#endif
constexpr char BOARD_PROFILE_NAME[] = "esp32-generic";
constexpr bool KEYPAD_AVAILABLE=true, TOUCH_AVAILABLE=true;
constexpr char BOARD_CHIP_NAME[] = "esp32";
constexpr uint8_t ROW_PINS[4] = {18,19,21,22};
constexpr uint8_t COL_PINS[4] = {23,25,26,27};
constexpr int PIN_TOUCH_SCL = 32;
constexpr int PIN_TOUCH_SDO = 33;
constexpr int PIN_BUZZER = 13;
constexpr int PIN_LED_WIFI = -1;
constexpr int PIN_LED_ERROR = 14;
constexpr int PIN_LED_ACK = -1;
constexpr int PIN_LED_QUANTITY = -1;
constexpr int PIN_LED_PENDING = -1;
constexpr int PIN_SETUP = 0;
#elif QC_BOARD_PROFILE == 2
#if !defined(CONFIG_IDF_TARGET_ESP32S2)
#error "Pin profile does not match the selected chip."
#endif
constexpr char BOARD_PROFILE_NAME[] = "esp32s2-generic";
constexpr bool KEYPAD_AVAILABLE=true, TOUCH_AVAILABLE=true;
constexpr char BOARD_CHIP_NAME[] = "esp32s2";
constexpr uint8_t ROW_PINS[4] = {4,5,6,7};
constexpr uint8_t COL_PINS[4] = {15,16,17,18};
constexpr int PIN_TOUCH_SCL = 8;
constexpr int PIN_TOUCH_SDO = 9;
constexpr int PIN_BUZZER = 10;
constexpr int PIN_LED_WIFI = 11;
constexpr int PIN_LED_ERROR = 12;
constexpr int PIN_LED_ACK = 13;
constexpr int PIN_LED_QUANTITY = 14;
constexpr int PIN_LED_PENDING = 21;
constexpr int PIN_SETUP = 0;
#elif QC_BOARD_PROFILE == 3
#if !defined(CONFIG_IDF_TARGET_ESP32S3)
#error "Pin profile does not match the selected chip."
#endif
constexpr char BOARD_PROFILE_NAME[] = "esp32s3-existing";
constexpr bool KEYPAD_AVAILABLE=true, TOUCH_AVAILABLE=true;
constexpr char BOARD_CHIP_NAME[] = "esp32s3";
constexpr uint8_t ROW_PINS[4] = {4,5,6,7};
constexpr uint8_t COL_PINS[4] = {15,16,17,18};
constexpr int PIN_TOUCH_SCL = 8;
constexpr int PIN_TOUCH_SDO = 9;
constexpr int PIN_BUZZER = 10;
constexpr int PIN_LED_WIFI = 11;
constexpr int PIN_LED_ERROR = 12;
constexpr int PIN_LED_ACK = 13;
constexpr int PIN_LED_QUANTITY = 14;
constexpr int PIN_LED_PENDING = 21;
constexpr int PIN_SETUP = 0;
#elif QC_BOARD_PROFILE == 4
#if !defined(CONFIG_IDF_TARGET_ESP32C3)
#error "Pin profile does not match the selected chip."
#endif
constexpr char BOARD_PROFILE_NAME[] = "esp32c3-keypad";
constexpr bool KEYPAD_AVAILABLE=true, TOUCH_AVAILABLE=false;
constexpr char BOARD_CHIP_NAME[] = "esp32c3";
constexpr uint8_t ROW_PINS[4] = {0,1,3,4};
constexpr uint8_t COL_PINS[4] = {5,6,7,10};
constexpr int PIN_TOUCH_SCL = -1;
constexpr int PIN_TOUCH_SDO = -1;
constexpr int PIN_BUZZER = -1;
constexpr int PIN_LED_WIFI = -1;
constexpr int PIN_LED_ERROR = -1;
constexpr int PIN_LED_ACK = -1;
constexpr int PIN_LED_QUANTITY = -1;
constexpr int PIN_LED_PENDING = -1;
constexpr int PIN_SETUP = 9;
#elif QC_BOARD_PROFILE == 5
#if !defined(CONFIG_IDF_TARGET_ESP32C3)
#error "Pin profile does not match the selected chip."
#endif
constexpr char BOARD_PROFILE_NAME[] = "esp32c3-touch";
constexpr bool KEYPAD_AVAILABLE=false, TOUCH_AVAILABLE=true;
constexpr char BOARD_CHIP_NAME[] = "esp32c3";
constexpr uint8_t ROW_PINS[4] = {0,0,0,0};
constexpr uint8_t COL_PINS[4] = {0,0,0,0};
constexpr int PIN_TOUCH_SCL = 0;
constexpr int PIN_TOUCH_SDO = 1;
constexpr int PIN_BUZZER = 3;
constexpr int PIN_LED_WIFI = 5;
constexpr int PIN_LED_ERROR = 6;
constexpr int PIN_LED_ACK = 4;
constexpr int PIN_LED_QUANTITY = 7;
constexpr int PIN_LED_PENDING = 10;
constexpr int PIN_SETUP = 9;
#elif QC_BOARD_PROFILE == 6
#if !defined(CONFIG_IDF_TARGET_ESP32C6)
#error "Pin profile does not match the selected chip."
#endif
constexpr char BOARD_PROFILE_NAME[] = "esp32c6-generic";
constexpr bool KEYPAD_AVAILABLE=true, TOUCH_AVAILABLE=true;
constexpr char BOARD_CHIP_NAME[] = "esp32c6";
constexpr uint8_t ROW_PINS[4] = {0,1,2,3};
constexpr uint8_t COL_PINS[4] = {6,7,18,19};
constexpr int PIN_TOUCH_SCL = 20;
constexpr int PIN_TOUCH_SDO = 21;
constexpr int PIN_BUZZER = 22;
constexpr int PIN_LED_WIFI = -1;
constexpr int PIN_LED_ERROR = 23;
constexpr int PIN_LED_ACK = -1;
constexpr int PIN_LED_QUANTITY = -1;
constexpr int PIN_LED_PENDING = -1;
constexpr int PIN_SETUP = 9;
#else
#error "Unknown QC_BOARD_PROFILE."
#endif
