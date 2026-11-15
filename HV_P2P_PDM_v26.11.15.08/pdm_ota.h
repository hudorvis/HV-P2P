#pragma once

#include <IPAddress.h>

#define HV_PDM_FIRMWARE_VERSION "v26.11.15.08"

void startPdmOta();
void servicePdmOtaConsole();
bool requestPdmOta(const IPAddress& peer, const IPAddress& local);
bool pdmOtaCheckSupported();
const char* pdmOtaPhase();
unsigned pdmOtaPercent();
IPAddress pdmOtaAuthorityIp();
uint16_t pdmOtaAuthorityPort();
