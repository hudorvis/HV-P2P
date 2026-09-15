#!/usr/bin/env python3
"""Run the backend regression suite without requiring Qt/PySide6 installation.

This is an early source/firmware-CI gate only. It supplies the tiny QtCore surface
used by backend.py/test_backend_logic.py so pure backend state-machine regressions
are caught before native firmware and three desktop jobs fan out. Each native SRVR
job still runs the same regression with the real pinned PySide6 runtime.
"""
from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRVR = ROOT / "SRVR_GitHub_v26.09.15.02"
TEST = SRVR / "tools" / "test_backend_logic.py"


class _BoundSignal:
    def __init__(self) -> None:
        self._slots = []

    def connect(self, fn) -> None:
        self._slots.append(fn)

    def emit(self, *args, **kwargs) -> None:
        for fn in tuple(self._slots):
            try:
                fn(*args, **kwargs)
            except TypeError:
                fn()


class _SignalDescriptor:
    def __init__(self, *args, **kwargs) -> None:
        self._name = None

    def __set_name__(self, owner, name) -> None:
        self._name = f"__qt_signal_{name}"

    def __get__(self, obj, owner):
        if obj is None:
            return self
        signal = getattr(obj, self._name, None)
        if signal is None:
            signal = _BoundSignal()
            setattr(obj, self._name, signal)
        return signal


def Signal(*args, **kwargs):
    return _SignalDescriptor(*args, **kwargs)


def Slot(*args, **kwargs):
    def decorate(fn):
        return fn
    return decorate


def Property(_type, fget=None, fset=None, freset=None, notify=None, **kwargs):
    if fget is not None and callable(fget):
        return property(fget, fset)
    def decorate(fn):
        return property(fn)
    return decorate


class QObject:
    def __init__(self, *args, **kwargs) -> None:
        pass


class QTimer:
    def __init__(self, *args, **kwargs) -> None:
        self.timeout = _BoundSignal()
        self.interval = 0

    def setInterval(self, value) -> None:
        self.interval = int(value)

    def start(self, *args, **kwargs) -> None:
        pass

    def stop(self) -> None:
        pass


class QCoreApplication:
    _instance = None

    def __init__(self, *args, **kwargs) -> None:
        type(self)._instance = self

    @classmethod
    def instance(cls):
        return cls._instance

    def processEvents(self) -> None:
        pass


def install_qtcore_stub() -> None:
    pyside = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")
    for name, value in {
        "QObject": QObject,
        "Property": Property,
        "Signal": Signal,
        "Slot": Slot,
        "QTimer": QTimer,
        "QCoreApplication": QCoreApplication,
    }.items():
        setattr(qtcore, name, value)
    pyside.QtCore = qtcore
    sys.modules["PySide6"] = pyside
    sys.modules["PySide6.QtCore"] = qtcore


def main() -> int:
    if not TEST.is_file():
        raise SystemExit(f"backend regression script missing: {TEST}")
    install_qtcore_stub()
    sys.path.insert(0, str(SRVR))
    runpy.run_path(str(TEST), run_name="__main__")
    print("BACKEND_HEADLESS_GATE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
