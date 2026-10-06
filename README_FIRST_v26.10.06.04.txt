HV P2P v26.10.06.04 - GitHub Ready Source

Locked follow-up to v26.10.06.03 focused only on automatic firmware-update recovery and truthful CTRL<->CTRL-TS RS485 diagnostics.

Key bench expectation: launch the new SRVR with older field firmware and do not manually reboot CTRL or CTRL-TS. CTRL must discover the release independently of later-stage coordinator state; CTRL-TS must then update automatically by the normal grant or the bounded CTRL-local recovery.

GitHub Actions/native compilation remains authoritative. No firmware binaries are included in this source package.
