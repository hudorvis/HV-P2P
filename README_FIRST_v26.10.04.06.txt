HV P2P v26.10.04.06 - READ THIS FIRST

This is the 2026-10-04 bench-follow-up release based directly on
HV P2P v26.10.04.04.

KEY CHANGES
- A running older CTRL can now trigger SRVR firmware convergence immediately from
  a fresh HMI_STATUS; a manual CTRL/CTRL-TS reboot should not be required merely
  to start discovery/update.
- CTRL-TS safe self-flash remains deliberately headless. Before going black it
  shows "Preparing safe updater - SRVR shows self-flash progress" for about 1.8 s;
  CTRL holds rediscovery for about 3.0 s. SRVR shows the exact self-flash progress.
- Canonical uncalibrated status is now "System | Uncalibrated".
- Joystick operator Value/Percentage snaps to 0.0 inside the configured neutral/
  deadband window without changing raw calibration or motion calculations.
- Limit Calibration now displays live Current Position plus captured Near / Ref /
  Far values on both SRVR and CTRL-TS. Virtual calibration movement is observable
  while the wizard is open.
- Persisted CTRL UIL1 layout can no longer override live SRVR AUX assignments;
  SRVR is the sole authority for AUX labels/semantics.
- New compact change-driven HMG1 transport carries Near/Far/Ref, ramp fractions
  and preset geometry/visibility to CTRL-TS ahead of bulk display telemetry.
- Normal live position remains in the 4 Hz bulk packet; faster current-position
  state is only added while a calibration wizard is active, protecting RS485
  event/POLL bandwidth.

PRESERVED SAFETY / CONTROL CONTRACTS
- W1P independent 500 ms VEL freshness watchdog.
- SRVR non-zero VEL refresh about 150 ms.
- AI0 physical E-stop / AI1 joystick mapping.
- Hard limits, predictive stopping/dynamic soft limits and Leadshine velocity mode.
- CTRL<->CTRL-TS single-flight half-duplex scheduling and EVENT retry/ACK behavior.
- CTRL-TS safe headless self-updater: the panel is intentionally black while it
  programs its own flash; do not interpret that phase as a live-display failure.
- Immediate CTRL-TS Waiting/Splash response to normal SRVR shutdown.
- Approved Run/Settings/Free-D/Log UI except the requested calibration/status
  readouts and corrected live geometry/AUX state.

BUILD POLICY
GitHub Actions/native compilation is authoritative. Do not treat locally fabricated
firmware binaries as release artifacts. Run the included source suite first, then
use the matched GitHub firmware/desktop artifacts and complete the native/bench
checklist before powered commissioning.
