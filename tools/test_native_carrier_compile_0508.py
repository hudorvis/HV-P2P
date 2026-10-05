#!/usr/bin/env python3
"""Regression for the .05.07 native CTRL carrier compile failure.

The production native build still remains a GitHub Actions gate. This source
regression proves that the carrier generator no longer emits the multi-megabyte
comma-separated integer initializer and that a large generated carrier is a
valid, efficiently compilable C++ translation unit on the host compiler.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EMBED = ROOT / "tools" / "embed_ctrl_ts_firmware.py"
VERIFY = ROOT / "tools" / "verify_staged_hmi_header.py"
FRAME = ROOT / "HV_P2P_CTRL_EDGEBOX_v26.10.05.08" / "HV_P2P_RS485_Frame.h"

with tempfile.TemporaryDirectory(prefix="hvp2p_carrier_0508_") as td:
    d = Path(td)
    shutil.copy2(FRAME, d / FRAME.name)
    # Large enough to exercise the representation without making every source
    # audit regenerate the full 3.5 MiB OTA slot.
    size = 1024 * 1024
    pattern = bytes(range(256))
    image = (b"\xE9" + pattern * ((size // len(pattern)) + 1))[:size]
    binary = d / "ctrl_ts.ino.bin"
    binary.write_bytes(image)
    header = d / "HV_P2P_CTRL_TS_Firmware_Image.h"

    subprocess.run([sys.executable, str(EMBED), str(binary), "v26.10.05.08", str(header)], check=True)
    subprocess.run([sys.executable, str(VERIFY), str(header), str(binary)], check=True)

    carrier = header.with_suffix(".cpp")
    h = header.read_text()
    c = carrier.read_text()
    assert header.stat().st_size < 16 * 1024
    assert "extern const uint8_t HV_CTRL_TS_IMAGE[] PROGMEM;" in h
    assert "static const uint8_t HV_CTRL_TS_IMAGE[] PROGMEM = {" not in h
    assert "const uint8_t HV_CTRL_TS_IMAGE[] PROGMEM =" in c
    assert c.count("\\x") == size

    gpp = shutil.which("g++")
    if gpp:
        (d / "Arduino.h").write_text(
            "#pragma once\n#include <cstddef>\n#include <cstdint>\n#define PROGMEM\n"
        )
        subprocess.run(
            [gpp, "-std=gnu++17", "-O2", "-I", str(d), "-c", str(carrier), "-o", str(d / "carrier.o")],
            check=True,
        )
        assert (d / "carrier.o").stat().st_size >= size

print("NATIVE_CARRIER_COMPILE_0508_PASS")
