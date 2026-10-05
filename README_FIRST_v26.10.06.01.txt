HV P2P v26.10.06.01 - READ THIS FIRST

PRIMARY PURPOSE OF THIS REVISION
--------------------------------
Correct the GitHub desktop regression test failure in v26.10.05.11 without
changing the production firmware-update behavior that .05.11 introduced.

EXACT GITHUB FAILURE
--------------------
backend.py imported correctly.  tools.test_backend_logic then replaced the real
W1PClient with FakeW1P for protocol-emission testing.  Production .05.11 added
W1PClient.firmware_snapshot() for background firmware ordering, but FakeW1P did
not implement it.  _ctrl_ts_update_allowed() therefore raised:

AttributeError: 'FakeW1P' object has no attribute 'firmware_snapshot'

WHAT v26.10.06.01 CHANGES
-------------------------
1. FakeW1P now mirrors the production firmware snapshot interface and supplies
   a current/matched four-field snapshot for its unrelated protocol test block.
2. A new source-level AST contract checks FakeW1P interface parity before the
   PySide desktop jobs run.
3. The new contract is included in run_all_source_checks.py.
4. Release/date metadata advances to v26.10.06.01 / 6 October 2026.

WHAT THIS REVISION DOES NOT CHANGE
----------------------------------
It does not add another production updater workaround for a test-harness error.
The .05.11 runtime updater/coordinator changes are retained unchanged apart from
normal version identity:

- background release discovery independent of Qt/window focus;
- CTRL -> W1P -> CTRL-TS firmware ordering;
- W1P network-thread firmware STATUS/FW_PROGRESS snapshot;
- new-SRVR-session exact manifest/SHA re-verification;
- graceful SRVR_OFFLINE ordering;
- CTRL-TS final reboot proof and legacy safe-updater convergence.

PRESERVED SAFETY / CONTROL CONTRACTS
------------------------------------
- W1P independent 500 ms VEL watchdog remains unchanged.
- Normal SRVR non-zero VEL refresh remains approximately 150 ms.
- AI0 E-stop / AI1 joystick mapping is unchanged.
- Joystick-neutral re-arm, Leadshine velocity architecture, hard limits and
  predictive/dynamic limits are unchanged.
- CTRL <-> CTRL-TS isolated half-duplex RS485 remains single-flight/serialized
  with EVENT ACK/retry handling.
- CTRL-TS remains black/headless only while writing its own flash.

VERIFICATION STATUS
-------------------
All source/static/regression/preflight checks available in this environment pass:
370 EdgeBox integration checks, all earlier bench/update regressions, the new
backend test-double contract, 53 build-pipeline checks, release/source hygiene,
55 Python files syntax checked and SRVR preflight.

PySide6 is not installed in this source-audit environment, so the actual PySide
runtime test remains an authoritative GitHub desktop-build gate. Native ESP32
compilation also remains a GitHub Actions gate. No locally fabricated firmware
binaries are included.
