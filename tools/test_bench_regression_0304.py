#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.05.01'
B=(ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
Q=(ROOT/f'SRVR_GitHub_v{VER}/qml/Main.qml').read_text()
L=(ROOT/f'SRVR_GitHub_v{VER}/qml/pages/LogPage.qml').read_text()
C=(ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()
T=(ROOT/f'HV_P2P_CTRL_TS_v{VER}/HV_P2P_CTRL_TS_v{VER}.ino').read_text()
W=(ROOT/f'HV_P2P_W1P_EDGEBOX_v{VER}/HV_P2P_W1P_EDGEBOX_v{VER}.ino').read_text()

# Desktop dropdown actions must not synchronously invalidate the complete live
# property graph; config updates are immediate and state telemetry follows <=50ms.
notify=B[B.index('def _emit_config_changed'):B.index('# --- QML actions ---')]
assert 'self.configChanged.emit()' in notify
assert 'self.stateChanged.emit()' not in notify
assert 'QTimer.singleShot(0, self._emit_config_changed)' in notify
assert 'root.visible ? backend.filteredLogEntries' in L
assert 'window.page===0?backend.cableProfile:[]' in Q
assert 'window.page===2?backend.freeDPreviewCableProfile:[]' in Q
assert '_last_ctrl_display_build_at' in B and '< HMI_DISPLAY_MIN_CHANGE_INTERVAL_S' in B

# AUX calibration preserves the axis sample from the exact CTRL packet that
# carried the rising edge, even if Qt later stalls before consuming the event.
assert 'put_nowait((aux_i, float(msg[1]), now))' in B
assert 'def _joystick_calibration_next(self, raw_override=None)' in B
assert 'self._joystick_calibration_next(raw_axis)' in B

# Graceful SRVR shutdown sends safety traffic before filesystem/worker teardown.
shutdown=B[B.index('def shutdown(self):'):]
assert 'self.w1p.emergency_stop()' in shutdown
assert 'self._send_srvr_offline()' in shutdown
assert shutdown.index('self.w1p.emergency_stop()') < shutdown.index('self._stop_config_writer()')
assert 'payload = b"STOP\\nSW_SRVON 0\\n"' in B
assert 'SRVR_OFFLINE' in B and 'SRVR_OFFLINE' in C
assert '#define SRVR_PEER_TIMEOUT_MS     750' in C
# Preserve the independent W1P fail-safe watchdog exactly as requested.
assert 'static const uint32_t W1P_VEL_COMMAND_TIMEOUT_MS = 500;' in W

# AUX-confirm workload is hardened: priority state packets use the light path,
# bulk HMI is temporarily suppressed, and the small debug path is heap-free.
assert 'const bool state_only = line.startsWith("HMS1|")' in T
assert 'if((bulk_packet || motion_only) && !calibration_active_now) update_progress_marker();' in T
assert 'g_hmiBulkSuppressUntilMs = millis() + 1000;' in C
assert 'const bool bulk_suppressed' in C
assert 'static char last[64]' in T

# The safe self-updater should not briefly flash its own progress dashboard just
# before intentional headless blackout; SRVR owns progress during that phase.
safe=T[T.index('if(!g_fw_headless_mode){'):T.index('if(!Update.begin(imageSize, U_FLASH))')]
assert 'fw_stage_safe_update_handoff' in safe
assert 'fw_set_device_status("CTRL-TS", "Restarting in safe update mode"' not in safe

# Reset diagnosis now carries live/min heap and free PSRAM through CTRL to SRVR.
for field in ('heap=%lu','minheap=%lu','psram=%lu'):
    assert field in T
for field in ('|ts_heap=', '|ts_min_heap=', '|ts_psram='):
    assert field in C
assert 'pre-reset heap=' in B
print('BENCH_REGRESSION_0304_PASS')
