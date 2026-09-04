#!/usr/bin/env python3
"""Host regression model for the CTRL/CTRL-TS identity and update target gate."""
from dataclasses import dataclass

REQUIRED_HW = "WS-ESP32S3-7"
REQUIRED_PROTO = 1
REQUIRED_VERSION = "v26.09.04.03"
REQUIRED_SHA = "a" * 64

@dataclass(frozen=True)
class Peer:
    hw: str
    proto: int
    version: str
    sha: str


def transport_ok(p: Peer) -> bool:
    return p.hw == REQUIRED_HW and p.proto == REQUIRED_PROTO


def identity_ok(p: Peer, image_available: bool = True) -> bool:
    return (
        transport_ok(p)
        and p.version == REQUIRED_VERSION
        and image_available
        and len(REQUIRED_SHA) == 64
        and p.sha == REQUIRED_SHA
    )


def should_auto_update(p: Peer, image_available: bool = True) -> bool:
    return transport_ok(p) and image_available and not identity_ok(p, image_available)

cases = [
    ("exact identity", Peer(REQUIRED_HW, 1, REQUIRED_VERSION, REQUIRED_SHA), True, False),
    ("old version", Peer(REQUIRED_HW, 1, "v26.08.30.01", "b"*64), False, True),
    ("wrong hash", Peer(REQUIRED_HW, 1, REQUIRED_VERSION, "b"*64), False, True),
    ("wrong hardware", Peer("OTHER-BOARD", 1, REQUIRED_VERSION, REQUIRED_SHA), False, False),
    ("wrong protocol", Peer(REQUIRED_HW, 2, REQUIRED_VERSION, REQUIRED_SHA), False, False),
]
for name, peer, expected_identity, expected_update in cases:
    assert identity_ok(peer) is expected_identity, name
    assert should_auto_update(peer) is expected_update, name

old = Peer(REQUIRED_HW, 1, "v26.08.30.01", "b"*64)
assert not identity_ok(old, image_available=False)
assert not should_auto_update(old, image_available=False)

# CTRL-TS side independently accepts FW_BEGIN only for exact target metadata.
def receiver_accepts_begin(hw: str, proto: int) -> bool:
    return hw == REQUIRED_HW and proto == REQUIRED_PROTO

assert receiver_accepts_begin(REQUIRED_HW, 1)
assert not receiver_accepts_begin("OTHER-BOARD", 1)
assert not receiver_accepts_begin(REQUIRED_HW, 2)

print("HMI_TARGET_GATE_PASS")
print("wrong hardware/protocol can never enter automatic update")
print("correct target with mismatched version/hash enters automatic update")
