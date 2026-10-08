#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER="26.10.08.03"
W=(ROOT/f"HV_P2P_W1P_EDGEBOX_v{VER}/HV_P2P_W1P_EDGEBOX_v{VER}.ino").read_text()
C=(ROOT/f"HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino").read_text()
T=(ROOT/f"HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino").read_text()
B=(ROOT/f"SRVR_GitHub_v{VER}/backend.py").read_text()
N=(ROOT/"tools/native_build_firmware.py").read_text()
assert '"DO1_CFG"' not in B[B.index('required_status'):B.index('if not required_status')]
for k in ('"DO2_CFG"','"DO3_CFG"','"DO4_CFG"','"DO5_CFG"'): assert k in B
assert 'if (!modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR0_VELOCITY' in W
assert 'if (!modbusWriteSingleRegister(DRIVE_MODBUS_ID, REG_PR_CONTROL, PR_TRIGGER_PATH0' in W
assert 'if (!g.drive_writes_enabled) return false;' in W
assert '0x06 | 0x80' in W and '0x10 | 0x80' in W
assert 'g_hmiReportedVersion = "";' in C and 'g_hmiPollOutstanding' in C
assert 'stale/unexpected EVENT' in C
assert 'session_not_compatible' in T and 'if(!g_ctrl_fw_compatible)' in T
assert 'boot_progress_bar' in T and 'Firmware transfer owns the splash status region' in T
assert 'FATAL DISPLAY: PSRAM unavailable/too small' in T and 'expected 800x480' in T
assert 'HEADER_H=45' in T and 'FOOT_H=35' in T and 'SW=780, GAP=7' in T
edgebox_fqbn = N[N.index('EDGEBOX_FQBN'):N.index('HMI_FQBN')]
assert 'PartitionScheme=app3M_fat9M_16MB' in edgebox_fqbn
assert 'PartitionScheme=custom' not in edgebox_fqbn

# v26.10.08.03 operator input / safety refinements.
assert 'self.reverse_joystick = False' in B
assert 'VEL_KEEPALIVE_S = 0.15' in B
assert 'def joystickPercentage' in B
assert 'W1P_VEL_COMMAND_TIMEOUT_MS = 500' in W
assert 'JOY_SAMPLES = 5' in C and 'trimmedSum' in C and 'CONTROL_INTERVAL_MS   25' in C
assert 'SGM_CONFIG_AI1_CONT_800SPS_6V144 = 0x50E3' in C
assert 'sampleCtrlEstopAI0' in C
assert 'AI0 carries the CTRL E-stop status' in C and 'AI1 carries the APEM 0-5 V joystick signal' in C
assert 'sgmSelectChannelVerified(SGM_CONFIG_AI0_CONT_800SPS_6V144, "AI0 E-stop")' in C
assert 'sgmEnsureChannelVerified(SGM_CONFIG_AI1_CONT_800SPS_6V144, "AI1 joystick")' in C
assert 'Always restore and verify AI1' in C
assert 'CTRL_ESTOP_HEALTHY_MIN_V = 3.5f' in C and 'CTRL_ESTOP_HEALTHY_CONFIRM_SAMPLES = 3' in C
# v26.10.08.03 direction-regression guard: CTRL normalises physical Left/Right
# before SRVR, so the default backend direction is Normal and sign is preserved.
BT=(ROOT/'SRVR_GitHub_v26.10.08.03/tools/test_backend_logic.py').read_text()
assert 'assert b.reverse_joystick is False' in BT
assert 'physical Left=-1' in B
assert 'b.requested_speed_mps < 0.0' in BT
assert 'b.requested_speed_mps > 0.0' in BT
# AI0/AI1 identity, status priority, session calibration, and OTA display ownership.
assert 'float axis = 1.0f - (2.0f * (float(raw) / EDGEBOX_JOY_5V_COUNTS))' in C
assert 'FLAG_CTRL_HMI_FAULT' in C and 'FLAG_CTRL_FW_FAULT' in C
assert 'if(estop_active) flags_out |= FLAG_ESTOP_PRESSED;' in C
assert 'if(hmi_safety) flags_out |= FLAG_CTRL_HMI_FAULT;' in C
assert 'position_reference_persistent' in B and 'self._not_calibrated = True' in B
assert 'def systemStatusLevel' in B and 'System | Uncalibrated' in B
assert 'g_boot_session_id' in W and 'BOOT_ID=' in W
assert 'fw_ensure_update_screen' in T and 'fw_display_owned' in T
assert 'if(fw_display_owned())' in T and 'CTRL-TS self-flash' in T
# v26.10.08.03 safe CTRL-TS self-update architecture.  The .02.01/.02.02
# experiment that changed RGB PCLK/bounce buffers and restarted RGB DMA while
# flash was being written is intentionally prohibited.  A displayed FW_BEGIN
# stages the exact target in retained internal RAM then reboots into a
# display-off/headless updater; Update.begin()/Update.write() are reachable only
# from that headless boot. No Preferences/NVS write is allowed in live display.
assert '#include <esp_lcd_panel_rgb.h>' not in T
for forbidden in ('esp_lcd_rgb_panel_set_pclk', 'esp_lcd_rgb_panel_restart', 'FW_RGB_PCLK_HZ', 'NORMAL_RGB_PCLK_HZ'):
    assert forbidden not in T
