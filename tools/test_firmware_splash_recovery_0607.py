#!/usr/bin/env python3
"""v26.10.08.02 regression: redundant authority discovery + stable splash recovery."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
VER = '26.10.08.02'
B = (ROOT/f'SRVR_GitHub_v{VER}'/'backend.py').read_text(encoding='utf-8')
C = (ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}'/f'HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text(encoding='utf-8')
T = (ROOT/f'HV_P2P_CTRL_TS_v{VER}'/f'HV_P2P_CTRL_TS_v{VER}.ino').read_text(encoding='utf-8')

# CTRL release discovery must have two independent transport opportunities:
# standalone background beacon and the proven heartbeat return path.
worker = re.search(r'def _controller_worker\(self\):(?P<body>.*?)(?=\n    def )', B, re.S)
assert worker, 'controller worker not found'
wb = worker.group('body')
assert 'HEARTBEAT_ACK' in wb
assert 'SRVR_FW|version=' in wb
assert 'heartbeat-return beacon recovered from error' in wb
assert 'FIRMWARE_BEACON_INTERVAL_S' in wb
assert 'def _send_ctrl_firmware_beacon' in B

# Once CTRL has cryptographically verified the current SRVR image and SRVR is
# live, the 12 s local CTRL-TS final-stage fallback must not depend on having
# received the optional SRVR firmware-session token.
service = re.search(r'static void handleHmiRx\(\).*?\n}', C, re.S)
assert service, 'CTRL HMI service not found'
svc = service.group(0)
assert 'coordinatorFallback = g_hmiMismatchSinceMs && srvrOnline && g_srvrFirmwareMatched' in svc
fallback_expr = re.search(r'const bool coordinatorFallback =.*?;', svc, re.S)
assert fallback_expr and 'g_srvrFirmwareSession.length()' not in fallback_expr.group(0)
# Mismatch timer itself must also arm without the optional session token.
assert 'if(g_srvrFirmwareMatched && srvrOnline &&\n         g_hmiReportedVersion.length()' in C

# A rebooted CTRL proves the prior CTRL OTA transaction has ended. A lost final
# FWSTAT must therefore be self-healed rather than leaving the dashboard at 100%.
hello = re.search(r'if\(frame.type == HVP2PRS485::HELLO_REQ\).*?return;', T, re.S)
assert hello and 'g_fw_row_active[1]' in hello.group(0)
assert 'fw_set_device_status("CTRL", "Complete", 100, false)' in hello.group(0)

# Runtime splash ownership must be connection-aware. Releasing an update screen
# while SRVR/CTRL is offline must go directly to the splash, never flash Home.
release = re.search(r'static void service_fw_screen_release\(\).*?(?=\nstatic void service_link_state)', T, re.S)
assert release
rb = release.group(0)
assert 'ctrl_link_alive && g_srvr_ok' in rb
assert 'lv_scr_load(boot_scr)' in rb
assert 'Waiting for SRVR' in rb and 'Waiting for CTRL' in rb

# POLL is the freshest live SRVR-presence authority. A stale HMI1/HMS1 true bit
# must not resurrect Home after a false POLL hint.
assert 'g_srvr_poll_hint_seen' in T and 'g_srvr_poll_hint' in T
assert 'else if(!g_srvr_poll_hint_seen || g_srvr_poll_hint) g_srvr_ok = true;' in T
assert 'g_srvr_poll_hint_seen = true;' in T

print('FIRMWARE_SPLASH_RECOVERY_0607_PASS')
