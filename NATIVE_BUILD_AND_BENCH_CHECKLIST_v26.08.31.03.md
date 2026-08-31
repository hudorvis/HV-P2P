# HV P2P v26.08.31.03 — Native Build & Functional Bench Checklist

## A. Native build gate

- [ ] Run `.github/workflows/firmware-build.yml` on GitHub.
- [ ] Confirm `ALL_SOURCE_CHECKS_PASS` appears before compilation.
- [ ] Confirm Arduino ESP32 core is exactly `3.3.8`.
- [ ] Confirm CTRL/W1P FQBN explicitly contains `FlashSize=16M`.
- [ ] Confirm CTRL-TS build uses 16 MB flash, OPI PSRAM and local `partitions.csv`.
- [ ] Confirm CTRL-TS native app is >32 KiB and <= `0x380000` bytes.
- [ ] Confirm carrier verification prints `STAGED_HMI_HEADER_PASS`.
- [ ] Confirm generated carrier hardware is `WS-ESP32S3-7`, protocol `1`, version
      `v26.08.31.03`, and its SHA matches the native CTRL-TS `.ino.bin`.
- [ ] Confirm complete CTRL app including embedded CTRL-TS image is <= `0x600000`.
- [ ] Confirm W1P app is <= `0x600000`.
- [ ] Download `HV-P2P-v26.08.31.03-Native-Firmware` artifact and retain
      `NATIVE_BUILD_MANIFEST.json` + `SHA256SUMS.txt`.

## B. Initial flashing

- [ ] Verify EdgeBox serial-number/hardware revision before using its external USB port for
      programming; older EdgeBox revisions use the internal UART programming header.
- [ ] One-time USB flash CTRL-TS v26.08.31.03 first.
- [ ] Flash W1P EdgeBox with its matching v26.08.31.03 native build.
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
- [ ] Confirm brake release/engage sequence before powered travel.

## H. Controlled motion acceptance

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

## Release label

Do not label v26.08.31.03 “hardware-tested” until every applicable physical gate above is recorded.
A successful GitHub native build means **compile-ready/test-firmware produced**, not powered-motion proof.
