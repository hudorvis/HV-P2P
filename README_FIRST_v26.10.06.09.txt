HV P2P v26.10.06.09 - GitHub Ready Source

Locked baseline: v26.10.06.08.

This revision is a CI/test-fixture hotfix only. Production CTRL, W1P, CTRL-TS, SRVR backend, QML and firmware-authority behavior is unchanged from v26.10.06.08 apart from release identity.

The Windows PySide test expected `E-Stop | CTRL` from a fixture that had not restored a fully healthy validated W1P state. v26.10.06.09 fixes that fixture and adds a source-level guard preventing the same dirty-state mistake from recurring. Production E-stop/fail-safe logic is not weakened.

GitHub Actions/native compilation and PySide runtime remain authoritative. No firmware binaries are included in this source package.
