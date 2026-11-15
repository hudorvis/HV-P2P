#!/usr/bin/env python3
"""Compile the PDM OTA worker and AP startup with host network and flash fixtures."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from native_build_firmware import SEMVER

ROOT = Path(__file__).resolve().parents[1]
with TemporaryDirectory(prefix="hvp2p-pdm-ota-") as directory:
    path = Path(directory)
    sketch = ROOT / f"HV_P2P_PDM_{SEMVER}"
    app = (sketch / "pdm_app.cpp").read_text(encoding="utf-8")
    ap_config = app[app.index("const IPAddress DEFAULT_LAN"):app.index("struct LogConfig")]
    ap_subnets = app[app.index("uint32_t hostOrder("):app.index("bool validWifi(")]
    ap_startup = app[app.index("bool stopAccessPoint("):app.index("const char* alarmFor(")]
    (path / "pdm_ap_config.h").write_text(ap_config)
    (path / "pdm_ap_startup.h").write_text(ap_subnets + ap_startup)
    (path / "mbedtls").mkdir()
    (path / "freertos").mkdir()
    for stub in ("Arduino.h", "ETH.h", "IPAddress.h", "Preferences.h", "HTTPClient.h", "NetworkClient.h", "Update.h",
                 "esp_ota_ops.h", "esp_partition.h", "mbedtls/sha256.h", "freertos/FreeRTOS.h", "freertos/task.h"):
        (path / stub).touch()
    executable = path / "pdm_ota_host"
    subprocess.run(["g++", "-std=c++17", "-I", str(path), "-I", str(sketch),
                    str(ROOT / "tools/pdm_ota_host.cpp"), "-o", str(executable)], check=True)
    subprocess.run([str(executable), SEMVER], check=True)
