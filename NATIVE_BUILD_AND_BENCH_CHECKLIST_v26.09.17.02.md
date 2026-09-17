# HV P2P v26.09.17.02 — Native Build & Functional Bench Checklist

## Windows CI dependency-tool gate

Before `pyside6-deploy` runs on Windows x64, CI must prove the MSVC x64 developer environment and real `dumpbin.exe` PE-header probe work, Nuitka is exactly 4.2, `--assume-yes-for-downloads` survives into the generated command, and the final PE is AMD64. The frozen executable smoke test remains mandatory.

## A. Native build / firmware-authority gate

- [ ] Run `.github/workflows/complete-build.yml` on GitHub.
- [ ] Confirm `ALL_SOURCE_CHECKS_PASS` before native compilation.
- [ ] Confirm Arduino ESP32 core is exactly `3.3.8`.
- [ ] Confirm CTRL-TS is built first with pinned Waveshare/LVGL dependencies and its app is `>32 KiB` and `<=0x380000`.
- [ ] Confirm `STAGED_HMI_HEADER_PASS` proves the exact native CTRL-TS image/version/SHA was embedded into staged CTRL.
- [ ] Confirm final CTRL and W1P use EdgeBox `FlashSize=16M` and each app is `<=0x600000`.
- [ ] Confirm compiled CTRL contains both `HV_P2P_FW_ROLE=CTRL;HV_P2P_FW_VERSION=v26.09.17.02` and `HV_P2P_FW_TARGET=EDGEBOX_ESP100;`.
- [ ] Confirm compiled W1P contains both `HV_P2P_FW_ROLE=W1P;HV_P2P_FW_VERSION=v26.09.17.02` and `HV_P2P_FW_TARGET=EDGEBOX_ESP100;`.
- [ ] Confirm `NATIVE_BUILD_MANIFEST.json` records exact canonical CTRL-TS/CTRL/W1P application sizes and SHA-256 values.
- [ ] Confirm `SRVR_FIRMWARE_BUNDLE` contains exactly `manifest.json`, `SHA256SUMS.txt`, `ctrl.bin`, `w1p.bin`.
- [ ] Confirm `verify_srvr_firmware_bundle.py` passes and bundle CTRL/W1P hashes exactly match the canonical native applications.
- [ ] Confirm macOS Intel (`x86_64`) and Apple Silicon (`arm64`) jobs both depend on `build-firmware`, verify the downloaded bundle, package it, and pass source/QML/frozen-app smoke tests.
- [ ] Confirm Windows x64 job depends on `build-firmware`, verifies/packages the same bundle, reports PE machine `0x8664`, and passes source/QML/frozen-exe smoke tests.
- [ ] Confirm each frozen SRVR smoke test succeeds with its bundled firmware resources present; absence/corruption must make SRVR firmware-authority startup fail closed.
- [ ] Confirm Complete Release is created only after firmware + both macOS architectures + Windows x64 pass.
- [ ] Confirm `COMPLETE_RELEASE/SHA256SUMS.txt` and the external Complete Release `.sha256` match.
- [ ] Preserve the exact downloaded Native Firmware and Complete Release artifacts byte-for-byte for audit.

## B. One-time bootstrap / first convergence

Follow `INITIAL_BOOTSTRAP_v26.09.17.02.md`. Keep the physical winch unable to move throughout bootstrap.

- [ ] One-time USB/full-device bootstrap CTRL-TS with v26.09.17.02 compatible firmware/partition map.
- [ ] One-time USB/full-device bootstrap W1P with the authority-aware v26.09.17.02 firmware and 16 MB dual-OTA partition map.
- [ ] One-time USB/full-device bootstrap **final staged CTRL** containing the real CTRL-TS image; never bypass the clean-source carrier `#error`.
- [ ] Start the matching native SRVR and confirm the authority service is available on the isolated control LAN.
- [ ] Reboot CTRL: verify it remains an E-stop source until exact release/running-SHA match, repairs older/same-version-mismatched image, and refuses automatic downgrade when device firmware is newer.
- [ ] Reboot W1P: verify software Servo Enable and motion remain inhibited until exact authority match.
- [ ] For a W1P update/repair, verify no flash write begins until the existing stopped/braked gate proves fresh near-zero EL7 speed, Servo Enable OFF and Brake Release OFF.
- [ ] Confirm an interrupted/invalid CTRL or W1P download does not activate the inactive image.
- [ ] Confirm CTRL does not start CTRL-TS update until CTRL reports its own SRVR match; then verify CTRL-TS reaches exact required version/hash.
- [ ] Confirm an old/missing `FW_MATCH` W1P status is treated fail-closed by SRVR.
- [ ] Confirm matched devices do not initiate surprise OTA during an active running session; future convergence occurs during planned stopped startup/reboot.

