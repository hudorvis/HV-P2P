# HV P2P v26.10.01.04 change summary

v26.10.01.04 is the fourth 1 October 2026 revision and is built directly from
v26.10.01.03. GitHub Actions remains the authoritative native compiler.

## 1. AUX calibration wizard lifecycle

The .03 AUX handler treated every confirmed `Limit Calibration` or
`Winch Calibration` AUX event as a new request and called `open...Calibration()`
unconditionally. That reset the wizard to step 1 on every press and looked like a
screen restart.

In .04 the AUX action is state-aware: the first confirmed press opens the selected
wizard; while that same wizard is open, subsequent confirmed presses call
`calibrationNext()`. The same contract is used for the newly added
`Joystick Calibration` AUX assignment via `joystickCalibrationNext()`.

## 2. Runtime CTRL-TS connection splash

The original `/splash.jpg` screen is now kept resident after startup. When the
runtime CTRL/SRVR status reports loss of SRVR, CTRL-TS loads that same splash and
shows exactly `Waiting for SRVR`. Loss of CTRL shows `Waiting for CTRL`. When both
links recover the existing main screen is restored; no ESP restart is used.
Firmware-update screen ownership remains higher priority than connection-splash
switching.

## 3. SRVR desktop icon

The packaged app icon has been replaced with the approved HV P2P visual language:
dark face, green rounded keyline, equal-size white `P2P` and `SRVR` rows. The same
source assets feed the macOS ICNS and Windows ICO packaging paths.

## 4. Direct old-release automatic OTA bridge

`.03` introduced non-blocking SRVR release beacons, but firmware already running
`.01` cannot understand those later beacon fields after it has once marked an old
SRVR session matched. That creates a compatibility gap when skipping `.02`.

`.04` closes the gap from the SRVR side. If a connected CTRL/W1P reports an older
release, SRVR starts a background upgrade-only upload of the exact image from the
already-validated immutable firmware bundle to the device's long-existing HTTP
`/update/app` endpoint. The motion path is forced safe before launch, the network
transfer never runs on the 25 ms SRVR motion/UI timer, retries are rate-limited,
and newer reported firmware is never automatically downgraded. Once CTRL reaches
`.04`, its normal embedded CTRL-TS convergence updates the display as required.

Current `.03+` field firmware retains the preferred UDP release beacon ->
fail-closed manifest/SHA/OTA flow, so this HTTP push exists specifically as a
backwards-compatibility bridge for pre-beacon releases.

## 5. CTRL-TS status text / missing glyphs

The Waveshare build only compiles selected Montserrat fonts; the decorative
Unicode glyphs previously placed before E-Stop, DRIVE, SPEED, POSITION and AUX
headings are absent from those fonts and render as square boxes. `.04` removes the
unsupported glyphs from CTRL-TS and uses plain supported text.

The E-Stop formatter is also defensive against legacy delimiter conversion: after
removing `E-Stop | ` / `E-Stop / ` it trims any residual leading `/`, so the final
form is `E-STOP | CTRL & W1P`, never `E-STOP | / CTRL & W1P`.

## 6. Joystick response / display cadence

`.03` removed the major blocking HTTP stall but retained a 50 ms CTRL sample cycle,
8-sample window and `70% old / 30% new` IIR. A fast physical step therefore still
settled visibly over many packets.

`.04` keeps the channel-safety architecture but changes the normal matched path to:

- 25 ms CTRL control/telemetry interval (40 Hz);
- 5-sample trimmed mean (one high and one low discarded);
- verified AI1 readback without rewriting an already-correct mux;
- `20% old / 80% new` light filter, reaching >96% of a step in two cycles;
- 25 ms SRVR state timer for live QML updates.

The actual drive still retains W1P's independent 500 ms velocity freshness
watchdog and the existing Leadshine/Modbus command-rate and safety architecture.

## Retained .03 behaviour

- Settings and Free-D are auto-save pages with no Apply/Reset footer.
- Joystick calibration commits on wizard completion and live Percentage uses the
  calibrated Left/Centre/Right range.
- No periodic HTTP firmware poll runs inside healthy CTRL/W1P motion loops.
- Position reference is session-only; red fault/E-stop -> yellow Un-Calibrated ->
  green Ready priority remains.
- AI0/pin 14 is CTRL E-stop; AI1/pin 16 is joystick, with verified mux ownership.

## Regression/build status

- EdgeBox source integration validation: **344 checks**.
- Build-pipeline validation: **52 checks**.
- New regression locks cover AUX wizard progression, Joystick Calibration AUX
  availability, runtime splash switching, unsupported CTRL-TS glyphs, E-Stop slash
  cleanup, direct pre-beacon upgrade bridge, upgrade-only version ordering, and the
  25 ms / 5-sample low-latency joystick path.
- macOS short version `26.10.1`, bundle build `2610.1.4`, full release
  `26.10.01.04`.
- Native ESP32 and frozen desktop compilation is intentionally left to GitHub
  Actions; physical RS485/Leadshine/motion checks remain bench gates.
