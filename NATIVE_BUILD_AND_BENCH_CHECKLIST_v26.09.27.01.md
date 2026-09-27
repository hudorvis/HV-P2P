# HV P2P v26.09.27.01 Native Build and Bench Checklist

## GitHub Actions gates
- Source/protocol regression suite passes.
- CTRL-TS native firmware builds first.
- Exact CTRL-TS application is embedded into staged CTRL and verified.
- CTRL and W1P native applications compile and retain role/target/version tokens.
- Immutable SRVR_FIRMWARE_BUNDLE is produced from those exact CTRL/W1P apps.
- Source checkout hash is identical before/after native firmware build.
- macOS Intel SRVR builds and frozen smoke test passes with external firmware
  bundle removed.
- macOS Apple Silicon SRVR does the same.
- Windows x64 builds under MSVC/Nuitka 4.2, PE machine is AMD64 0x8664, and the
  frozen executable smoke test passes with the external firmware bundle removed.
- COMPLETE_RELEASE is created only after all four jobs succeed.

## Powered-off wiring checks
CTRL <-> CTRL-TS:
- continuity EdgeBox pin 7 to Waveshare A;
- continuity EdgeBox pin 8 to Waveshare B;
- no A/B short;
- expected A-B resistance around 60 ohms when both 120-ohm terminations are active.

W1P <-> Leadshine:
- custom cable, not straight-through RJ45;
- EdgeBox pin 7 to Leadshine CN3 pin 1 (485+);
- EdgeBox pin 8 to Leadshine CN3 pin 2 (485-);
- verify actual-drive CN3 1<->4 and 2<->5 continuity before relying on duplicated
  pairs described by newer Leadshine documentation;
- confirm intended far-end termination.

## Leadshine settings
Confirm on the actual EL7 and restart after changes:
- P05.29 = 4 (8N1)
- P05.30 = 6 (115200)
- P05.31 = 1 (slave ID 1)

## CTRL-TS updater bench proof
With CTRL and CTRL-TS manually commissioned from the same GitHub build:
- CTRL discovers the expected WS-ESP32S3-7 target and protocol.
- A bootstrap/same-version wrong-hash CTRL-TS is considered incompatible.
- CTRL enters firmware transfer only after CTRL itself exactly matches SRVR.
- Observe FW_BEGIN -> FW_READY -> FW_BLOCK/FW_ACK progression -> 100% -> FW_END
  -> FW_RESULT -> REBOOT.
- After reboot CTRL-TS reports the real native SHA and SRVR shows Link Active.
- Pull/reconnect RS485 only with the machine safe; verify link loss fails closed
  and a clean reconnect requires current compatibility/status.

## W1P / EL7 bench proof
Keep machinery mechanically unable to move for the first test.
- W1P reports exact SRVR firmware match before physical operation is allowed.
- Operational EL7 link becomes Connected at 115200 8N1 slave 1.
- If it does not, inspect W1P diagnostic output for a 38400 8N2 factory-comms
  detection before changing wiring or drive parameters.
- Confirm the 650 ms VEL watchdog independently stops and inhibits the drive.
- Confirm peer timeout, E-stop, RS485 loss and malformed/stale STATUS remain
  fail-closed.
- Confirm OTA/service refuses to proceed unless stopped, Servo Enable OFF and
  brake release OFF are freshly proven.

## Release acceptance
Do not treat the source ZIP alone as a proven hardware release. Preserve the
GitHub Complete Release ZIP and its checksum byte-for-byte, then retain the
first successful CTRL/CTRL-TS and W1P/EL7 commissioning logs with the release.