## C. CTRL <-> CTRL-TS RS485, no motion hardware

- [ ] Wire EdgeBox RS485 A/B to Waveshare RS485 A/B; verify common installation practice,
      shield/ground strategy and termination before power-up.
- [ ] Confirm CTRL discovers `hw=WS-ESP32S3-7`, protocol 1.
- [ ] Fresh USB-flashed CTRL-TS may initially report hash `bootstrap`; confirm CTRL treats this
      as a correct target but mismatched image and automatically transfers the embedded image.
- [ ] Confirm progress reaches 100%, exact SHA/size passes, Waveshare reboots and new HELLO
      reports the required version/hash.
- [ ] Confirm CTRL does not clear the HMI safety gate before the post-reboot exact identity.
- [ ] Confirm all five AUX touchscreen events reach CTRL/SRVR and there are no physical AUX inputs.
- [ ] Confirm display matches the approved CTRL-TS design reference.
- [ ] Disconnect RS485: CTRL/SRVR must show safe/incompatible state and motion must remain inhibited.
- [ ] Test lost/reconnected RS485 without reset.

## D. Automatic update recovery tests

Perform these with motor power disabled.

- [ ] Serve an older-than-installed SRVR release to a deliberately newer test CTRL/W1P: confirm warning/hold and **no automatic downgrade**.
- [ ] Corrupt a role manifest/hash in a controlled test bundle: SRVR startup/validator or EdgeBox validation must fail closed and no invalid image may activate.
- [ ] Interrupt CTRL Ethernet OTA mid-transfer: old partition remains bootable; retry can converge later.
- [ ] Interrupt W1P Ethernet OTA mid-transfer behind the service gate: old partition remains bootable and Servo Enable remains inhibited.
- [ ] Start W1P authority repair with EL7 feedback unavailable: update must remain at the stopped/braked safety gate rather than bypassing it.

- [ ] Re-send a matching image: no unnecessary update once hash/version exactly match.
- [ ] Build a later test HMI version, embed in matching CTRL, and verify mismatch triggers update.
- [ ] Disconnect RS485 during block transfer; reconnect/reboot and confirm old image remains bootable.
- [ ] Interrupt power before FW_END; confirm old image boots.
- [ ] Interrupt response after FW_END; confirm idempotent FW_RESULT retry recovers.
- [ ] Present a wrong hardware-id/protocol test peer: CTRL must log update BLOCKED and must not send
      firmware blocks.

## E. CTRL EdgeBox I/O

- [ ] Verify DI0 NC E-stop loop: 24 V healthy = software healthy; open/pressed = unsafe.
- [ ] Confirm E-stop source appears correctly in SRVR.
- [ ] Verify AI0/AGND wiring for the 0-5 V joystick on the configured 0-10 V EdgeBox option.
- [ ] Record raw ADC at Left / Centre / Right and confirm no clipping or inverted endpoint.
- [ ] Run SRVR Left / Centre / Right calibration and verify neutral/deadband behavior.
- [ ] Disconnect/fault analogue input/I2C and confirm the existing analogue fault safety indication.

## F. Ethernet / SRVR

- [ ] SRVR .100, CTRL .101, W1P .102 reachable on intended subnet.
- [ ] CTRL A7 status/joystick and AUX1..AUX5 decode correctly.
- [ ] W1P status and command vocabulary remain compatible.
- [ ] Disconnect SRVR/network while motion is inhibited; confirm peer-loss safe state.
- [ ] Verify SRVR Run / Setup / Free-D / Log pages match approved visual baseline and no controls clip.

## G. W1P <-> Leadshine EL7, low-energy first

- [ ] Motor/mechanical load disabled or safely restrained for communications tests.
- [ ] Verify RS485 A/B polarity and the EdgeBox internal 120-ohm termination against the point-to-point
      installation; avoid unintended excessive termination/bias.
