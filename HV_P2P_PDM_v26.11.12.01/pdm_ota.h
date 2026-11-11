#pragma once

#define HV_PDM_FIRMWARE_VERSION "v26.11.12.01"

void startPdmOta();
void servicePdmOtaConsole();
const char* pdmOtaPhase();
unsigned pdmOtaPercent();
