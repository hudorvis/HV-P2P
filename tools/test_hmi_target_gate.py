#!/usr/bin/env python3
"""Host regression model for the CTRL/CTRL-TS identity and safe-update target gate."""
from dataclasses import dataclass

REQUIRED_HW = "WS-ESP32S3-7"
REQUIRED_PROTO = 1
REQUIRED_VERSION = "v26.10.05.11"
REQUIRED_SHA = "a" * 64

@dataclass(frozen=True)
class Peer:
    hw: str
    proto: int
    version: str
    sha: str
    safe_ota: int


def transport_ok(p: Peer) -> bool:
    return p.hw == REQUIRED_HW and p.proto == REQUIRED_PROTO


def identity_ok(p: Peer, image_available: bool = True) -> bool:
    return (
        transport_ok(p)
        and p.version == REQUIRED_VERSION
        and image_available
        and len(REQUIRED_SHA) == 64
        and p.sha == REQUIRED_SHA
        and p.safe_ota >= 2
    )


def should_auto_update(p: Peer, image_available: bool = True) -> bool:
    # v26.10.05.11+ capability is mandatory. Pre-.03 receivers can speak the
    # transport protocol but self-program flash while their RGB/PSRAM display is
    # active, so the carrier must require a one-time USB bootstrap instead.
    return transport_ok(p) and p.safe_ota >= 2 and image_available and not identity_ok(p, image_available)

cases = [
    ("exact identity", Peer(REQUIRED_HW, 1, REQUIRED_VERSION, REQUIRED_SHA, 2), True, False),
    ("level-2 older version", Peer(REQUIRED_HW, 1, "v26.08.30.01", "b"*64, 2), False, True),
    ("level-2 wrong hash", Peer(REQUIRED_HW, 1, REQUIRED_VERSION, "b"*64, 2), False, True),
    ("legacy receiver level 0", Peer(REQUIRED_HW, 1, "v26.10.02.02", "b"*64, 0), False, False),
    (".03 receiver level 1", Peer(REQUIRED_HW, 1, "v26.10.02.03", "b"*64, 1), False, False),
    ("wrong hardware", Peer("OTHER-BOARD", 1, REQUIRED_VERSION, REQUIRED_SHA, 2), False, False),
    ("wrong protocol", Peer(REQUIRED_HW, 2, REQUIRED_VERSION, REQUIRED_SHA, 2), False, False),
]
for name, peer, expected_identity, expected_update in cases:
    assert identity_ok(peer) is expected_identity, name
    assert should_auto_update(peer) is expected_update, name

old = Peer(REQUIRED_HW, 1, "v26.08.30.01", "b"*64, 0)
assert not identity_ok(old, image_available=False)
assert not should_auto_update(old, image_available=False)

# CTRL-TS side independently accepts only the exact target metadata and never
# accepts a numerically older release than the one currently running.
def version_tuple(v: str):
    if not v.startswith("v"):
        return None
    parts = v[1:].split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)

def receiver_accepts_begin(hw: str, proto: int, version: str) -> bool:
    cand = version_tuple(version)
    running = version_tuple(REQUIRED_VERSION)
    return hw == REQUIRED_HW and proto == REQUIRED_PROTO and cand is not None and cand >= running

assert receiver_accepts_begin(REQUIRED_HW, 1, REQUIRED_VERSION)
assert receiver_accepts_begin(REQUIRED_HW, 1, "v26.10.05.11")
assert not receiver_accepts_begin(REQUIRED_HW, 1, "v26.10.02.02")
assert not receiver_accepts_begin("OTHER-BOARD", 1, REQUIRED_VERSION)
assert not receiver_accepts_begin(REQUIRED_HW, 2, REQUIRED_VERSION)

print("HMI_TARGET_GATE_PASS")
print("wrong hardware/protocol can never enter automatic update")
print("safe_ota level 0/1 receiver can never enter automatic self-update")
print("safe_ota level-2 exact target with mismatched identity enters automatic update")
