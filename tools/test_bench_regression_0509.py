#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VER = '26.10.06.01'
B = (ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
Q = (ROOT/f'SRVR_GitHub_v{VER}/qml/pages/SetupPage.qml').read_text()
C = (ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
T = (ROOT/f'HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino').read_text()
W = (ROOT/f'HV_P2P_W1P_EDGEBOX_v{VER}/HV_P2P_W1P_EDGEBOX_v{VER}.ino').read_text()

# 1) Final CTRL-TS reboot is not complete merely because REBOOT was ACKed.
assert 'HMI_FW_WAIT_REBOOT_CONFIRM' in C
ack = C[C.index('if((g_hmiFwState == HMI_FW_WAIT_REBOOT_ACK'):C.index('static void hmiFwServiceTimeout()')]
assert 'awaiting new boot identity' in ack
assert 'g_hmiFwState = HMI_FW_WAIT_REBOOT_CONFIRM' in ack
assert 'hmiFwReset(nullptr)' not in ack
hello = C[C.index('if(frame.type == HVP2PRS485::HELLO_RESP)'):C.index('if(frame.type == HVP2PRS485::EVENT)')]
assert 'newBootId != g_hmiFwPreUpdateBootId' in hello
assert 'updated CTRL-TS identity confirmed after reboot' in hello
assert 'exact image identity reported without a changed boot_id; reboot transaction remains open' in hello
assert 'legacyExactIdentityProof = !g_hmiFwPreUpdateBootId.length()' in hello
assert 'reboot confirmed by exact target identity (legacy peer did not provide pre-update boot_id)' in hello
# GitHub native compile regression: newBootId must live in the HELLO_RESP scope,
# not inside the earlier reset-reason block. .05.07/.05.08 referenced it later
# after the nested declaration had gone out of scope.
hello_pre_match = hello[:hello.index('bool match = hmiIdentityMatches();')]
assert 'g_hmiReportedHash = hvGetPipeField(line, "hash");\n    // Keep the current HELLO boot identity' in hello_pre_match
assert 'String newBootId = hvGetPipeField(line, "boot_id");' in hello_pre_match
assert '{\n      String newBootId = hvGetPipeField(line, "boot_id");' not in hello_pre_match
timeout = C[C.index('static void hmiFwServiceTimeout()'):C.index('static bool hmiTransportCompatible')]
assert '> 14000U' in timeout and 'g_hmiFwRebootEnforceCount < 8U' in timeout
assert '(now - g_hmiFwLastTxMs) >= 1500U' in timeout
assert 'post-reboot peer replied ERROR while confirmation is pending' in C
# Receiver keeps autonomous fallback alive in the headless loop; boot_service_uart
# owns timeout+reboot servicing exactly once per iteration.
boot_uart = T[T.index('static void boot_service_uart()'):T.index('static bool boot_prepare_splash_canvas')]
assert 'fw_service_timeout();' in boot_uart and 'fw_service_reboot();' in boot_uart
headless = T[T.index('if(safeHeadlessBoot)'):T.index('Serial.printf("[WS-HMI] PSRAM found')]
assert 'boot_service_uart();' in headless and 'fw_service_headless_idle_return();' in headless
assert headless.count('fw_service_reboot();') == 0 and headless.count('fw_service_timeout();') == 0

# 2) CTRL-TS travel geometry has separate endpoint/readout, preset and track lanes.
create = T[T.index('static void create_ui()'):]
assert 'AUX_H=74' in create and 'TRAVEL_H=100' in create
assert 'preset_lbl[i]=make_label(travel_panel,"",0,35,&lv_font_montserrat_10' in create
assert 'travel_near_lbl=make_label(travel_panel,"NEAR",8,6,&lv_font_montserrat_10' in create
assert 'travel_far_lbl=make_label(travel_panel,"FAR",712,6,&lv_font_montserrat_10' in create
assert 'lv_font_montserrat_8' not in create
ps=T.index('static void update_preset_markers()'); preset=T[ps:T.index('static void apply_hmi_packet', ps)]
assert 'const int line_top_y = 47;' in preset
assert 'const int label_y_top = 34;' in preset and 'const int label_y_bottom = 69;' in preset
ramp = T[T.index('static void update_ramp_markers()'):T.index('static void update_preset_markers')]
assert 'const int ramp_top = 56;' in ramp
ref = T[T.index('static void update_reference_marker()'):T.index('static void update_ramp_markers')]
assert 'lv_obj_set_pos(travel_ref_marker, marker_x, 47);' in ref

# 3) Settings naming matches CTRL/W1P Link rows.
assert 'text:"Link"' in Q
assert 'text:"CTRL-TS Link"' not in Q

# 4) Calibration unknown values are ASCII '-' and Cancel is end-to-end/event-safe.
overlay = T[T.index('static bool apply_calibration_overlay_fields'):T.index('static int split_csv')]
assert 'if(!v.length()) v = "-";' in overlay
assert 'v = "—"' not in overlay
assert 'g_cal_cancel_btn=make_button' in T and '"Cancel"' in T
assert 'send_hmi_command("CAL_CANCEL")' in T
assert 'else if(send_hmi_command("CAL_CANCEL"))' in T and 'local touch request only after the command was successfully queued' in T
assert 'FLAG_CAL_CANCEL' in C and 'cmd == "CAL_CANCEL"' in C
assert 'FLAG_CAL_CANCEL = 0x2000' in B
assert '_ctrl_cal_cancel_pending = True' in B
motion = B[B.index('    def _motion_tick(self):'):B.index('    # --- Free-D ---')]
assert 'if self.joystick_calibration_open:' in motion and 'self.cancelJoystickCalibration()' in motion
assert 'elif self.calibration_open:' in motion and 'self.cancelCalibration()' in motion
# Limit captures are staged and do not mutate live calibration until Ref commit.
limit = B[B.index('    def openLimitCalibration'):B.index('    @Slot(str,str)\n    def setNetwork')]
assert 'existing calibration preserved until Ref commit' in limit
step0 = limit[limit.index('if self.calibration_step == 0:'):limit.index('elif self.calibration_step == 1:')]
step1 = limit[limit.index('elif self.calibration_step == 1:'):limit.index('elif self.calibration_step == 2:')]
for forbidden in ('self.state.near_limit.position_m =', 'self.state.far_limit.position_m =', 'self.reverse_motor =', '_save_config()'):
    assert forbidden not in step0 and forbidden not in step1
step2 = limit[limit.index('elif self.calibration_step == 2:'):limit.index('else:\n                self.calibration_open = False')]
for required in ('self.reverse_motor = new_reverse', 'self.state.near_limit.position_m = 0.0',
                 'self.state.far_limit.position_m = span', 'self.state.ref_point.position_m = ref', 'self._save_config()'):
    assert required in step2
cancel = limit[limit.index('    def cancelCalibration'):limit.index('    def _sync_position')]
assert 'previous calibration retained' in cancel and '_save_config()' not in cancel

# 5) One bad W1P status/PONG cannot manufacture an immediate safety fault.
parse = B[B.index('    def _parse_w1p(self, line)'):B.index('    def _sanity_accept_winch_position')]
pong = parse[parse.index('if line.startswith("PONG")'):parse.index('if line.startswith("HELLO")')]
assert '_invalidate_w1p_status' not in pong
status = parse[parse.index('if not line.startswith("STATUS")'):]
assert 'required_status' in status and '_reject_w1p_status' in status
# No unconditional invalidation is permitted on STATUS; valid freshness commits last.
assert '_invalidate_w1p_status()' not in status
assert status.index('self._w1p_status_last_seen = time.time()') > status.index('required_status')
assert 'strict_bits' in status and 'invalid boolean field' in status
assert 'invalid enum field RS_STAT' in status and 'invalid enum field LEAD_CFG' in status
assert 'math.isfinite(numeric_value)' in status and 'invalid numeric field' in status

# 6/7) macOS background liveness and moving VEL refresh are thread-owned, bounded,
# while W1P's independent 500 ms watchdog remains exactly unchanged.
assert 'SRVR_ALIVE_INTERVAL_S = 0.25' in B
assert 'def _srvr_alive_worker(self):' in B and 'b"SRVR_ALIVE\\n"' in B
assert 'if(line == "SRVR_ALIVE")' in C and 'g_lastSrvrRxMs = millis();' in C
assert '#define SRVR_PEER_TIMEOUT_MS     750' in C
assert 'VEL_KEEPALIVE_S = 0.15' in B
assert 'VEL_BACKGROUND_REFRESH_S = 0.18' in B
assert 'VEL_REFRESH_LEASE_S = 0.22' in B
assert '_vel_refresh_last_tx = time.monotonic()' in B  # normal queued VEL suppresses duplicate worker refresh
assert 'def arm_velocity_refresh(self, text: str):' in B
assert 'mono_now < self._vel_refresh_until' in B
assert 'self.w1p.arm_velocity_refresh(cmd)' in B
assert 'self.w1p.clear_velocity_refresh()' in B
assert 'static const uint32_t W1P_VEL_COMMAND_TIMEOUT_MS = 500;' in W
assert '(now - lastVelocityCommandMs) <= W1P_VEL_COMMAND_TIMEOUT_MS' in W
# Neutral-return safety interlock remains intentional after any real stop.
assert 'self._joystick_neutral_required = True' in motion
assert 'waiting for joystick neutral before re-arm' in motion

print('BENCH_REGRESSION_0509_PASS')
