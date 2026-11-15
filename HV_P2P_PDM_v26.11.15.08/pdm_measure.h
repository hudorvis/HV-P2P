#pragma once

#include <Arduino.h>

bool startSampler(uint32_t periodMs);
void setSamplePeriod(uint32_t periodMs);
uint32_t missedSampleSlots();
