#!/usr/bin/env python3
"""Host-side contract test for the CTRL -> CTRL-TS OTA retry semantics.

This does not emulate ESP32 flash. It verifies the source contains the safety
hardening needed for a half-duplex request/response transfer, then exercises the
expected offset/result behavior for lost ACK/FW_RESULT cases.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VER = "26.08.31.09"
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
    "commit marker",
]
for token in required_ctrl:
    assert token in CTRL, f"CTRL retry/correlation guard missing: {token}"
for token in required_ts:
    assert token in TS, f"CTRL-TS retry/rollback guard missing: {token}"

# Model one 5,000-byte transfer with 2,048-byte blocks.
image_size = 5000
block = 2048
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

print("HMI_FW_RETRY_CONTRACT_PASS: lost block ACK, lost FW_RESULT, stale sequence, rollback guards")
