# HV P2P v26.10.05.07 change summary

Date: 2026-10-05

Authoritative lineage: `HV P2P v26.10.05.06 - GitHub Ready Source.zip` -> this bench-reliability revision.

## 1. CTRL-TS final reboot convergence

- CTRL no longer treats the final `REBOOT` ACK as proof that CTRL-TS actually restarted.
- A new `HMI_FW_WAIT_REBOOT_CONFIRM` phase keeps the transaction open until CTRL receives a fresh CTRL-TS `HELLO_RESP` with a **different `boot_id`** and the exact required firmware version/SHA-256.
- While confirmation is pending, CTRL performs bounded reboot enforcement and keeps soliciting identity. An ACK only confirms command receipt.
- CTRL-TS retains its verified-image autonomous reboot fallback and services it from the headless updater loop.
- This specifically hardens upgrades from older `safe_ota=2` touchscreen firmware whose final reboot behavior may be less reliable.

## 2. CTRL-TS travel layout

- AUX tiles are reduced slightly in height and the travel panel is increased from 91 px to 100 px.
- Near/Far readouts, REF, travel line/current skate marker, triangular ramp zones and preset labels now use separate vertical lanes.
- Preset labels alternate between dedicated upper/lower lanes and no longer share the Near/Far value row.
- The minimum operator font remains Montserrat 10; no smaller touchscreen font was introduced.

## 3. SRVR Settings wording

- Settings -> CTRL-TS subheading is now `Link`, matching the CTRL and W1P sections.
- Project validation was updated so the old `CTRL-TS Link` wording cannot silently return.

## 4. Calibration placeholders, Cancel and transactional limits

- Uncaptured CTRL-TS Joystick and Limit calibration values now render as ASCII `-`, avoiding the missing-glyph rectangle from the compiled LVGL font.
- CTRL-TS has a dedicated `Cancel` control for calibration overlays.
- `CAL_CANCEL` is carried through the existing acknowledged/retried CTRL-TS EVENT path, translated by CTRL into a new non-conflicting A7 flag, and edge-captured by SRVR.
- Joystick Calibration cancel discards only staged Left/Centre/Right samples and retains the saved calibration.
- Limit Calibration is now transactional: Near/Far/Ref captures and any auto-detected Winch Invert change remain staged until the final Ref confirmation. Near/Far no longer partially overwrite live limits or save configuration mid-wizard.
- Cancel stops commanded motion, applies the neutral-return interlock, exits calibration/service ownership, clears staged captures and retains the previous valid calibration/configuration.

## 5. False transient red/E-stop state

- W1P STATUS parsing is now validate-before-commit. Missing fields, invalid 0/1 safety tokens, invalid RS485/config enums and non-finite numeric values are rejected without erasing the previous complete safety snapshot.
- The previous snapshot still expires normally through `WINCH_STATUS_TIMEOUT_S`; a genuinely stale W1P remains fail-safe.
- `PONG` is treated as Ethernet liveness only and no longer invalidates the last good W1P STATUS.
- Rejected STATUS frames are counted/logged so future bench faults identify their source instead of appearing only as a brief red flash.

## 6. SRVR background reliability on macOS

- CTRL peer liveness is no longer dependent on the Qt/QML timer. A dedicated SRVR communications worker sends `SRVR_ALIVE` every 250 ms while CTRL retains its existing 750 ms peer timeout.
- Graceful shutdown still sends explicit `SRVR_OFFLINE`; the liveness worker is stopped before that final offline transmission so background keepalives cannot resurrect a closed SRVR session.
- Non-zero W1P VEL retains the normal ~150 ms SRVR cadence. A short worker-side refresh lease can bridge a missed Qt scheduling interval while motion is active, but expires quickly so W1P's independent 500 ms watchdog remains authoritative if SRVR control production actually stops.

## 7. Random stops during Limit Calibration

- The post-stop joystick-neutral interlock is intentionally preserved.
- The underlying false-stop paths are addressed instead: malformed W1P STATUS no longer creates an instantaneous safety fault, and brief GUI scheduling stalls can no longer immediately starve the non-zero VEL refresh.
- W1P service mode continues to bypass the normal software limit envelope during Limit Calibration at the existing reduced service speed; W1P's independent 500 ms VEL watchdog remains unchanged.

## Verification

- Added `tools/test_bench_regression_0507.py` and extended PySide backend regression coverage for the new transactional/status behavior.
- Complete source/static/regression/preflight suite passes locally.
- PySide6 runtime tests remain a GitHub Actions gate in environments where PySide6 is installed.
- Native ESP32 and frozen desktop compilation remain GitHub Actions authoritative. No locally fabricated firmware binaries are included.
