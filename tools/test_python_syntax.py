#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
files=sorted(p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts)
for p in files:
    try:
        compile(p.read_text(encoding="utf-8"), str(p), "exec")
    except Exception as exc:
        print(f"PYTHON_SYNTAX_FAIL {p.relative_to(ROOT)}: {exc}")
        raise
print(f"PYTHON_SYNTAX_PASS {len(files)} files")
