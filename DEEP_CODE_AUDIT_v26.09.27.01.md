# HV P2P v26.09.27.01 Deep Code Audit

## Scope
This audit covers the reconstructed source release from SRVR through CTRL,
CTRL-TS and W1P, including the two RS485 links, firmware authority, W1P safety,
build orchestration and frozen-application packaging. It is a source-level audit;
GitHub Actions remains the authoritative native ESP32/Qt compiler and physical
machine tests remain commissioning gates.

## Safety invariants preserved
- W1P retains the independent 650 ms VEL freshness watchdog.
- W1P OTA/reboot/service operations require command zero, drive writes locked,
  software Servo Enable inhibited, verified EL7 feedback, near-zero observed
  speed, SRV-ST OFF and BRK-OFF OFF on consecutive fresh samples.
- Virtual Position Source never emits non-zero physical W1P velocity and never
  restores physical Servo Enable.
- Missing/stale firmware authority is a safety source, not merely a warning.
- New W1P sessions cannot inherit stale RS485 or authority health.
- Same-version firmware requires exact SHA match; newer field firmware is not
  automatically downgraded.

## CTRL <-> CTRL-TS RS485 review
The code uses the documented two-wire half-duplex topology. CTRL uses EdgeBox
hardware RTS direction control. CTRL-TS only responds in master response slots.
The updater is bounded by a 3072-byte protocol payload maximum, uses 1024-byte
firmware chunks and 4096-byte UART RX buffers. At 115200 baud a conservative
~1088-byte framed transfer occupies about 94.4 ms on the wire, leaving ample
receive-buffer headroom. Master/slave turnaround is 2.5 ms.

Updater state was reviewed for lost FW_READY/FW_ACK/FW_RESULT, stale response
sequence, duplicate blocks, duplicate FW_BEGIN, duplicate REBOOT, interrupted
transfer and post-finalization reboot. Advancement requires the exact outstanding
sequence and exact expected next offset.

## W1P <-> Leadshine review
Normal operation is 115200 8N1 Modbus RTU, slave 1. The inter-frame gap is 2.0 ms.
The configuration sweep stops on the first real transport failure so a dead link
cannot monopolise the loop through all configuration registers. The diagnostic
factory probe is read-only at 38400 8N2 and is gated by fail-safe stationary
conditions; it restores 115200 8N1 and the prior link state before returning.

The W1P safe-service gate still performs fresh post-stop EL7 reads and requires
stable near-zero speed, Servo Enable output OFF and brake release output OFF.

## Firmware authority review
SRVR refuses to serve an incomplete/tampered firmware bundle. Manifest/image
identity is bound to schema, authority, release, role, hardware target, exact
size and SHA-256. CTRL/W1P additionally scan the received native image for their
embedded role/target/version identity before finalising the OTA partition.

## Source/build validation completed before sealing
The master source runner completed with `ALL_SOURCE_CHECKS_PASS`, including:
- 316 EdgeBox/source integration checks;
- RS485 framing host CRC contract;
- CTRL-TS updater retry/idempotence contract;
- CTRL-TS target gate;
- CTRL-TS transport/buffering/timing contract;
- splash rendering contract;
- Leadshine commissioning contract;
- SRVR automatic OTA contract;
- SRVR authority server/tamper rejection;
- native build orchestration simulation;
- build pipeline validation (50 checks);
- Modbus CRC contract;
- SRVR wire protocol;
- Speed-mode contract;
- release consistency;
- source hygiene;
- Python syntax;
- SRVR project preflight.

The PySide6 backend runtime regression is included in both GitHub desktop build
jobs and executes there after PySide6 is installed. PySide6 is not installed in
the local source-audit environment, so that runtime test is not claimed as a
local pass. Native Arduino and frozen Qt builds are likewise GitHub gates.

## Release decision
No additional source defect was found that justified altering the locked UI or
motion model. The release is suitable to submit to GitHub Actions. It is not
considered a proven machine release until GitHub native compilation passes and
bench commissioning confirms both RS485 links and the safe motion interlocks.
