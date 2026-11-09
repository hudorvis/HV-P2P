#pragma once

#define HV_PDM_FIRMWARE_VERSION "v26.11.09.02"

void startPdmOta();
void servicePdmOtaConsole();
const char* pdmOtaPhase();
unsigned pdmOtaPercent();
