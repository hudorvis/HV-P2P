# HV P2P v26.09.29.02 Native Build and Bench Checklist

## GitHub Actions gates
- Source/protocol regression suite passes, including `test_audit_regressions.py`.
- CTRL-TS builds first.
- Exact native CTRL-TS application is embedded into staged CTRL and verified.
- CTRL/W1P use the supported EdgeBox `PartitionScheme=app3M_fat9M_16MB` FQBN value while their sketch-local `partitions.csv` supplies the actual 6 MB dual-OTA layout; both retain role/target/version
  identity tokens.
- Immutable SRVR firmware authority bundle is generated from those exact apps.
- Source checkout hash is identical before/after native firmware build.
- macOS Intel, macOS Apple Silicon and Windows x64 frozen SRVR jobs all pass.
- Complete Release is created only after all required jobs succeed.

## CTRL / joystick bench
- Confirm EdgeBox is the 0-10 V analogue-input option.
- +5 V -> APEM pin 1; 0 V -> pin 3; output pin 4 -> EdgeBox AI0 pin 14;
  same 0 V -> EdgeBox AGND pin 12 or 22.
- Confirm digital GND pin 24 is not being used as the analogue reference.
- Check CTRL serial diagnostic shows SGM58031 detected at 0x48.
- Verify near 0/2.5/5 V field readings across joystick travel, then run SRVR
  Set Left / Set Centre / Set Right calibration.

## CTRL <-> CTRL-TS
Powered off:
- continuity EdgeBox pin 7 -> Waveshare A;
- continuity EdgeBox pin 8 -> Waveshare B;
- no A/B short;
- approximately 60 ohms across A/B when both endpoint 120-ohm terminations are
  active.

Powered bench test:
- CTRL-TS reports PSRAM diagnostics and valid 800x480 display.
- Bootstrap/SHA mismatch triggers stable FW_BEGIN/FW_READY/FW_BLOCK/FW_ACK
  progression with a graphical 0-100% progress bar.
- FW_END verification completes, reboot occurs, and fresh HELLO reports the new
  exact version/SHA.
- Fast CTRL-TS reboot forces a new HELLO/COMPATIBLE session; stale normal POLL
  traffic must not bypass compatibility.
- Unplug/reconnect only with machine safe; stale detected version is cleared on
  CTRL timeout and clean reconnection revalidates identity.

## W1P <-> Leadshine
Powered off:
- custom RJ45 mapping, not straight-through;
- EdgeBox pin 7 -> Leadshine 485+ (CN3 1/4 pair);
- EdgeBox pin 8 -> Leadshine 485- (CN3 2/5 pair);
- intended far-end termination present.

Leadshine settings and powered bench:
- P05.29 = 4, P05.30 = 6, P05.31 = 1; restart drive after changes.
- Operational link becomes Connected at 115200 8N1 slave 1.
- Confirm a valid Modbus exception is reported as an exception, not a wiring
  timeout.
- Confirm a deliberately failed velocity write cannot be followed by PR0 trigger.
- Confirm the 650 ms VEL watchdog independently stops and inhibits the drive.
- Confirm peer timeout, E-stop, malformed/stale status and RS485 loss remain
  fail-closed.
- Confirm OTA/service refuses to proceed unless stopped, Servo Enable OFF and
  brake release OFF are freshly proven.

## Release acceptance
Do not treat this source ZIP alone as a proven hardware release. Preserve the
GitHub Complete Release ZIP/checksum and retain successful CTRL/CTRL-TS and
W1P/EL7 commissioning logs with the release record.
