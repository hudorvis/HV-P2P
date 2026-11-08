# HV P2P source audit v26.11.08.01

| Component | Reviewed paths | Defect and correction |
| --- | --- | --- |
| SRVR | W1P HELLO/STATUS parsing, encoder plausibility, calibration captures, safety-link freshness, diagnostics and DSP1 | The unsigned timestamp delta turned a small rollback into almost 49.7 days of allowed travel. The filter now accepts only positive forward deltas shorter than half the counter range. A legacy frame with no device timestamp uses monotonic host elapsed time. Position and parsed signed counts commit together. Detailed RS485 faults wait through discovery and require fresh STATUS. |
| W1P | P08.44–P08.47 read, configuration sweep, encoder extension, velocity, stop/brake verification, STATUS and startup logs | A poll-start timestamp included time spent reading configuration and waiting for Modbus. Both position paths record the validated reply time. Brake output-only polls still leave encoder sequence and sample time alone. Serial startup now reports 8N1 and the factory probe requires operational failure evidence. |
| CTRL | A6/A7 input path, AUX edges, master UART polling/quiet guard, DSP/HMI forwarding and OTA coordination | Absolute millis comparisons could truncate pulses that crossed wrap or replay previously expired AUX/CANCEL bits. Wrap-safe comparison and clearing expired deadlines preserves the intended timing and 16-bit flag mapping. |
| CTRL-TS | HELLO/POLL/EVENT/ACK, display-bound marker/state updates, confirmation and safe self-update | Absolute comparisons could clear confirmations or trigger verified/safe reboot early near wrap. The scheduled deadlines now survive wrap. A deadline that would equal the inactive zero sentinel waits one additional millisecond. |

## Validation boundaries

- The SRVR position envelope uses the approved encoder-rate calculation, including its existing 3000 RPM telemetry margin. W1P retains the 2500 RPM commanded ceiling. The host traversal cases exercise the telemetry calculation with 125, 250, 500, 2500 and 3000 RPM simulated inputs.
- Encoder sequence and timestamp are checked independently within the W1P session. HELLO or a changed BOOT_ID invalidates the position reference. A rollback rejection leaves the previous position baseline in place so the next valid sample can recover normally.
- The normal and service paths share sample bookkeeping. Service verification still requires two consecutive quiet intervals, Servo Enable OFF, EL7 BRK-OFF OFF, and EdgeBox DO0 release OFF before the protected operation.
- The integration validator preserves the reviewed Modbus transport, velocity writes, soft limits, watchdog, Servo Enable, brake release and E-stop implementation locks. Revised locks cover only STATUS and service bookkeeping plus the brake hold feedback-age calculation. The age threshold and output/safety prerequisites retain their approved values.
- The SRVR QML files, firmware partition tables, authority code and requirements are byte-identical to the approved package. Existing regression cases cover Free-D, Setup persistence, SRVR-to-CTRL display, CTRL-TS marker smoothing, role and image verification, updater recovery, E-stops, brake sequencing and motion limits.
- Qt resource compilation, QML lint under the existing workflow flags and the full offscreen SRVR smoke test ran locally. The smoke used a temporary matching firmware manifest with test bytes. QML lint diagnostics match the approved baseline, and both smoke runs report a HelveticaNeue fallback on Linux.
- Native Arduino and frozen desktop builds are GitHub Actions gates. Fitted drive timing, encoder scaling, loaded motion and hardware safety are the separate bench commissioning gates.

See TEST_RESULTS_v26.11.08.01.txt and SOURCE_REGRESSION_LOG_v26.11.08.01.txt for executed checks.