WPREP=(ROOT/'tools/prepare_waveshare_library.py').read_text()
assert 'LVGL_PORT_RGB_BOUNCE_BUFFER_SIZE' not in WPREP
assert '#include <esp_attr.h>' in T and '__NOINIT_ATTR' in T and 'FW_SAFE_HANDOFF_MAGIC' in T
for forbidden in ('putString("upd_target"', 'putString("upd_sha"', 'putBool("upd_mode"'):
    assert forbidden not in T
assert 'fw_stage_safe_update_handoff' in T and 'fw_prepare_headless_mode' in T and 'fw_headless_blackout' in T
assert 'digitalWrite(LCD_BL, LOW)' in T and 'digitalWrite(LCD_RST, LOW)' in T
assert 'g_fw_safe_reboot_due_ms' in T and 'fw_safe_reboot_retry' in T
assert 'text == "fw_safe_reboot_retry"' in C and 'holding discovery until reboot completes' in C
assert '"|safe_ota=2"' in T
assert 'g_hmiSafeOtaLevel' in C and 'g_hmiSafeOtaCapable = g_hmiSafeOtaLevel >= 2' in C
assert 'manual USB bootstrap to v26.10.03.04 or newer required' in C
assert 'fw_compare_release_versions' in T and 'fw_downgrade_blocked' in T
assert 'no firmware transfer started for 60 s' in T and 'lastActivity = last_hmi_rx' not in T
begin=T[T.index('static void fw_handle_begin'):T.index('static void fw_handle_block')]
assert begin.index('if(!g_fw_headless_mode)') < begin.index('Update.begin(imageSize, U_FLASH)')
normal_branch=begin[begin.index('if(!g_fw_headless_mode)'):begin.index('Update.begin(imageSize, U_FLASH)')]
assert 'fw_stage_safe_update_handoff(version, sha)' in normal_branch
assert 'g_fw_safe_reboot_due_ms = millis() + 1800' in normal_branch
for forbidden in ('g_fw_prefs', 'Preferences', 'Update.begin', 'Update.write'):
    assert forbidden not in normal_branch
assert 'return;' in normal_branch

# .04 bench fix: duplicate FW_BEGIN cannot postpone the scheduled reboot, and CTRL
# suppresses HMI rediscovery long enough for the 900 ms restart to happen.
assert 'if(g_fw_safe_reboot_due_ms)' in begin
dup=begin[begin.index('if(g_fw_safe_reboot_due_ms)'):begin.index('if(g_fw_finalized)')]
assert 'g_fw_safe_reboot_due_ms =' not in dup and 'fw_stage_safe_update_handoff' not in dup
assert 'g_hmiSafeRebootHoldUntilMs = millis() + 3000;' in C
assert 'safeRebootHold' in C
blackout=T[T.index('static bool fw_headless_blackout'):T.index('static void fw_service_headless_idle_return')]
assert 'new ESP_IOExpander_CH422G' not in blackout and 'expander->init()' not in blackout and 'expander->begin()' not in blackout
block=T[T.index('static void fw_handle_block'):T.index('static void fw_handle_end')]
assert 'Update.write(g_fw_write_buf, dataLen)' in block
for forbidden in ('esp_lcd', 'fw_rgb_', 'lv_refr_now'):
    assert forbidden not in block
