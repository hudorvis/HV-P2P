# CTRL Joystick Wiring — v26.09.29.01

The CTRL EdgeBox must be the **0-10 V analogue-input option**. The firmware reads **AI0** through the onboard SGM58031.

## Functional wiring

| Connection | Wire to |
|---|---|
| External regulated +5 V | Joystick +5 V / Vcc only |
| External 5 V supply 0 V | Joystick 0 V **and** EdgeBox **AGND** |
| Joystick single-axis analogue output | EdgeBox **AI0** |

## EdgeBox terminal numbers

Seeed's EdgeBox ESP-100 user manual labels the 24-pin multifunction terminal as:
- **Pin 13 = AI0**
- **Pin 11 = AGND**
- **Pins 21/22 = AGND** (internally common with the other AGND)
- **Pin 23 = GND** is isolated from AGND and is **not** the joystick analogue return.

A simple commissioning connection is therefore:

```text
5 V PSU +  --------------------> APEM joystick +5 V / Vcc
5 V PSU 0 V ----+--------------> APEM joystick 0 V
                +--------------> EdgeBox AGND (pin 11, 21 or 22)
APEM axis OUT ------------------> EdgeBox AI0 (pin 13)
```

Do not feed the joystick output into a digital input, and do not connect the joystick return to the isolated EdgeBox GND instead of AGND.

The exact APEM connector pin number / wire colour depends on the joystick model and termination option. Use the joystick's datasheet labels for **+5 V**, **0 V**, and the required single-axis output; do not infer those three pins solely from connector orientation.

After wiring, use the SRVR joystick calibration wizard to capture Left / Centre / Right. The CTRL serial monitor command `J` also prints AI0 and estimated field voltage for commissioning.
