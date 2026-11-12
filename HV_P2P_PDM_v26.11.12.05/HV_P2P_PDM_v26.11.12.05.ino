/*
  HV P2P PDM v26.11.12.05
  Board: OLIMEX ESP32-POE-ISO. See the SYS PDM bootstrap guide.
  The ADC, SD writer and HTTP service have separate execution paths.
*/

void pdmSetup();
void pdmLoop();

void setup() { pdmSetup(); }
void loop() { pdmLoop(); }
