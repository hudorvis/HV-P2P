#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.05.07'
B=(ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
Q=(ROOT/f'SRVR_GitHub_v{VER}/qml/Main.qml').read_text()
S=(ROOT/f'SRVR_GitHub_v{VER}/qml/components/SpanDiagram.qml').read_text()
C=(ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
T=(ROOT/f'HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino').read_text()

# One SRVR-owned status vocabulary, large enough for long labels on the wire.
for status in ('System | Active', 'System | Uncalibrated', 'System | Battery Change Mode', 'System | Joystick Calibration'):
    assert status in B, status
assert 'kind = "Winch Calibration" if self.calibration_type == "Winch" else "Limit Calibration"' in B
assert 'return f"System | {kind}", "yellow"' in B
assert 'f"status={self._display_field(status, 40)}"' in B
assert 'return "System | Active", "green"' in B
assert 'return "System | Battery Change Mode", "yellow"' in B
assert 'shown = "STATE | " + text;' not in T
assert 'shown = "E-Stop | " + detail;' in T
assert 'if(statusField.startsWith("System / ")) statusField = "System | "' in T
assert 'if(statusField.startsWith("E-Stop / ")) statusField = "E-Stop | "' in T

# Geometry/motion packets are display-data only and cannot mutate system status.
assert 'const bool status_packet = state_only || bulk_packet;' in T
status_section=T[T.index('String statusField = getField(line, "status")'):T.index('uint16_t flags_now', T.index('String statusField = getField(line, "status")'))]
assert 'if(status_packet && statusField.length())' in status_section
assert 'if(status_packet && !statusField.length())' in status_section
assert 'geometry_only || motion_only' not in status_section[status_section.index('if(status_packet && statusField.length())'):]

# Motion is a compact ~10 Hz path; do not restore 10 Hz 900-byte bulk frames.
assert '#define HMI_MOTION_MIN_MS          80' in C
assert 'String out = "HMM1"' in C and 'buildHmiMotionPacketFromSrvr' in C
assert '(now - g_lastHmiMotionTxMs) >= HMI_MOTION_MIN_MS' in C
assert 'line.startsWith("HMM1|")' in T and 'motion_only' in T
assert 'lv_anim_set_time(&a, 90);' in T
assert '#define DISPLAY_FORWARD_MIN_MS 250' in C

# Smallest dashboard data font is Montserrat 10, including presets and limits.
main=T[T.index('static void create_ui'):]
assert 'lv_font_montserrat_8' not in main
assert 'preset_lbl[i]=make_label(travel_panel,"",0,35,&lv_font_montserrat_10' in main

# Modern update order: CTRL self-pull first, W1P gated behind CTRL, CTRL-TS final.
assert 'parts <= (26, 10, 1, 1)' in B
assert 'if not (self._ctrl_fw_match and self._ctrl_authority_fresh()):' in B[B.index('def _send_w1p_firmware_beacon'):B.index('def _legacy_firmware_push_worker')]
assert 'def _ctrl_ts_update_allowed' in B and '(now - matched_since) >= 1.0' in B
assert 'f"fw_ts_allowed={1 if self._ctrl_ts_update_allowed() else 0}"' in B
assert 'g_hmiTsCoordinatorSeen' in C and 'g_hmiTsUpdateAllowed' in C
assert 'ts_allowed' in B[B.index('def _send_ctrl_firmware_beacon'):B.index('def _send_w1p_firmware_beacon')]
# CTRL authority download must quiesce the HMI bus so FWSTAT is not suppressed by a stuck POLL.
assert 'g_ctrlAuthorityUpdatePending = true;' in C
assert 'if(g_hmiPollOutstanding || hmiBusRecoveryQuiet())' in C
assert '!g_ctrlAuthorityUpdatePending && !safeRebootHold' in C
assert 'hmiSendFirmwareStatusText(msg)' in C

# CTRL-TS's own flash remains safely headless; SRVR is exact progress then.
assert 'headless boot: RGB/LVGL/PSRAM display stack remains uninitialized' in T
assert 'Preparing safe updater - SRVR shows self-flash progress' in T

# Limit Calibration uses the Joystick wizard's 3-step shell, but with a properly bounded cable view.
assert 'width:f(720); height:f(540)' in Q
assert 'model:["Set Near","Set Far","Set Ref"]' in Q
assert 'model: ["Set Left", "Set Centre", "Set Right"]' in Q
assert 'height:f(84)' in Q and 'compactMode:true' in Q
assert 'var graphTop=root.compactMode ? 16 : 30' in S
assert 'tower(c,20,graphBottom,graphTop); tower(c,width-20,graphBottom,graphTop)' in S

print('BENCH_REGRESSION_0501_PASS')
