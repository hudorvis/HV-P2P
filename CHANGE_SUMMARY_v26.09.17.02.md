# HV P2P v26.09.17.02 Change Summary

## Purpose

Corrective CTRL <-> CTRL-TS RS485/boot-display revision based on live commissioning of v26.09.15.02. The physical link proved able to exchange HELLO/version information, but CTRL repeatedly timed out waiting for firmware-update replies and CTRL-TS remained at 0% update. The Waveshare boot splash also rendered cropped/distorted.

## RS485 / CTRL-TS firmware-transfer corrections

- CTRL and CTRL-TS now allocate 4096-byte UART RX buffers before `HardwareSerial.begin()`.
- CTRL firmware blocks are reduced from 2048 to 1024 data bytes.
- Master and slave half-duplex quiet/turnaround guards are both 2500 us.
- CTRL firmware reply timeout is 3000 ms while CTRL-TS receiver timeout remains 5000 ms, leaving a deterministic retry window.
- CTRL suppresses normal HELLO/POLL traffic while firmware transfer owns the bus.
- Lost block ACKs are idempotent: retransmitted blocks are not written twice and the receiver returns its authoritative next offset.
- Lost final results are idempotent: repeated `FW_END` returns the already-verified size/SHA result.
- Firmware updater responses are sequence-correlated so stale replies cannot advance state.
- CTRL logs `FW_READY` and `FW_RESULT`; CTRL-TS logs updater response transmission for commissioning diagnostics.
- CTRL-TS updater timeout and scheduled reboot service now run during the boot splash loop, before the main UI loop starts.
- Duplicate REBOOT requests cannot postpone an already scheduled reboot.
- A finalized inactive partition cannot be erased by a late/duplicate `FW_BEGIN` while reboot is pending.
- CTRL display-forward state now advances only after a successful framed UART send; compatibility restoration clears the delivery cache and forces an immediate full HMI refresh instead of waiting up to the 3-second keepalive.

At 115200 baud a 1024-byte firmware frame occupies about 90.5 ms on the wire, comfortably inside the 4096-byte receive buffers and the new retry timing.

## Splash correction

The Waveshare splash renderer no longer assumes the microSD JPEG is already an exact 800x480 landscape image. It now:

- detects portrait artwork and rotates it clockwise for the landscape panel;
- performs aspect-preserving contain-fit into the 800x480 canvas;
- centers the image without cropping;
- retains a fast path for native 800x480 artwork;
- keeps the existing bottom boot-status overlay.

A host-side splash contract now exercises landscape, portrait, widescreen, square and smaller images and checks that mapped output remains inside the panel bounds.

## Deep audit preservation result

After normalizing the revision string, the only production-code files changed from v26.09.15.02 are:

- `HV_P2P_CTRL_EDGEBOX_v26.09.17.02.ino`
- `HV_P2P_CTRL_TS_v26.09.17.02.ino`

W1P firmware, SRVR backend/runtime, firmware-authority service, locked Run/Setup QML, authority headers and RS485 frame header are otherwise unchanged from v26.09.15.02.

Preserved unchanged:

- approved Run and Setup UI;
- Speed = W1P DYNAMIC cable-speed PI;
- Power = TRADITIONAL;
- W1P independent 650 ms VEL watchdog;
- W1P stopped/braked OTA service gate;
- Servo Enable inhibition, E-stop handling and RS485 protections;
- SRVR-authoritative no-auto-downgrade behavior;
- CTRL must match SRVR before CTRL-TS convergence.

## Bootstrap note for this revision

Because the RS485 receiver/timing fix is itself in the CTRL-TS application, a CTRL-TS currently running v26.09.15.02 should receive one more manual Arduino IDE USB bootstrap of v26.09.17.02. After that, the CTRL -> CTRL-TS automatic RS485 updater is intended to handle future releases.

CTRL and W1P remain eligible for the SRVR-authoritative Ethernet convergence path once the matching v26.09.17.02 SRVR build is installed. During commissioning, manual USB bootstrap remains the recovery fallback.

Native ESP32 binaries and desktop executables are not fabricated in this source package; GitHub Actions remains the authoritative native build gate.
