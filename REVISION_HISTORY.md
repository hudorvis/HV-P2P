
## v26.09.29.02
- EdgeBox Arduino/GitHub partition-option compatibility hotfix.
- EdgeBox board has no visible Custom partition menu; native build now selects the supported 16M 3MB APP/9.9MB FATFS option while the sketch-local `partitions.csv` supplies the actual project dual-OTA layout.
- Supersedes v26.09.29.01 before deployment.

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
- **v26.09.29.02** — closes audit/bench defects found in v26.09.27.01: W1P STATUS
  field mismatch, stale PR0 trigger possibility, Modbus write exceptions,
  duplicate RS485 failure counting, best-effort stop gating, CTRL-TS session/
  sequence/stale-identity handling, stable graphical firmware progress,
  headless display recovery, full-height 800x480 Run fit and EdgeBox
  partition-menu compatibility while retaining the sketch-local dual-OTA layout.
