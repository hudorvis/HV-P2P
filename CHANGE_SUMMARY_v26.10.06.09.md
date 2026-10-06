# HV P2P v26.10.06.09 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.08`.

This is a CI/test-fixture hotfix only. Production behavior is locked to `.06.08`; after normalising release identity, CTRL, W1P, CTRL-TS, SRVR backend, QML and firmware-authority sources are unchanged.

## GitHub failure corrected

The Windows PySide runtime job imported `backend.py` successfully, then failed in `tools.test_backend_logic` while asserting the operator E-stop banner. The test expected `E-Stop | CTRL` but the backend correctly returned `E-Stop | CTRL & W1P`.

The fixture only set `w1p.last_seen` and `winch_rs_status = Connected`; that is not sufficient to establish a healthy W1P under the current fail-safe resolver, which also checks validated STATUS freshness, firmware authority/match and internal watchdog/service-safety state. Earlier runtime tests could therefore leave W1P intentionally unsafe and contaminate the later CTRL-only assertion.

`.06.09` fixes the fixture, not production safety logic:

- explicitly establishes fully healthy validated CTRL and W1P snapshots before the connection-loss banner test;
- simulates CTRL-only loss from that healthy baseline;
- explicitly restores healthy CTRL before simulating W1P-only loss;
- then simulates both links lost;
- adds `tools/test_estop_banner_fixture_contract_0609.py` so this exact dirty-fixture pattern is caught in the source/static suite before PySide desktop jobs.

## Locked behavior preserved

All `.06.08` production behavior is unchanged: automatic update/recovery, CTRL-TS display interpolation, persistent Ramping status, calibration/AUX behavior, W1P Encoder/Leadshine path, 500 ms W1P VEL watchdog, ~150 ms SRVR non-zero VEL refresh, limits and safety arbitration.

## Verification

The complete source/static regression runner reaches `ALL_SOURCE_CHECKS_PASS`, including 370 EdgeBox integration checks, every historical updater/RS485/calibration/motion regression, `.06.08`, the new `.06.09` fixture contract, 53 build-pipeline checks, release consistency, source hygiene, Python syntax and SRVR preflight.

PySide6 is not installed in the local source-audit environment, so the exact PySide runtime remains an authoritative GitHub desktop CI gate. Native ESP32 and frozen desktop compilation also remain GitHub Actions gates.
