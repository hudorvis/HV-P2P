# HV P2P v26.11.08.02

Build workflow revision of v26.11.08.01.

The reported GitHub job refreshed all package indexes, then timed out while waiting for HTTP headers for the Espressif Xtensa toolchain archive (esp-x32@2601). The firmware compile step was skipped. [Reported GitHub job](https://github.com/hudorvis/HV-P2P/actions/runs/42474040932/job/128711246655)

- Configures the stable Espressif Board Manager URL for the full firmware job and allows 120 seconds of download inactivity before Arduino CLI times out.
- Gives index refresh and pinned core installation three attempts each. The workflow names the failed command and stops before compiling when setup fails.
- Verifies the EdgeBox and ESP32-S3 board IDs individually using Arduino CLI.
- Adds a regression that executes the GitHub shell steps with simulated download failures and missing boards.
- Advances matched SRVR, W1P, CTRL and CTRL-TS release identifiers to v26.11.08.02.

See TEST_RESULTS_v26.11.08.02.txt for local validation and the outstanding checks.
