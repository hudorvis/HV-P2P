# HV P2P v26.08.31.09 — Native Build & Functional Bench Checklist

## A. Native build gate

- [ ] Run `.github/workflows/complete-build.yml` on GitHub.
- [ ] Confirm `ALL_SOURCE_CHECKS_PASS` appears before compilation.
- [ ] Confirm Arduino ESP32 core is exactly `3.3.8`.
- [ ] Confirm `Waveshare_ST7262_LVGL` is fetched at exact commit `593775b89ebfd2d411df3eadba7bc382767ed4a4` and the workflow verifies `rev-parse HEAD`.
- [ ] Confirm CTRL/W1P FQBN explicitly contains `FlashSize=16M`.
- [ ] Confirm CTRL-TS build uses 16 MB flash, OPI PSRAM and local `partitions.csv`.
- [ ] Confirm CTRL-TS native app is >32 KiB and <= `0x380000` bytes.
- [ ] Confirm carrier verification prints `STAGED_HMI_HEADER_PASS`.
- [ ] Confirm generated carrier hardware is `WS-ESP32S3-7`, protocol `1`, version
      `v26.08.31.09`, and its SHA matches the native CTRL-TS `.ino.bin`.
- [ ] Confirm complete CTRL app including embedded CTRL-TS image is <= `0x600000`.
- [ ] Confirm W1P app is <= `0x600000`.
- [ ] Confirm the native builder verifies the compiled CTRL binary contains `HV_P2P_FW_ROLE=CTRL;HV_P2P_FW_VERSION=v26.08.31.09`.
- [ ] Confirm the native builder verifies the compiled W1P binary contains `HV_P2P_FW_ROLE=W1P;HV_P2P_FW_VERSION=v26.08.31.09`.
- [ ] Confirm `NATIVE_BUILD_MANIFEST.json` records the exact Waveshare git commit.
- [ ] Confirm the macOS app Info.plist reports `CFBundleIdentifier=com.hvp2p.srvr`, `CFBundleShortVersionString=26.8.31`, `CFBundleVersion=2608.31.9`, and `HVP2PReleaseVersion=26.08.31.09`.
- [ ] Confirm the Complete Release `SRVR/` directory contains the original unextracted `HV P2P SRVR v26.08.31.09 macOS Intel.zip` and no extracted `.app`.
- [ ] Confirm `COMPLETE_RELEASE/SHA256SUMS.txt` exists and the external `HV P2P v26.08.31.09 Complete Release.zip.sha256` matches the exact combined ZIP.
- [ ] Download `HV-P2P-v26.08.31.09-Native-Firmware` artifact and retain `NATIVE_BUILD_MANIFEST.json` + `SHA256SUMS.txt`.
- [ ] Download and preserve the exact Complete Release ZIP byte-for-byte; do not extract/re-zip the nested SRVR ZIP before returning it for audit.

## B. Initial flashing

- [ ] Verify EdgeBox serial-number/hardware revision before using its external USB port for
      programming; older EdgeBox revisions use the internal UART programming header.
- [ ] One-time USB flash CTRL-TS v26.08.31.09 first.
- [ ] Flash W1P EdgeBox with its matching v26.08.31.09 native build.
- [ ] Flash CTRL EdgeBox with the **staged/native CTRL build** that contains the real HMI image.
- [ ] Never attempt to compile the clean CTRL source by deleting/bypassing the carrier `#error`.

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
- [ ] Verify Goto Preset ramp-in/creep arrives without overshoot/reverse hunting.
- [ ] Verify Battery Change auto-cancels correctly on return inside limits.
- [ ] Exercise E-stop from SRVR, CTRL and W1P and verify source/combinations display correctly.

## K. v26.08.31.09 locked Run / Setup / Virtual acceptance

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

Do not label v26.08.31.09 “hardware-tested” until every applicable physical gate above is recorded.
A successful GitHub native build means **compile-ready/test-firmware produced**, not powered-motion proof.
