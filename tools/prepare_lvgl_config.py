#!/usr/bin/env python3
"""Create the LVGL 8.3.11 Arduino configuration required by HV P2P CTRL-TS.

LVGL's Arduino packaging expects lv_conf.h beside the lvgl library directory,
not inside it.  This helper copies the installed library's matching template and
turns on only the project settings that differ from the stock template.
"""
from pathlib import Path
import argparse
import re
import sys

REQUIRED_FONTS = (8, 10, 12, 14, 16, 18, 24)


def replace_one(text: str, pattern: str, repl: str, label: str) -> str:
    out, n = re.subn(pattern, repl, text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"ERROR: could not set {label}; template layout changed")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--libraries-dir', type=Path, required=True,
                    help='Arduino libraries directory containing lvgl/')
    args = ap.parse_args()

    libs = args.libraries_dir.expanduser().resolve()
    template = libs / 'lvgl' / 'lv_conf_template.h'
    target = libs / 'lv_conf.h'
    if not template.is_file():
        raise SystemExit(f'ERROR: LVGL template not found: {template}')

    text = template.read_text(errors='strict')
    if 'Configuration file for v8.3.11' not in text:
        raise SystemExit('ERROR: expected LVGL 8.3.11 template')

    text = replace_one(text, r'^#if\s+0\s+/\*Set it to "1" to enable content\*/',
                       '#if 1 /*Set it to "1" to enable content*/', 'config enable')
    text = replace_one(text, r'^#define\s+LV_COLOR_DEPTH\s+\d+',
                       '#define LV_COLOR_DEPTH 16', 'LV_COLOR_DEPTH')
    text = replace_one(text, r'^#define\s+LV_TICK_CUSTOM\s+\d+',
                       '#define LV_TICK_CUSTOM 1', 'LV_TICK_CUSTOM')

    for size in REQUIRED_FONTS:
        text = replace_one(text,
                           rf'^#define\s+LV_FONT_MONTSERRAT_{size}\s+\d+',
                           f'#define LV_FONT_MONTSERRAT_{size} 1',
                           f'LV_FONT_MONTSERRAT_{size}')

    target.write_text(text)

    # Final deterministic sanity checks.
    written = target.read_text()
    required = [
        '#if 1 /*Set it to "1" to enable content*/',
        '#define LV_COLOR_DEPTH 16',
        '#define LV_TICK_CUSTOM 1',
        '#define LV_TICK_CUSTOM_INCLUDE "Arduino.h"',
        '#define LV_TICK_CUSTOM_SYS_TIME_EXPR (millis())',
    ] + [f'#define LV_FONT_MONTSERRAT_{n} 1' for n in REQUIRED_FONTS]
    missing = [x for x in required if x not in written]
    if missing:
        raise SystemExit('ERROR: generated LVGL config missing: ' + ', '.join(missing))

    print(f'LVGL_CONFIG_READY {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
