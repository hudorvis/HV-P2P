#!/usr/bin/env python3
"""Patch the pinned Waveshare_ST7262_LVGL 0.1 source for ESP32_IO_Expander 0.0.3.

The upstream library declares ESP32_IO_Expander 0.0.3 as its dependency, but its
Waveshare_ST7262_LVGL.cpp still references the pre-0.0.3 CH422G address symbol
ESP_IO_EXPANDER_I2C_CH422G_ADDRESS.  ESP32_IO_Expander 0.0.3 exposes the
address-variant symbol ESP_IO_EXPANDER_I2C_CH422G_ADDRESS_000 instead.

This script applies the narrow compatibility patch after GitHub Actions clones
Waveshare_ST7262_LVGL and verifies that the installed IO-expander library really
defines the replacement symbol.  It fails closed if the expected source/API is
not present, so an upstream library change cannot be silently accepted.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import re

OLD = "ESP_IO_EXPANDER_I2C_CH422G_ADDRESS"
NEW = "ESP_IO_EXPANDER_I2C_CH422G_ADDRESS_000"


def library_declares(root: Path, token: str) -> bool:
    lib = root / "ESP32_IO_Expander"
    if not lib.is_dir():
        raise SystemExit(f"ERROR: ESP32_IO_Expander library not found: {lib}")
    for p in lib.rglob("*"):
        if not p.is_file():
            continue
        try:
            if token in p.read_text(errors="ignore"):
                return True
        except OSError:
            pass
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--libraries-dir", type=Path, required=True)
    args = ap.parse_args()
    libs = args.libraries_dir.expanduser().resolve()

    if not library_declares(libs, NEW):
        raise SystemExit(
            f"ERROR: installed ESP32_IO_Expander does not declare required {NEW}; "
            "refusing to patch Waveshare library"
        )

    cpp = libs / "Waveshare_ST7262_LVGL" / "src" / "Waveshare_ST7262_LVGL.cpp"
    if not cpp.is_file():
        raise SystemExit(f"ERROR: Waveshare source not found: {cpp}")

    text = cpp.read_text(errors="strict")
    # Replace only the exact legacy identifier; do not touch already-suffixed symbols.
    patched, count = re.subn(rf"\b{re.escape(OLD)}\b(?!_000)", NEW, text)
    if count == 0:
        if NEW in text and OLD not in re.sub(rf"\b{re.escape(NEW)}\b", "", text):
            print("WAVESHARE_COMPAT_ALREADY_PATCHED")
            return 0
        raise SystemExit(
            f"ERROR: expected legacy Waveshare token {OLD} not found; upstream source changed"
        )

    cpp.write_text(patched)
    verify = cpp.read_text()
    if re.search(rf"\b{re.escape(OLD)}\b(?!_000)", verify):
        raise SystemExit("ERROR: legacy CH422G address token remains after patch")
    if NEW not in verify:
        raise SystemExit("ERROR: replacement CH422G address token missing after patch")

    print(f"WAVESHARE_COMPAT_PATCH_PASS replacements={count} symbol={NEW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
