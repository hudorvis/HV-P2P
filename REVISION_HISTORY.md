# v26.09.29.04
- Final CTRL analogue-input mapping: AI0/pin 14 = 5 V normally-closed E-stop status; AI1/pin 16 = APEM joystick signal.
- SGM58031 continuous joystick channel and temporary E-stop sampling channel swapped accordingly; diagnostics/docs/tests updated.
- Otherwise functionally identical to v26.09.29.03.

## v26.09.29.04
- CTRL AI1 changed to a 5 V normally-closed E-stop status input for the commissioned voltage-input EdgeBox hardware.
- Joystick sampling upgraded to 8-sample trimmed-mean plus the existing light IIR filter.
- SRVR CTRL Setup adds calibrated Current Percentage; new/reset joystick Direction defaults Inverted.
- W1P VEL freshness watchdog reduced to 500 ms and SRVR non-zero VEL refresh tightened to 150 ms.
- Retains the v26.09.29.02 EdgeBox partition-menu hotfix and all v26.09.29.01 audit/bench corrections.

# HV P2P Revision History

- **v26.08.31.01 - v26.09.04.03** — EdgeBox transition, commissioning/safety,
  locked Run/Setup UI, Virtual Position Source and cross-platform native-build
  baseline.
- **v26.09.14.x - v26.09.15.02** — SRVR-authoritative CTRL/W1P automatic OTA,
  exact SHA/identity verification, stale W1P session fail-closed handling and
  non-dirty native-build pipeline.
- **v26.09.17.01 - v26.09.17.02** — CTRL <-> CTRL-TS RS485 updater hardening:
  4096-byte UART buffers, 1024-byte blocks, conservative turnaround, bounded
  retries/idempotence, startup servicing and splash aspect/orientation handling.
- **v26.09.20.01 - v26.09.27.01** — W1P <-> Leadshine commissioning hardening,
  2.0 ms Modbus inter-frame margin, 38400 8N2 read-only factory-comms diagnostic,
  650 ms velocity freshness watchdog, OTA/service safety gates and continued
  CTRL-TS automatic convergence. **v26.09.27.01 is the authoritative direct
  source baseline for the present release.**
- **v26.09.29.04** — closes audit/bench defects found in v26.09.27.01: W1P STATUS
  field mismatch, stale PR0 trigger possibility, Modbus write exceptions,
  duplicate RS485 failure counting, best-effort stop gating, CTRL-TS session/
  sequence/stale-identity handling, stable graphical firmware progress,
  headless display recovery, full-height 800x480 Run fit and EdgeBox
  partition-menu compatibility while retaining the sketch-local dual-OTA layout.
