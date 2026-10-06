#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=(ROOT/'HV_P2P_CTRL_EDGEBOX_v26.10.06.10/HV_P2P_CTRL_EDGEBOX_v26.10.06.10.ino').read_text()
W=(ROOT/'HV_P2P_W1P_EDGEBOX_v26.10.06.10/HV_P2P_W1P_EDGEBOX_v26.10.06.10.ino').read_text()
H=(ROOT/'HV_P2P_CTRL_EDGEBOX_v26.10.06.10/HV_P2P_SRVR_Authority_OTA.h').read_text()
B=(ROOT/'SRVR_GitHub_v26.10.06.10/backend.py').read_text()
M=(ROOT/'SRVR_GitHub_v26.10.06.10/main.py').read_text()
for role,src in [('CTRL',C),('W1P',W)]:
    assert f'HV_P2P_FW_ROLE={role};HV_P2P_FW_TARGET=EDGEBOX_ESP100;HV_P2P_FW_VERSION=v26.10.06.10;' in src
    assert 'serviceSrvrFirmwareAuthority' in src and 'newer_than_srvr_no_downgrade' in src
    assert 'hashRunningPrefix' in src and 'downloadAndStage' in src
assert 'out.schema == "hv-p2p-firmware-manifest-v1"' in H
assert 'out.authority == "HV_P2P_SRVR"' in H
for tok in ('m.role != expectedRole','m.target != expectedTarget','TokenScanner scanner(m.role, m.target, m.version)','scanner.complete()','image_sha256_mismatch','Update.end(true)'):
    assert tok in H, tok
assert 'if(!g_srvrFirmwareMatched) return;' in C or '!g_srvrFirmwareMatched' in C
assert 'hvPrepareSafeServiceState' in W and W.index('hvPrepareSafeServiceState') < W.rindex('downloadAndStage')
assert 'FW_MATCH=' in W and '|fw_match=' in C
assert 'self._ctrl_fw_match = False' in B and 'self._w1p_fw_match = False' in B
assert 'fields.get("fw_match", "0")' in B and 'fields.get("FW_MATCH", "0")' in B
assert 'self._invalidate_w1p_status()' in B and 'required_status =' in B
assert 'or (not ctrl_fw_ok)' in B and 'or (not w1p_fw_ok)' in B
assert 'start_firmware_authority' in M and 'FIRMWARE AUTHORITY STARTUP FAIL' in M
# Backwards-compatible direct upgrade bridge for pre-beacon .01 nodes. It must
# use the already-validated authority bundle, remain asynchronous, and never
# downgrade a node that reports a newer release.
for tok in ('def _legacy_firmware_push_worker', 'HTTPConnection', '"/update/app"',
            'multipart/form-data', 'daemon=True', 'def _firmware_version_is_older'):
    assert tok in B, tok
assert 'firmware_bundle=authority.bundle' in M
assert 'def _legacy_firmware_push_required' in B and 'parts <= (26, 10, 1, 1)' in B
assert 'allow_modern_fallback' in B and 'modern_fallback' in B
assert '_fw_modern_fallback_delay_s' in B
assert 'self._send_velocity(0.0, force=True)' in B
print('AUTO_OTA_CONTRACT_PASS')
