#pragma once
#include <Arduino.h>

// HV P2P v26.08.31.01 BUILD GUARD
// ---------------------------------
// This file is intentionally NOT a flashable placeholder. The commissioning
// build pipeline MUST replace it with the generated header produced from the
// real, natively compiled CTRL-TS application .bin before CTRL is compiled.
// Keeping the build blocked here prevents an incomplete CTRL firmware from
// ever being mistaken for a production/commissioning image.
#error "CTRL-TS firmware image has not been staged. Build CTRL-TS first, then run tools/embed_ctrl_ts_firmware.py (or the supplied GitHub Actions firmware workflow) before compiling CTRL."
