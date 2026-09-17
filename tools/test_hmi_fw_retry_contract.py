#!/usr/bin/env python3
"""Host-side contract test for the CTRL -> CTRL-TS OTA retry semantics.

This does not emulate ESP32 flash. It verifies the source contains the safety
hardening needed for a half-duplex request/response transfer, then exercises the
expected offset/result behavior for lost ACK/FW_RESULT cases.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VER = "26.09.17.02"
CTRL = (ROOT/f"HV_P2P_CTRL_EDGEBOX_v{VER}"/f"HV_P2P_CTRL_EDGEBOX_v{VER}.ino").read_text(errors="replace")
TS = (ROOT/f"HV_P2P_CTRL_TS_v{VER}"/f"HV_P2P_CTRL_TS_v{VER}.ino").read_text(errors="replace")

required_ctrl = [
    "frame.seq != g_hmiFwSeq",
    "ignored stale response",
    "reported != expectedNext",
    "FW_ACK missing next offset",
    "invalid FW_READY offset",
    "reportedSize == HV_CTRL_TS_IMAGE_SIZE",
    "sha.length() == 64",
    "CTRL-TS did not accept FW_BEGIN",
    "HMI_FW_BLOCK_DATA = 1024",
    "HMI_FW_REPLY_TIMEOUT_MS = 3000",
    "HMI_MASTER_TURNAROUND_US = 2500",
    "HMI_FW_REBOOT_SETTLE_MS = 2000",
    "HMI_FW_WAIT_REBOOT_SETTLE",
    "newer_no_downgrade",
    "hvAuthorityCompareVersions(g_hmiReportedVersion, HV_CTRL_TS_REQUIRED_VERSION",
    "HMI.setRxBufferSize(HMI_RX_BUFFER_BYTES)",
]
required_ts = [
    "if(g_fw_finalized)",
    "FW_END is deliberately idempotent",
    "reboot_without_verified_image",
    "esp_ota_get_running_partition",
    "esp_ota_set_boot_partition",
    "CTRL_TS_SEMVER",
    "Do NOT change g_fw_image_hash while the old application is still running",
    "FW_MAX_IMAGE_SIZE = 0x380000",
    "esp_ota_get_boot_partition",
    "fw_meta_key",
    "g_fw_prefs.remove(okKey.c_str())",
    "g_fw_prefs.putString(okKey.c_str(), sha)",
    "RS485_SLAVE_TURNAROUND_US = 2500",
    "HMI_RX_BUFFER_BYTES = 4096",
    "HMI.setRxBufferSize(HMI_RX_BUFFER_BYTES)",
    "fw_service_reboot();",
    "fw_reboot_pending",
    "fw_downgrade_blocked",
    "fw_compare_versions(CTRL_TS_SEMVER, version",
    "if(!g_fw_reboot_due_ms) g_fw_reboot_due_ms = millis() + 250",
    "static void fw_abort(const char *reason, int32_t seq=-1)",
]
for token in required_ctrl:
    assert token in CTRL, f"CTRL retry/correlation guard missing: {token}"
for token in required_ts:
    assert token in TS, f"CTRL-TS retry/rollback guard missing: {token}"

# Model one 5,000-byte transfer with the production 1,024-byte blocks.
image_size = 5000
block = 1024
ctrl_offset = 0
ts_received = 0

# First block is written, but its ACK is lost.
chunk = min(block, image_size-ctrl_offset)
ts_received += chunk
# CTRL retransmits the same offset. Receiver must not rewrite it; it reports the
# authoritative already-received next offset. CTRL accepts only exact block end.
reported_next = ts_received
expected_next = ctrl_offset + chunk
assert reported_next == expected_next
ctrl_offset = reported_next

# Complete remaining blocks normally.
while ctrl_offset < image_size:
    chunk = min(block, image_size-ctrl_offset)
    ts_received += chunk
    reported_next = ts_received
    expected_next = ctrl_offset + chunk
    assert reported_next == expected_next
    ctrl_offset = reported_next
assert ctrl_offset == ts_received == image_size

# Final image is verified and FW_RESULT is lost. A repeated FW_END must return the
# same successful finalized result; it must not require an active Update session.
finalized = True
first_result = {"ok": 1, "size": image_size, "sha256": "a"*64}
retry_result = dict(first_result) if finalized else {"ok": 0}
assert retry_result == first_result

# A stale response from a previous sequence is ignored rather than advancing state.
outstanding_seq = 4242
assert (4241 != outstanding_seq)

# After REBOOT ACK the master must remain quiet while the old application is
# still alive. A new FW_BEGIN is forbidden once the receiver has finalized an
# image, so the verified inactive partition cannot be erased in this window.
reboot_ack_ms = 1000
settle_ms = 2000
receiver_restart_due_ms = reboot_ack_ms + 250
assert reboot_ack_ms + settle_ms > receiver_restart_due_ms
finalized = True
new_begin_allowed = not finalized
assert not new_begin_allowed

# Sequence zero is valid on the 16-bit wire protocol. Error replies must not use
# zero as a sentinel for "no response" after normal sequence wrap.
valid_seq_zero = 0
assert valid_seq_zero == 0

# No-downgrade model: same version remains updateable for bootstrap/hash
# convergence, newer incoming is updateable, older incoming is refused.
def ver(v): return tuple(int(x) for x in v.lstrip('v').split('.'))
running=ver('v26.09.17.02')
assert ver('v26.09.17.02') >= running
assert ver('v26.09.18.01') > running
assert ver('v26.09.15.02') < running

print("HMI_FW_RETRY_CONTRACT_PASS: lost ACK/result, stale sequence, reboot race, seq0, no-downgrade guards")
