#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.05.06'
B=(ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
C=(ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
Q=(ROOT/f'SRVR_GitHub_v{VER}/qml/pages/SetupPage.qml').read_text()

# CTRL pull gets a short grace period; a live older node then receives the
# verified push fallback without requiring a manual reboot.
assert 'self._fw_modern_fallback_delay_s = 2.5' in B
svc=B[B.index('def _service_legacy_firmware_push'):B.index('def _motion_tick')]
assert 'if not self._fw_mismatch_since.get("ctrl", 0.0):' in svc
assert 'allow_modern_fallback=True' in svc

# CTRL first is mandatory, but W1P state cannot strand the touchscreen forever.
allow=B[B.index('def _ctrl_ts_update_allowed'):B.index('def _build_controller_display_packet')]
assert 'self._ctrl_fw_match and self._ctrl_authority_fresh()' in allow
assert '(now - matched_since) >= 1.0' in allow
assert 'return not w1p_updating' in allow
assert 'if self.w1p.connected:' not in allow

# Once the old CTRL-TS accepts the first FW_BEGIN and asks for the safe reboot,
# CTRL must carry that authorization across the display-off/headless transition.
assert 'static bool g_hmiSafeUpdateContinuation = false;' in C
assert 'g_hmiSafeUpdateContinuation = true;' in C[C.index('fw_safe_reboot_retry')-700:C.index('fw_safe_reboot_retry')+900]
start=C[C.index('static void hmiFwStart()'):C.index('static bool hmiFwHandleFrame')]
assert 'coordinatorGrant' in start and 'g_hmiSafeUpdateContinuation' in start
rx=C[C.index('static void handleHmiRx()'):C.index('static bool initEthernetStatic')]
assert 'g_hmiSafeUpdateContinuation || (g_hmiTsCoordinatorSeen && g_hmiTsUpdateAllowed)' in rx
assert 'g_hmiSafeUpdateContinuation = false;' in C[C.index('static bool applySrvrFirmwareBeacon'):C.index('static String buildHmiStatePacketFromSrvr')]

# Older safe_ota=2 receivers rely on CTRL's final REBOOT frame. Retry it much
# faster than bulk firmware traffic so an isolated dropped frame cannot leave
# the verified old receiver black indefinitely.
timeout=C[C.index('static void hmiFwServiceTimeout()'):C.index('static bool hmiTransportCompatible')]
assert 'HMI_FW_WAIT_REBOOT_ACK) ? 750U' in timeout
assert 'HMI_FW_WAIT_REBOOT_ACK) ? 8U' in timeout

# Exact requested AUX ordering.
choices=Q[Q.index('property var auxChoices:'):Q.index('    ]', Q.index('property var auxChoices:'))]
order=['Acceleration Mode','Battery Change Mode','Drive Mode','Joystick Calibration','Limit Calibration','None','Winch Calibration',
       'Near Limit Recall','Near Limit Save','Near Limit Slip','Ref Point Recall','Ref Point Save','Ref Point Slip',
       'Far Limit Recall','Far Limit Save','Far Limit Slip','Preset 1 Recall','Preset 1 Save','Preset 1 Slip']
idx=[choices.index(f'"{x}"') for x in order]
assert idx == sorted(idx)
assert choices.index('"Preset 10 Recall"') < choices.index('"Preset 1 Save"')
assert choices.index('"Preset 10 Save"') < choices.index('"Preset 1 Slip"')

print('FIRMWARE_UPDATE_CONVERGENCE_0506_PASS')
