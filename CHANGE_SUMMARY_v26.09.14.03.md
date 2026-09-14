# HV P2P v26.09.14.03 Change Summary

This is the corrective/deep-audit revision following the v26.09.14.02 GitHub run.

## GitHub failure corrected

The three reported desktop failures (macOS Intel, macOS Apple Silicon and Windows x64) were one shared backend regression-fixture error. `tools/test_backend_logic.py` simulated a healthy W1P with a legacy STATUS packet that omitted the new `FW_MATCH` field. Since v26.09.14.01 intentionally treats missing `FW_MATCH` as fail-closed, the backend correctly asserted the W1P firmware-authority safety source and the old test expectation was wrong.

The healthy fixture now explicitly reports `FW_MATCH=1` / `FW_AUTH=matched`, while a separate regression proves that an omitted `FW_MATCH` remains fail-closed. The healthy fixture also supplies the full RS485/feedback-good field set so firmware-authority behavior is isolated from unrelated feedback faults.

## Additional deep-audit safety corrections

The audit found a stale-session edge case in SRVR's W1P receive path. W1P peer connectivity can be refreshed by HELLO/PONG/diagnostic traffic, whereas firmware-authority and drive health are only trustworthy from a full STATUS packet. v26.09.14.03 therefore:

- tracks full W1P STATUS freshness independently of generic peer traffic;
- invalidates previous firmware-authority and RS485-good state immediately on a new-session `HELLO`;
- requires a fresh full STATUS before SRVR motion safety or the RS485-ready property can consider W1P healthy;
- parses STATUS fail-closed: prior authority/RS485 health is invalidated first and STATUS freshness is committed only after the complete safety-critical parse succeeds;
- rejects malformed STATUS without allowing stale matched/RS485-good state to survive.

These changes strengthen SRVR-side safety only; they do not relax any W1P-local protection.

## Earlier native compile fix retained

The v26.09.14.02 Arduino ESP32 `Print.h` macro collision remains fixed: the shared CTRL/W1P authority SHA helper uses `HEX_DIGITS`, never a local symbol named `HEX`.

## CI hardening

- A Qt-independent backend regression harness is now included in `tools/run_all_source_checks.py`, so pure backend state-machine regressions are caught even where PySide6 is unavailable.
- The master source/backend/protocol suite now runs at the start of the firmware job, before Arduino/toolchain/library setup and before the native jobs fan out.
- A release-consistency test rejects mixed active sketch/SRVR/workflow version paths.
- The real pinned-PySide6 backend regression remains in each macOS/Windows SRVR job, so the headless gate does not replace native runtime validation.

## Preserved/locked behavior

- Approved Run tab QML: byte-identical to the locked baseline.
- Approved Setup tab QML: byte-identical to the locked baseline.
- Speed mode: unchanged W1P DYNAMIC cable-speed PI architecture.
- Power mode: unchanged TRADITIONAL behavior.
- W1P independent 650 ms VEL watchdog: preserved and hash-locked.
- W1P stopped/braked OTA service gate, Servo Enable inhibition, brake/E-stop/RS485 protections, rollback/recovery and neutral re-arm: preserved.
- No automatic downgrade of newer CTRL/W1P firmware.
- CTRL must match SRVR before CTRL->CTRL-TS firmware convergence.
- macOS Intel, macOS Apple Silicon and Windows x64 SRVR build requirements and prior Windows/Nuitka fixes remain intact.

Native ESP32 binaries and frozen SRVR applications remain GitHub Actions outputs. This source package does not fabricate them locally.
