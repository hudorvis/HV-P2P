# HV P2P v26.09.29.04 change summary

## CTRL analogue-input mapping finalisation
- Swapped the commissioned CTRL analogue inputs as requested: **AI0 / pin 14 = 5 V NC E-stop status**, **AI1 / pin 16 = APEM joystick signal**.
- The SGM58031 now leaves AI1 running continuously at 800 SPS for the filtered joystick path, briefly switches to AI0 every 50 ms for fail-unsafe E-stop sampling, then restores AI1.
- Updated serial diagnostics, commissioning/wiring documentation and regression checks to make the mapping unambiguous.
- No other motion, RS485, HMI, watchdog, calibration or UI behaviour was intentionally changed from v26.09.29.03.

---

## Basis
Built directly from v26.09.29.02. Native ESP32/desktop compilation remains a
GitHub Actions gate; this source package is not a locally fabricated native build.

## CTRL analogue input commissioning
- CTRL joystick is now on EdgeBox AI1 (physical multifunction-connector pin 16).
- CTRL E-stop status uses **AI0 pin 14** so
  the existing regulated 5 V CTRL supply can be used.
- AI0 is wired as a 5 V normally-closed loop: >=3.5 V is healthy; low/open/mid-band
  is unsafe. Assertion is immediate; clearing requires three consecutive healthy
  samples. ADC/read/configuration failure fails unsafe.
- Documentation records the commissioned EdgeBox modification: factory 249-ohm
  4-20 mA shunts removed, retained divider used for voltage input.

## Joystick stability and operator readout
- AI1 now uses an **8-sample trimmed mean** at 800 SPS: the highest and lowest
  conversions are discarded and the remaining six are averaged before the existing
  light 0.70/0.30 IIR filter. This improves noise/spike rejection without adding a
  large slow filter.
- SRVR Setup / CTRL adds **Current Percentage** directly below Current Value. It
  displays calibrated physical stick position as -100.0% .. 0.0% .. +100.0%.
- New/reset SRVR configurations default CTRL Direction to **Inverted** as requested.
  Saved/imported configurations remain authoritative.

## Faster motion-command deadman
- W1P independent VEL freshness watchdog reduced from 650 ms to **500 ms**.
- SRVR unchanged non-zero VEL refresh tightened from 250 ms to **150 ms**, retaining
  multiple refresh opportunities within the shorter watchdog window.
- The watchdog remains independent of STATUS/PING traffic and retains the existing
  stop / write-lock / software Servo Enable inhibit behaviour.

## Retained v26.09.29.02 fixes
All prior W1P/Leadshine Modbus sequencing, exception, RS485 recovery, CTRL-TS
session/updater, splash progress, headless recovery, full-height Run UI and EdgeBox
partition-menu fixes are retained unchanged.
