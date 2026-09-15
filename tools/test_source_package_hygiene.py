#!/usr/bin/env python3
"""Keep GitHub-ready source revisions minimal, current, and free of generated payloads."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VER = "26.09.15.02"

failures: list[str] = []
for d in ("PREVIEWS", "REFERENCE_ONLY", "NATIVE_BUILD_ARTIFACTS", "HVP2P_NATIVE_BUILD_ARTIFACTS", "__pycache__", ".pytest_cache", ".mypy_cache"):
    hits = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob(d)]
    if hits:
        failures.append(f"redundant/generated directory present {d}: {hits}")

for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    rel = p.relative_to(ROOT).as_posix()
    if p.name.startswith("CHANGE_AUDIT_"):
        failures.append(f"legacy change-audit file present: {rel}")
    if p.suffix.lower() in {".bin", ".exe", ".dmg", ".msi", ".pyc"} or ".app/" in rel:
        failures.append(f"generated/native build output present in source package: {rel}")

singletons = {
    "CHANGE_SUMMARY": f"CHANGE_SUMMARY_v{VER}.md",
    "DEEP_CODE_AUDIT": f"DEEP_CODE_AUDIT_v{VER}.md",
    "INITIAL_BOOTSTRAP": f"INITIAL_BOOTSTRAP_v{VER}.md",
    "NATIVE_BUILD_AND_BENCH_CHECKLIST": f"NATIVE_BUILD_AND_BENCH_CHECKLIST_v{VER}.md",
    "README_FIRST": f"README_FIRST_v{VER}.txt",
}
for prefix, required in singletons.items():
    matches = sorted(p.name for p in ROOT.glob(prefix + "*"))
    if matches != [required]:
        failures.append(f"{prefix} documents must be exactly [{required}], got {matches}")

# Active code/tools may only carry current-release path tokens. Revision history
# may describe older versions, so it is intentionally excluded here.
path_re = re.compile(r"(?:SRVR_GitHub|HV_P2P_(?:CTRL_EDGEBOX|CTRL_TS|W1P_EDGEBOX))_v(\d+\.\d+\.\d+\.\d+)")
for p in list((ROOT / "tools").glob("*.py")) + list((ROOT / f"SRVR_GitHub_v{VER}" / "tools").glob("*.py")) + [ROOT / ".github/workflows/complete-build.yml"]:
    text = p.read_text(encoding="utf-8", errors="replace")
    stale = sorted({m.group(1) for m in path_re.finditer(text) if m.group(1) != VER})
    if stale:
        failures.append(f"active file {p.relative_to(ROOT)} references stale release paths: {stale}")

if failures:
    for f in failures:
        print("FAIL", f)
    raise SystemExit("SOURCE_PACKAGE_HYGIENE_FAIL")

files = [p for p in ROOT.rglob("*") if p.is_file()]
print(f"SOURCE_PACKAGE_HYGIENE_PASS files={len(files)} version=v{VER}")
