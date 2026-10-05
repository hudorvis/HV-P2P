# HV P2P v26.10.05.09 change summary

Date: 2026-10-05

Authoritative lineage: `HV P2P v26.10.05.06.zip` -> `v26.10.05.09`.

This revision was rebuilt from the supplied `.05.06` source after the intermediate
`.05.07`/`.05.08` GitHub builds exposed a C++ scope error. The `.05.08` firmware-
carrier experiment has been removed; the original `.05.06` native embed/build
architecture is retained.

## Requested bench fixes

- **CTRL-TS final reboot:** CTRL now distinguishes `REBOOT received` from `reboot
  completed`. After ACK it enters `HMI_FW_WAIT_REBOOT_CONFIRM`, continues bounded
  reboot enforcement and HELLO discovery, and accepts completion only when the
  exact target version/SHA is running. A changed `boot_id` is required when the
  previous peer supplied one; a legacy peer with no pre-update `boot_id` can prove
  reboot by exact target identity.
- **CTRL-TS travel layout:** AUX height reduced from 83 to 74 px and travel height
  increased from 91 to 100 px. Endpoint readouts, REF, track/skate, ramps and
  Preset labels occupy separate lanes. No font below Montserrat 10 is introduced.
- **Settings heading:** `CTRL-TS Link` is renamed to `Link` and validators now lock
  the requested wording.
- **Calibration:** missing values use ASCII `-`; both touchscreen calibration
  overlays include Cancel; Cancel uses the retry-safe EVENT path. Limit Calibration
  stages Near/Far/Ref and motor-direction inference and commits them together only
  after Ref. Cancel does not partially overwrite existing calibration.
- **Transient red state:** W1P telemetry is validate-before-commit. Invalid or
  incomplete STATUS samples are rejected/logged without deleting the last complete
  fresh snapshot. PONG is liveness-only and no longer clears W1P authority.
- **Background macOS operation:** CTRL peer liveness is serviced by a dedicated
  SRVR background worker (`SRVR_ALIVE`) rather than relying solely on the Qt timer.
  Explicit `SRVR_OFFLINE` remains authoritative on clean shutdown.
- **Random calibration stops:** false transient safety interruptions no longer
  repeatedly invoke the intentional joystick-neutral re-arm latch. A short leased
  worker-side VEL bridge covers an occasional missed GUI refresh while preserving
  the normal ~150 ms SRVR cadence and the unchanged 500 ms W1P watchdog.

## GitHub compile fix

GitHub `.05.08` reported:

`error: 'newBootId' was not declared in this scope`

The variable had been declared inside a nested reset-reason block and then used by
post-reboot identity arbitration later in `handleHmiFrame()`. `.05.09` declares it
at HELLO_RESP scope and adds a regression that forbids the old nested declaration.

## Preserved architecture

No functional change is made to W1P firmware beyond the release identity. AI0/AI1,
Leadshine Modbus velocity control, W1P 500 ms watchdog, hard-limit/predictive-limit
logic, CTRL-TS single-flight RS485 scheduling, AUX ownership, Battery Change Mode,
Virtual Position Source physical inhibition, canonical status wording and signed
wire velocity are preserved.

## Verification

The final source/static/regression/preflight suite passes. Native Arduino and frozen
desktop compilation remain GitHub Actions gates; no local firmware binaries are
included in this source package.
