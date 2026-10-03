HV P2P v26.10.03.02 - READ THIS FIRST

This revision follows the v26.10.02.04 bench cycle.

KEY CHANGES
- CTRL-TS self-flash remains deliberately display-off/headless. CTRL now relays
  CTRL-TS update percentage to SRVR so progress remains visible while the physical
  touchscreen is black.
- AUX touch callbacks no longer execute confirmation/UI/String/RS485 work inside
  the LVGL task. They queue a fixed event for the Arduino main loop instead.
- The dormant CTRL-TS settings self-reboot timer is removed.
- CTRL-TS boot_id + reset_reason are relayed through CTRL to SRVR diagnostics.
- Joystick Calibration prompts preserve commas and use the requested Press Confirm
  wording.
- SRVR and CTRL-TS now share one canonical normalized current/REF position.
- The unsupported leading diamond is removed from the SRVR top status banner.

IMPORTANT CTRL-TS UPDATE NOTE
During CTRL-TS's own OTA programming the display intentionally turns off. This is
not a lost UI: the unit is in its RGB/LVGL/PSRAM-free headless updater. Monitor the
CTRL-TS percentage in SRVR Setup. The screen returns after verified reboot.

A manual Arduino flash may be followed by a same-version automatic exact-image
synchronization because manual flashing does not install the trusted GitHub-staged
SHA metadata. Let that exact-image repair finish unless the logs report an error.

Use GitHub Actions-produced native/staged artifacts. Native compilation is not
fabricated locally.

macOS bundle build: 2610.2.5