setup=T[T.index('void setup()'):T.index('void loop()')]
assert setup.index('fw_prepare_headless_mode()') < setup.index('load_fw_identity()') < setup.index('\n  lcd_init();')
assert 'if(safeHeadlessBoot)' in setup and 'while(true)' in setup
headless_branch=setup[setup.index('if(safeHeadlessBoot)'):setup.index('Serial.printf("[WS-HMI] PSRAM found')]
assert 'boot_service_uart();' in headless_branch
assert 'lcd_init()' not in headless_branch and 'psramFound()' not in headless_branch
reboot_start=T.index('static void fw_handle_reboot')
assert 'fw_clear_headless_update_state();' in T[reboot_start:T.index('static void fw_service_reboot', reboot_start)]

# v26.10.08.03 field-feedback regressions: a newer SRVR must be noticed without
# power-cycling field nodes *and without periodic HTTP in the healthy real-time
# loops*. SRVR's normal UDP beacons invalidate an old match; only the already
# fail-closed unmatched/update path may perform HTTP/SHA/OTA work.
for node in (C, W):
    assert 'if(g_srvrFirmwareMatched) return;' in node
    assert 'FW_AUTH_MATCHED_RECHECK_MS' not in node
    assert 'authorityUnchanged' not in node and 'previousVersion' not in node
assert 'static bool applySrvrFirmwareBeacon' in C
assert 'line.startsWith("SRVR_FW|")' in C and 'line.startsWith("DSP1|")' in C
ctrl_beacon = C[C.index('static bool applySrvrFirmwareBeacon'):C.index('static void handleUdpRx')]
assert 'g_srvrFirmwareMatched = false;' in ctrl_beacon and 'authority_changed' in ctrl_beacon
assert 'if (line.startsWith("SRVR_FW|"))' in W
w_beacon = W[W.index('if (line.startsWith("SRVR_FW|"))'):W.index('if (line.startsWith("SRVR_FW|"))')+1200]
assert 'driveStopNow();' in w_beacon and 'requestSoftwareSrvonInhibit(true, "SRVR_FW_CHANGED")' in w_beacon
assert 'f"srvr_fw={self._current_firmware_version()}"' in B
assert 'def _send_ctrl_firmware_beacon' in B and 'def _send_w1p_firmware_beacon' in B and 'SRVR_FW|version=' in B
assert 'def _srvr_alive_worker(self):' in B
assert 'self._send_ctrl_firmware_beacon(force=True)' in B and 'self._send_w1p_firmware_beacon(force=True)' in B
tick=B[B.index('    def _tick(self):'):B.index('    # --- config ---')]
assert '_send_ctrl_firmware_beacon' not in tick and '_send_w1p_firmware_beacon' not in tick
assert 'stale_release_report' in B
assert 'reported_match and version_current and authority_current' in B
assert 'reported_w1p_match and self._firmware_version_matches_current' in B
assert 'return self._current_firmware_version()' in B
assert '"Update required"' in B
assert 'static lv_obj_t *g_fw_screen = nullptr;' in T
assert r'HV P2P\nFirmware Update' in T and 'g_fw_row_bar[3]' in T
assert 'fw_set_device_status("CTRL-TS"' in T and 'FWSTAT|device=CTRL' in C
assert 'FW_PROGRESS|device=W1P' in W and 'fw_w1p_pct=' in B and 'fw_ctrl_pct=' in B
assert 'g_status_text = "E-Stop | " + src;' in T
assert 'detail.startsWith("E-Stop / ")' in T
assert 'while(detail.startsWith("/"))' in T
# Unsupported icon glyphs must never return to CTRL-TS's compiled Montserrat-only UI.
for glyph in ('◇','⚙','◴','⌖'):
    assert glyph not in T
