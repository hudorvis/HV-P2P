# HV P2P v26.10.06.08 change summary

Date: 2026-10-06

Locked baseline: `v26.10.06.07`.

This revision is deliberately narrow. Production changes are limited to the CTRL-TS travel-marker rendering and the canonical SRVR Ramping status semantics. W1P/Leadshine production logic was audited but is functionally unchanged apart from release identity.

## 1. CTRL-TS travel marker is smooth without forward prediction

The `.06.07` display-only smoother predicted the skate marker ahead of the latest verified HMM1 position using measured speed for up to 180 ms. At higher speed the prediction could get slightly ahead of the next real position sample; the following authoritative sample then pulled the marker backwards, producing the visible forward-jump/back-step effect.

`.06.08` removes forward prediction. CTRL-TS now:

- keeps the existing verified HMM1 position transport and control calculations unchanged;
- measures the actual verified-sample interval (normally about 100 ms);
- interpolates the marker from its current displayed position to the next verified `pos_frac` over that observed interval at the local ~60 Hz/16 ms display-service cadence;
- suppresses tiny opposite-direction encoder/sample dither only while measured speed has a clear direction;
- allows the display to settle to exact verified telemetry when speed returns to zero.

The numeric Current Position remains authoritative telemetry. The interpolation is presentation-only and cannot affect velocity commands, limits, calibration or safety.

## 2. `System | Ramping` persists while physically inside an end ramp zone

The canonical SRVR resolver previously required both ramp-zone position and non-zero motion toward the endpoint. That caused a stopped skate inside a ramp zone to return to `System | Active`.

`.06.08` defines Ramping as a position-zone state:

- `System | Near Limit` / `System | Far Limit` remain higher priority inside their existing 1.0 m endpoint windows;
- outside those limit windows, any position inside the configured Near or Far ramp zone resolves to yellow `System | Ramping`, whether moving or stationary;
- red fault/E-stop and existing service/calibration/Battery Change/Uncalibrated priorities remain unchanged.

No ramp-distance or motion-control calculation was changed.

## 3. W1P Encoder / Leadshine path audit

No W1P production change was required. The audit confirmed the current implementation retains:

- EdgeBox isolated RS485 on UART1 TX GPIO17 / RX GPIO18 / RTS GPIO8 using hardware half-duplex;
- Modbus RTU slave address 1, 115200 baud and 8N1 verification/configuration;
- Leadshine PR internal-command mode and PR0 velocity command path;
- signed P09.03 velocity command plus P09.04/P09.05 acceleration/deceleration and P08.02 trigger/emergency-stop control;
- 32-bit motor-position and drive-I/O feedback reads;
- SRVR Encoder mode consumption of W1P `POS_M` / signed `VEL_MPS` telemetry;
- continuous convergence of units-per-metre, direction, span, software limits and motion-profile settings;
- Servo Ready, RS485/configuration, firmware authority, SRVR presence, joystick freshness, limit and E-stop gates before drive writes;
- independent W1P 500 ms VEL freshness watchdog unchanged.

Live motor commissioning remains a physical bench gate: wiring polarity, drive parameters, motor/brake wiring, units-per-metre and Servo Ready must be verified on the real EL7-RS installation before unrestricted motion.

## Locked behavior preserved

- `.06.07` automatic firmware discovery/recovery and CTRL-TS splash handling unchanged.
- CTRL/W1P firmware behavior unchanged apart from release identity.
- W1P 500 ms VEL watchdog unchanged.
- Normal SRVR non-zero VEL refresh remains approximately 150 ms.
- AI0 E-stop / AI1 joystick mapping unchanged.
- Predictive/dynamic soft limits, hard limits and Leadshine velocity architecture unchanged.
- Calibration transactions/AUX confirmation behavior unchanged.
- Run/Settings UI unchanged.

## Verification

The complete source/static/regression/preflight suite passes, including 370 EdgeBox integration checks, all historical updater/RS485/calibration/motion contracts, `test_bench_regression_0608.py`, 53 build-pipeline checks, release consistency, source hygiene, Python syntax and SRVR preflight.

Native ESP32 and frozen desktop/PySide compilation remain GitHub Actions gates. No local firmware binaries are fabricated.
