# HV P2P Revision History

- **v26.08.31.01 - v26.09.04.03** — commissioning, safety, locked Run/Setup UI,
  Virtual Position Source, Speed/Power semantics and cross-platform native-build
  baseline. v26.09.04.03 is the surviving user-uploaded source used as the base
  for the current reconstruction.
- **v26.09.14.x - v26.09.15.02** — SRVR-authoritative CTRL/W1P automatic OTA,
  exact SHA/identity verification, stale W1P session fail-closed handling,
  explicit Nuitka firmware data inclusion and non-dirty native-build pipeline.
- **v26.09.17.01 - v26.09.17.02** — CTRL <-> CTRL-TS RS485 updater hardening:
  larger UART buffers, smaller blocks, conservative turnaround, bounded retries,
  idempotent update completion/reboot, startup servicing, reconnect refresh and
  corrected splash aspect/orientation rendering.
- **v26.09.20.01** — W1P <-> Leadshine hardening: 2.0 ms Modbus inter-frame
  margin, bounded no-response configuration sweep and safe read-only 38400/8N2
  factory-framing diagnostic.
- **v26.09.27.01** — current reconstructed release. The generated v26.09.20.01
  attachment expired and its exact bytes were unavailable, so its later change
  contracts were reconstructed on the surviving v26.09.04.03 source and audited
  again under a new version identity. Locked Run/Setup QML remains unchanged.