- [ ] Confirm 115200 8N1, Modbus ID 1.
- [ ] Confirm P05.29/30/31 expected RS485 mode/baud/address.
- [ ] Confirm DO2 Ready / DO3 Enabled / DO4 Brake / DO5 Fault assignments.
- [ ] Confirm local W1P E-stop stops commands and drops software Servo Enable.
- [ ] Confirm 750 ms SRVR peer timeout stops drive and drops software Servo Enable.
- [ ] **Independent VEL deadman:** while commanding low-speed motion, deliberately continue W1P `STATUS` traffic but stop sending `VEL`. Confirm W1P stops, locks drive writes and inhibits software Servo Enable within the 650 ms VEL freshness limit.
- [ ] Confirm the preceding test reports `VEL_WD=1` / `SAFETY_SRC=VEL_WATCHDOG` to SRVR and cannot auto-resume motion.
- [ ] Confirm clearing the watchdog requires the existing STOP + joystick-neutral + Servo Enable re-arm sequence.
- [ ] Confirm brake release/engage sequence before powered travel.

## H. W1P browser-service / OTA safety acceptance

Perform with mechanical energy controlled and before normal powered-motion acceptance.

- [ ] While W1P/EL7 actual velocity is non-zero, attempt browser app OTA; the action must not proceed unless W1P first reaches and proves the fail-closed service-safe state.
- [ ] Repeat for browser filesystem OTA, `/reboot` and `/reset-nvs`.
- [ ] Confirm service-safe entry commands a stop, locks drive writes and inhibits software Servo Enable.
- [ ] Confirm the action is refused with HTTP 409 if fresh EL7 feedback cannot prove near-zero velocity / inhibited state.
- [ ] Confirm `SERVICE_LOCK=1` reaches SRVR while the service latch is active.
- [ ] With the drive safely stationary and EL7 feedback fresh, confirm an intended service action can proceed.
- [ ] On CTRL, rename the W1P application binary so the filename looks like CTRL firmware; confirm content-role verification rejects it before activation.
- [ ] On W1P, rename the CTRL application binary so the filename looks like W1P firmware; confirm content-role verification rejects it before activation.
- [ ] Confirm a correct same-role application binary is accepted by each browser updater.

## I. W1P IP readdress / SRVR persistence / Free-D integrity

Perform W1P readdress tests with motion inhibited and the EL7 connected so the safe-service proof can complete.

- [ ] With W1P connected at the default `.102`, change only the SRVR Setup `W1P IP` draft to an unused address on the same subnet and press Apply.
- [ ] Confirm SRVR first sends the request to the old address and W1P reaches the verified stopped/braked service-safe state before saving/rebooting.
- [ ] Confirm W1P acknowledges `OK SET_NETWORK ... REBOOTING=1`, reboots provisionally, then reconnects on the new address and reports that address in `STATUS IP=`.
- [ ] Confirm first valid SRVR contact on the new address commits the provisional NVS transaction and subsequent W1P reboot retains the new IP.
- [ ] ACK-loss test: suppress/drop the old-address `OK SET_NETWORK` reply while allowing W1P to reboot; confirm SRVR proves the requested new address from `STATUS IP=` and still commits the Setup change correctly.
- [ ] Rollback test: issue a readdress but prevent SRVR from contacting W1P on the new address; confirm W1P automatically restores its previous IP and reboots after the 10-second confirmation window.
- [ ] Confirm motion remains inhibited through readdress/reconnect/rollback and requires the normal safety-clear joystick-neutral re-arm path.
- [ ] Attempt a duplicate CTRL/W1P address and a W1P address equal to the configured SRVR address; confirm the change is rejected.
- [ ] Disconnect W1P and attempt to Apply a different W1P IP; confirm Setup does not silently commit/retarget the unreachable address.
- [ ] After a successful readdress, reboot W1P again and confirm the new local IP persists from NVS.
- [ ] Exercise several SRVR settings saves, then confirm `config.json.bak` exists beside `config.json`.
- [ ] On a non-production test Mac/config directory, deliberately corrupt only `config.json` while retaining a known-good `.bak`; restart SRVR and confirm it recovers the backup and atomically restores the primary.
- [ ] Feed a valid Free-D D1 packet and confirm live telemetry updates; alter one payload byte without updating checksum and confirm the corrupted packet is ignored.
- [ ] Exercise `u24` Zoom/Focus values below and above `0x7FFFFF`, including `0x800000` and `0xFFFFFF`, and confirm output bytes preserve the full unsigned 24-bit values.

