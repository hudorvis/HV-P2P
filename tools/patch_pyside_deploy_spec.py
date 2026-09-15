#!/usr/bin/env python3
"""Patch pyside6-deploy's generated spec with HV P2P deployment invariants.

Nuitka intentionally treats *.bin as executable/binary code and skips those files
when they are discovered through --include-data-dir. CTRL/W1P ESP application
images are data to SRVR, so force those two exact files with --include-data-files.
"""
from __future__ import annotations

import argparse
from pathlib import Path

FORCED_FW_FLAGS = (
    "--include-data-files=firmware_bundle/ctrl.bin=firmware_bundle/ctrl.bin",
    "--include-data-files=firmware_bundle/w1p.bin=firmware_bundle/w1p.bin",
)
LEGACY_FW_DIR_FLAG = "--include-data-dir=firmware_bundle=firmware_bundle"


def patch_spec(spec_path: Path, *, windows: bool = False) -> None:
    for name in ("manifest.json", "SHA256SUMS.txt", "ctrl.bin", "w1p.bin"):
        p = Path("firmware_bundle") / name
        if not p.is_file() or p.stat().st_size <= 0:
            raise SystemExit(f"required staged firmware bundle file missing/empty: {p}")

    lines = spec_path.read_text(encoding="utf-8").splitlines()
    section = ""
    nuitka_changed = False
    icon_changed = not windows
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.lower()
        if windows and section == "[app]" and stripped.startswith("icon") and "=" in line:
            prefix = line.split("=", 1)[0]
            line = prefix + "= HV_P2P_SRVR_icon.ico"
            icon_changed = True
        elif section == "[nuitka]" and stripped.startswith("extra_args") and "=" in line:
            prefix, value = line.split("=", 1)
            args = value.strip().split()
            # Remove the old directory rule: it never carried *.bin and only
            # duplicated text resources already discovered by pyside6-deploy.
            args = [a for a in args if a != LEGACY_FW_DIR_FLAG]
            if windows and "--assume-yes-for-downloads" not in args:
                args.append("--assume-yes-for-downloads")
            for flag in FORCED_FW_FLAGS:
                if flag not in args:
                    args.append(flag)
            line = prefix + "= " + " ".join(args)
            nuitka_changed = True
        out.append(line)

    if not nuitka_changed:
        raise SystemExit("pysidedeploy.spec [nuitka] extra_args field not found")
    if not icon_changed:
        raise SystemExit("pysidedeploy.spec [app] icon field not found")
    if windows:
        icon = Path("HV_P2P_SRVR_icon.ico")
        if not icon.is_file() or icon.stat().st_size <= 1024:
            raise SystemExit("Windows icon missing/invalid")
    spec_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", nargs="?", default="pysidedeploy.spec")
    ap.add_argument("--windows", action="store_true")
    args = ap.parse_args()
    patch_spec(Path(args.spec), windows=args.windows)
    print("PYSIDE_DEPLOY_SPEC_PATCH_PASS")
    for flag in FORCED_FW_FLAGS:
        print(flag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
