HV P2P v26.10.04.02 - READ THIS FIRST

This is the 2026-10-03 whole-project communications audit successor to v26.10.03.04.

KEY CHANGES
- CTRL<->CTRL-TS remains single-flight half-duplex. Normal POLL cadence is 60 ms,
  bulk HMI remains 4 Hz, and a completed HMI TEXT frame postpones the next POLL
  so the touchscreen gets a quiet render/apply window.
- CTRL-TS now services/parses RS485 before entering the main LVGL critical section.
  POLL/EVENT replies therefore do not wait behind ordinary dashboard rendering.
- Idle EVENT replies are compact; full queue/CRC/resync/heap/PSRAM diagnostics
  still travel on every real event and at least once per second.
- Persistent SRVR->W1P settings are now paced and verified against W1P STATUS.
  SRVR remains authoritative and retries a mismatch instead of letting an old W1P
  value overwrite a newly selected operator setting after a lost UDP datagram.
- W1P firmware-progress packets are no longer filtered before SRVR can parse them.
- W1P physical E-stop clear or SRVR reconnect no longer restores software Servo
  Enable automatically. Only SRVR's explicit neutral-verified SW_SRVON 1 can clear
  that inhibit.
- SRVR config notifications are deferred/coalesced so ComboBox callbacks can close
  before the wider QML config graph refreshes. DSP1 changed-state construction is
  capped at 10 Hz while CTRL's priority HMS1 state path remains available.

PRESERVED SAFETY / CONTROL CONTRACTS
- W1P independent 500 ms VEL freshness watchdog.
- SRVR non-zero VEL refresh about 150 ms.
- AI0 physical E-stop / AI1 joystick mapping.
- Hard limits, predictive stopping/dynamic soft limits and Leadshine velocity mode.
- CTRL-TS safe headless self-updater: the touchscreen is intentionally black while
  programming its own flash; SRVR is the progress display.
- Boot ID/reset reason and heap/min-heap/PSRAM diagnostics.
- Approved Run/Setup/Free-D/Log UI and exact joystick-calibration prompt wording.
- Settings and Free-D auto-save; no Apply/Reset controls.

BUILD POLICY
GitHub Actions/native compilation is authoritative. Do not treat locally fabricated
firmware binaries as release artifacts. Run the included source suite first, then
use the matched GitHub firmware/desktop artifacts and complete the native/bench
checklist before powered commissioning.
