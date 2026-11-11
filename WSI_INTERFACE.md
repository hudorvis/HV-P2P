# Wind Speed Indicator (WSI)

In SRVR, open **Monitoring → WSI** and enter the WSI Olimex Ethernet address. Assign the board its own IP address. The WSI view starts without an address. **Open WSI Web UI** uses HTTP port 80 on the saved address. **Log Settings** writes only to the selected device.

## Device API

The Olimex WSI firmware needs to provide these endpoints. The sensor model and wiring are needed to implement acquisition on the board.

| Endpoint | Response or action |
| --- | --- |
| `GET /` | WSI web dashboard |
| `GET /api/wind?after=<sample-id>` | PDM live/history metadata with `role: "wsi"`, `wind_mps` as the single measurement, and `recent` rows in `[t_ms, utc_ms, wind_mps]` format |
| `GET /api/history` | Existing PDM pagination and snapshot parameters with CSV header `t_ms,utc_ms,wind_mps` and a `#end,<cursor>,<offset>` trailer |
| `GET /api/logcfg` | `role: "wsi"`, `log_hours` and `sample_period_ms` |
| `POST /api/logcfg` | Persist `log_hours` and `sample_period_ms`. Respond with the role, stored values and `ok: true` |
| `POST /api/time` | Accept the optional SRVR UTC clock synchronisation |

Use the PDM cursor semantics for `boot`, `generation`, `now_t`, `now_utc_ms`, `stored_through`, `t`, `utc_ms`, `gap`, `more`, `sd_ok` and `log_healthy`. Use `null` for unavailable live measurements and empty CSV fields for missing values. An optional `fw_version` identifies the running firmware. Use integer log durations of 1–12 hours and intervals of 250, 500, 1000 or 2000 milliseconds.

This release includes the SRVR integration and a simulated WSI endpoint for tests. Olimex WSI sensor firmware is pending.
