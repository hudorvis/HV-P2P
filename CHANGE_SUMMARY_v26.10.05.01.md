# HV P2P v26.10.05.01 change summary

Date: 2026-10-05

Authoritative lineage: `HV P2P v26.10.04.07 - GitHub Ready Source.zip` -> this October 5 bench-correction release.

## 1. Firmware update sequencing and CTRL progress

A fresh SRVR could previously move the CTRL-TS into firmware UI/self-update before the operator saw the expected CTRL update phase. A second failure mode existed inside CTRL: the blocking SRVR-authority download could begin with an HMI POLL/EVENT transaction still outstanding. The progress callback correctly refused to transmit RS485 firmware status while that transaction was outstanding, but the blocking download no longer serviced the response, suppressing CTRL progress for the whole transfer.

`.05.01` adds an explicit CTRL authority-update-pending state. CTRL first quiesces the normal HMI transaction, stops starting new HELLO/POLL work, waits until the outstanding transaction/recovery window is clear, and only then begins its blocking authority download. CTRL progress can therefore use the otherwise-idle RS485 bus and is also reported to SRVR.

SRVR now coordinates the update order: CTRL must be current/fresh before W1P authority is advertised, and CTRL-TS is not allowed to start until CTRL is current and W1P has either converged or had a short discovery window when absent. The legacy browser-push bridge is restricted to genuinely old pre-authority firmware (`<= 26.10.01.01`) so modern nodes use the verified SRVR authority path.

The safe CTRL-TS self-flash boundary is unchanged: the physical panel can show CTRL/W1P progress and a final `Preparing safe updater - SRVR shows self-flash progress` handoff, but it is intentionally black while programming its own application partition. SRVR remains the exact progress display during that phase.

## 2. Canonical SRVR/CTRL-TS system status

SRVR is now the sole authority for the main system status vocabulary:

- `System | Active` — green
- `System | Uncalibrated` — yellow
- `System | Battery Change Mode` — yellow
- `System | Joystick Calibration` — yellow
- `System | Limit Calibration` — yellow
- `System | Winch Calibration` — yellow
- `E-Stop | <source>` — red

The pipe-delimited wire protocol still escapes `|` as `/`, but CTRL-TS normalizes the safe wire spelling back to the canonical on-screen form. The status field allowance was enlarged so the longer calibration/Battery Change descriptions cannot be truncated.

A concrete flicker bug was removed: HMG1 geometry packets and the new HMM1 motion packets are display-data-only and cannot run the "no status field => Active" fallback. This prevents geometry traffic from alternating an uncalibrated yellow banner with a false green Active state.

## 3. Smoother CTRL-TS live motion without saturating RS485

The CTRL-TS position/speed readouts previously depended mostly on the ~900-byte bulk HMI frame, capped at 4 Hz for bus safety. That made the marker visibly jump 2-4 times per second even though SRVR was smooth.

`.05.01` adds compact `HMM1` verified motion updates containing only position, normalized fraction, signed To Near/To Far and speed. CTRL sends them at an 80 ms minimum interval with a 250 ms keepalive. CTRL-TS uses a short 90 ms linear marker animation only between received samples; it does not extrapolate beyond measured data. Bulk telemetry remains at 4 Hz and the single-flight POLL/EVENT arbiter is unchanged.

## 4. CTRL-TS readability

Preset labels are now Montserrat 10, matching the smallest approved `Drive Mode` / `Acceleration Mode` text. Near/Far labels and units are kept at the same minimum readable size; larger numeric distance values remain larger.

## 5. Limit Calibration visual repair

The requested three-step Limit Calibration remains `Set Near -> Set Far -> Set Ref & Done` and uses the same 720x540 wizard structure as Joystick Calibration. The previous compact Side View was forced into a 64 px-high viewport, which distorted the cable slope and cropped most of both tower icons.

The calibration cable viewport is now 84 px high. Compact `SpanDiagram` reserves a dedicated top label/tower band, scales the tower geometry fully inside the viewport and uses the live/captured Near/Ref/Far state without clipping the cable graph. The three Near/Ref/Far value boxes and live current-position feedback remain part of the wizard.

## 6. Deep communications alignment audit

The pass rechecked SRVR -> CTRL -> CTRL-TS ownership and found/locked these rules:

- HMS1 is priority state/status/configuration.
- HMG1 is change-driven geometry (limits, ramp fractions, Ref and presets) and cannot mutate status.
- HMM1 is compact verified live motion and cannot mutate status.
- HMI1 remains the large 4 Hz dashboard snapshot.
- Exactly one RS485 transaction may own the half-duplex bus at a time.
- Firmware transfer remains exclusive.
- AUX EVENT ACK/retry and fixed-queue behavior remain unchanged.
- CTRL-TS caches latest runtime packets while firmware UI owns the panel and replays them when normal UI returns.

## Preserved safety/control architecture

- W1P independent 500 ms VEL freshness watchdog.
- SRVR non-zero VEL refresh approximately 150 ms.
- AI0 physical E-stop / AI1 joystick mapping.
- Hard limits, predictive stopping/dynamic soft limits and Leadshine velocity mode.
- Battery Change service behavior and Limit Calibration completion forcing Battery Change Off.
- Immediate CTRL-TS Waiting/Splash response to a normal SRVR shutdown.

## Verification

The complete source/static/preflight suite passes from the final `v26.10.05.01` layout, including 370 EdgeBox integration checks, RS485/update/AUX contracts, the new October 5 bench regression, 53 build-pipeline checks, release consistency, source hygiene, Python syntax and SRVR preflight. GitHub Actions remains authoritative for PySide6 runtime execution, native ESP32 compilation and frozen desktop builds.
