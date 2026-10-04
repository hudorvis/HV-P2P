# CTRL Analogue Wiring — v26.10.04.06

The commissioned CTRL EdgeBox uses its onboard SGM58031 with the factory 249-ohm
4-20 mA shunts removed so AI0..AI3 operate as voltage inputs through the retained
10 k / 10 k divider network.

## EdgeBox multifunction connector (as labelled on the physical unit)

- **Pin 12 = AGND**
- **Pin 14 = AI0** — CTRL E-stop 5 V NC status loop
- **Pin 16 = AI1** — APEM joystick signal
- Pin 18 = AI2
- Pin 20 = AI3
- Pins 21 and 22 are also AGND.

## APEM BHN140A01BKBK0500 joystick

Use one complete redundant channel. For channel 1:

- APEM pin 1 -> regulated +5 V
- APEM pin 3 -> 5 V supply 0 V
- APEM pin 4 -> EdgeBox AI1 pin 16
- 5 V supply 0 V -> EdgeBox AGND pin 12

The commissioned joystick measures approximately 0.52 V / 2.60 V / 4.63 V across
its full travel with the EdgeBox voltage-input shunt removed.

## CTRL E-stop status input

Wire a normally-closed status loop from the same regulated 5 V supply:

```text
5 V +  ---- E-STOP NC contact ---- EdgeBox AI0 pin 14
5 V 0 V -------------------------- EdgeBox AGND pin 12
```

The firmware treats AI0 >= 3.5 V (up to 6.0 V) as healthy. Low, open-circuit,
mid-band, ADC failure or channel-selection failure is unsafe/E-stop active. E-stop
assertion is immediate at the next 25 ms CTRL sample; clearing requires three
consecutive healthy samples.

This analogue input is a CTRL status/safety input, not a substitute for an
independent safety-rated hardwired STO/safety-relay chain on a production machine.
