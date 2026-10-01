# HV P2P v26.10.01.02 Native Build and Bench Checklist

## GitHub Actions gates

- Run the complete source/protocol regression suite, including
  `test_speed_mode_contract.py` and `test_motion_innovations_contract.py`.
- CTRL-TS must compile first; embed that exact native application and SHA into
  staged CTRL before CTRL compilation.
- CTRL/W1P use the supported EdgeBox
  `PartitionScheme=app3M_fat9M_16MB` selector while sketch-local
  `partitions.csv` supplies the actual 6 MB dual-OTA slots.
- Generate the immutable SRVR firmware-authority bundle from the exact CTRL/W1P
  native applications.
- Source checkout hash must be identical before/after native firmware build.
- macOS Intel, macOS Apple Silicon and Windows x64 SRVR builds/smoke tests must
  all pass before the Complete Release is created.

## CTRL / analogue-input bench

- Confirm the required factory 249-ohm 4-20 mA shunts have been removed from
  AI0/AI1 for this voltage-input commissioning.
- Joystick: +5 V -> APEM supply, 0 V -> APEM ground + EdgeBox AGND pin 12,
  proportional output -> EdgeBox **AI1 pin 16**.
- E-stop status: +5 V -> normally-closed E-stop contact -> EdgeBox **AI0 pin 14**;
  supply 0 V -> EdgeBox AGND.
- Confirm joystick voltage remains approximately full-range while connected to
  the EdgeBox, then run SRVR Left/Centre/Right calibration.
- Confirm AI0 is healthy high when the E-stop is released and goes unsafe when
  pressed/open/faulted.
- Confirm CTRL serial diagnostics show SGM58031 at 0x48 and no analogue fault.

## Joystick centre-drift commissioning

1. Complete normal joystick calibration and verify Percentage reaches expected
   negative/zero/positive values.
2. Leave the system stationary with the joystick released for at least 5 s.
3. Warm the enclosure/controls through a realistic operating period and verify a
   small centre-voltage drift does not produce a non-zero motion request.
4. Verify the automatic correction remains slow and small; it must not change the
   saved Left/Centre/Right calibration values after restart.
5. Deliberately create/measure a centre error larger than the bounded trim only
   during a safe non-motion test and verify SRVR recommends recalibration instead
   of silently learning a large offset.

## Predictive stopping / dynamic soft limits

Commission this from low speed upward with an unloaded/light-load system first.
For both Near and Far directions:

1. Verify the existing absolute limit still blocks outward movement at the limit.
2. Approach from well inside the span with a steady joystick command and verify
   commanded speed begins tapering before the endpoint.
3. Repeat at increasing speed and confirm the taper starts farther from the limit
   as stopping distance increases.
4. Confirm motion remains smooth through the existing user ramp zone and the
   predictive envelope; the more restrictive limit should win.
5. Simulate/deliberately interrupt SRVR updates only under safe bench conditions
   and verify W1P's local limit cap plus the 500 ms VEL watchdog remain effective.
6. Do not approve full-speed operation until measured stopping distance remains
   comfortably inside the calibrated limits in both directions and under the
   worst intended load/slope.

## Speed mode / incline-load commissioning

Use **Speed** acceleration mode and start with conservative speed/accel values.
The goal is constant cable speed, not constant motor power.

1. On level/light load, compare W1P `REQ_VEL_MPS`, `PROFILE_VEL_MPS`,
   `CMD_VEL_MPS` and measured `VEL_MPS` at several steady joystick positions.
2. Uphill: verify actual velocity remains close to target while the servo supplies
   the additional torque/current required by gravity/load. W1P correction may
   increase the velocity command slightly but must remain bounded.
3. Downhill: verify the servo holds the same commanded direction/speed and does
   not free-run/overspeed. Braking should be produced as negative/regenerative
   torque inside the Leadshine velocity loop; W1P must not flip command sign just
   to brake.
4. Watch Leadshine DC-bus/regeneration/over-voltage alarms and resistor heating.
   A long or heavy downhill run may exceed the internal regenerative resistor's
   energy capacity and require the drive manufacturer's external regenerative
   resistor arrangement.
5. Repeat in both cable directions and at the maximum intended payload only after
   the low-energy tests are stable.

## CTRL <-> CTRL-TS preset-name check

- Set Preset Names = **Short Names** and confirm SRVR Top View, Side View and
  CTRL-TS all show `P1`...`P10` consistently.
- Set Preset Names = **Long Names**, edit several preset names in SRVR, and
  confirm the same long labels appear on both SRVR diagrams and CTRL-TS.
- Confirm changing name display mode does not change preset positions or motion.

## CTRL <-> CTRL-TS RS485 / OTA

- Continuity: EdgeBox pin 7 -> Waveshare A; pin 8 -> Waveshare B; no A/B short.
- About 60 ohms across A/B when both 120-ohm endpoint terminations are active.
- Verify bootstrap/SHA mismatch performs stable FW_BEGIN/FW_BLOCK/FW_END transfer,
  exact SHA verification, reboot and a fresh HELLO/COMPATIBLE session.
- Verify stale detected TS identity clears after link timeout.

## W1P <-> Leadshine

- Use the custom RS485 mapping, not a straight-through RJ45 cable.
- EdgeBox pin 7 -> Leadshine 485+; EdgeBox pin 8 -> Leadshine 485-; intended
  far-end termination present.
- Confirm P05.29=4, P05.30=6, P05.31=1 and restart the drive after changes.
- Operational link must become Connected at 115200 8N1 slave 1.
- Verify Modbus exceptions are reported as exceptions, a failed velocity write
  cannot trigger stale PR0, and the independent 500 ms VEL watchdog stops/inhibits
  the drive.

## Release acceptance

Do not treat the source ZIP alone as a proven machine release. Preserve the
GitHub Complete Release ZIP/checksums and the successful bench logs for
CTRL/CTRL-TS, W1P/EL7, predictive limits and incline Speed-mode testing.