assert 'const char *aux_heads[AUX_COUNT]={"AUX 1","AUX 2","AUX 3","AUX 4","AUX 5"}' in T
assert 'make_label(drive,"DRIVE"' in T and 'make_label(speed,"SPEED"' in T and 'make_label(position,"POSITION"' in T

# Runtime SRVR loss returns to the original resident splash instead of inventing
# another screen or rebooting the display.
assert 'static void service_runtime_connection_screen()' in T
assert 'const char *msg = ctrl_link_alive ? "Waiting for SRVR" : "Waiting for CTRL";' in T
assert 'lv_scr_load(boot_scr);' in T and 'lv_scr_load(g_main_scr);' in T
assert 'Keep the original JPEG splash resident after startup' in T

# AUX calibration commands are stateful Confirm controls: first press opens,
# subsequent confirmed presses advance the existing wizard. Joystick calibration
# is a first-class AUX assignment too.
SETUP=(ROOT/f'SRVR_GitHub_v{VER}/qml/pages/SetupPage.qml').read_text()
assert SETUP.index('"Joystick Calibration"') < SETUP.index('"Limit Calibration"') < SETUP.index('"Winch Calibration"')
aux=B[B.index('def _handle_aux_action'):B.index('def _display_field', B.index('def _handle_aux_action'))]
assert 'self.calibration_open and self.calibration_type == "Limit"' in aux and 'self.calibrationNext()' in aux
assert 'self.calibration_open and self.calibration_type == "Winch"' in aux
assert 'self.joystick_calibration_open' in aux and 'self._joystick_calibration_next(raw_axis)' in aux and 'self.openJoystickCalibration()' in aux
assert 'cal_active=' in B and 'cal_kind=' in B and 'cal_instruction=' in B
assert 'g_cal_overlay=make_panel' in T and 'apply_calibration_overlay_fields' in T
assert 'Hold Joystick Left, then Press Confirm' in B
assert 'Use the assigned AUX: press once for Confirm?' not in T
assert 'g_cal_hint_lbl' not in T
assert 'lv_obj_move_foreground(g_cal_overlay)' not in T
assert 'if(!g_calibration_overlay_active)' in T and 'calibration overlay shown' in T
assert 'g_last_cal_overlay_kind' in T and 'g_last_cal_overlay_step' in T
assert 'kind != g_last_cal_overlay_kind || step != g_last_cal_overlay_step' in T
assert 'const bool calibration_active_now = (geometry_only || motion_only || position_only) ? g_calibration_overlay_active : apply_calibration_overlay_fields(line);' in T
assert 'if(!calibration_active_now){' in T
assert 'if(position_only){' in T and 'if(!calibration_active_now) update_progress_marker();' in T and '(marker_now - g_last_marker_packet_ms) > 500U' in T
assert 'lv_obj_invalidate(lbl);' not in T[T.index('static void set_label_text_if_changed'):T.index('static String display_aux_label')]
assert '#include <esp_system.h>' in T and 'esp_reset_reason()' in T

# Direct .01 -> current release bridge: old matched firmware cannot understand
# the later UDP release beacon, so SRVR asynchronously uploads its already
# verified bundle through the pre-existing /update/app endpoint.
M=(ROOT/f'SRVR_GitHub_v{VER}/main.py').read_text()
assert 'firmware_bundle=authority.bundle' in M
assert 'def _legacy_firmware_push_worker' in B and 'HTTPConnection' in B and '"/update/app"' in B
assert 'multipart/form-data' in B and 'daemon=True' in B and 'def _service_legacy_firmware_push' in B
assert 'def _firmware_version_is_older' in B and 'def _try_start_legacy_firmware_push' in B
assert 'self._motion_tick(); self._service_w1p_setting_sync(); self._service_legacy_firmware_push();' in B
assert 'ctrl_present = bool(self._ctrl_connected() or self._ctrl_authority_fresh())' in B

