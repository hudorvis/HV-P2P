# HV P2P v26.10.05.11 change summary

Date: 2026-10-05

Authoritative lineage: user-supplied `v26.10.05.06` -> reviewed `.05.09` -> `.05.10` -> `.05.11`.

## Primary fix — automatic firmware convergence no longer depends on the Qt UI timer

Bench symptom in `.05.10`:

- Opening the new SRVR did not visibly start the normal automatic firmware update.
- Manually rebooting CTRL caused CTRL to discover and install `.05.10`.
- CTRL-TS could remain on `.05.09`, even after a manual touchscreen reboot.

The `.05.09 -> .05.10` diff confirmed that CTRL, W1P, CTRL-TS and `firmware_authority.py` update logic had not changed. The regression was a latent coordinator timing defect exposed by the next normal release change.

`.05.09` had correctly moved `SRVR_ALIVE` into a background networking worker so macOS window/background scheduling could not falsely disconnect CTRL. However, the lightweight `SRVR_FW` release beacon and the firmware-order / `ts_allowed` coordinator grant were still emitted only by SRVR's 25 ms Qt `_tick()` callback. A delayed or deprioritised Qt event loop could therefore keep CTRL looking connected while never telling it that a newer release existed.

A manual CTRL reboot appeared to fix the problem because CTRL's boot-time firmware-authority manifest fetch is independent of the Qt timer. CTRL-TS could still stay old because its final-stage grant was also tied to the Qt-driven coordinator traffic.

### `.05.11` correction

- The existing background SRVR communications worker now owns both:
  - `SRVR_ALIVE` every ~250 ms; and
  - lightweight CTRL/W1P firmware-authority beacons every 500 ms.
- The Qt `_tick()` no longer owns release discovery or update-order beacons.
- No HTTP download, flash operation or motion decision was moved into the SRVR background worker. CTRL and W1P still perform their own fail-closed manifest/SHA verification and OTA staging.
- This makes automatic release discovery independent of window focus, QML rendering load and Qt timer scheduling.

## Firmware update ordering hardened

Firmware order remains **CTRL -> W1P -> CTRL-TS**.

- W1P firmware/version/authority state is now captured directly in the W1P network thread from complete STATUS packets **and W1P `FW_PROGRESS` packets**, rather than requiring Qt to drain the W1P receive queue before the final CTRL-TS gate can advance. Progress packets keep the coordinator positively informed while W1P's blocking OTA download temporarily pauses normal STATUS output.
- After CTRL has exactly matched the running SRVR release for at least one second, the coordinator gives W1P a bounded 3-second discovery window before considering it genuinely absent. This prevents a healthy W1P from being skipped simply because its first STATUS arrived slightly later than CTRL's reboot.
- If a participating W1P enters OTA and temporarily disappears, the final touchscreen stage remains held through its normal reboot. A bounded 15-second absence timeout prevents a failed/physically absent W1P from stranding CTRL-TS forever.

## Fresh SRVR sessions now force exact authority re-verification

The architecture already generated a unique firmware-authority session token for every SRVR process, but CTRL and W1P did not fully enforce that boundary when the version string itself was unchanged.

`.05.11` now makes a new SRVR process/session fail closed once and re-verify the immutable manifest plus running-image SHA on CTRL and W1P. If the image is already exact, it is accepted without re-flashing. If the same version string carries a different SHA, the exact SRVR image is required.

This prevents a stale prior-SRVR-session `FW_MATCH=1` state from being inherited indefinitely.

## Graceful shutdown ordering hardened

A deep concurrency audit found a small race in the new background architecture: a firmware beacon worker already waiting on the CTRL TX lock could theoretically transmit one `SRVR_FW` after graceful `SRVR_OFFLINE`.

`.05.11` re-checks `_stop_evt` while holding the same TX lock used by `SRVR_OFFLINE`, so the explicit offline packet is guaranteed to be the final CTRL presence/coordinator packet. W1P firmware beacons also stop immediately once shutdown begins.

## Preserved `.05.10` bench fixes

- Limit Calibration Current Winch Position re-zeros to the staged Near point and shows travel toward Far without prematurely committing the calibration.
- Run -> Shortcuts -> System controls fit inside the tab using the same 31 px control height as the Limits controls.
- `Drive Mode | Practice Mode` is transmitted intact to CTRL-TS; the SRVR AUX field is no longer truncated at 24 characters.

## Preserved safety/control contracts

- W1P independent non-zero VEL freshness watchdog remains **500 ms**.
- Normal SRVR non-zero VEL refresh remains approximately **150 ms**.
- The bounded background VEL bridge remains a short producer-lease bridge only; it cannot defeat the W1P watchdog.
- AI0 E-stop / AI1 joystick mapping is unchanged.
- Joystick-neutral re-arm, hard limits, predictive stopping/dynamic soft limits and Leadshine velocity architecture are unchanged.
- CTRL <-> CTRL-TS RS485 remains isolated, half-duplex, single-flight/serialized with EVENT ACK/retry handling.
- CTRL-TS safe self-update remains headless/black while actually writing its own flash.
- REBOOT ACK remains command receipt only; update completion still requires post-reboot target identity/reboot proof.
- The approved CTRL-TS UI and `.05.10` calibration/layout changes are unchanged except for release identity.

## Verification

The complete source/static/regression/preflight suite passes after the `.05.11` changes, including:

- 370 EdgeBox integration checks;
- RS485 frame/serialization/update retry/target/transport contracts;
- all earlier bench regressions through `.05.10`;
- new `test_firmware_background_convergence_0511.py` coverage;
- firmware coordinator and final reboot convergence contracts;
- CTRL-TS safe-update and parser diagnostics contracts;
- Leadshine commissioning, Modbus, speed and motion contracts;
- firmware authority server, embed and native-build orchestration tests;
- 53 build-pipeline validation checks;
- release consistency and source hygiene;
- Python syntax across 54 files; and
- SRVR project preflight.

PySide6 is not installed in this source-audit environment, so the full PySide runtime suite remains a GitHub desktop-build gate. Native Arduino compilation remains the authoritative GitHub Actions firmware gate. No local firmware binaries are fabricated or included.
