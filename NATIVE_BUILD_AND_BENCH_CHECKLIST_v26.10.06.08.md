# HV P2P v26.10.06.08 native build and bench checklist

## GitHub build

- [ ] Native CTRL-TS compile passes.
- [ ] Native CTRL compile passes with staged CTRL-TS image.
- [ ] Native W1P compile passes.
- [ ] SRVR Intel macOS build/smoke passes.
- [ ] SRVR Apple Silicon build/smoke passes.
- [ ] SRVR Windows x64 build/smoke passes.
- [ ] Release manifest/checksums pass.

## Locked-regression checks

- [ ] `.06.07` automatic CTRL -> W1P -> CTRL-TS update behavior remains normal.
- [ ] CTRL-TS AUX two-tap confirmation remains deterministic.
- [ ] Joystick / Limit / Winch calibration remains transactional/safe.
- [ ] W1P independent 500 ms VEL watchdog remains unchanged.
- [ ] AI0 E-stop / AI1 joystick mapping remains correct.

## CTRL-TS progress marker

- [ ] Run at low speed: marker moves continuously along the cable path.
- [ ] Run at high speed: marker remains visually fluid with no forward overshoot followed by a backward correction.
- [ ] Reverse direction: marker transitions cleanly and then moves smoothly in the new direction.
- [ ] Stop: marker settles to the verified position without continued prediction/drift.
- [ ] Numeric Current Position remains correct and is not visually predicted.

## Ramping state

- [ ] Mid-span outside ramp zones: `System | Active` green.
- [ ] Enter Near ramp while moving: `System | Ramping` yellow.
- [ ] Stop inside Near ramp but >1.0 m from Near: remains `System | Ramping` yellow.
- [ ] Within 1.0 m of Near: `System | Near Limit` yellow.
- [ ] Repeat equivalent Far-ramp / Far-limit checks.
- [ ] Genuine E-stop/fault still overrides with red.

## W1P Encoder / Leadshine controlled commissioning

Before powered movement, verify against the current EL7-RS manual and installation wiring:

- [ ] EdgeBox RS485 A/B wired to the correct EL7-RS differential pair; shield/reference arranged per the final wiring design.
- [ ] EL7 RS485 address = 1.
- [ ] EL7 RS485 = 115200 baud, 8 data bits, no parity, 1 stop bit.
- [ ] PR internal-command mode is accepted/verified by W1P.
- [ ] W1P STATUS reports RS485/configuration/drive feedback healthy.
- [ ] Servo Ready feedback is present before enabling motion.
- [ ] Confirm motor direction with a very low commanded speed and safe unloaded mechanics.
- [ ] Verify units-per-metre/encoder direction before trusting absolute position or limits.
- [ ] Confirm STOP/E-stop and the independent 500 ms W1P VEL watchdog before higher-speed testing.
- [ ] Perform Limit Calibration only after direction/scaling feedback has been verified.

Native firmware binaries must come from GitHub Actions; do not substitute locally fabricated binaries for the release artifacts.
