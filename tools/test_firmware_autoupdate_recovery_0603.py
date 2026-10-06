#!/usr/bin/env python3
"""v26.10.06.09 regression: automatic update recovery must not require GUI ticks/reboots."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.06.09'
B=(ROOT/f'SRVR_GitHub_v{VER}'/'backend.py').read_text(encoding='utf-8')

# Primary release discovery remains in the independent comms worker.
assert 'self._send_ctrl_firmware_beacon(force=True)' in B
assert 'self._send_w1p_firmware_beacon(force=True)' in B

# Recovery from a missed modern pull must also run from that worker, not only _tick().
worker=re.search(r'def _srvr_alive_worker\(self\):(?P<body>.*?)(?=\n    def _controller_worker)', B, re.S)
assert worker, 'SRVR communications worker missing'
wb=worker.group('body')
assert '_service_firmware_recovery_background()' in wb, 'firmware fallback still depends on Qt/UI tick'

recovery=re.search(r'def _service_firmware_recovery_background\(self\).*?(?=\n    def _service_legacy_firmware_push)', B, re.S)
assert recovery, 'background firmware recovery service missing'
rb=recovery.group(0)
assert 'allow_modern_fallback=True' in rb
assert '"ctrl"' in rb and '"w1p"' in rb
assert 'self.w1p.send("STOP")' in rb and 'self.w1p.clear_velocity_refresh()' in rb

# A proven stale CTRL status should cause an immediate release beacon rather than
# waiting for the next periodic opportunity or a device reboot.
status=re.search(r'def _handle_ctrl_hmi_status\(self, line: str\):(?P<body>.*?)(?=\n    def _joystick_min_cal_span)', B, re.S)
assert status
sb=status.group('body')
assert 'self._send_ctrl_firmware_beacon(force=True)' in sb
assert 'self._firmware_version_is_older(self._ctrl_fw_version)' in sb

# Final-stage coordinator remains ordered but cannot strand CTRL-TS forever.
coord=re.search(r'def _ctrl_ts_update_allowed\(self\) -> bool:(?P<body>.*?)(?=\n    def _build_controller_display_packet)', B, re.S)
assert coord
cb=coord.group('body')
assert 'W1P_FINAL_STAGE_WAIT_S' in B and 'W1P_ACTIVE_UPDATE_WAIT_S' in B
assert '_ctrl_ts_grant_latched' in B
assert '_grant_ctrl_ts_update' in cb
assert 'bounded W1P wait expired; W1P remains fail-closed' in cb
assert 'waiting for W1P update' in cb
assert 'W1P waiting for safe idle' in cb

# .06.02 requested fixes remain present; this updater revision must not roll them back.
assert 'renew_velocity_refresh_from_controller' in B
Q=(ROOT/f'SRVR_GitHub_v{VER}'/'qml'/'Main.qml').read_text(encoding='utf-8')
S=(ROOT/f'SRVR_GitHub_v{VER}'/'qml'/'pages'/'SetupPage.qml').read_text(encoding='utf-8')
TS=(ROOT/f'HV_P2P_CTRL_TS_v{VER}'/f'HV_P2P_CTRL_TS_v{VER}.ino').read_text(encoding='utf-8')
assert 'text:"Joystick"' in Q and 'text:"Limit"' in Q and 'text:"Winch"' in Q
assert 'property var auxChoices: [\n        "None"' in S
assert 'service_progress_marker_smooth()' in TS

print('FIRMWARE_AUTOUPDATE_RECOVERY_0603_PASS')
