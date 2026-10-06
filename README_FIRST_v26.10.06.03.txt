HV P2P v26.10.06.03 - READ THIS FIRST

LOCKED BASELINE
---------------
v26.10.06.02 is the locked project baseline. This revision changes only firmware
update discovery/recovery/coordinator behavior required by the reported .06.02
auto-update regression.

WHAT WAS FOUND
--------------
1. The normal modern CTRL/W1P pull update was background-safe, but the verified
   HTTP fallback used when that pull was missed was still evaluated only by the
   Qt/UI timer. A node could therefore remain stale until a manual reboot caused
   boot-time authority discovery.
2. CTRL-TS was correctly ordered last, but a present W1P that could not converge
   could hold fw_ts_allowed=0 forever, leaving CTRL at 100% and CTRL-TS Waiting.

WHAT CHANGED
------------
- Firmware recovery eligibility now runs from the background communications
  worker as well as the existing Qt path.
- Fresh stale-CTRL status forces an immediate SRVR_FW beacon retry.
- Modern CTRL/W1P HTTP fallback still uses the exact verified authority image and
  remains asynchronous.
- CTRL-TS remains the last intended stage. W1P receives a normal ordered attempt;
  actively flashing W1P gets a long completion window. A W1P stuck waiting for
  safe idle cannot strand the independent CTRL-TS stage forever.
- W1P remains firmware-mismatched/fail-closed until it later converges; releasing
  CTRL-TS does not relax motion safety.

UNCHANGED FROM .06.02
---------------------
- Limit Calibration VEL-bridge fix.
- Short System calibration captions.
- AUX None-first ordering.
- Smooth CTRL-TS progress marker.
- System Shortcut geometry alignment.
- W1P 500 ms VEL watchdog and ~150 ms normal SRVR VEL refresh.
- AI0 E-stop / AI1 joystick mapping, hard/predictive limits and Leadshine motion.
- CTRL<->CTRL-TS safe single-flight RS485 updater protocol.

SCOPE AUDIT
-----------
After normalizing the release string, only SRVR backend.py changes functionally
from v26.10.06.02. CTRL, W1P, CTRL-TS, QML and firmware_authority.py are unchanged.

VERIFICATION
------------
The complete source/static/regression/preflight suite passes. Native ESP32 and
frozen desktop compilation remain GitHub Actions gates. No local firmware binary
is fabricated or included in this source package.
