# HV P2P SYS v26.11.09.04

- Corrects GitHub workflow validation in v26.11.09.03. The firmware job exports its Arduino directories from a runner step so setup, cache and install receive the paths after the job starts.
- Retains verified archive caching and per-archive GitHub release fallback for ESP32 core 3.3.8.
- Advances the release identity for SRVR, CTRL-TS, CTRL, W1P and PDM.

See [verification](TEST_RESULTS_v26.11.09.04.txt) and the [Olimex guide](PDM_BOOTSTRAP_v26.11.09.04.md).
