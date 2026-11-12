#pragma once

#include <IPAddress.h>

#define HV_PDM_FIRMWARE_VERSION "v26.11.12.08"

void startPdmOta();
void servicePdmOtaConsole();
const char* pdmOtaPhase();
unsigned pdmOtaPercent();
IPAddress pdmOtaAuthorityIp();
uint16_t pdmOtaAuthorityPort();
