#!/usr/bin/env python3
"""Static/logic contract for the display-off CTRL-TS self-updater.

This prevents the two bench regressions seen in .01-.03:
1) RGB/PSRAM corruption caused by writing flash while the display pipeline lived.
2) .03's safe-reboot race where CTRL could rediscover the still-running UI and
   repeatedly send FW_BEGIN, continuously postponing the touchscreen reboot.
Native compilation and real-hardware timing remain GitHub/bench gates.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
VER = "26.10.06.10"
T = (ROOT/f"HV_P2P_CTRL_TS_v{VER}"/f"HV_P2P_CTRL_TS_v{VER}.ino").read_text()
C = (ROOT/f"HV_P2P_CTRL_EDGEBOX_v{VER}"/f"HV_P2P_CTRL_EDGEBOX_v{VER}.ino").read_text()
P = (ROOT/'tools'/'prepare_waveshare_library.py').read_text()
WF = next((ROOT/'.github'/'workflows').glob('*.yml')).read_text()

# The failed .01/.02 active-RGB OTA experiment is prohibited outright.
for token in ('esp_lcd_rgb_panel_set_pclk', 'esp_lcd_rgb_panel_restart', 'FW_RGB_PCLK_HZ', 'NORMAL_RGB_PCLK_HZ'):
    assert token not in T, token
assert '#include <esp_lcd_panel_rgb.h>' not in T
assert 'LVGL_PORT_RGB_BOUNCE_BUFFER_SIZE' not in P
assert 'LVGL_PORT_RGB_BOUNCE_BUFFER_SIZE (LVGL_PORT_DISP_WIDTH * 20)' not in WF

# Safe handoff lives only in retained INTERNAL RAM. The normal displayed
# FW_BEGIN is forbidden from touching Preferences/NVS or Update.*.
for token in ('#include <esp_attr.h>', '__NOINIT_ATTR', 'FwSafeHandoff',
              'FW_SAFE_HANDOFF_MAGIC', 'fw_safe_handoff_checksum',
              'fw_stage_safe_update_handoff', 'fw_prepare_headless_mode',
              'fw_headless_blackout', 'fw_clear_headless_update_state',
              'FW_HEADLESS_IDLE_RETURN_MS', 'ESP_RST_SW'):
    assert token in T, token
for forbidden in ('putString("upd_target"', 'putString("upd_sha"', 'putBool("upd_mode"',
                  'getString("upd_target"', 'getString("upd_sha"', 'getBool("upd_mode"'):
    assert forbidden not in T, forbidden

# Pre-restart blackout still uses the already-initialized, known-good Waveshare
# expander instance. The headless boot itself must NOT create a second CH422G/I2C
# initialization path before the Waveshare stack exists.
reboot_start = T.index('static void fw_service_reboot(){')
reboot_service = T[reboot_start:T.index('static void fw_service_timeout(){', reboot_start)]
assert 'expander->digitalWrite(LCD_BL, LOW);' in reboot_service
assert 'expander->digitalWrite(LCD_RST, LOW);' in reboot_service
blackout = T[T.index('static bool fw_headless_blackout'):T.index('static void fw_service_headless_idle_return')]
for forbidden in ('new ESP_IOExpander_CH422G', 'expander->init()', 'expander->begin()',
                  'expander->pinMode', 'Wire.begin', 'lcd_init()', 'psramFound()'):
    assert forbidden not in blackout, forbidden
assert 'display stack remains uninitialized' in blackout

begin = T[T.index('static void fw_handle_begin'):T.index('static void fw_handle_block')]
headless_gate = begin.index('if(!g_fw_headless_mode)')
update_begin = begin.index('Update.begin(imageSize, U_FLASH)')
assert headless_gate < update_begin
handoff = begin[headless_gate:update_begin]
for token in ('fw_stage_safe_update_handoff(version, sha)',
              'Make the transition explicit',
              'fw_safe_reboot_retry',
              'g_fw_safe_reboot_due_ms = millis() + 1800',
              'return;'):
    assert token in handoff, token
for forbidden in ('g_fw_prefs', 'Preferences', '.put', '.remove', 'Update.begin', 'Update.write', 'lv_refr_now'):
    assert forbidden not in handoff, forbidden

# Critical .03 bench fix: once the safe reboot has been scheduled, a duplicate
# FW_BEGIN may repeat the transition reply but MUST NOT restage or move the
# deadline. This prevents an endless 0% loop.
dup_guard = begin[begin.index('if(g_fw_safe_reboot_due_ms)'):begin.index('if(g_fw_finalized)')]
assert 'fw_safe_reboot_retry' in dup_guard
assert 'return;' in dup_guard
for forbidden in ('fw_stage_safe_update_handoff', 'g_fw_safe_reboot_due_ms =', 'Update.begin', 'Update.write'):
    assert forbidden not in dup_guard, forbidden
assert begin.index('if(g_fw_safe_reboot_due_ms)') < begin.index('fw_stage_safe_update_handoff(version, sha)')

# CTRL must also stay quiet long enough for the 1800 ms touchscreen handoff to
# actually happen. This is non-blocking: it suppresses only HMI discovery/OTA,
# not the real-time CTRL control loop.
for token in ('g_hmiSafeRebootHoldUntilMs', 'millis() + 3000',
              'holding discovery until reboot completes', 'safeRebootHold'):
    assert token in C, token
safe_reply = C[C.index('text == "fw_safe_reboot_retry"'):C.index('Serial.printf("[HMI FW] CTRL-TS updater error')]
assert 'g_hmiSafeRebootHoldUntilMs = millis() + 3000;' in safe_reply
hello_service = C[C.index('static void handleHmiRx'):C.index('static bool initEthernetStatic')]
assert 'if(!g_ctrlAuthorityUpdatePending && !safeRebootHold && (now - g_lastHmiHelloTxMs) >= 500)' in hello_service

# Handoff acceptance is constrained to the deliberate software restart and its
# RAM payload is magic/checksum/format validated before headless entry.
prep = T[T.index('static bool fw_prepare_headless_mode'):T.index('static void fw_clear_headless_update_state')]
for token in ('esp_reset_reason() != ESP_RST_SW', 'FW_SAFE_HANDOFF_MAGIC',
              'fw_safe_version_valid', 'fw_safe_sha_valid', 'fw_safe_handoff_checksum'):
    assert token in prep, token
assert 'g_fw_safe_handoff.magic = 0;' in prep

setup = T[T.index('void setup()'):T.index('void loop()')]
assert setup.index('fw_prepare_headless_mode()') < setup.index('load_fw_identity()') < setup.index('\n  lcd_init();')
assert setup.index('fw_headless_blackout()') < setup.index('load_fw_identity()')
assert '[WS-HMI] early reset_reason=' in setup
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

# boot_service_uart continues servicing timeout/reboot while setup is parked
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

# Migration safety boundary: .03 advertises safe_ota=1 but contains the reboot
# race above. .04 raises the capability level to 2, and CTRL .04 refuses to
# auto-stream into level 0/1 receivers. One manual .04 bootstrap is therefore
# the conservative recovery boundary; .04+ can auto-update thereafter.
assert '"|safe_ota=2"' in T
assert 'g_hmiSafeOtaLevel' in C
assert 'g_hmiSafeOtaCapable = g_hmiSafeOtaLevel >= 2' in C
assert 'if(g_hmiSafeOtaLevel < 2) return false;' in C
assert 'if(!g_hmiSafeOtaCapable)' in C
assert 'lacks safe_ota=2' in C
assert 'manual USB bootstrap to v26.10.03.04 or newer required' in C
assert 'fw_state=" + String(hmiFwStateText())' in C
assert 'fw_compare_release_versions' in T
assert 'fw_downgrade_blocked' in T
assert 'if(releaseRelation < 0)' in T

# Tiny timing model of the observed race: a 100 ms rediscovery cadence can push a
# 1800 ms reboot forever if every duplicate resets the deadline. Fixed receiver
# leaves the original deadline untouched, and fixed CTRL additionally stays quiet
# for 3000 ms.
old_due = 1800
for t in range(100, 2000, 100):
    if t < old_due:
        old_due = t + 1800
assert old_due > 2000  # demonstrates the old starvation mechanism
fixed_due = 1800
for t in range(100, 2000, 100):
    if t < fixed_due:
        pass  # duplicate is acknowledged but deadline is NOT moved
assert fixed_due == 1800
assert 3000 > fixed_due

print('CTRL_TS_SAFE_UPDATE_CONTRACT_PASS')
