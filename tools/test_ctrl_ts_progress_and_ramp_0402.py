#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ctrl = next((ROOT / 'HV_P2P_CTRL_EDGEBOX_v26.10.06.10').glob('*.ino')).read_text()
ts = next((ROOT / 'HV_P2P_CTRL_TS_v26.10.06.10').glob('*.ino')).read_text()

# CTRL firmware progress must bypass only the *compatibility* gate, not bus serialization.
assert 'static bool hmiSendFirmwareStatusText' in ctrl
fw_send = ctrl.split('static bool hmiSendFirmwareStatusText',1)[1].split('static void hmiAckEvent',1)[0]
for guard in ('hmiFwActive()', 'g_hmiPollOutstanding', 'hmiBusRecoveryQuiet()'):
    assert guard in fw_send, f'firmware status sender missing serialization guard: {guard}'
assert '(void)hmiSendFirmwareStatusText(msg);' in ctrl
assert '(void)hmiSendText(msg);' not in ctrl.split('static void reportCtrlAuthorityUpdateProgress',1)[1].split('static void serviceSrvrFirmwareAuthority',1)[0]

# CTRL-TS must remain the progress display for CTRL/W1P before its own safe update.
start = ctrl.split('static void hmiFwStart(bool coordinatorFallback=false)',1)[1].split('static bool hmiFwHandleFrame',1)[0]
assert 'g_hmiTsCoordinatorSeen' in start and 'g_hmiTsUpdateAllowed' in start
assert 'CTRL-TS update deferred until SRVR coordinator grants final-stage update' in start

# Firmware state belongs in compact HMS1; sparse ramp/Ref geometry belongs in HMG1.
state = ctrl.split('static String buildHmiStatePacketFromSrvr',1)[1].split('static String buildHmiGeometryPacketFromSrvr',1)[0]
for key in ('fw_ctrl_active','fw_ctrl_pct','fw_w1p_active','fw_w1p_pct'):
    assert f'"{key}"' in state, f'HMS1 missing {key}'
geometry = ctrl.split('static String buildHmiGeometryPacketFromSrvr',1)[1].split('static String buildHmiMotionPacketFromSrvr',1)[0]
for key in ('ramp_near','ramp_far','near','far','ramp_near_frac','ramp_far_frac'):
    assert f'"{key}"' in geometry, f'HMG1 missing {key}'
assert 'else if(line.startsWith("HMS1|"))' in ts and 'apply_external_fw_fields(line);' in ts
assert 'line.startsWith("HMG1|")' in ts

# Preserve the safe display-off self updater; do not reintroduce flash writes under RGB/LVGL.
setup = ts.split('void setup()',1)[1].split('void loop()',1)[0]
headless_pos = setup.find('if(safeHeadlessBoot)')
lcd_pos = setup.find('lcd_init();')
assert 0 <= headless_pos < lcd_pos, 'headless updater no longer exits before LCD/LVGL init'
assert 'fw_headless_blackout()' in setup
assert 'fw_set_device_status("CTRL-TS", "Preparing safe updater - SRVR shows self-flash progress", 0, true);' in ts
m = re.search(r'g_fw_safe_reboot_due_ms\s*=\s*millis\(\)\s*\+\s*(\d+)', ts)
assert m and int(m.group(1)) >= 800, 'pre-handoff dashboard is not held long enough to render intentionally'

# AUX value line must be single-line and wider/smaller-font so Practice Mode is not wrapped/cropped.
create = ts.split('static void create_ui()',1)[1]
assert 'aux_state[i]=make_label(aux_btn[i],aux_value_part(g_aux_labels[i]).c_str(),4,48,&lv_font_montserrat_10' in create
assert 'AUX_W-8' in create
assert 'lv_label_set_long_mode(aux_state[i], LV_LABEL_LONG_CLIP);' in create

# Ramp visualization must be a proportional wedge, not the old uniform thin rectangle.
assert 'RAMP_STRIP_COUNT = 10' in ts
ramp = ts.split('static void update_ramp_markers()',1)[1].split('static void update_preset_markers',1)[0]
assert 'near_w * (row + 1)' in ramp and 'far_w * (row + 1)' in ramp
assert 'ramp_l_strip[row]' in ramp and 'ramp_r_strip[row]' in ramp
assert 'lv_obj_set_size(ramp_l, near_w, ramp_h)' not in ramp

print('CTRL_TS_PROGRESS_RAMP_0402_PASS')
