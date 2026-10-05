HV P2P v26.10.05.06 - READ THIS FIRST
- Restores signed DSP1/HMM1 speed transport while keeping SRVR/CTRL-TS Current Speed displays magnitude-only, matching the PySide runtime contract.

This is the 2026-10-05 bench-follow-up release based directly on the authoritative
HV P2P v26.10.04.07 GitHub-ready source.

KEY CHANGES
- Coordinates firmware convergence so CTRL becomes current before W1P/CTRL-TS,
  and quiesces the CTRL<->CTRL-TS bus before CTRL enters its blocking authority
  download so CTRL update progress is no longer suppressed by an outstanding POLL.
- Keeps the safe CTRL-TS self-flash headless: CTRL/W1P progress can be shown on
  CTRL-TS, but the panel is intentionally black while CTRL-TS writes its own flash;
  SRVR shows the exact percentage during that phase.
- Centralizes canonical status text in SRVR and prevents geometry/motion packets
  from changing it. Normal display strings are System | Active, System |
  Uncalibrated and System | Battery Change Mode, with calibration and E-Stop
  variants following the same format.
- Adds compact ~10 Hz HMM1 verified motion updates for smoother CTRL-TS speed,
  position and travel-marker movement while retaining the 4 Hz bulk HMI cap.
- Raises CTRL-TS preset/position small text to the approved Montserrat 10 minimum.
- Repairs the Limit Calibration Side View inside the Joystick-style three-step
  wizard so towers/cable fit the viewport without cropping/distortion.

PRESERVED SAFETY / CONTROL CONTRACTS
- W1P independent 500 ms VEL freshness watchdog.
- SRVR non-zero VEL refresh about 150 ms.
- AI0 physical E-stop / AI1 joystick mapping.
- Hard limits, predictive stopping/dynamic soft limits and Leadshine velocity mode.
- CTRL<->CTRL-TS single-flight half-duplex scheduling and EVENT retry/ACK behavior.
- Immediate CTRL-TS Waiting/Splash response to normal SRVR shutdown.

BUILD POLICY
GitHub Actions/native compilation is authoritative. Do not treat locally fabricated
firmware binaries as release artifacts. Run the included source suite first, then
use the matched GitHub firmware/desktop artifacts and complete the native/bench
checklist before powered commissioning.