## J. Controlled motion acceptance

Only after independent E-stop/STO/brake/power-isolation circuits are proven.

- [ ] First movement at very low speed with generous clearance.
- [ ] Verify displayed direction stays consistent with joystick when Winch Invert changes motor direction.
- [ ] Verify Near/Far soft limits cannot be crossed.
- [ ] Verify position precision to 0.01 m and no stale 1-2 s speed lag.
- [ ] Verify Power and Speed acceleration modes independently.
- [ ] Verify Speed mode holds requested cable speed under reasonable load variation.
- [ ] In Speed mode, apply a repeatable load increase while holding joystick request constant; confirm measured cable speed returns toward the requested speed and W1P `CMD_VEL_MPS` increases rather than decreases.
- [ ] Apply a load reduction/down-slope condition at the same requested speed; confirm measured cable speed remains controlled and W1P `CMD_VEL_MPS` reduces rather than increases.
- [ ] Repeat in the reverse direction and confirm the correction direction remains symmetric and never commands an unintended direction reversal.
- [ ] Switch to Power mode and confirm the outer measured-speed correction is no longer active; response remains the established traditional velocity-profile behavior.
- [ ] Verify Goto Preset ramp-in/creep arrives without overshoot/reverse hunting.
- [ ] Verify Battery Change auto-cancels correctly on return inside limits.
- [ ] Exercise E-stop from SRVR, CTRL and W1P and verify source/combinations display correctly.

## K. v26.09.17.02 locked Run / Setup / Virtual acceptance

Perform Virtual-mode checks with the physical load safely isolated until its output-inhibit behavior is independently confirmed.

- [ ] Confirm Run top-left logo is exactly `HV P2P` / `SRVR` and no separate `HV P2P | SRVR` heading remains.
- [ ] On Preset 1-5, Preset 6-10 and Limits, test every Save/Recall/Slip class: first press shows `Confirm? 5s`; second press executes; no second press times out and restores the original label.
- [ ] While one Shortcut action is pending, press a different action. Confirm the first is cancelled and only the second action enters confirmation.
- [ ] Confirm preset visibility, System Power/Speed, Off/On, Mode 1/Mode 2 and calibration buttons remain immediate controls and cancel any pending Shortcut confirmation.
- [ ] Confirm Run System displays full `Mode 1` / `Mode 2`, preserves editable mode names, and Power / Off / Mode 1 / Limit Calibration share one left action alignment.
- [ ] Confirm Position TO NEAR / TO FAR `m` units sit immediately beside the numeric values.
- [ ] Confirm CTRL and W1P Setup boxes use matching six-row geometry and their dividers align vertically.
- [ ] Confirm CTRL labels are `CTRL IP / Link / RS485 / E-Stop / Firmware / Direction`; W1P labels are `W1P IP / Link / RS485 / E-Stop / Firmware / Direction`.
- [ ] Confirm CTRL Firmware and W1P Firmware show the actual connected firmware identity reported by each controller.
- [ ] Confirm CTRL-TS panel contains only CTRL-TS Link, divider, Detected, Required and Update, and Link shows green Active / red Disconnected.
- [ ] Confirm Motion Profiles Mode 1/Mode 2 content remains unchanged and the centre divider has visually even clearance.
- [ ] Set Position Source to Virtual and Apply. With W1P disconnected but CTRL/CTRL-TS healthy, confirm joystick motion updates SRVR position/speed and all normal Run profile/limit behavior can be demonstrated.
- [ ] Packet-capture the SRVR->W1P path while Virtual is active: confirm **no non-zero `VEL` packet is emitted**. If W1P is present, confirm periodic `STOP` and `SW_SRVON 0` keep physical Servo Enable inhibited.
- [ ] While Virtual is moving, inject/receive physical W1P POS_M/VEL_MPS telemetry and confirm it does not overwrite the simulated SRVR position/speed.
- [ ] Use a Virtual Slip/re-reference action and confirm no physical `SYNC_POS` is sent to W1P.
- [ ] Return Position Source to Encoder. Confirm simulation stops and physical motion remains inhibited until the joystick is returned through neutral and the existing safety/re-arm sequence completes.

## Release label

Do not label v26.09.17.02 “hardware-tested” until every applicable physical gate above is recorded.
A successful GitHub native build means **compile-ready/test-firmware produced**, not powered-motion proof.
