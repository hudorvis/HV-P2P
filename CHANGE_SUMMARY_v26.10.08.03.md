# HV P2P v26.10.08.03 change summary

Date: 2026-10-08

Source baseline: **v26.10.08.02**. The approved 38400/8N2 Leadshine link, EdgeBox DO0 brake control, CTRL-TS marker smoothing, updater, motion, calibration, AUX, limits and all unrelated project behaviour remain locked.

## Only functional change — W1P local E-stop input

W1P local E-stop status has moved from the EdgeBox 24 V digital input `DI0` to the isolated analogue input **AI0**, matching the commissioned CTRL 5 V status-loop approach.

W1P now uses the onboard **SGM58031 at I2C 0x48**, with AI0 selected continuously at 800 SPS. Firmware samples the channel every 10 ms and interprets the reconstructed field voltage as:

- **3.5 V to 6.0 V**: healthy sample.
- **Below 3.5 V, above 6.0 V, open circuit or mid-band**: E-stop active.
- **ADC/I2C/configuration failure**: E-stop active.
- Clearing requires **3 consecutive healthy samples**; assertion is immediate on the next sample.
- ADC recovery is retried while remaining fail-closed; recovery still needs three new healthy samples before the E-stop can clear.

`WinchState.local_estop` now initializes `true`, so W1P is fail-closed from construction/startup until AI0 is proven healthy. The existing E-stop stop path is unchanged: `driveStopNow()`, drive writes locked, and software Servo Enable inhibited. A cleared local E-stop never re-enables torque by itself; SRVR neutral re-arm remains authoritative.

## W1P AI0 hardware / wiring requirement

This firmware expects W1P AI0 to use the **same voltage-input hardware arrangement as CTRL**: the factory 249-ohm 4–20 mA shunt for AI0 must be removed, or the EdgeBox must be the 0–10 V AI hardware option.

On the commissioned connector labelling:

- **Pin 14 = AI0**
- **Pin 12 = AGND** (pins 21/22 are also AGND)

Wire the normally-closed 5 V status loop as:

```text
5 V +  ---- E-STOP NC contact ---- EdgeBox AI0 pin 14
5 V 0 V -------------------------- EdgeBox AGND pin 12
```

Use **AGND**, not PGND/GND/DO_GND, for the analogue return.

## Preserved v26.10.08.02 behaviour

- W1P ↔ EL7 operational Modbus remains **38400 baud / 8N2 / ID 1**.
- EdgeBox **DO0 / GPIO40** remains the physical 24 V holding-brake switch, fail-applied LOW/off, while EL7 logical `BRK-OFF` remains the timing authority.
- CTRL → W1P → CTRL-TS update ordering and the CTRL-TS update-status rows remain unchanged.
- CTRL, CTRL-TS and SRVR production behaviour is unchanged apart from release identity.

## Validation added/updated

- `test_w1p_estop_ai0_100803.py` locks the AI0/5 V E-stop contract and established stop/Servo-inhibit path.
- `validate_edgebox_integration.py` now hash-locks the W1P AI0 ADC acquisition and E-stop decision functions.
- Existing DO0 brake, Leadshine communication, updater, motion, calibration, AUX and historical regression contracts remain in the complete source runner.
