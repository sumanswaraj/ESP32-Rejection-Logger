#pragma once
inline bool fakeValidGPIO(int pin){return (pin>=0 && pin<=19)||(pin>=21 && pin<=23)||(pin>=25 && pin<=27)||(pin>=32 && pin<=39);}
#define GPIO_IS_VALID_GPIO(pin) fakeValidGPIO(pin)
#define GPIO_IS_VALID_OUTPUT_GPIO(pin) (fakeValidGPIO(pin) && (pin)<34)
