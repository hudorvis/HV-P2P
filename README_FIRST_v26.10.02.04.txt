HV P2P v26.10.02.04 - READ THIS FIRST

This release fixes the v26.10.02.03 CTRL-TS safe-update handoff that could remain
at "Restarting in safe update mode | 0%" indefinitely.

ROOT CAUSE
CTRL could rediscover the still-running touchscreen before its 350 ms scheduled
safe reboot and send another FW_BEGIN. .03 moved the reboot deadline each time,
so repeated discovery could postpone the reboot forever.

FIX
- CTRL now holds only HMI discovery/update traffic for 1.2 s after the safe-reboot
  acknowledgement; the real-time control loop is not blocked.
- CTRL-TS duplicate FW_BEGIN messages cannot move an already scheduled reboot.
- Headless boot no longer initializes a second CH422G/I2C/display path.
- Safe-update capability is now safe_ota=2.

IMPORTANT RECOVERY
A CTRL-TS on .03 (safe_ota=1) must be manually USB/Arduino flashed to .04 once.
CTRL .04 intentionally will not auto-stream firmware into the known level-1
receiver. After .04 is installed, future automatic headless updates are enabled.

Use GitHub Actions-produced native/staged artifacts. Native compilation is not
fabricated locally.

macOS bundle build: 2610.2.4
