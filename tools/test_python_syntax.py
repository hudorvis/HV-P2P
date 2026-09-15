#!/usr/bin/env python3
"""Syntax-check project Python sources without writing __pycache__ files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
count = 0
for path in sorted(ROOT.rglob("*.py")):
    rel = path.relative_to(ROOT)
    # Generated/native outputs are never source and must not be syntax checked.
    if any(part in {"NATIVE_BUILD_ARTIFACTS", "__pycache__", ".git"} for part in rel.parts):
        continue
    text = path.read_text(encoding="utf-8", errors="strict")
    compile(text, str(path), "exec")
    count += 1
print(f"PYTHON_SYNTAX_PASS files={count}")
