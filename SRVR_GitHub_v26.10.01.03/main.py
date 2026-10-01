#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

# Force Qt Quick Controls to use a deterministic non-native visual style.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

# The smoke test is used by GitHub Actions to prove that both the source tree
# and the frozen .app can create the QML engine, instantiate every locked page,
# and exercise the calibration overlay without requiring an interactive desktop.
SMOKE_TEST = "--smoke-test" in sys.argv
if SMOKE_TEST:
    try:
        sys.argv.remove("--smoke-test")
    except ValueError:
        pass
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

# Import these explicitly. Besides documenting what the QML frontend needs,
# it gives deployment tools an unambiguous dependency path for the Qt Quick /
# Qt Quick Controls runtime modules.
import PySide6.QtQuick  # noqa: F401
import PySide6.QtQuickControls2  # noqa: F401

from backend import HVP2PBackend
from firmware_authority import FirmwareAuthorityError, start_firmware_authority

APP_VERSION = "26.10.01.03"


def _exercise_qml(app: QGuiApplication, engine: QQmlApplicationEngine, backend: HVP2PBackend) -> bool:
    """Non-interactive source/frozen smoke test used by CI."""
    roots = engine.rootObjects()
    if not roots:
        print("SMOKE FAIL: no QML root object", file=sys.stderr)
        return False

    root = roots[0]
    try:
        # Exercise all primary pages.
        for page in range(4):
            root.setProperty("page", page)
            app.processEvents()

        # Exercise all four Shortcuts sub-tabs on the Run page.
        root.setProperty("page", 0)
        for tab in range(4):
            root.setProperty("shortcutTab", tab)
            app.processEvents()

        # Exercise the locked Limit Calibration popup, including step changes.
        backend.openLimitCalibration()
        app.processEvents()
        backend.calibrationNext()
        app.processEvents()
        backend.calibrationBack()
        app.processEvents()
        backend.cancelCalibration()
        app.processEvents()

        # Exercise the three-step Joystick Calibration popup and corrected axis.
        backend.openJoystickCalibration()
        app.processEvents()
        backend._ctrl_axis = -0.82
        backend.joystickCalibrationNext()
        app.processEvents()
        backend._ctrl_axis = 0.08
        backend.joystickCalibrationNext()
        app.processEvents()
        backend._ctrl_axis = 0.91
        backend.joystickCalibrationNext()
        app.processEvents()
        if backend.joystickCalibrationOpen:
            raise RuntimeError("Joystick Calibration wizard did not complete")
        if abs(backend.joystick_cal_left + 0.82) > 1e-6 or abs(backend.joystick_cal_centre - 0.08) > 1e-6 or abs(backend.joystick_cal_right - 0.91) > 1e-6:
            raise RuntimeError("Joystick calibration did not become live at wizard completion")
        backend._ctrl_axis = 0.08
        if abs(float(backend.joystickValue)) > 1e-6 or abs(float(backend.joystickPercentage)) > 1e-6:
            raise RuntimeError("Auto-saved joystick calibrated centre is not zero")

        # Exercise the editable Run/System controls that previously appeared
        # visually correct but behaved read-only in the first Qt test builds.
        backend.state.near_limit.position_m = 0.0
        backend.state.far_limit.position_m = 100.0
        backend.setPresetName(0, "Smoke Preset")
        backend.setPresetPosition(0, 12.34)
        if backend.presets[0]["name"] != "Smoke Preset" or abs(float(backend.presets[0]["position"]) - 12.34) > 1e-6:
            raise RuntimeError("editable preset fields failed")
        backend.renameDriveMode(0, "Smoke Mode")
        if backend.driveMode1Name != "Smoke Mode":
            raise RuntimeError("editable drive-mode name failed")
        backend.setRamping("Near", "Distance", 20.0)
        backend.changeRampingMode("Near", "Percentage")
        if backend.nearRampMode != "Percentage" or abs(float(backend.nearRampValue) - 20.0) > 1e-6:
            raise RuntimeError("ramp Distance->Percentage conversion failed")
        backend.changeRampingMode("Near", "Distance")
        if abs(float(backend.nearRampValue) - 20.0) > 1e-6:
            raise RuntimeError("ramp Percentage->Distance conversion failed")

        # Exercise final Settings auto-save. Every accepted edit must become live
        # and persistent immediately; the mirror remains aligned with live state.
        backend.beginSetupEdit()
        backend.setSetupNetwork("CTRL", "172.20.1.199")
        backend.setSetupJoystickDeadband(4.5)
        backend.renameSetupDriveMode(0, "Shared Smoke Mode")
        backend.setSetupDriveModeValue(0, "max_speed_mps", 20.0)
        backend.setSetupAuxAssignment("CTRL", 0, "Preset 1 Save")
        backend.setSetupAuxAssignment("W1P", 4, "Preset 10 Save")
        if backend.ctrlIp != "172.20.1.199" or backend.driveMode1Name != "Shared Smoke Mode":
            raise RuntimeError("Settings auto-save did not update live state")
        if abs(float(backend.joystickDeadband) - 4.5) > 1e-6:
            raise RuntimeError("Settings deadband auto-save failed")
        if backend.setupDraft["drive_modes"][0]["name"] != backend.driveMode1Name:
            raise RuntimeError("Settings mirror diverged from saved live state")
        if backend.setupDraft["ctrl_aux_assignments"][0] != "Preset 1 Save" or backend.setupDraft["w1p_aux_assignments"][4] != "Preset 10 Save":
            raise RuntimeError("Settings AUX Preset Save options failed")
        backend.beginSetupEdit()
        if backend.setupDraft["drive_modes"][0]["name"] != "Shared Smoke Mode":
            raise RuntimeError("Settings auto-saved state was lost on page navigation")

        # Exercise the structured Log page model without changing legacy text export.
        backend._log("[W1P] RS485 disconnected warning")
        backend._log("[Free-D] packet received")
        if not backend.filteredLogEntries("Network", "Warning", "rs485"):
            raise RuntimeError("Log Network/Warning/Search filter failed")
        if not backend.filteredLogEntries("Free-D", "All", "packet"):
            raise RuntimeError("Log Free-D filter failed")

        # Exercise Free-D auto-save. Committed values must immediately update
        # live output/network state and survive a page refresh.
        backend.beginFreeDEdit()
        backend.setFreeDNetwork("Output", "IP", "172.20.1.30")
        backend.setFreeDNetwork("Output", "Port", "5002")
        backend.setFreeDNetwork("Output", "FPS", "50")
        backend.setFreeDOffset("Input", "Pan", 1.25)
        backend.setFreeDInvert("Output", "Y", True)
        backend.setGeometryPoint(1, "x", 25.0)
        backend.setGeometryPoint(1, "y", 5.0)
        backend.setWeightUnit("Skate", "lbs")
        backend.setLensType("u16")
        backend.setLensScale("Auto")
        if backend.freeDOutputIp != "172.20.1.30" or backend.freeDOutputPort != 5002:
            raise RuntimeError("Free-D auto-save did not update live output")
        backend.beginFreeDEdit()
        if backend.freeDDraft["target_ip"] != "172.20.1.30":
            raise RuntimeError("Free-D auto-saved state was lost on page navigation")

        # The shared Run/Free-D cable profile must react to tension changes.
        backend.state.near_limit.position_m = 0.0
        backend.state.far_limit.position_m = 100.0
        backend.state.pos_m = 0.0
        backend.geometry = [
            {"name":"P1","x":10.0,"y":0.0,"z":0.0},
            {"name":"P2","x":30.0,"y":0.0,"z":None},
            {"name":"P3","x":50.0,"y":0.0,"z":None},
            {"name":"P4","x":70.0,"y":0.0,"z":None},
            {"name":"P5","x":90.0,"y":0.0,"z":0.0},
        ]
        if abs(float(backend.cableProfile[0]["x"])) > 1e-9 or abs(float(backend.cableProfile[-1]["x"]) - 100.0) > 1e-9:
            raise RuntimeError("P1/P5 incorrectly became cable-span endpoints")
        backend.skate_weight_kg = 0.0
        backend.cable_weight_kg100m = 4.5
        backend.cable_tension_kg = 50.0
        low_tension_mid = backend.cableProfile[len(backend.cableProfile)//2]["y"]
        backend.cable_tension_kg = 200.0
        high_tension_mid = backend.cableProfile[len(backend.cableProfile)//2]["y"]
        if not low_tension_mid < high_tension_mid:
            raise RuntimeError("Cable Tension did not update calculated sag profile")

        # Exercise every operator sag input on the real Qt/macOS Free-D preview
        # path. The rig is deliberately parked at Near: the moving-skate preview
        # must still show the loaded path across the complete run.
        backend._freed_draft_dirty = False
        backend.beginFreeDEdit()
        backend.setWeightValue("Tension", 100.0)
        backend.setWeightValue("Cable", 4.5)
        backend.setWeightValue("Skate", 20.0)
        backend.setHighlineMode("Single Highline")
        base_mid = backend.freeDPreviewCableProfile[len(backend.freeDPreviewCableProfile)//2]["y"]
        backend.setWeightValue("Skate", 40.0)
        if not backend.freeDPreviewCableProfile[len(backend.freeDPreviewCableProfile)//2]["y"] < base_mid:
            raise RuntimeError("Skate Weight did not affect calculated sag profile")
        backend.setWeightValue("Skate", 20.0)
        backend.setWeightValue("Cable", 9.0)
        if not backend.freeDPreviewCableProfile[len(backend.freeDPreviewCableProfile)//2]["y"] < base_mid:
            raise RuntimeError("Cable Weight did not affect calculated sag profile")
        backend.setWeightValue("Cable", 4.5)
        backend.setHighlineMode("Dual Highline")
        if not backend.freeDPreviewCableProfile[len(backend.freeDPreviewCableProfile)//2]["y"] > base_mid:
            raise RuntimeError("Highline Mode did not affect calculated skate-load sag")

        # The shared status banner must retain the legacy SRVR software E-stop
        # action without affecting other independent safety sources.
        before = bool(backend._srvr_estop)
        backend.toggleSrvrEStop()
        backend.toggleSrvrEStop()
        if bool(backend._srvr_estop) != before:
            raise RuntimeError("SRVR E-stop toggle failed")
        app.processEvents()
    except Exception as exc:
        print(f"SMOKE FAIL: {exc}", file=sys.stderr)
        return False

    print("SMOKE PASS: locked pages, Settings/Free-D auto-save, structured Log, shortcuts and calibration overlay instantiated")
    return True


def main() -> int:
    # The SRVR is the firmware authority.  Validate the immutable bundle before
    # creating the UI so a damaged/missing frozen bundle fails closed at startup.
    try:
        authority = start_firmware_authority(f"v{APP_VERSION}")
    except FirmwareAuthorityError as exc:
        print(f"FIRMWARE AUTHORITY STARTUP FAIL: {exc}", file=sys.stderr)
        return 10
    except OSError as exc:
        print(f"FIRMWARE AUTHORITY BIND FAIL: {exc}", file=sys.stderr)
        return 11

    app = QGuiApplication(sys.argv)
    app.setApplicationName("HV P2P SRVR")
    app.setOrganizationName("H-V")
    app.setOrganizationDomain("h-v.au")

    # resources.qrc is compiled by pyside6-rcc to rc_resources.py in CI.
    # Qt's project tooling expects this rc_<qrc-name>.py naming convention.
    import rc_resources  # noqa: F401

    backend = HVP2PBackend(version=APP_VERSION, smoke_test=SMOKE_TEST)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("appVersion", APP_VERSION)
    engine.load(QUrl("qrc:/qml/Main.qml"))

    if not engine.rootObjects():
        backend.shutdown()
        authority.close()
        return 2

    app.aboutToQuit.connect(backend.shutdown)
    app.aboutToQuit.connect(authority.close)

    if SMOKE_TEST:
        ok = _exercise_qml(app, engine, backend)
        backend.shutdown()
        authority.close()
        # A short event-loop turn catches deferred QML/component errors while
        # still guaranteeing that the CI step terminates.
        QTimer.singleShot(80, app.quit)
        app.exec()
        return 0 if ok else 3

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
