#!/usr/bin/env python3
"""Embed the *real, natively compiled* CTRL-TS application image in CTRL.

Usage:
  python3 tools/embed_ctrl_ts_firmware.py \
      HV_P2P_CTRL_TS_v26.09.04.02.ino.bin v26.09.04.02 \
      HV_P2P_CTRL_EDGEBOX_v26.09.04.02/HV_P2P_CTRL_TS_Firmware_Image.h

The source tree intentionally contains a #error build guard instead of a zero-byte
placeholder.  This helper replaces that guard only after a genuine ESP32 app image
exists.  It validates target size, ESP image magic, semantic version and the shared
RS485 protocol version, then writes the generated carrier header atomically.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
import re
import sys
import tempfile

MAX_IMAGE = 0x380000              # CTRL-TS app0/app1 slot size
EXPECTED_HW = "WS-ESP32S3-7"
VERSION_RE = re.compile(r"^v\d{2}\.\d{2}\.\d{2}\.\d{2}$")
ESP_IMAGE_MAGIC = 0xE9
MIN_PLAUSIBLE_IMAGE = 32


def die(message: str) -> "NoReturn":
    raise SystemExit(f"ERROR: {message}")


def protocol_version_for(output_header: Path) -> int:
    frame_header = output_header.parent / "HV_P2P_RS485_Frame.h"
    if not frame_header.is_file():
        die(f"shared RS485 header not found beside carrier output: {frame_header}")
    text = frame_header.read_text(errors="replace")
    match = re.search(r"PROTOCOL_VERSION\s*=\s*(\d+)\s*;", text)
    if not match:
        die("could not determine HVP2P RS485 PROTOCOL_VERSION")
    value = int(match.group(1))
    if not 1 <= value <= 255:
        die(f"invalid HVP2P RS485 protocol version {value}")
    return value


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: embed_ctrl_ts_firmware.py <ctrl-ts.ino.bin> <vYY.MM.DD.RR> <output.h>"
        )

    src = Path(sys.argv[1]).resolve()
    version = sys.argv[2].strip()
    out = Path(sys.argv[3]).resolve()

    if not VERSION_RE.fullmatch(version):
        die(f"version must match vYY.MM.DD.RR, got {version!r}")
    if not src.is_file():
        die(f"CTRL-TS application binary not found: {src}")

    data = src.read_bytes()
    if len(data) < MIN_PLAUSIBLE_IMAGE:
        die(f"firmware image is implausibly small ({len(data)} bytes)")
    if len(data) > MAX_IMAGE:
        die(f"{len(data)} bytes exceeds the 0x{MAX_IMAGE:X}-byte CTRL-TS OTA slot")
    if data[0] != ESP_IMAGE_MAGIC:
        die(
            f"{src.name} does not look like an ESP application image "
            f"(expected first byte 0x{ESP_IMAGE_MAGIC:02X}, got 0x{data[0]:02X})"
        )

    protocol = protocol_version_for(out)
    sha = hashlib.sha256(data).hexdigest()

    lines = [
        "#pragma once",
        "#include <Arduino.h>",
        "",
        "// AUTO-GENERATED FROM A NATIVE CTRL-TS APPLICATION BINARY. Do not hand edit.",
        f'// Source binary: {src.name}',
        f'// SHA-256: {sha}',
        "static constexpr bool HV_CTRL_TS_IMAGE_AVAILABLE = true;",
        f'static constexpr const char* HV_CTRL_TS_REQUIRED_HW = "{EXPECTED_HW}";',
        f"static constexpr uint8_t HV_CTRL_TS_REQUIRED_PROTOCOL = {protocol};",
        f'static constexpr const char* HV_CTRL_TS_REQUIRED_VERSION = "{version}";',
        f'static constexpr const char* HV_CTRL_TS_REQUIRED_SHA256 = "{sha}";',
        f"static constexpr size_t HV_CTRL_TS_IMAGE_SIZE = {len(data)}UL;",
        "static const uint8_t HV_CTRL_TS_IMAGE[] PROGMEM = {",
    ]
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        lines.append("  " + ", ".join(f"0x{b:02X}" for b in chunk) + ",")
    lines += ["};", "", 'static_assert(sizeof(HV_CTRL_TS_IMAGE) == HV_CTRL_TS_IMAGE_SIZE, "CTRL-TS carrier size mismatch");', ""]

    atomic_write(out, "\n".join(lines))
    print(f"Image:    {src}")
    print(f"Hardware: {EXPECTED_HW}")
    print(f"Protocol: {protocol}")
    print(f"Version:  {version}")
    print(f"Size:     {len(data)} bytes ({len(data)/1024/1024:.3f} MiB)")
    print(f"SHA256:   {sha}")
    print(f"Wrote:    {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
