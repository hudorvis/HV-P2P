#!/usr/bin/env python3
"""Verify a generated CTRL-TS carrier header against its embedded byte array."""
from __future__ import annotations
from pathlib import Path
import hashlib, re, sys

MAX_IMAGE = 0x380000
EXPECTED_HW = "WS-ESP32S3-7"
EXPECTED_VERSION = "v26.08.31.04"


def fail(msg: str) -> None:
    raise SystemExit(f"ERROR: {msg}")


def grab(pattern: str, text: str, label: str) -> str:
    m = re.search(pattern, text)
    if not m:
        fail(f"missing {label}")
    return m.group(1)


def main() -> int:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: verify_staged_hmi_header.py <generated_header.h> [expected_binary.bin]")
    header = Path(sys.argv[1])
    text = header.read_text(errors="replace")
    if '#error "CTRL-TS firmware image has not been staged' in text:
        fail("header is still the build guard; no native CTRL-TS image is staged")
    if not re.search(r'HV_CTRL_TS_IMAGE_AVAILABLE\s*=\s*true\s*;', text):
        fail("HV_CTRL_TS_IMAGE_AVAILABLE is not true")

    hw = grab(r'HV_CTRL_TS_REQUIRED_HW\s*=\s*"([^"]+)"', text, "hardware id")
    protocol = int(grab(r'HV_CTRL_TS_REQUIRED_PROTOCOL\s*=\s*(\d+)', text, "protocol"))
    version = grab(r'HV_CTRL_TS_REQUIRED_VERSION\s*=\s*"([^"]+)"', text, "version")
    expected_sha = grab(r'HV_CTRL_TS_REQUIRED_SHA256\s*=\s*"([0-9a-fA-F]{64})"', text, "SHA-256").lower()
    declared_size = int(grab(r'HV_CTRL_TS_IMAGE_SIZE\s*=\s*(\d+)', text, "image size"))

    if hw != EXPECTED_HW:
        fail(f"wrong HMI hardware id {hw!r}")
    if not 1 <= protocol <= 255:
        fail(f"invalid protocol {protocol}")
    if version != EXPECTED_VERSION:
        fail(f"wrong carrier version {version!r}; expected {EXPECTED_VERSION}")
    if not 0 < declared_size <= MAX_IMAGE:
        fail(f"declared image size {declared_size} is outside 1..0x{MAX_IMAGE:X}")

    block = re.search(r'HV_CTRL_TS_IMAGE\[\]\s+PROGMEM\s*=\s*\{(.*?)\};', text, re.S)
    if not block:
        fail("embedded byte array not found")
    tokens = re.findall(r'0x([0-9A-Fa-f]{2})', block.group(1))
    data = bytes(int(x, 16) for x in tokens)
    if len(data) != declared_size:
        fail(f"embedded array is {len(data)} bytes, declared {declared_size}")
    if not data or data[0] != 0xE9:
        fail("embedded image does not have ESP application image magic 0xE9")
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_sha != expected_sha:
        fail(f"embedded image SHA mismatch: {actual_sha} != {expected_sha}")

    if len(sys.argv) == 3:
        binary = Path(sys.argv[2]).read_bytes()
        if binary != data:
            fail("embedded byte array is not byte-identical to supplied native binary")

    print("STAGED_HMI_HEADER_PASS")
    print(f"hardware={hw}")
    print(f"protocol={protocol}")
    print(f"version={version}")
    print(f"size={declared_size}")
    print(f"sha256={actual_sha}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
