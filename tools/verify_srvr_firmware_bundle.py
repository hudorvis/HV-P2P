#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import sys

VER = "26.09.15.02"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    args = ap.parse_args()
    srvr = Path(__file__).resolve().parents[1] / f"SRVR_GitHub_v{VER}"
    sys.path.insert(0, str(srvr))
    from firmware_authority import validate_firmware_bundle
    b = validate_firmware_bundle(args.bundle, VER)
    print(f"SRVR_FIRMWARE_BUNDLE_VERIFY_PASS release={b.release} bundle_id={b.manifest['bundle_id']}")
    for role in ("CTRL", "W1P"):
        e = b.manifest["roles"][role]
        print(f"  {role}: {e['size']} bytes {e['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
