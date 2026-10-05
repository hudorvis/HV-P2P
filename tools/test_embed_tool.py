#!/usr/bin/env python3
"""Unit-test carrier generation without pretending the dummy image is flashable."""
from pathlib import Path
import hashlib, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FRAME = ROOT / 'HV_P2P_CTRL_EDGEBOX_v26.10.05.08' / 'HV_P2P_RS485_Frame.h'
EMBED = ROOT / 'tools' / 'embed_ctrl_ts_firmware.py'
VERIFY = ROOT / 'tools' / 'verify_staged_hmi_header.py'

with tempfile.TemporaryDirectory(prefix='hvp2p_embed_test_') as td:
    d=Path(td)
    # Test fixture only: ESP image magic + deterministic bytes. It is never copied
    # into release firmware and is not represented as a native/flashable image.
    fixture=d/'fixture.ino.bin'
    fixture.write_bytes(bytes([0xE9]) + bytes((i % 251 for i in range(1,4096))))
    shutil.copy2(FRAME, d/'HV_P2P_RS485_Frame.h')
    out=d/'HV_P2P_CTRL_TS_Firmware_Image.h'
    subprocess.run([sys.executable,str(EMBED),str(fixture),'v26.10.05.08',str(out)],check=True)
    subprocess.run([sys.executable,str(VERIFY),str(out),str(fixture)],check=True)
    txt=out.read_text()
    carrier=out.with_suffix('.cpp')
    assert carrier.is_file()
    carrier_txt=carrier.read_text()
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() in txt
    assert 'HV_CTRL_TS_REQUIRED_PROTOCOL = 1' in txt
    assert 'extern const uint8_t HV_CTRL_TS_IMAGE[] PROGMEM;' in txt
    assert 'const uint8_t HV_CTRL_TS_IMAGE[] PROGMEM =' in carrier_txt
    # The external carrier uses escaped string-literal bytes rather than a
    # multi-megabyte comma-separated integer initializer.
    assert '0xE9,' not in carrier_txt
    assert '\\xE9' in carrier_txt

    # Host-compile the generated translation unit with a tiny Arduino shim. This
    # catches malformed/greedy string escapes before GitHub's native ESP build.
    gpp=shutil.which('g++')
    if gpp:
        (d/'Arduino.h').write_text(
            '#pragma once\n#include <cstddef>\n#include <cstdint>\n#define PROGMEM\n'
        )
        subprocess.run([gpp,'-std=gnu++17','-I',str(d),'-c',str(carrier),'-o',str(d/'carrier.o')],check=True)
print('EMBED_TOOL_SELFTEST_PASS')
