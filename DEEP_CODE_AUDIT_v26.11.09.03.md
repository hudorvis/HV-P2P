# HV P2P SYS build audit v26.11.09.03

The reported Actions run received HTTP 504 on the Xtensa compiler, Xtensa debugger and RISC-V compiler archives. Each failure used one of the three whole-install attempts. Earlier completed downloads were picked up on the following attempts.

The workflow now resolves the 19 required Linux x64 archives for Arduino ESP32 3.3.8 from the Arduino and Espressif indexes. It verifies length and SHA-256 before staging each archive for the CLI. Each archive has four attempts. For GitHub releases the retry can use the release-assets API. A successful board check allows the workflow to save the archives to its version- and runner-specific cache. Restored archives are verified before install.

## PDM integration carried forward

This revision uses the verified v26.11.09.02 GitHub source archive. PDM source and dashboard came from standalone v26.11.09.01. See the release inventory for file-level comparison.

| Area | Reviewed and exercised |
| --- | --- |
| Existing SYS | Compared CTRL, W1P and CTRL-TS sources after normalising the release identity. Compared the SRVR motion tick, velocity and stop emission, firmware worker, fallback push and CTRL-TS update gate with the baseline. Ran the existing encoder, Modbus timestamp, RS485 startup, watchdog, E-stop, brake, limits and coordinator regressions. |
| Firmware authority | Optional PDM metadata validates independently of the required CTRL/W1P pair. Its Ethernet peer needs a refreshed idle lease for the image and the final activation permit. A missing or invalid PDM image leaves the existing authority routes available. |
| PDM OTA | The Olimex checks target, release, size, Ethernet interface and SHA-256. The verified image is staged in the inactive OTA partition. A second permission check follows the cooperative SD writer pause. The transport host test exercises short, stalled, wrong-target and corrupt streams, permission loss and successful boot selection. |
| Settings and SD | The USB partition table retains the standalone NVS offset and size. Network/AP, channel configuration, calibration, alarms and log interval use the original versioned and legacy settings paths. ADC sampling and the CSV row, retention and history formats carry forward. The OTA path writes the inactive app slot and OTA metadata. |
| Browser | The original desktop and iOS pages, JavaScript and chart library are compressed into the app. Decoding the embedded assets reproduces the included web source files. The existing Ethernet and AP dashboard routes are served without SD web assets. |
| SRVR Power | The network worker is separate from motion. The client opens a paged durable-history snapshot, appends newer live IDs, applies PDM offsets and preserves empty readings and time gaps. It resumes on reconnect and resets cursors when the PDM boot or storage generation changes. Address persistence lives in a separate SRVR settings file. |
| CI | Builds CTRL-TS before staging its image into CTRL, then builds CTRL, W1P and PDM. The exact validated PDM application is included in macOS Intel, macOS Apple Silicon and Windows x64 SRVR deployment. Frozen smoke in CI requires a valid bundled PDM image. |

The source checks, local native firmware build and Linux Qt smoke are recorded in [test results](TEST_RESULTS_v26.11.09.03.txt). See the [bench checklist](NATIVE_BUILD_AND_BENCH_CHECKLIST_v26.11.09.03.md) for physical Olimex, drive and system tests.
