# HV P2P v26.10.01.01 change summary

v26.10.01.01 is the first 1 October 2026 revision and is built directly from
the authoritative `HV P2P v26.09.29.06` source. It preserves the approved .06
UI and the existing RS485, OTA, Leadshine, velocity-watchdog, joystick filtering,
centre-drift, predictive-stopping and hard-limit architecture except where the
reported safety/status/update defects required a change.

## CTRL AI0 / AI1 acquisition hardening

- AI0 / pin 14 remains the CTRL analogue E-stop input.
- AI1 / pin 16 remains the joystick input.
- Every joystick transaction now explicitly selects and verifies AI1 before a
  fresh conversion is accepted.
- Every E-stop transaction explicitly selects and verifies AI0, samples it, and
  restores/verifies AI1 on every exit path, including ADC read failure.
- Health/diagnostic code no longer treats a conversion from an unknown current
  mux state as a named AI0/AI1 sample. Joystick diagnostics use the cached sample
  that was acquired through the verified AI1 transaction.
- CTRL-TS link and firmware-authority faults remain fail-safe, but they now have
  dedicated status bits instead of being mislabeled as the physical CTRL E-stop.

## Calibration/reference and system-status priority

- Winch position reference is now deliberately runtime/session-only. A saved
  configuration cannot make a new power/session start appear calibrated.
- SRVR always starts uncalibrated and a W1P reboot/session change invalidates the
  current reference even if SRVR itself stayed open. W1P publishes a boot-session
  identifier in HELLO/STATUS for this purpose.
- Limit Calibration and the existing Slip/re-reference operations remain the
  supported ways to establish the runtime position reference.
- Status priority is now safety/fault/E-stop first, then yellow
  **System Un-Calibrated**, then green **System Ready** only when safety is healthy
  and the position reference is valid.
- A missing/unsafe W1P is included as a W1P safety source even if the SRVR
  Position Source is set to Virtual; Virtual no longer makes absent production
  hardware look ready.

## Joystick direction

- CTRL now normalises the installed electrical polarity at the hardware-input
  boundary so physical Left is negative and physical Right is positive.
- The SRVR default joystick direction is therefore Normal instead of applying a
  second commissioned inversion downstream.
- Existing non-default Left/Centre/Right captures are migrated once so they keep
  describing the same physical positions after the transport-polarity correction.
- The Value/Percentage display, requested joystick velocity and direction-sensitive
  limit logic now share the same calibrated sign convention.

## CTRL-TS firmware update display

- A runtime firmware update now creates/owns a dedicated full-screen update view
  after the normal boot splash has been destroyed.
- The screen shows CTRL/SRVR connection state plus stable update phase, percentage
  and progress bar.
- Normal CFG/HMI rendering, link-state drawing and screen keepalive rendering are
  suppressed while the firmware updater owns the display, preventing the normal
  UI from flashing over the update screen. Firmware RS485 servicing continues.

## Regression/build changes

- Added/updated regression contracts for verified AI0/AI1 transactions, dedicated
  CTRL safety-source flags, non-persistent calibration authority, W1P reboot
  invalidation, red/yellow/green status priority, corrected joystick direction
  and exclusive CTRL-TS updater display ownership.
- Updated old tests that had previously locked in .06 defects: persisted
  calibrated state, Virtual-mode W1P readiness bypass and the downstream default
  joystick inversion.
- macOS bundle metadata is advanced to short version `26.10.1` and build
  `2610.1.1`; application/release identity is `26.10.01.01`.
- GitHub Actions remains the authoritative native Arduino and frozen desktop
  compiler. No local native firmware binary is substituted into this source ZIP.
