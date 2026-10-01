# HV P2P v26.10.01.03 Initial Bootstrap

## Build first
Upload this GitHub-ready source to the repository and let the included workflow
finish. Do not fabricate application binaries locally. Use the GitHub
`COMPLETE_RELEASE/FIRMWARE/STAGED_SOURCE` folders for manual commissioning.

## Manual commissioning settings
See `ARDUINO_IDE_SETTINGS_v26.10.01.03.md`.

Critical items:
- CTRL/W1P EdgeBox: 16 MB, QIO, **PSRAM Disabled**, **Partition Scheme 16M Flash (3MB APP/9.9MB FATFS)**. The sketch-local `partitions.csv` supplies the actual project dual-OTA layout.
- CTRL-TS Waveshare: 16 MB, QIO, **PSRAM Enabled**, **Partition Scheme Custom**.
- A clean initial flash may erase all flash; routine re-flashes should normally
  preserve NVS.

## Recommended first v26.10.01.03 commissioning order
1. Flash CTRL-TS manually from the GitHub STAGED_SOURCE.
2. Flash CTRL manually from the GitHub STAGED_SOURCE. The staged CTRL contains
   the exact native CTRL-TS image/hash from the same GitHub firmware build.
3. Start the matching v26.10.01.03 SRVR.
4. For W1P, use automatic SRVR convergence only if the EdgeBox already has the
   correct dual-OTA layout and can prove the stopped/braked service gate.
   Otherwise manually flash W1P from STAGED_SOURCE once.
5. Bench-test with machinery unable to move before enabling motion hardware.

## CTRL joystick
See `CTRL_JOYSTICK_WIRING_v26.10.01.03.md`. Current CTRL reads the onboard
EdgeBox SGM58031 AI1; the older external ADS1115 architecture is not used.

## CTRL EdgeBox <-> CTRL-TS Waveshare RS485
- EdgeBox RJ45 pin 7 / RS485_A -> Waveshare A.
- EdgeBox RJ45 pin 8 / RS485_B -> Waveshare B.
- CTRL UART: RX18/TX17/RTS8; Waveshare UART: RX15/TX16 auto-direction.
- 115200 8N1.
- EdgeBox internal 120-ohm termination plus the Waveshare endpoint termination
  gives the intended point-to-point two-end termination.

On a bootstrap/SHA mismatch, the splash should now display a stable
`Updating CTRL-TS firmware | N%` message and graphical progress bar, then
`Verifying`, `verified`, and `restarting` states.

## W1P EdgeBox <-> Leadshine EL7-RS
Do not use a straight-through RJ45 data mapping.
- EdgeBox RJ45 pin 7 / A -> Leadshine 485+ (CN3 pin 1; pin 4 is the duplicate +
  point in the current manual).
- EdgeBox RJ45 pin 8 / B -> Leadshine 485- (CN3 pin 2; pin 5 is the duplicate -
  point in the current manual).
- Leadshine CN3 pins 7/8 are ground, not the EdgeBox A/B destination.

Required EL7 communications settings:
- P05.29 = 4 (8N1)
- P05.30 = 6 (115200)
- P05.31 = 1 (slave ID 1)
Restart/power-cycle the drive after changing serial format/baud.

If the operational link is absent while safely stationary, W1P retains the
read-only 38400 8N2 factory-framing diagnostic and always restores 115200 8N1.
