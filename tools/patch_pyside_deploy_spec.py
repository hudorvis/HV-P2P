#!/usr/bin/env python3
"""Patch pyside6-deploy's Nuitka args to force the immutable firmware data files.

Nuitka can classify .bin as binary/executable-like content, so using a data-dir
include alone is insufficient. Each authority file is listed explicitly.
"""
from pathlib import Path
import sys

FILES = (
    "firmware_bundle/ctrl.bin",
    "firmware_bundle/w1p.bin",
    "firmware_bundle/manifest.json",
    "firmware_bundle/SHA256SUMS.txt",
)

def patch(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    section = ""
    changed = False
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.lower()
        if section == "[nuitka]" and stripped.startswith("extra_args") and "=" in line:
            prefix, value = line.split("=", 1)
            args = value.strip().split()
            for rel in FILES:
                flag = f"--include-data-files={rel}={rel}"
                if flag not in args:
                    args.append(flag)
            line = prefix + "= " + " ".join(args)
            changed = True
        out.append(line)
    if not changed:
        raise SystemExit("pysidedeploy.spec [nuitka] extra_args field not found")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_pyside_deploy_spec.py <pysidedeploy.spec>")
    patch(Path(sys.argv[1]))
