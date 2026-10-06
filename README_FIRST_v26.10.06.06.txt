HV P2P v26.10.06.06 - GitHub Ready Source

CI/runtime-test fixture hotfix built from locked v26.10.06.05.

Production CTRL, W1P, CTRL-TS, SRVR backend, QML and firmware-authority behavior are unchanged from .06.05 apart from release identity. The fix makes the PySide backend runtime test explicitly create a stationary mid-span state before asserting System | Active, and adds a source-level guard for that fixture.

GitHub Actions/native compilation remains authoritative. No firmware binaries are included in this source package.
