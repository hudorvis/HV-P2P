# HV P2P v26.09.29.06 change summary

v26.09.29.06 is a functional revision built directly from the last good
v26.09.29.05 source. It retains the commissioned AI0 E-stop / AI1 joystick
mapping and all prior RS485, OTA, Leadshine, watchdog and safety hardening.

## SRVR operator interface

- CTRL Setup joystick readouts are renamed from **Current Value** / **Current
  Percentage** to **Value** / **Percentage**.
- Both numeric readouts share the same 72 px scaled value column and
  `Text.AlignRight`, so the two live values align exactly on the right edge.
- Run -> Shortcuts -> System now has a **Preset Names** row directly below
  Calibration Mode with **Short Names** and **Long Names** buttons.
- Short Names are fixed `P1` ... `P10`; Long Names remain the existing editable
  preset names.
- The selected name style is persisted by SRVR and is used consistently by the
  Run Top View, Side View and the CTRL-TS display packet. Long names are carried
  through the display packet using the normal 24-character sanitised field cap
  instead of the previous 8-character preset-name truncation.

## Joystick centre drift management

- Adds a conservative runtime-only automatic centre trim.
- The saved Left / Centre / Right calibration points are never silently changed.
- Centre learning is allowed only with a healthy CTRL link, no E-stop, no
  calibration/Goto/service override, zero requested speed, near-zero measured
  speed, the joystick already close to neutral and a stable multi-second sample
  window.
- Automatic correction is limited to +/-3% of the smaller calibrated half-span
  and moves slowly (20 s time constant).
- Larger stable displacement is not learned away; SRVR logs that joystick
  recalibration is recommended.
- Opening/completing joystick calibration resets the temporary centre trim.

## Predictive stopping / dynamic soft limits

- Adds a reaction-time-aware stopping envelope in SRVR while preserving the
  existing Near/Far hard limits and ramping zones.
- The permitted speed is continuously reduced as remaining distance falls, using
  the configured deceleration, a conservative deceleration derating, a fixed
  safety margin and a control-reaction allowance.
- W1P independently repeats the predictive speed cap locally before its motion
  profile, so the end-of-travel protection does not depend solely on the next
  SRVR network packet.
- Service/calibration mode retains its deliberate limit bypass behaviour.

## Speed acceleration mode / incline review

- Speed mode remains a velocity-control architecture, not a fixed motor-power
  command. The Leadshine EL7 PR path remains configured for velocity mode.
- W1P's 50 Hz Speed/Dynamic outer loop compares shaped cable-speed target with
  measured drive speed and applies a bounded PI correction.
- Under-speed (for example, climbing an incline) increases the velocity command
  correction, allowing the EL7's internal velocity loop to demand more motor
  torque/current.
- Over-speed (for example, a gravity-assisted descent) reduces the correction;
  the EL7 velocity loop can provide negative/regenerative motor torque while the
  requested travel direction remains unchanged.
- W1P never reverses the requested velocity merely to create braking torque.
- The existing source contract test covers both forward/reverse under-speed and
  over-speed cases, correction bounds, integral reset and the no-sign-reversal
  rule.
- The physical regenerative resistor / DC-bus energy capacity remains a hardware
  commissioning constraint on long or heavily loaded downhill operation.

## Build / regression

- macOS bundle build number advanced to `2609.29.3`.
- Added `test_motion_innovations_contract.py` covering UI naming, preset-name
  propagation, runtime-only bounded centre trim, predictive stopping and the
  slope/speed-mode control contract.
- Updated the W1P reviewed function hashes for the deliberately changed local
  predictive-limit implementation.
- GitHub Actions remains the authoritative native Arduino and frozen desktop
  compiler. No native firmware binaries or desktop executables are fabricated in
  this source ZIP.
