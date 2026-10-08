# HV P2P v26.10.08.02 deep code audit

## Scope lock

Source baseline: `v26.10.06.11`.

Functional production edits are limited to:

1. W1P operational EL7 Modbus format changed from 115200/8N1 to the factory 38400/8N2, ID 1 expectation.
2. W1P EdgeBox DO0 physical motor-brake control while retaining EL7 logical BRK-OFF timing authority.
3. W1P telemetry addition `BRAKE_DO0` and SRVR validation/use of it as the physical brake-release state.
4. Release identity/build metadata, focused regression tests and documentation.

CTRL and CTRL-TS production logic remains unchanged apart from release identity. The `.06.11` DMP1/HMP1 marker path is retained. W1P DI0 E-stop remains active and unchanged as an independent local stop input.

## EL7 RS485 audit

Normal W1P Modbus is `38400`, `SERIAL_8N2`, slave ID 1. Configuration validation requires `P05.29=5`, `P05.30=4`, `P05.31=1`. These values match the EL7-RS factory communication defaults.

The old 115200/8N1 setting exists only in `serviceLeadshineFactoryCommsProbe()` as a bounded read-only diagnostic fallback. `leadshineFactoryProbeSafe()` requires drive writes disabled, software Servo Enable inhibited, no active service operation and all commanded/profiled/measured motion near zero before the fallback can run. It restores 38400/8N2 immediately and restores all saved link-health counters so a diagnostic response cannot become operational authority.

## Hardware/output audit

- EdgeBox DO0 is GPIO40.
- Multi-function connector is documented as pin 1 `DO_24V`, pin 3 `DO_GND`, pin 5 `DO0`.
- DO0 is initialized LOW before Serial, Ethernet, Modbus, OTA or motion startup.
- LOW/off means coil de-energised / spring brake applied.
- HIGH/on means coil energised / brake released.
- The Leadshine physical DO4 terminal no longer carries the brake coil; DO4 remains configured as logical `BRK-OFF` for timing/state verification.

## Brake release/application audit

`edgeboxBrakeReleaseStartAllowed()` requires the existing firmware, communications, watchdog, service and drive health prerequisites plus fresh full EL7 feedback, software Servo Enable ready, SRDY, SRV-ST, verified DO4=`BRK-OFF`, asserted logical BRK-OFF, and no EL7 alarm/no-motion fault.

An orderly stop does **not** immediately force a released holding brake on. `edgeboxBrakeReleaseHoldAllowed()` follows fresh logical EL7 BRK-OFF so the servo can complete its native stop/brake timing. `serviceLeadshineBrakeTransitionStatus()` refreshes only `P08.47` at a 25 ms minimum interval while that transition matters; it does not alter the locked 100 ms normal position-feedback cadence. Invalid/stale output status or lost RS485 authority fails the hold gate and turns DO0 off.

The raw P08.47 BRK-OFF bit is stored independently from DO4 configuration validity. A new release still requires the mapping to be verified, while a transient later configuration-read failure does not itself force premature brake application if previously verified mapping and fresh live BRK-OFF sequencing remain authoritative.

## Local E-stop audit

There is **no W1P E-stop bypass** in this release. `updateLocalInputs()` reads `PIN_LOCAL_ESTOP`, treats a non-healthy level as active, calls `driveStopNow()`, locks drive writes and requests software Servo Enable inhibit. `edgeboxBrakeReleaseStartAllowed()` explicitly rejects a local E-stop, and the shutdown sequencer treats local E-stop as a brake-shutdown condition.

## Service/OTA audit

`hvPrepareSafeServiceState()` retains service re-arm, STOP, drive-write lock, Servo Enable inhibit and fresh feedback proof. It additionally services the EdgeBox brake output and requires two consecutive post-stop samples proving measured speed <= 0.05 m/s, SRV-ST off, logical BRK-OFF off and EdgeBox DO0 brake release off. OTA/reboot/NVS/network-readdress operations therefore cannot proceed solely from intended software state.

## Firmware update status audit

CTRL and W1P emit `FW_PROGRESS` to SRVR. CTRL also emits direct `FWSTAT` to CTRL-TS while its update loop is occupied. SRVR tracks CTRL/W1P update phase and percentage and includes both in DSP1; CTRL forwards those fields in priority HMS1; CTRL-TS consumes them and renders the CTRL and W1P rows. Coordinator ordering remains CTRL first, W1P second and CTRL-TS final, preserving touchscreen visibility during the two field-controller updates.

## Telemetry/SRVR audit

`BRAKE_OUT` remains the EL7 logical BRK-OFF state and `BRAKE_DO0` is the physical EdgeBox command. SRVR validates both boolean fields and uses `BRAKE_DO0` for `winch_brake_released`.

## Current/headroom note

The commissioning resistance measurement of 36.2 ohm implies approximately 0.663 A at 24 V and 0.729 A at 26.4 V using a simple resistance calculation. That is below Seeed's product-level published 1 A output capacity, but the public wording does not clearly specify a separate 1 A rating per channel versus the output bank. Real current, voltage drop and thermal behavior therefore remain mandatory bench checks before relying on direct brake drive.

## Focused verification

- `test_w1p_edgebox_brake_do0_1008.py` locks pin/polarity, startup fail-safe, release gate, hold sequencing, transition-only P08.47 polling, service proof and SRVR physical-state telemetry.
- `test_w1p_estop_active_1008.py` proves the local DI0 E-stop remains active and still enters the established stop/Servo-inhibit path.
- `test_leadshine_commissioning_contract.py` locks operational 38400/8N2/ID1 and the non-authoritative legacy diagnostic probe.
- `test_full_system_update_status_1008.py` proves CTRL and W1P progress reaches the CTRL-TS status UI and that CTRL-TS remains the final update stage.
- `validate_edgebox_integration.py` normalized-hash locks the reviewed E-stop, brake and safe-service functions while preserving the established motion/control contracts.
