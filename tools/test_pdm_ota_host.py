#!/usr/bin/env python3
"""Compile the real PDM OTA header against host transport and flash fixtures."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from native_build_firmware import SEMVER

ROOT = Path(__file__).resolve().parents[1]
with TemporaryDirectory(prefix="hvp2p-pdm-ota-") as directory:
    path = Path(directory)
    (path / "mbedtls").mkdir()
    for stub in ("Arduino.h", "HTTPClient.h", "NetworkClient.h", "Update.h",
                 "esp_ota_ops.h", "esp_partition.h", "mbedtls/sha256.h"):
        (path / stub).touch()
    executable = path / "pdm_ota_host"
    subprocess.run(["g++", "-std=c++17", "-I", str(path), "-I", str(ROOT / f"HV_P2P_PDM_{SEMVER}"),
                    str(ROOT / "tools/pdm_ota_host.cpp"), "-o", str(executable)], check=True)
    subprocess.run([str(executable), SEMVER], check=True)
