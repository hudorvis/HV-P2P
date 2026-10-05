# HV P2P v26.10.06.01 change summary

Date: 2026-10-06

Authoritative lineage: user-supplied `v26.10.05.06` -> reviewed `.05.09` -> `.05.10` -> `.05.11` -> `v26.10.06.01`.

## Primary correction — GitHub PySide backend regression test compatibility

The `.05.11` GitHub macOS desktop job successfully imported the real `backend.py`, then failed inside `tools.test_backend_logic` with:

`AttributeError: 'FakeW1P' object has no attribute 'firmware_snapshot'`

The production `.05.11` backend intentionally added `W1PClient.firmware_snapshot()` so CTRL -> W1P -> CTRL-TS firmware ordering can read W1P firmware state directly from the background UDP worker instead of depending on the Qt event loop. The runtime regression suite temporarily replaces the real `W1PClient` with a small `FakeW1P` while testing W1P command emission and CTRL display packets. That fake retained the older W1P interface and did not implement the new firmware snapshot method.

As soon as `_build_controller_display_packet()` evaluated `fw_ts_allowed`, `_ctrl_ts_update_allowed()` called the production `self.w1p.firmware_snapshot()` interface and the outdated test double raised before the rest of the desktop build could continue.

### v26.10.06.01 fix

- `FakeW1P` now implements the same four-field firmware snapshot contract used by `W1PClient`: `(version, match, authority, snapshot_time)`.
- The fake advertises the current test release as `matched`, because the surrounding regression block is testing DSP/AUX and W1P command transport rather than the updater-denial path.
- A new source-level test, `test_backend_test_double_contract_0601.py`, parses the PySide runtime test and requires the W1P firmware-order interface to exist on `FakeW1P` whenever production backend code calls it.
- The new contract is included in `run_all_source_checks.py`, so this class of mismatch is caught in the Ubuntu source/protocol job before the macOS/Windows PySide jobs.

## Production updater behavior preserved from v26.10.05.11

No updater state-machine workaround was added for this CI failure. The production CTRL/W1P/CTRL-TS/SRVR firmware-coordinator behavior from `.05.11` is carried forward unchanged apart from release identity, including:

- background `SRVR_ALIVE` and firmware/coordinator beacons independent of the Qt UI timer;
- W1P firmware snapshot/order tracking in the W1P network thread, including `FW_PROGRESS` while ordinary STATUS pauses during OTA;
- firmware update order **CTRL -> W1P -> CTRL-TS**;
- bounded W1P discovery and absence handling;
- new-SRVR-session manifest/SHA re-verification;
- graceful shutdown ordering that prevents a late firmware beacon after `SRVR_OFFLINE`;
- CTRL-TS final reboot proof rather than treating REBOOT ACK as update completion;
- legacy CTRL-TS safe-updater convergence support;
- transactional Limit Calibration and calibration Cancel/rollback;
- W1P validate-before-commit safety STATUS arbitration;
- macOS-background liveness and bounded VEL-refresh hardening.

## Preserved v26.10.05.10 bench fixes

- Limit Calibration Current Winch Position re-zeros to the staged Near point and reports travel toward Far without committing the new calibration early.
- Run -> Shortcuts -> System controls fit within the panel using the same 31 px control height as the Limits controls.
- `Drive Mode | Practice Mode` is transmitted intact to CTRL-TS without the previous 24-character source truncation.

## Preserved safety/control contracts

- W1P independent non-zero VEL freshness watchdog remains **500 ms**.
- Normal SRVR non-zero VEL refresh remains approximately **150 ms**.
- AI0 E-stop / AI1 joystick mapping is unchanged.
- Joystick-neutral re-arm, hard limits, predictive stopping/dynamic soft limits and Leadshine velocity architecture are unchanged.
- CTRL <-> CTRL-TS RS485 remains isolated half-duplex and single-flight/serialized with EVENT ACK/retry handling.
- CTRL-TS safe self-update remains black/headless while writing its own flash.

## Verification

The complete source/static/regression/preflight suite passes for `v26.10.06.01`, including:

- 370 EdgeBox integration checks;
- every earlier bench/update regression through `.05.11`;
- new backend test-double interface contract coverage;
- firmware authority, updater convergence, RS485 framing/serialization and target/retry contracts;
- native-build orchestration and 53 build-pipeline checks;
- Modbus, speed, motion and SRVR wire contracts;
- release consistency and source hygiene;
- Python syntax across 55 files; and
- SRVR project preflight.

PySide6 is not installed in this source-audit environment, so the full `tools.test_backend_logic` runtime remains an authoritative GitHub desktop-build gate. Native ESP32 compilation likewise remains the GitHub Actions gate. No local firmware binaries are fabricated or included.
