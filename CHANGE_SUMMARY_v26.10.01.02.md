# HV P2P v26.10.01.02 change summary

v26.10.01.02 is the second 1 October 2026 revision. It is built directly from
v26.10.01.01, which itself was built from the authoritative v26.09.29.06 source.
The approved UI and the existing RS485, OTA, Leadshine, velocity-watchdog,
joystick filtering, centre-drift, predictive-stopping and hard-limit architecture
remain unchanged except for the field-feedback fixes below.

## v26.10.01.02 hardware-feedback fixes

- CTRL and W1P no longer treat a successful SRVR firmware match as permanent for
  the whole power session. They re-fetch the small SRVR authority manifest every
  2 seconds while matched. An unchanged manifest avoids re-hashing flash; a new
  version/SHA immediately invalidates the old match and enters the existing safe
  OTA path. A field-node reboot is no longer required to discover a newer SRVR.
- SRVR independently checks reported node versions against its own release. Old
  `fw_match=1` state from a previous SRVR session is classified as stale, and the
  CTRL-TS panel reports **Update required** rather than **Up to date** until the
  current release is actually installed.
- CTRL-TS now replaces the JPEG boot splash with the same dedicated opaque update
  screen used for runtime updates as soon as FW_BEGIN is accepted. The JPEG canvas
  is deleted/freed before transfer redraws, and the progress bar is only redrawn
  when the displayed integer percentage changes. This addresses the vertical
  duplicate/shift flash visible in the supplied bench video.
- CTRL-TS reconstructs E-stop display text from the delimiter-safe `estop_src`
  field. The packet sanitisation of `E-Stop | W1P` can therefore no longer render
  the incorrect `E-STOP | / W1P` status.

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

- A firmware update creates/owns a dedicated full-screen update view whether it
  begins during the boot splash or after the normal UI has started.
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
  `2610.1.2`; application/release identity is `26.10.01.02`.
- GitHub Actions remains the authoritative native Arduino and frozen desktop
  compiler. No local native firmware binary is substituted into this source ZIP.
