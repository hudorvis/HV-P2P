#pragma once

#define HV_PDM_FIRMWARE_VERSION "v26.11.12.02"

void startPdmOta();
void servicePdmOtaConsole();
const char* pdmOtaPhase();
unsigned pdmOtaPercent();