# Settings and Free-D are auto-save pages. No footer Apply/Reset interaction is
# permitted to return, and joystick-wizard completion immediately activates the
# captured range so both live Value and Percentage use the calibrated endpoints.
Q=(ROOT/f"SRVR_GitHub_v{VER}/qml/Main.qml").read_text()
assert 'text:"Apply"' not in Q and 'text:"Reset"' not in Q
assert 'backend.applySetupSettings' not in Q and 'backend.resetSetupSettings' not in Q
assert 'backend.applyFreeDSettings' not in Q and 'backend.resetFreeDSettings' not in Q
assert 'def _commit_setup_draft' in B and 'def _commit_freed_draft' in B
joy=B[B.index('def _joystick_calibration_next'):B.index('@Slot(str,bool)', B.index('def _joystick_calibration_next'))]
assert 'self._commit_setup_draft(notify=False)' in joy
assert 'Joystick calibration saved' in joy
assert 'def joystickPercentage' in B and '_operator_joystick_axis(self._calibrated_joystick(self._ctrl_axis)) * 100.0' in B
assert 'freed_snap = self._freed_snapshot()' in B

# v26.10.08.03 bench-hardening regressions: ordinary AUX confirmation must never
# execute UI/protocol/String work in the LVGL callback or reboot CTRL-TS. Reset
# identity is relayed through CTRL so a future hardware reset is diagnosable.
aux_cb=T[T.index('static void aux_event_cb'):T.index('static void service_aux_touch_events', T.index('static void aux_event_cb'))]
assert 'queue_aux_touch' in aux_cb and 'confirm_aux_idx' not in aux_cb and 'send_hmi_command' not in aux_cb and 'String(' not in aux_cb
assert 'static void service_aux_touch_events()' in T
bg_cb=T[T.index('static void bg_event_cb'):T.index('static void aux_event_cb', T.index('static void bg_event_cb'))]
assert 'queue_aux_cancel' in bg_cb and 'cancel_pending_aux' not in bg_cb
assert 'service_aux_touch_events();' in T[T.index('void loop()'):]
assert 'g_settings_reset_due_ms' not in T
assert '|boot_id=' in T and '|reset_reason=' in T
assert 'g_hmiReportedBootId' in C and 'g_hmiReportedResetReason' in C
assert 'reboot detected old_boot=' in C and '|boot_id=' in C and '|reset_reason=' in C
assert 'fw_pct=' in C and 'hmiFwProgressPct()' in C
assert 'ctrlTsFirmwareProgress' in B and 'CTRL-TS] reboot detected' in B

# Human-readable calibration instructions preserve commas; only packed list
# fields sanitize commas. The exact requested joystick prompts are locked here.
assert 'def _display_field(value, limit: int = 24, *, replace_comma: bool = True)' in B
assert 'cal_instruction={self._display_field(cal_instruction, 64, replace_comma=False)}' in B
for prompt in ('Hold Joystick Left, then Press Confirm',
               'Release Joystick to Centre, then Press Confirm',
               'Hold Joystick Right, then Press Confirm'):
    assert prompt in B

# SRVR and CTRL-TS share one canonical Near->Far coordinate for current/REF
# markers; the top status banner must not prepend unsupported diamond glyphs.
MQ=(ROOT/f'SRVR_GitHub_v{VER}/qml/Main.qml').read_text()
SD=(ROOT/f'SRVR_GitHub_v{VER}/qml/components/SpanDiagram.qml').read_text()
assert 'text:backend.bannerText' in MQ and '♢' not in MQ and '◇' not in MQ
assert 'def _span_fraction' in B and 'def positionFraction' in B and 'def refFraction' in B
assert 'pos_frac=' in B and 'ref_frac=' in B
assert 'g_pos_frac' in T and 'g_ref_frac' in T
assert 'float next_frac = constrain(g_pos_frac' in T and 'float frac = constrain(g_ref_frac' in T
assert 'currentFraction:backend.positionFraction' in MQ and 'refFraction:backend.refFraction' in MQ
assert 'property real currentFraction: -1' in SD and 'property real refFraction: -1' in SD

print('AUDIT_REGRESSIONS_PASS')
