HV P2P v26.10.06.02 - READ THIS FIRST

LOCKED BASELINE
---------------
v26.10.06.01 is the locked project baseline. This revision intentionally changes
only the five requested bench/UI points. No unrelated refactor or design change
is included.

WHAT CHANGED
------------
1. Limit Calibration long-move reliability:
   Fresh CTRL joystick packets can renew the existing background VEL bridge only
   while the physical joystick remains coherent with the command and no relevant
   CTRL safety flag is active. Normal ~150 ms VEL cadence and W1P's independent
   500 ms watchdog are unchanged.

2. Run > Shortcuts > System calibration captions:
   Joystick Calibration / Limit Calibration / Winch Calibration are displayed as
   Joystick / Limit / Winch on this tab only.

3. Settings AUX Assign:
   None is now the first drop-down option.

4. CTRL-TS progress marker:
   The marker is locally smoothed at the touchscreen UI cadence between verified
   ~10 Hz motion samples, using bounded 180 ms signed-speed interpolation. Numeric
   Current Position remains verified telemetry and no predicted value enters
   motion/safety logic.

5. Run > Shortcuts > System geometry:
   Uses the same 31 px row grid, 3 px row spacing, 5 px control gaps and standard
   component fonts as the neighbouring shortcut tabs while retaining the approved
   label/action column allocation.

SCOPE AUDIT
-----------
After normalising the version token, functional production changes are confined
to SRVR backend.py, Run Main.qml, Settings SetupPage.qml and CTRL-TS firmware.
CTRL and W1P firmware logic are unchanged apart from release identity.

SAFETY CONTRACTS PRESERVED
--------------------------
- W1P VEL watchdog: 500 ms unchanged.
- Normal SRVR non-zero VEL refresh: ~150 ms unchanged.
- AI0 E-stop / AI1 joystick mapping unchanged.
- Neutral-return interlock unchanged for genuine safety stops.
- Hard/predictive limits and Leadshine velocity architecture unchanged.
- Existing firmware-update ordering/reboot convergence unchanged.

VERIFICATION
------------
The complete source/static/regression/preflight runner passes, including 370
EdgeBox integration checks and 53 build-pipeline checks. PySide runtime, native
ESP32 compilation and frozen desktop builds remain GitHub Actions gates. No local
firmware binaries are fabricated or included.
