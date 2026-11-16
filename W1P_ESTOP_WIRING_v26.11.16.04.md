# W1P 24 V E-Stop and brake wiring — v26.11.16.04

The W1P EdgeBox ESP-100 uses **DI0** for its 24 V normally closed E-Stop
input and **DO0** for the Leadshine motor holding-brake release.

## Common POS and GND buses

Match the printed signal names on the EdgeBox. The pin numbers below
follow the enclosure label, Seeed's schematic and its Arduino wiki.

| From | To |
|---|---|
| POS bus (+24 VDC) | EdgeBox `+24V_IN` pin **23** and `DO_24V` pin **1** |
| GND bus (PSU 0 V) | EdgeBox `PGND` pin **24**, `DO_GND` pin **3**, and `S/S` pin **2** |
| POS bus | First terminal of the E-Stop's normally closed contact |
| Second terminal of the E-Stop contact | EdgeBox `DI0` pin **4** |
| POS bus | Leadshine motor holding brake red (+) |
| EdgeBox `DO0` pin **5** | Leadshine motor holding brake black (−), the switched return |

The E-Stop button uses a two-core cable. `S/S` is the digital input common and
connects to the GND bus in the rack. The same adequately sized 24 VDC supply
can feed both the EdgeBox main power input and its separate digital output
supply terminals. The EL7's logical BRK-OFF timing reaches W1P over Modbus.
See [W1P brake wiring](W1P_BRAKE_WIRING_v26.11.16.04.md) for the coil load
and brake sequence.

## Firmware and commissioning

Install the matched v26.11.16.04 release to use the DI0 input. The preceding
v26.11.16.02 release reads its E-Stop contact on AI0 with a 5 V loop. Route
the new 24 V stop signal only to the labelled DI0 terminal.

W1P starts with its E-Stop active and the brake applied. The optocoupled
input reads high while the NC loop supplies 24 V. Pressing the button, an
open wire, or loss of the field loop's supply drops the input. W1P asserts
the stop on the first open sample, locks drive writes and requests servo
inhibit. Release requires three consecutive healthy samples and the standard
SRVR joystick-neutral re-arm before servo enable.

With the winch unloaded and isolated from motion hazards, verify a startup
with DI0 open, press and release, an open wire, and loss of the 24 V field
signal. Check that SRVR logs W1P-ES and the brake operates with the intended
EL7 timing. Use an independent hardwired safety circuit for the winch's
safety-rated E-Stop function.
