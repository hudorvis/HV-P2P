# HV P2P W1P direct motor-brake wiring — v26.10.08.03

## Scope

The Leadshine `ELM2M-2000LB130E-H` 24 V spring-applied holding-brake coil is switched by **W1P EdgeBox DO0**. The `EL7-RS2000P` still owns the logical brake timing: DO4 remains configured as `BRK-OFF`, W1P reads that live state over Modbus (`P08.47`), and the physical EL7 DO4 terminal is not used to carry brake current.

## EdgeBox connector pins

On the EdgeBox ESP-100 24-pin multi-function connector:

- **Pin 1 — DO_24V**: +24 V supply for the isolated digital-output bank.
- **Pin 3 — DO_GND / DO_0V**: 0 V supply/reference for the isolated digital-output bank.
- **Pin 5 — DO0**: low-side switched brake return, mapped to GPIO40.
- **Pin 23 — +24V_IN** and **Pin 24 — GND/PGND** are the EdgeBox main supply terminals and are separate from the DO-bank supply pins.

**Do not wire the brake coil between DO0 and DO_GND.** DO0 is the switched return. The coil is wired between +24 V and DO0.

## Wiring

```text
                 24 VDC POWER SUPPLY

 +24 V -------------+----------------------> EdgeBox pin 1  DO_24V
                     |
                     +----------------------> Motor brake +24 V / Pin 2
                                                |
                                                |  brake coil
                                                |
 Motor brake 0 V / Pin 1 ----------------------+-------> EdgeBox pin 5  DO0

 0 V ------------------------------------------> EdgeBox pin 3  DO_GND
```

If one adequately sized 24 V PSU also powers the EdgeBox main input, it may feed pins 23/24 as well as the DO-bank pins 1/3. Pins 1/3 still require their own connections; `DO_24V` is an input supply for the output bank, not a generated 24 V source.

## Brake polarity / E-stop behavior

The brake is spring-applied and electrically released:

- DO0 **HIGH/on** -> coil energised -> **brake RELEASED**.
- DO0 **LOW/off** -> coil de-energised -> **brake APPLIED**.
- EdgeBox/output supply lost -> brake **APPLIED**.

Therefore an E-stop must **not** energise DO0. W1P's stop path removes motion/Servo Enable authority and the physical brake then applies when the EL7's fresh logical BRK-OFF sequence clears. If the EL7 output-status/RS485 path becomes invalid or stale, W1P fails DO0 LOW. DO0 is forced LOW during the earliest startup stage before network, Modbus, updater or motion initialization.

The local W1P E-stop remains active, but v26.10.08.03 moves its status input to **AI0 / 5 V NC loop**. See `W1P_ESTOP_WIRING_v26.10.08.03.md`. There is no firmware bypass.

## Current estimate

Commissioning resistance measurement: **36.2 ohm**, provided it was taken with the brake unpowered and isolated.

At 24.0 V, simple Ohm's-law estimates are approximately **0.663 A** and **15.9 W**. At 26.4 V, the same resistance gives approximately **0.729 A**. Seeed publishes a 1 A current capacity for the 24 V output section, but public wording does not clearly establish whether that is per channel or total bank capacity. Measure real energized current and check output/connector temperature before relying on direct drive.

## Firmware sequencing

A new brake release requires exact firmware authority, healthy SRVR connection, no local E-stop/watchdog/service lock, healthy/fresh EL7 RS485/config/feedback, software Servo Enable ready, SRDY and SRV-ST asserted, verified DO4=`BRK-OFF`, logical BRK-OFF asserted, and no drive/no-motion fault.

Once released, W1P follows fresh logical BRK-OFF during orderly shutdown rather than immediately applying the holding brake. Only `P08.47` is refreshed at a 25 ms minimum interval during this transition; normal position feedback remains at 100 ms. OTA/reboot/reset waits for two fresh samples proving speed near zero, SRV-ST off, logical BRK-OFF off and physical DO0 off.

## EL7 RS485 settings used by this release

W1P normal operation is **38400 baud, 8N2, Modbus ID 1**, matching `P05.29=5`, `P05.30=4`, `P05.31=1`. If any of those drive parameters are changed, restart the EL7 before expecting the new communication setting to take effect.

## Commissioning checks

1. Confirm the 36.2 ohm resistance was measured with the brake coil unpowered/isolated, then measure actual energized DC current on the bench.
2. Verify boot/reset leaves DO0 off and the brake mechanically applied.
3. Verify normal Servo Enable produces EL7 logical BRK-OFF first, then DO0 on/brake released.
4. Verify normal stop and local E-stop command the established servo stop/inhibit path and the brake applies after the EL7 clears BRK-OFF; loss of RS485/output-status authority must fail DO0 off.
5. Verify OTA/reboot is rejected until DO0 is physically commanded off and the other safe-service proofs pass.
6. Do not treat the motor holding brake, software E-stop path or DO0 output as STO or as a safety-rated emergency braking function.

The EdgeBox examples support solenoid-type digital-output loads, but do not add an arbitrary external flyback diode across the motor brake without checking the brake/drive requirements: a simple diode can alter brake engagement timing.
