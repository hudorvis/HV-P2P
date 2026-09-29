# HV P2P v26.09.29.01 Audit Closure

## Scope
This release closes the source-level findings from the full v26.09.27.01 audit
covering SRVR, CTRL EdgeBox, W1P EdgeBox, CTRL-TS Waveshare, both RS485 links,
OTA authority, startup/recovery, safety-state propagation and the native build
pipeline. GitHub Actions remains the authoritative native compiler and physical
motion remains a bench/commissioning gate.

## W1P <-> Leadshine EL7-RS
Retained correct contracts:
- EdgeBox UART1: TX17 / RX18 / RTS8, ESP-IDF RS485 half-duplex;
- 115200 8N1, slave ID 1;
- Modbus CRC16 polynomial/byte order;
- 2.0 ms inter-frame gap, 50 ms reply timeout and three read attempts;
- P05.29=4, P05.30=6, P05.31=1 expectations;
- safe read-only 38400 8N2 factory-framing diagnostic;
- independent ~650 ms velocity-command freshness watchdog;
- stopped/braked/Servo-Enable-inhibited service gate.

Closed defects:
- FC06/FC16 exception responses are decoded as five-byte exception frames;
- no double-counting of a single write failure at two stack levels;
- PR0 trigger cannot follow a failed velocity write;
- PR emergency stop gets a bounded best-effort attempt despite prior link-health
  state;
- SRVR and real W1P STATUS now agree on DO2..DO5 safety configuration fields.

Hardware note retained: the EdgeBox RS485 RJ45 pair must be custom-mapped to the
Leadshine 485 pair; it is not a straight-through RJ45 data cable. Independent
hardwired torque-disable/STO remains a future hardware safety recommendation
because a completely broken RS485 cable cannot carry a software stop command.

## CTRL EdgeBox <-> CTRL-TS Waveshare
Retained correct contracts:
- CTRL: TX17 / RX18 / RTS8 hardware half-duplex;
- CTRL-TS: RX15 / TX16, automatic transceiver direction;
- 115200 8N1;
- 4096-byte RX buffers;
- 1024-byte firmware blocks;
- 2.5 ms turnaround guard;
- framed protocol with sequence and CRC32;
- exact version/SHA compatibility;
- idempotent FW_BEGIN/FW_BLOCK/FW_END/reboot recovery.

Additional closure:
- normal EVENT frames are correlated to the outstanding POLL sequence;
- every CTRL-TS boot requires a new HELLO/COMPATIBLE session;
- stale CTRL-TS identity is cleared on CTRL link timeout;
- updater status no longer fights the boot-state ticker;
- real 0-100% splash progress bar added;
- display/PSRAM faults retain a headless RS485 update path;
- Run screen vertical geometry fills the native 800x480 panel with equal top and
  bottom margins.

## Build/OTA
CTRL/W1P and CTRL-TS all use sketch-local dual-OTA partition tables. The native
builder now explicitly selects `PartitionScheme=custom` for EdgeBox as well as
CTRL-TS. Source CTRL intentionally retains its hard build guard until GitHub has
built the exact CTRL-TS binary and generated the carrier header.

No native ESP32 binaries or desktop applications were fabricated locally.
