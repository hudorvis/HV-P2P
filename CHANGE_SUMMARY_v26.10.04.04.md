# HV P2P v26.10.04.04 change summary

Date: 2026-10-04

Authoritative lineage: `HV P2P v26.10.04.03 - GitHub Ready Source.zip` -> this `.04.04` Settings-convergence and canonical Near/Far/ramp-geometry correction.

## Settings state convergence

Battery Change Mode and Acceleration Mode remain live SRVR state, not independent Setup-only values. `.04.04` hardens the two Qt Quick ComboBoxes with explicit `Binding` objects. This avoids relying on a writable ComboBox `currentIndex` binding surviving its own user interaction. A CTRL-TS AUX change, automatic Battery Change cancellation, or any other live-state change therefore re-selects the visible Settings value from SRVR truth.

## Battery Change operation

Battery Change remains a deliberate reduced-speed service override:

- maximum requested speed is 5 km/h (1.3889 m/s);
- the normal software Near/Far ramp/predictive limit envelope is bypassed so the skate can travel outside the calibrated safe span for battery service;
- W1P receives `SERVICE_MODE=1` and independently permits that service travel;
- physical E-stop, controller/link safety, firmware authority and the independent W1P 500 ms VEL freshness watchdog remain active;
- the mode only auto-cancels after the skate has first travelled outside the saved span and then returns at least 20 mm inside it.

Distances are signed relative to the saved limits. Past Near, `To Near` is negative and `To Far` grows beyond the normal span. Past Far, `To Far` is negative and `To Near` continues increasing.

## Firmware readouts

The `.04.03` version-or-progress model is retained and rechecked:

- CTRL `Firmware`: running version normally, live phase/percentage during update;
- W1P `Firmware`: running version normally, live phase/percentage during update;
- CTRL-TS: one `Firmware` row only, using detected running version normally and update state/percentage while updating.

The safe CTRL-TS self-flash remains headless/display-off while its own flash is written; SRVR remains the exact progress display for that final phase.

## Virtual Position Source

Virtual remains an SRVR-local simulation and may be flown with W1P/Leadshine absent. It uses the real CTRL/joystick input and normal SRVR motion logic, including the same Near/Far ramp and predictive limiting. No non-zero physical W1P VEL is emitted. If a W1P is present, SRVR repeatedly holds it at `STOP` and `SW_SRVON 0`. Returning to Encoder requires the normal neutral/re-arm path.

Battery Change can also be exercised in Virtual mode to test service travel outside the saved limits without moving the real winch.

## Canonical Near/Far and ramp geometry

`.04.04` makes SRVR the single authority for every displayed ramp boundary:

- one current span = `abs(Far - Near)`;
- one effective Near ramp distance and one effective Far ramp distance, each clamped to the current span;
- one normalized Near ramp fraction and one normalized Far ramp fraction;
- Percentage and Distance are maintained as equivalent representations after ramp edits and after Near/Far limit changes.

Run Top View, Run Side View, Free-D Top View, Free-D Side View and the CTRL-TS travel bar all consume those same normalized ramp fractions. This removes independent UI-side distance-to-percentage conversions.

CTRL-TS live position, Reference and preset markers are also centred on the same exact 0–100% Near/Far coordinate used by SRVR, eliminating the previous few-pixel endpoint offset at Far.

## Verification

Added `test_limit_ramp_geometry_0404.py`. The complete source/static/preflight suite remains the release gate; native ESP32 compilation, frozen desktop runtime and powered motion remain GitHub Actions / bench gates.
