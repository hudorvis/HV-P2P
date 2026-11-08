# HV P2P v26.11.08.01

Approved source package **HV P2P v26.10.19.01 ChatGPT.zip**. Released for source build on 8 November 2026.

## Encoder and RS485 corrections

- SRVR rejects backward, repeated and ambiguous encoder timestamps even when POS_SEQ advances. It accepts forward movement across the 32-bit wrap and keeps the previous validated position and raw counts when it rejects a sample.
- W1P timestamps the validated four-register Modbus reply. Position, velocity interval, sequence and sample age now agree, including samples recorded during stopped/braked service verification. Failed reads leave the last successful sample intact and evaluate staleness at the end of the attempt.
- W1P prints the operational 115200 8N1 startup settings and waits for operational failures before the stopped, read-only 38400 8N2 factory probe. W1P logs readiness using the current feedback poll. SRVR distinguishes startup discovery from sustained faults and publishes detailed diagnostics after DSP1 construction.

## Additional defects corrected

- Malformed counts can no longer commit position without its matching raw value. SRVR ignores positions marked NONE, reseeds from the next accepted sample after leaving Virtual, and clears session-local counts and staged calibration at a W1P session boundary. Winch calibration requires fresh raw counts.
- SRVR uses monotonic time for motion-link freshness, velocity keepalive, the display send cadence and explicit position-sync grace. Non-finite A6/A7 joystick values fail validation before they can become live inputs.
- CTRL preserves the existing AUX and calibration-cancel pulses, RS485 recovery quiet time and safe reboot hold across clock wrap. CTRL-TS preserves the confirmation hold and update/splash deadlines across the same boundary.
- A genuine W1P reply at millisecond zero counts as valid feedback. Brake hold still requires valid output feedback within its configured age limit.

The shipped audit and test logs describe the source evidence. GitHub compilation and physical commissioning are separate stages.
