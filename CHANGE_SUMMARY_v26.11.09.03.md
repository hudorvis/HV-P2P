# HV P2P SYS v26.11.09.03

- Build workflow follow-up to v26.11.09.02 after sequential 504 timeouts during Arduino ESP32 setup.
- Gives every core or tool archive four download attempts and checks the index length and SHA-256 before staging it.
- Uses GitHub’s release-assets API on alternating retries for release URLs and retains verified downloads across Actions runs.
- Keeps Arduino CLI 1.5.1 and Arduino ESP32 3.3.8 pinned. The firmware roles, boards and desktop packages use the matched release identity.
- Carries forward the Olimex PDM, its embedded dashboard and SRVR Power.

See [local verification](TEST_RESULTS_v26.11.09.03.txt) and the [Olimex guide](PDM_BOOTSTRAP_v26.11.09.03.md).
