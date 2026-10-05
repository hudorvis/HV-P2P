HV P2P v26.10.05.07 - READ THIS FIRST

This is the 2026-10-05 bench-follow-up release based directly on the authoritative
HV P2P v26.10.05.06 source supplied for this revision.

KEY FIXES
- CTRL-TS final firmware reboot now requires proof of a new boot_id plus exact
  target version/SHA; a REBOOT ACK alone is no longer treated as completion.
- CTRL-TS travel layout is rebalanced so Near/Far, REF, skate/ramp graphics and
  Preset names do not overlap; Montserrat 10 remains the minimum small font.
- Settings -> CTRL-TS uses the subheading Link.
- Uncaptured calibration fields show '-' and CTRL-TS has a retry-safe Cancel.
- Limit Calibration is transactional: Near/Far/Ref/Winch Invert stage until Ref;
  Cancel leaves the previous valid calibration untouched and exits safely.
- W1P status is validate-before-commit, so one malformed STATUS/PONG cannot
  manufacture a one-frame E-stop/red flash.
- A background SRVR liveness worker prevents macOS window focus from starving
  the CTRL peer heartbeat.
- A bounded worker-side VEL refresh bridges brief GUI scheduling stalls during
  motion/calibration without changing W1P's independent 500 ms watchdog.

PRESERVED SAFETY / CONTROL CONTRACTS
- W1P independent 500 ms VEL freshness watchdog.
- Normal SRVR non-zero VEL refresh approximately 150 ms.
- AI0 physical E-stop / AI1 joystick mapping.
- Neutral-return re-arm after a genuine safety stop.
- Hard limits, predictive stopping/dynamic soft limits and Leadshine velocity mode.
- CTRL<->CTRL-TS single-flight half-duplex scheduling and EVENT retry/ACK behavior.
- Firmware ordering CTRL -> W1P -> CTRL-TS.
- CTRL-TS is intentionally headless/black while writing its own flash.
- Immediate CTRL-TS Waiting/Splash response to normal SRVR shutdown.

BUILD POLICY
GitHub Actions/native compilation is authoritative. No locally fabricated firmware
binaries are release artifacts. Run the included source suite, build the matched
GitHub firmware/desktop artifacts, then complete the native/bench checklist before
powered commissioning.
