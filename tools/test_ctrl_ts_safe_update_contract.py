#!/usr/bin/env python3
"""Static contract for the display-off CTRL-TS self-updater.

This exists specifically to prevent the v26.10.02.01/.02 regression where
self-flash manipulated/restarted the active RGB pipeline and could corrupt the
Waveshare panel. Native compilation is still a GitHub Actions gate.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
VER = "26.10.02.03"
T = (ROOT/f"HV_P2P_CTRL_TS_v{VER}"/f"HV_P2P_CTRL_TS_v{VER}.ino").read_text()
P = (ROOT/'tools'/'prepare_waveshare_library.py').read_text()
WF = next((ROOT/'.github'/'workflows').glob('*.yml')).read_text()

# The failed .01/.02 experiment is prohibited outright.
for token in ('esp_lcd_rgb_panel_set_pclk', 'esp_lcd_rgb_panel_restart', 'FW_RGB_PCLK_HZ', 'NORMAL_RGB_PCLK_HZ'):
    assert token not in T, token
assert '#include <esp_lcd_panel_rgb.h>' not in T
assert 'LVGL_PORT_RGB_BOUNCE_BUFFER_SIZE' not in P
assert 'LVGL_PORT_RGB_BOUNCE_BUFFER_SIZE (LVGL_PORT_DISP_WIDTH * 20)' not in WF

# Safe handoff must live only in retained INTERNAL RAM.  In particular, normal
# displayed FW_BEGIN is forbidden from touching Preferences/NVS or Update.*.
for token in ('#include <esp_attr.h>', '__NOINIT_ATTR', 'FwSafeHandoff',
              'FW_SAFE_HANDOFF_MAGIC', 'fw_safe_handoff_checksum',
              'fw_stage_safe_update_handoff', 'fw_prepare_headless_mode',
              'fw_headless_blackout', 'fw_clear_headless_update_state',
              'FW_HEADLESS_IDLE_RETURN_MS', 'ESP_RST_SW'):
    assert token in T, token
for forbidden in ('putString("upd_target"', 'putString("upd_sha"', 'putBool("upd_mode"',
                  'getString("upd_target"', 'getString("upd_sha"', 'getBool("upd_mode"'):
    assert forbidden not in T, forbidden
assert 'expander->digitalWrite(LCD_BL, LOW);' in T
assert 'expander->digitalWrite(LCD_RST, LOW);' in T

begin = T[T.index('static void fw_handle_begin'):T.index('static void fw_handle_block')]
headless_gate = begin.index('if(!g_fw_headless_mode)')
update_begin = begin.index('Update.begin(imageSize, U_FLASH)')
assert headless_gate < update_begin
handoff = begin[headless_gate:update_begin]
for token in ('fw_stage_safe_update_handoff(version, sha)',
              'Restarting in safe update mode',
              'fw_safe_reboot_retry',
              'g_fw_safe_reboot_due_ms = millis() + 350',
              'return;'):
    assert token in handoff, token
for forbidden in ('g_fw_prefs', 'Preferences', '.put', '.remove', 'Update.begin', 'Update.write', 'lv_refr_now'):
    assert forbidden not in handoff, forbidden

# Handoff acceptance is constrained to the deliberate software restart and its
# RAM payload is magic/checksum/format validated before blackout/headless entry.
prep = T[T.index('static bool fw_prepare_headless_mode'):T.index('static void fw_clear_headless_update_state')]
for token in ('esp_reset_reason() != ESP_RST_SW', 'FW_SAFE_HANDOFF_MAGIC',
              'fw_safe_version_valid', 'fw_safe_sha_valid', 'fw_safe_handoff_checksum'):
    assert token in prep, token
assert 'g_fw_safe_handoff.magic = 0;' in prep

setup = T[T.index('void setup()'):T.index('void loop()')]
assert setup.index('fw_prepare_headless_mode()') < setup.index('load_fw_identity()') < setup.index('\n  lcd_init();')
assert setup.index('fw_headless_blackout()') < setup.index('load_fw_identity()')
headless = setup[setup.index('if(safeHeadlessBoot)'):setup.index('Serial.printf("[WS-HMI] PSRAM found')]
assert 'while(true)' in headless
assert 'boot_service_uart();' in headless
assert 'lcd_init()' not in headless
assert 'psramFound()' not in headless
assert 'blackout setup failed; abandoning headless update' in setup

# Actual self-flash remains exclusively in the display-off/headless stage.
block = T[T.index('static void fw_handle_block'):T.index('static void fw_handle_end')]
assert 'Update.write(g_fw_write_buf, dataLen)' in block
for token in ('esp_lcd', 'fw_rgb_', 'lv_refr_now', 'lvgl_port_lock'):
    assert token not in block, token

# boot_service_uart must continue servicing timeout/reboot while setup is parked
# forever in headless mode.
boot_uart = T[T.index('static void boot_service_uart'):T.index('static bool boot_prepare_splash_canvas')]
assert 'fw_service_timeout();' in boot_uart
assert 'fw_service_reboot();' in boot_uart

# Failed/no-CTRL safe mode cannot leave a permanently black unit, and verified
# OTA clears all headless state before normal reboot.
assert 'no firmware transfer started for 60 s; returning to normal UI' in T
assert 'lastActivity = last_hmi_rx' not in T
reboot_start = T.index('static void fw_handle_reboot')
reboot = T[reboot_start:T.index('static void fw_service_reboot', reboot_start)]
assert 'if(g_fw_headless_mode) fw_clear_headless_update_state();' in reboot
assert 'g_fw_safe_reboot_due_ms' in T[T.index('static bool fw_display_owned'):T.index('static String fw_connection_text')]

# Migration safety boundary: pre-v26.10.02.03 receivers do not implement the
# display-off updater and must never be asked to self-flash automatically.
C = (ROOT/f"HV_P2P_CTRL_EDGEBOX_v{VER}"/f"HV_P2P_CTRL_EDGEBOX_v{VER}.ino").read_text()
assert '"|safe_ota=1"' in T
assert 'g_hmiSafeOtaCapable' in C
assert 'hvGetPipeField(line, "safe_ota") == "1"' in C
assert 'if(!g_hmiSafeOtaCapable)' in C
assert 'manual USB bootstrap to v26.10.02.03 or newer required' in C
assert 'fw_state=" + String(hmiFwStateText())' in C
assert 'fw_compare_release_versions' in T
assert 'fw_downgrade_blocked' in T
assert 'if(releaseRelation < 0)' in T

print('CTRL_TS_SAFE_UPDATE_CONTRACT_PASS')
