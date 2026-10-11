#!/usr/bin/env python3
"""Patch pyside6-deploy for deterministic HV P2P desktop builds.

The release freezes with a pinned Nuitka version because pyside6-deploy otherwise
installs whatever Nuitka is newest on the build date.  v26.10.08.05 demonstrated
why that is unsafe: the identical project moved to Nuitka 4.3 and the frozen Intel
macOS smoke test segfaulted.  The known project build line is pinned to 4.2.2.

Nuitka can also classify .bin as binary/executable-like content, so using a
data-dir include alone is insufficient. Each authority file is listed explicitly.
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
    nuitka_args_changed = False
    packages_changed = False
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.lower()

        if section == "[python]" and stripped.startswith("packages") and "=" in line:
            prefix, value = line.split("=", 1)
            packages = [item.strip() for item in value.split(",") if item.strip()]
            replaced = False
            for index, package in enumerate(packages):
                name = package.split("==", 1)[0].split(">=", 1)[0].strip().lower()
                if name == "nuitka":
                    packages[index] = "nuitka==4.2.2"
                    replaced = True
                    break
            if not replaced:
                packages.insert(0, "nuitka==4.2.2")
            line = prefix + "= " + ",".join(packages)
            packages_changed = True

        if section == "[nuitka]" and stripped.startswith("extra_args") and "=" in line:
            prefix, value = line.split("=", 1)
            args = value.strip().split()
            for rel in FILES:
                flag = f"--include-data-files={rel}={rel}"
                if flag not in args:
                    args.append(flag)
            line = prefix + "= " + " ".join(args)
            nuitka_args_changed = True
        out.append(line)

    if not packages_changed:
        raise SystemExit("pysidedeploy.spec [python] packages field not found")
    if not nuitka_args_changed:
        raise SystemExit("pysidedeploy.spec [nuitka] extra_args field not found")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_pyside_deploy_spec.py <pysidedeploy.spec>")
    patch(Path(sys.argv[1]))
