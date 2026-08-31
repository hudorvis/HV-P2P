#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
wf=(ROOT/'.github/workflows/firmware-build.yml').read_text()
builder=(ROOT/'tools/native_build_firmware.py').read_text()
embed=(ROOT/'tools/embed_ctrl_ts_firmware.py').read_text()
guard=(ROOT/'HV_P2P_CTRL_EDGEBOX_v26.08.31.01/HV_P2P_CTRL_TS_Firmware_Image.h').read_text()
w1pp=(ROOT/'HV_P2P_W1P_EDGEBOX_v26.08.31.01/partitions.csv').read_text()
checks={
 'workflow core 3.3.8': 'esp32:esp32@3.3.8' in wf,
 'workflow Arduino CLI pinned': "version: '1.5.1'" in wf,
 'HMI LVGL pinned': "lvgl@8.3.11" in wf,
 'display panel pinned': "ESP32_Display_Panel@0.1.6" in wf,
 'IO expander pinned': "ESP32_IO_Expander@0.0.3" in wf,
 'JPEGDEC pinned': "JPEGDEC@1.8.4" in wf,
 'native builder HMI first': builder.find('hmi_app = compile_sketch') < builder.find('ctrl_app = compile_sketch'),
 'native builder embeds before CTRL': builder.find('embed_ctrl_ts_firmware.py') < builder.find('ctrl_app = compile_sketch'),
 'EdgeBox forces 16M': 'Edgebox-ESP-100' in builder and 'FlashSize=16M' in builder,
 'HMI forces 16M OPI': 'FlashSize=16M' in builder and 'PSRAM=opi' in builder,
 'HMI target slot guarded': 'HMI_SLOT = 0x380000' in builder,
 'CTRL target slot guarded': 'CTRL_SLOT = 0x600000' in builder,
 'source CTRL hard build guard': '#error "CTRL-TS firmware image has not been staged.' in guard,
 'embed verifies ESP magic': 'ESP_IMAGE_MAGIC = 0xE9' in embed,
 'embed writes HW/proto/version/hash': all(x in embed for x in ('HV_CTRL_TS_REQUIRED_HW','HV_CTRL_TS_REQUIRED_PROTOCOL','HV_CTRL_TS_REQUIRED_VERSION','HV_CTRL_TS_REQUIRED_SHA256')),
 'W1P dual OTA added': all(x in w1pp for x in ('ota_0','ota_1','0x600000')),
 'artifact upload present': 'HV-P2P-v26.08.31.01-Native-Firmware' in wf,
}
failed=[k for k,v in checks.items() if not v]
for k,v in checks.items(): print(('OK  ' if v else 'FAIL')+k)
if failed: raise SystemExit('BUILD_PIPELINE_VALIDATION_FAIL: '+', '.join(failed))
print(f'BUILD_PIPELINE_VALIDATION_PASS ({len(checks)} checks)')
