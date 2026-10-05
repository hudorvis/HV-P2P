# HV P2P v26.10.05.08 native-build and bench checklist

## Native GitHub build gate

1. Upload the complete `.05.08` source to the GitHub Actions repository.
2. Require `tools/native_build_firmware.py` to complete CTRL-TS -> generated carrier -> CTRL -> W1P in that order.
3. Confirm the log reports a small carrier metadata header plus the generated carrier/native-image sizes before CTRL compilation.
4. Require the `HV-P2P-v26.10.05.08-Native-Firmware` artifact and all desktop artifacts to be produced.
5. Treat GitHub Actions binaries as authoritative; do not substitute locally fabricated firmware.

## `.05.07` functional regression checks retained

- Start SRVR with CTRL/W1P/CTRL-TS on the previous release and confirm automatic update order CTRL -> W1P -> CTRL-TS.
- Confirm CTRL-TS leaves its black safe-updater screen automatically. A REBOOT ACK alone must not complete the transaction; CTRL must see a new boot ID and exact target identity.
- Confirm Near/Far distances, REF, skate/ramp zones and Preset Position names are all readable with no vertical overlap.
- Confirm Settings -> CTRL-TS shows `Link`.
- In Joystick and Limit Calibration, uncaptured fields show `-`, not a replacement-glyph box.
- Cancel Joystick Calibration at each step and verify no pending values commit.
- Cancel Limit Calibration after Near and after Far; verify the previous valid Near/Far/Ref, span and Winch Invert remain unchanged and service ownership is released safely.
- During Limit Calibration, move repeatedly toward Far and verify no unexplained stop/neutral-reset occurs under healthy communications.
- Put SRVR behind other macOS applications for an extended period while monitoring CTRL-TS. Verify no false lost-SRVR red/E-stop flash occurs while the SRVR process/network worker remains healthy.
- Create a genuine CTRL/W1P/E-stop/link failure and confirm red status still takes priority and motion still requires joystick neutral before re-arm.

## Watchdog/timing acceptance

- W1P non-zero VEL freshness watchdog remains exactly 500 ms.
- Ordinary SRVR non-zero VEL refresh remains approximately 150 ms.
- Background bridge traffic must stop when its short producer lease expires, leaving W1P's watchdog authoritative.
- CTRL-TS HMI EVENT handling remains single-flight/serialized with ACK/retry semantics.

## Release gate

- Complete source/static/regression/preflight suite passes.
- PySide6 backend logic passes in desktop CI.
- Native ESP32 compilation passes in GitHub Actions.
- macOS Intel, macOS Apple Silicon and Windows x64 SRVR build/smoke tests pass.
