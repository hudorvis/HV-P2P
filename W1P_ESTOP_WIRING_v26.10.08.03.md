# W1P AI0 5 V E-stop wiring — v26.10.08.03

## Firmware contract

W1P reads its local E-stop status from **EdgeBox AI0** using the onboard SGM58031. The input is fail-closed:

- 3.5–6.0 V for three consecutive samples -> local W1P E-stop **clear**.
- Open circuit / 0 V / low or mid-band voltage / over-range -> local W1P E-stop **active**.
- ADC/I2C/configuration failure -> local W1P E-stop **active**.
- E-stop assertion occurs on the next 10 ms sample; clearing requires three healthy samples.
- Clearing the local E-stop does not re-enable the servo. SRVR still owns neutral-return re-arm.

## Required analogue-input hardware

This release assumes W1P AI0 is configured as a **voltage input**, the same as the commissioned CTRL EdgeBox. The factory EdgeBox analogue input is normally a 4–20 mA input; for the project's 0–5 V wiring, the AI0 249-ohm current shunt must be removed or the EdgeBox must be the 0–10 V hardware option.

Do not connect the 5 V loop to a factory/current-mode AI0 and assume the firmware conversion is valid.

## Connector wiring

Using the pin numbering printed on the commissioned EdgeBox used in this project:

- **Pin 14 = AI0**
- **Pin 12 = AGND**
- Pins 21/22 are also AGND.

```text
Regulated isolated 5 V supply

+5 V  ---- normally-closed E-stop contact ---- AI0, pin 14
 0 V  ---------------------------------------- AGND, pin 12
```

Use **AGND** as the return. Do not use PGND, main-power GND, `DO_GND`, or the 24 V digital-input `S/S` terminal as the AI0 reference.

## Bench test

1. Power W1P with AI0 open. It should report `E-Stop W1P`; the servo must remain inhibited and DO0 brake release must remain unavailable.
2. Apply the regulated 5 V NC loop to AI0/AGND. After three healthy samples (normally tens of milliseconds), W1P may report the local E-stop clear, but servo re-arm still requires the established SRVR neutral sequence.
3. Open the loop. W1P must assert its local E-stop on the next sample, stop motion, lock drive writes and request software Servo Enable inhibit.
4. Disconnect or fault the SGM58031/I2C path during a controlled bench test. The result must be E-stop active, not healthy.
5. Confirm the serial diagnostic reports AI0 near the actual 5 V field level. If it reports roughly half/double the expected value, stop and verify the EdgeBox analogue-input hardware option/shunt configuration before motion testing.

This software status input is not a substitute for a safety-rated STO/safety-relay chain where one is required by the final machine risk assessment.
