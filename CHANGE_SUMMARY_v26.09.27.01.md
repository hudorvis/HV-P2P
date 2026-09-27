# HV P2P v26.09.27.01 Change Summary

## Why this revision exists
The previously generated v26.09.20.01 download expired and its exact artifact
bytes were no longer recoverable. The project was therefore reconstructed from
the surviving v26.09.04.03 source plus the preserved later change contracts and
reissued as **v26.09.27.01**. Reusing v26.09.20.01 would have created a false
version/hash identity.

## CTRL <-> CTRL-TS RS485 hardening retained
- EdgeBox UART: RX18 / TX17 / RTS8, hardware half-duplex, 115200 8N1.
- Waveshare UART: RX15 / TX16, automatic direction, 115200 8N1.
- 4096-byte receive buffers on both sides.
- 1024-byte firmware chunks instead of 2048-byte blocks.
- 2.5 ms master/slave turnaround guard.
- 3 s master firmware-response timeout; 5 s CTRL-TS receiver-session timeout.
- Firmware transfer owns the bus; normal HELLO/POLL traffic is suspended.
- Reply sequence and exact next-offset correlation.
- Lost block ACK and lost final FW_RESULT are idempotently recoverable.
- Duplicate FW_BEGIN cannot erase an already-finalized image.
- Duplicate REBOOT cannot postpone a scheduled reboot.
- CTRL-TS services updater timeout/reboot while still in startup/splash code.
- CTRL display-forward cache advances only after a successful framed send and is
  reset on restored CTRL-TS compatibility.
- Splash rendering now rotates portrait artwork when required and aspect-fits it
  inside 800x480 without cropping.

## W1P <-> Leadshine RS485 hardening retained
- Operational protocol remains Modbus RTU 115200 8N1, slave ID 1.
- Inter-frame guard is 2.0 ms.
- Configuration audit aborts after the first genuine timeout/CRC/framing loss so
  a disconnected drive cannot block through a long chain of register retries.
- A CRC-valid Modbus exception still proves that the physical peer responded.
- Safe read-only 38400 8N2 factory-framing probe can diagnose an EL7 still at
  factory communications settings; it never promotes normal RS485 health and
  always restores 115200 8N1.
- The factory probe is allowed only while drive writes and software Servo Enable
  are inhibited and requested/profile/commanded/actual motion are effectively
  zero.

## SRVR-authoritative OTA reconstructed
- Native GitHub firmware is built CTRL-TS -> embed exact CTRL-TS image into CTRL
  -> CTRL -> W1P.
- CTRL/W1P carry retained role, target and release identity tokens.
- Native build creates an immutable SRVR_FIRMWARE_BUNDLE with exact image size,
  SHA-256, role, target and release metadata.
- SRVR validates the whole bundle before opening the firmware authority service.
- Devices validate authority/schema/bundle metadata, role, target, version,
  image size, SHA-256, ESP image magic and embedded identity before activation.
- Same-version wrong-SHA is fail-closed and replaced with the exact SRVR image.
- Newer-than-SRVR nodes are never silently downgraded.
- CTRL must exactly match SRVR before CTRL may update CTRL-TS.
- W1P update remains behind the stopped/braked safe-service gate.

## SRVR session/state hardening reconstructed
- Missing CTRL FW_MATCH is fail-closed.
- W1P HELLO/PONG invalidates prior firmware-authority/RS485 status until a fresh,
  complete STATUS packet arrives.
- A new W1P STATUS invalidates the prior status first and is only marked fresh
  after all safety-critical fields parse successfully.

## Build/packaging hardening retained
- ESP32 Arduino core 3.3.8 and display dependencies remain pinned.
- Native artifacts are written under RUNNER_TEMP, not the source checkout.
- Source tree is hashed before/after native firmware build and mutation fails CI.
- Explicit Nuitka data-file flags carry ctrl.bin and w1p.bin (plus manifest and
  checksum) because .bin files cannot be trusted to a generic data-dir include.
- Windows keeps x64 MSVC setup, real dumpbin PE probing, Nuitka 4.2,
  --assume-yes-for-downloads, AMD64 PE validation and frozen smoke testing.
- Complete release is created only after firmware + both macOS architectures +
  Windows x64 succeed.

## Locked UI preservation
The approved Run and Setup QML were not changed during this reconstruction.
Release seal fingerprints:
- Main.qml: `60edb4348c98827902f21006ffa4e4aa274e65d0527f32782f5f3de97bead93e`
- SetupPage.qml: `9cede2819a4c7d931247121711d2441e01537fdd05c804b0fc646caa5fded7fd`
