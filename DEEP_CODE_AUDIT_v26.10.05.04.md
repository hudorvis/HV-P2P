# HV P2P v26.10.05.04 deep code audit

Date: 2026-10-05

## Scope

Focused follow-up audit of the `.05.03` bench findings covering calibration-limit bypass timing, CTRL-TS calibration presentation, post-update black-screen recovery, operator speed display, travel-bar geometry, and SRVR Shortcuts/Settings ordering.

## 1. Limit Calibration transient old-limit catch

SRVR already treats open Limit/Winch calibration as a service override, and W1P bypasses its normal software limit envelope when `SERVICE_MODE` is active. The weakness was timing: `SERVICE_MODE` was fed only through the paced settings synchronizer. At calibration entry, one or more old-limit-controlled motion cycles could therefore occur before W1P confirmed service mode.

### Correction

`_sync_service_mode_to_winch(force=True)` now transmits the desired `SERVICE_MODE` immediately when W1P is connected, records the attempted value/timestamp, and still marks the setting pending for the existing STATUS-confirmed retry path. The command is therefore low-latency but remains convergent if UDP is lost. Normal operation still uses the full predictive/hard-limit architecture.

## 2. CTRL-TS calibration readout mismatch

The touchscreen overlay used a compact single-line summary, unlike the SRVR wizard's three captured positions plus current value. This made live calibration harder to interpret and visually inconsistent.

### Correction

The overlay now uses three real value boxes. Limit Calibration labels them Near / Ref / Far and adds `Current Winch Position`; Joystick Calibration labels them Left / Centre / Right and adds `Current Joystick Position`. CTRL forwards the joystick calibration pending values while calibration is active. Winch Calibration retains its own controls rather than showing irrelevant position boxes.

## 3. Verified OTA could remain black

CTRL-TS intentionally performs its own flash in a headless safe updater. After `FW_END`, a verified image could be finalized successfully but the updater relied on CTRL subsequently delivering an explicit `REBOOT`. If that final RS485 command was lost, the valid new application existed in flash but the headless updater could remain running indefinitely, appearing as a permanent black screen.

### Correction

A successful verified finalize now arms a 2.5 s autonomous reboot deadline. If CTRL's explicit `REBOOT` arrives, it shortens the deadline to about 250 ms. Only the post-verification exit is changed; the flash itself remains display-off and the image-integrity checks remain mandatory.

## 4. Speed sign is a presentation concern

Reverse travel legitimately uses signed internal velocity. The user-facing Current Speed, however, is a magnitude readout and should not display negative km/h/m/s.

### Correction

SRVR and CTRL-TS operator speed displays now use absolute magnitude. Signed velocity is preserved internally for motion direction, predictive stopping and command generation.

## 5. CTRL-TS travel-bar width

The position bar was visually inset more than necessary. Its canonical geometry is now expanded to near the full 800 px display width while retaining small safe margins for rendering: 8 px left to 772 px right in the 780 px content panel.

## 6-8. SRVR UI consistency

Run > Shortcuts now gives Acceleration and Battery Change the same full two-button width as the Preset Names row and adds a third Calibration Mode choice. Settings calibration actions are alphabetically Joystick / Limit / Winch. AUX assignment choices are alphabetized for all non-preset functions, while the Preset Save / Recall / Slip blocks remain grouped at the bottom.

## Safety review

No W1P motion/watchdog source was intentionally changed. The 500 ms velocity freshness watchdog, Leadshine closed-loop velocity path, E-stop inputs, hard limits, predictive/dynamic limits and SRVR ~150 ms non-zero velocity refresh remain as before. Immediate calibration `SERVICE_MODE` is only asserted when the existing service-override conditions are true and is still confirmed/retried through W1P STATUS.

## Regression coverage

`test_bench_regression_0504.py` covers the immediate service-mode command, positive operator speed, CTRL-TS calibration boxes/current rows, verified-image autonomous reboot, full-width travel bar and requested SRVR UI ordering/layout. Older static tests that encoded the superseded calibration summary or option ordering were updated to require the new contract rather than relaxed.
