#!/usr/bin/env python3
"""Stage the real native CTRL-TS application as an external CTRL carrier source.

Usage:
  python3 tools/embed_ctrl_ts_firmware.py \
      HV_P2P_CTRL_TS_v26.10.05.08.ino.bin v26.10.05.08 \
      HV_P2P_CTRL_EDGEBOX_v26.10.05.08/HV_P2P_CTRL_TS_Firmware_Image.h

The clean source tree intentionally contains a #error build guard.  After the
CTRL-TS has been natively compiled, this helper replaces the guard with a small
metadata/declaration header and writes a sibling .cpp containing the exact image
as escaped string-literal data.

Why the data is kept out of the header:
  A multi-megabyte comma-separated C initializer is reparsed as millions of
  integer tokens every time the CTRL sketch translation unit is compiled.  That
  made the GitHub native CTRL build fragile as the touchscreen image grew.
  Keeping the exact same bytes in one generated translation unit materially
  reduces compiler AST/memory pressure without changing the CTRL firmware image
  contents, the RS485 transfer protocol, or the verified SHA-256 identity.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
import re
import sys
import tempfile
from typing import NoReturn

MAX_IMAGE = 0x380000
EXPECTED_HW = "WS-ESP32S3-7"
VERSION_RE = re.compile(r"^v\d{2}\.\d{2}\.\d{2}\.\d{2}$")
ESP_IMAGE_MAGIC = 0xE9
MIN_PLAUSIBLE_IMAGE = 32
STRING_BYTES_PER_LINE = 256


def die(message: str) -> NoReturn:
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


def escaped_literal_source(data: bytes, header_name: str) -> str:
    lines = [
        "// AUTO-GENERATED FROM A NATIVE CTRL-TS APPLICATION BINARY. Do not hand edit.",
        f'#include "{header_name}"',
        "",
        "// One external translation unit keeps the multi-megabyte carrier out of",
        "// the main Arduino sketch parser while preserving byte-for-byte identity.",
        "const uint8_t HV_CTRL_TS_IMAGE[] PROGMEM =",
    ]
    for i in range(0, len(data), STRING_BYTES_PER_LINE):
        chunk = data[i : i + STRING_BYTES_PER_LINE]
        lines.append('  "' + "".join(f"\\x{b:02X}" for b in chunk) + '"')
    lines += [
        "  ;",
        "",
        'static_assert(sizeof(HV_CTRL_TS_IMAGE) == HV_CTRL_TS_IMAGE_SIZE + 1,',
        '              "CTRL-TS carrier size mismatch");',
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: embed_ctrl_ts_firmware.py <ctrl-ts.ino.bin> <vYY.MM.DD.RR> <output.h>"
        )

    src = Path(sys.argv[1]).resolve()
    version = sys.argv[2].strip()
    out = Path(sys.argv[3]).resolve()
    carrier_cpp = out.with_suffix(".cpp")

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

    header_lines = [
        "#pragma once",
        "#include <Arduino.h>",
        "",
        "// AUTO-GENERATED METADATA FOR THE NATIVE CTRL-TS APPLICATION CARRIER.",
        f"// Source binary: {src.name}",
        f"// SHA-256: {sha}",
        "static constexpr bool HV_CTRL_TS_IMAGE_AVAILABLE = true;",
        f'static constexpr const char* HV_CTRL_TS_REQUIRED_HW = "{EXPECTED_HW}";',
        f"static constexpr uint8_t HV_CTRL_TS_REQUIRED_PROTOCOL = {protocol};",
        f'static constexpr const char* HV_CTRL_TS_REQUIRED_VERSION = "{version}";',
        f'static constexpr const char* HV_CTRL_TS_REQUIRED_SHA256 = "{sha}";',
        f"static constexpr size_t HV_CTRL_TS_IMAGE_SIZE = {len(data)}UL;",
        "extern const uint8_t HV_CTRL_TS_IMAGE[] PROGMEM;",
        "",
    ]

    # Write data first, metadata last.  A staged header must never claim the
    # carrier is available unless its sibling source has already been written.
    atomic_write(carrier_cpp, escaped_literal_source(data, out.name))
    atomic_write(out, "\n".join(header_lines))

    print(f"Image:    {src}")
    print(f"Hardware: {EXPECTED_HW}")
    print(f"Protocol: {protocol}")
    print(f"Version:  {version}")
    print(f"Size:     {len(data)} bytes ({len(data)/1024/1024:.3f} MiB)")
    print(f"SHA256:   {sha}")
    print(f"Header:   {out}")
    print(f"Carrier:  {carrier_cpp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
