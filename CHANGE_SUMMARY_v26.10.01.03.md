# HV P2P v26.10.01.03 change summary

v26.10.01.03 is the third 1 October 2026 revision and is built directly from
v26.10.01.02. It preserves the approved HV P2P UI/motion/safety architecture
except for the requested Settings/Free-D auto-save change and the fixes below.
GitHub Actions remains the authoritative native compiler.

## Joystick calibration readout

- Completing the Left/Centre/Right joystick calibration wizard is now the commit
  point. The captured range becomes live and is persisted immediately; there is
  no separate Settings Apply step.
- Setup `Value` and `Percentage` are calculated from the active calibrated range,
  so captured Left/Centre/Right correspond to approximately -1/0/+1 and
  -100/0/+100% respectively.
- The existing neutral-return interlock remains active after calibration, so a
  wizard completed at a displaced stick position cannot immediately command
  motion.

## Joystick latency / real-time firmware authority

Bench testing of v26.10.01.02 exposed a periodic 1-2 second CTRL telemetry stall.
The cause was the v26.10.01.02 firmware-authority fix performing a blocking HTTP
manifest request every two seconds from the same CTRL main loop that samples AI1
and emits the 20 Hz A7 joystick packet. The HTTP helper permits long network
timeouts, so a slow request could pause joystick telemetry.

v26.10.01.03 removes all periodic HTTP work from healthy matched CTRL and W1P
real-time loops:

- SRVR includes its current release in the existing CTRL `DSP1` UDP packet.
- SRVR sends W1P a lightweight `SRVR_FW` UDP beacon every 500 ms.
- A matched node simply compares that beacon version with its installed release.
  A changed release immediately invalidates the old match.
- Only after the node is already fail-closed/unmatched does the existing
  manifest/SHA/OTA HTTP path run.
- W1P stops the drive, disables drive writes and asserts software Servo Enable
  inhibit before entering that unmatched update path.

This preserves automatic discovery of a newly launched SRVR release without a
reboot, while keeping normal joystick acquisition, UDP telemetry and the W1P
500 ms velocity watchdog free of HTTP blocking.

## Settings and Free-D auto-save

- Removed the bottom `Apply` and `Reset` buttons from both Settings and Free-D.
- Every accepted button, combo, checkbox or committed field edit is now applied
  and saved immediately.
- Text fields save on Enter/focus-loss/normal editor commit rather than on every
  keystroke, avoiding partial values such as an intermediate IP address.
- Setup keeps a mirror model only for stable QML bindings; it is refreshed from
  the saved live state after each successful commit.
- Ordinary Settings edits no longer clear CTRL receive history or reconfigure
  W1P unless the relevant network setting actually changed.
- W1P IP changes retain the existing safe transactional readdress procedure. If
  readdress cannot be confirmed, the requested auto-save change is rejected.
- Free-D output packets are generated from the current live auto-saved snapshot.
- Load Config now validates, applies and persists the imported Setup/Run/Free-D
  configuration immediately. Save Config exports the current auto-saved state.

## v26.10.01.02 fixes retained

- Running CTRL/W1P detect a newer SRVR release automatically without a manual
  controller reboot.
- SRVR independently rejects stale old-release firmware-match claims.
- CTRL-TS replaces the JPEG boot splash with its dedicated opaque firmware update
  screen before transfer rendering and redraws progress only when percentage
  changes.
- CTRL-TS E-stop source formatting no longer produces `E-STOP | / W1P`.

## Earlier v26.10.01.01 fixes retained

- Verified channel-bound SGM58031 transactions: AI0/pin 14 E-stop and AI1/pin 16
  joystick, with guaranteed verified AI1 restoration after E-stop sampling.
- Physical CTRL E-stop identity separated from CTRL-TS/firmware safety faults.
- Position reference is session-only and invalidated by W1P boot-session changes.
- Status priority is red safety/fault, then yellow `System Un-Calibrated`, then
  green `System Ready`.
- Physical joystick polarity is corrected once at CTRL so Left is negative and
  Right positive through calibration, readout, requested speed and limit logic.

## Regression/build status

- Source regression coverage now locks the non-blocking SRVR firmware beacons,
  immediate joystick calibration activation, calibrated percentage readout,
  Settings/Free-D auto-save, absence of Apply/Reset UI, and selective controller
  link reconfiguration.
- EdgeBox integration validation contains 333 checks in this source revision.
- macOS bundle metadata is short version `26.10.1`, build `2610.1.3`; full
  application/release identity is `26.10.01.03`.
- Native ESP32 and frozen desktop compilation is intentionally not fabricated
  locally; GitHub Actions performs the authoritative builds.
