HV P2P v26.10.05.10 - READ THIS FIRST

Authoritative lineage
---------------------
This revision was rebuilt from the user-supplied `HV P2P v26.10.05.06.zip`.
Only the requested bench fixes and their regression coverage were reapplied.
The temporary .05.08 firmware-carrier redesign is NOT present.

FIXES IN THIS REVISION
----------------------
1. CTRL-TS final updater reboot
   - A REBOOT ACK no longer completes the update transaction.
   - CTRL waits for a newly booted CTRL-TS with the exact target version/SHA.
   - A changed boot_id is used when available; legacy safe-updater peers that did
     not report a pre-update boot_id may prove reboot by exact target identity.
   - Bounded REBOOT enforcement continues after ACK while HELLO discovery runs.

2. CTRL-TS travel layout
   - AUX tiles are slightly shorter and the travel panel is taller.
   - Near/Far values, REF, track/skate, ramp wedges and Preset names have separate
     vertical lanes. Montserrat 10 remains the smallest travel/preset font.

3. SRVR Settings wording
   - CTRL-TS subheading is now `Link`.

4. Calibration placeholders and Cancel
   - Uncaptured Left/Centre/Right and Near/Far/Ref values display `-`.
   - CTRL-TS Joystick and Limit calibration overlays expose Cancel.
   - Cancel is sent through the existing retry/ACK-safe HMI EVENT queue.
   - Limit Calibration is transactional: Near/Far/Ref and Winch Invert are staged
     and committed together only at the final Ref step. Cancel preserves the prior
     calibration and exits service motion safely.

5. False red status flash during Limit Calibration
   - W1P STATUS is validate-before-commit.
   - One malformed/incomplete STATUS no longer destroys the last valid safety
     snapshot; it is rejected and logged while normal freshness timeout remains
     authoritative.
   - PONG no longer invalidates a valid W1P STATUS snapshot.

6. macOS/background SRVR communications
   - A dedicated background SRVR_ALIVE worker keeps CTRL peer-liveness independent
     of Qt window-focus scheduling.
   - Graceful shutdown still sends explicit SRVR_OFFLINE and wins final ordering.

7. Random Limit Calibration motion stops
   - The false transient safety paths above no longer repeatedly trip the existing
     joystick-neutral re-arm interlock.
   - A bounded W1P worker-side non-zero VEL bridge covers a missed GUI refresh
     interval while the normal SRVR command cadence remains approximately 150 ms.
   - W1P's independent 500 ms VEL freshness watchdog is unchanged.

8. GitHub native compile correction
   - The reboot-confirmation `newBootId` variable now lives in the complete
     HELLO_RESP scope. The earlier .05.07/.05.08 source referenced it after its
     nested declaration had gone out of scope.
   - Regression coverage explicitly locks this scope contract.

PRESERVED SAFETY / CONTROL CONTRACTS
------------------------------------
- W1P independent 500 ms VEL freshness watchdog.
- Normal SRVR non-zero VEL refresh approximately 150 ms.
- AI0 physical E-stop / AI1 joystick mapping.
- Joystick-neutral re-arm after a genuine safety stop.
- Hard limits, predictive stopping/dynamic soft limits and Leadshine velocity mode.
- CTRL<->CTRL-TS isolated half-duplex single-flight scheduling and EVENT ACK/retry.
- SRVR-owned CTRL-TS AUX presentation/assignments.
- Battery Change Mode semantics and automatic return to Off inside calibrated limits.
- Virtual Position Source remains physical-W1P-inhibited.
- Current Speed remains positive magnitude to the operator while signed transport
  velocity remains signed internally/on the wire.
- Firmware order remains CTRL -> W1P -> CTRL-TS.
- CTRL-TS remains intentionally headless/black only while programming its own flash.

BUILD POLICY
------------
GitHub Actions/native compilation remains authoritative. This source package does
not contain fabricated local firmware binaries. The included source/static/
regression/preflight suite passes locally; the native ESP32 and frozen desktop
builds remain GitHub Actions release gates.
