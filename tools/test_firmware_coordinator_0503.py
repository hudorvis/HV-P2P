#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
VER='26.10.06.11'
B=(ROOT/f'SRVR_GitHub_v{VER}/backend.py').read_text()
C=(ROOT/f'HV_P2P_CTRL_EDGEBOX_v{VER}/HV_P2P_CTRL_EDGEBOX_v{VER}.ino').read_text()

# The final-stage CTRL-TS grant must ride the lightweight release beacon, not
# depend on a coincident bulk DSP1 packet.
beacon=B[B.index('def _send_ctrl_firmware_beacon'):B.index('def _send_w1p_firmware_beacon')]
assert 'ts_allowed={1 if self._ctrl_ts_update_allowed_safe() else 0}' in beacon
apply=C[C.index('static bool applySrvrFirmwareBeacon'):C.index('static String buildHmiStatePacketFromSrvr')]
assert 'hvGetPipeField(line, "ts_allowed")' in apply
assert 'hvGetPipeField(line, "fw_ts_allowed")' in apply
assert 'g_hmiTsCoordinatorSeen = true;' in apply
assert 'g_hmiTsUpdateAllowed = (tsGrant == "1");' in apply
start=C[C.index('static void hmiFwStart(bool coordinatorFallback=false)'):C.index('static bool hmiFwHandleFrame')]
assert 'g_hmiTsCoordinatorSeen' in start and 'g_hmiTsUpdateAllowed' in start
assert 'g_latestDisplayPacket' not in start

# A grant arriving after the mismatch HELLO must still be able to start the
# transfer without a reboot/timing coincidence, but only from a fresh verified
# peer identity and the safe OTA transport target.
rx=C[C.index('static void handleHmiRx()'):C.index('static bool initEthernetStatic')]
for tok in ('freshIdentity', 'g_hmiIdentitySeenMs', 'g_hmiTsCoordinatorSeen',
            'g_hmiTsUpdateAllowed', '!hmiIdentityMatches()', 'hmiTransportCompatible()',
            'g_hmiSafeOtaCapable', 'hmiFwStart(coordinatorFallback);'):
    assert tok in rx, tok
assert '|ts_grant=' in C

# Modern pull remains first choice, but an older node that stays mismatched for
# a bounded interval receives the already-verified SRVR image through its proven
# /update/app endpoint. This prevents update start from requiring a manual reboot.
assert 'self._fw_modern_fallback_delay_s = 2.5' in B
assert 'allow_modern_fallback: bool = False' in B
assert 'modern_fallback = bool(allow_modern_fallback and self._firmware_version_is_older(reported))' in B
svc=B[B.index('def _service_legacy_firmware_push'):B.index('def _motion_tick')]
assert 'self._fw_mismatch_since.get("ctrl"' in svc
assert 'self._fw_mismatch_since.get("w1p"' in svc
assert 'allow_modern_fallback=True' in svc
assert 'self._fw_progress["ctrl"]["active"]' in svc and 'self._ctrl_fw_authority in ("updating", "rebooting")' in svc
assert 'self._fw_progress["w1p"]["active"]' in svc and '"update_waiting_safe_idle"' in svc

# CTRL must converge first. W1P gets the ordered second stage and a bounded
# recovery window, but a safe-idle deferral must not strand CTRL-TS forever.
assert 'if not (self._ctrl_fw_match and self._ctrl_authority_fresh()):' in svc
allow=B[B.index('def _ctrl_ts_update_allowed'):B.index('def _build_controller_display_packet')]
assert '(now_wall - matched_since) >= 1.0' in allow
assert 'self._fw_progress["w1p"]["active"]' in allow
assert 'W1P_FINAL_STAGE_WAIT_S' in allow
assert 'W1P_ACTIVE_UPDATE_WAIT_S' in allow
assert '_ctrl_ts_grant_latched' in allow
assert 'bounded W1P wait expired; W1P remains fail-closed' in allow
assert 'if self.w1p.connected:\n            return False' not in allow

print('FIRMWARE_COORDINATOR_0503_PASS')
