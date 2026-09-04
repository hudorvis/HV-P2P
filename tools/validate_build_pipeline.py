#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
wf=(ROOT/'.github/workflows/complete-build.yml').read_text()
builder=(ROOT/'tools/native_build_firmware.py').read_text()
lvglprep=(ROOT/'tools/prepare_lvgl_config.py').read_text()
waveshareprep=(ROOT/'tools/prepare_waveshare_library.py').read_text()
hmi=(ROOT/'HV_P2P_CTRL_TS_v26.09.04.03/HV_P2P_CTRL_TS_v26.09.04.03.ino').read_text()
embed=(ROOT/'tools/embed_ctrl_ts_firmware.py').read_text()
guard=(ROOT/'HV_P2P_CTRL_EDGEBOX_v26.09.04.03/HV_P2P_CTRL_TS_Firmware_Image.h').read_text()
w1pp=(ROOT/'HV_P2P_W1P_EDGEBOX_v26.09.04.03/partitions.csv').read_text()
checks={
 'workflow core 3.3.8': 'esp32:esp32@3.3.8' in wf,
 'workflow Arduino CLI pinned': "version: '1.5.1'" in wf,
 'HMI LVGL pinned': "lvgl@8.3.11" in wf,
 'display panel pinned': "ESP32_Display_Panel@0.1.6" in wf,
 'IO expander pinned': "ESP32_IO_Expander@0.0.3" in wf,
 'Waveshare CH422G 0.0.3 compatibility patch': 'prepare_waveshare_library.py --libraries-dir' in wf and 'ESP_IO_EXPANDER_I2C_CH422G_ADDRESS_000' in waveshareprep and 'refusing to patch Waveshare library' in waveshareprep,
 'Waveshare library commit pinned': "WAVESHARE_ST7262_LVGL_COMMIT: '593775b89ebfd2d411df3eadba7bc382767ed4a4'" in wf and 'git -C "$WAVESHARE_LIB" fetch --depth 1 origin "$WAVESHARE_ST7262_LVGL_COMMIT"' in wf and 'rev-parse HEAD' in wf,
 'native manifest records Waveshare commit': 'WAVESHARE_ST7262_LVGL_COMMIT' in builder and '"dependencies"' in builder and '"commit": WAVESHARE_ST7262_LVGL_COMMIT' in builder,
 'native builder verifies retained app role/version identity': 'require_binary_token(ctrl_app' in builder and 'HV_P2P_FW_ROLE=CTRL' in builder and 'require_binary_token(w1p_app' in builder and 'HV_P2P_FW_ROLE=W1P' in builder,
 'JPEGDEC pinned': "JPEGDEC@1.8.4" in wf,
 'LVGL config prepared beside library': 'prepare_lvgl_config.py --libraries-dir' in wf and 'lv_conf.h' in wf,
 'LVGL config enables Arduino tick': 'LV_TICK_CUSTOM 1' in lvglprep and 'LV_TICK_CUSTOM_SYS_TIME_EXPR (millis())' in lvglprep,
 'LVGL required fonts enabled': 'REQUIRED_FONTS = (8, 10, 12, 14, 16, 18, 24)' in lvglprep and 'LV_FONT_MONTSERRAT_{size}' in lvglprep,
 'HMI only uses available Montserrat sizes': 'lv_font_montserrat_9' not in hmi and 'lv_font_montserrat_11' not in hmi,
 'HMI avoids Arduino HEX macro collision': 'static const char HEX[]' not in hmi and 'HEX_DIGITS' in hmi,
 'HMI Update.write uses const-safe scratch buffer': 'static void fw_handle_block(const HVP2PRS485::Frame &frame)' in hmi and 'memcpy(g_fw_write_buf, frame.payload + 4, dataLen)' in hmi and 'Update.write(g_fw_write_buf, dataLen)' in hmi,
 'HMI LVGL 35 percent opacity is explicit': 'LV_OPA_35' not in hmi and 'HV_OPA_35 = (lv_opa_t)89' in hmi,
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
 'firmware artifact upload present': 'HV-P2P-v26.09.04.03-Native-Firmware' in wf,
 'SRVR macOS Intel job present': 'runner: macos-15-intel' in wf and 'HV-P2P-SRVR-v26.09.04.03-macOS-Intel' in wf and 'expected_arch: x86_64' in wf,
 'SRVR macOS Apple Silicon job present': 'runner: macos-15' in wf and 'HV-P2P-SRVR-v26.09.04.03-macOS-Apple-Silicon' in wf and 'expected_arch: arm64' in wf,
 'SRVR Windows x64 job present': 'runs-on: windows-2025' in wf and 'HV-P2P-SRVR-v26.09.04.03-Windows-x64' in wf and 'expected AMD64/x64 executable' in wf,
 'Windows MSVC developer tools initialized': 'ilammy/msvc-dev-cmd@v1' in wf and 'Get-Command dumpbin.exe' in wf,
 'Windows dumpbin probe uses real PE image': '$probePe = $env:ComSpec' in wf and '$dumpOutput = & $dumpbin /headers $probePe 2>&1' in wf and '$dumpExit = $LASTEXITCODE' in wf and 'dumpbin PE-header probe failed' in wf and '& dumpbin.exe /?' not in wf,
 'Windows deploy steps re-resolve dumpbin': wf.count('Deployment dumpbin: $deployDumpbin') >= 2 and wf.count('Get-Command dumpbin.exe -ErrorAction Stop') >= 3,
 'Windows Nuitka compiler pinned': 'python -m pip install \"Nuitka==4.2\" ordered-set zstandard' in wf and 'python -m nuitka --version' in wf,
 'Windows dependency-tool downloads are noninteractive': "flag = '--assume-yes-for-downloads'" in wf and 'generated Nuitka command is missing --assume-yes-for-downloads' in wf,
 'Windows deploy dry-run proves assume-yes flag': "Select-String -Path deploy-dry-run.txt -SimpleMatch '--assume-yes-for-downloads'" in wf,
 'complete matched artifact present': 'HV-P2P-v26.09.04.03-Complete-Release' in wf and 'needs: [build-firmware, build-srvr-macos, build-srvr-windows]' in wf,
 'SRVR bundle metadata pinned': all(x in wf for x in ('BUNDLE_IDENTIFIER', 'com.hvp2p.srvr', "BUNDLE_SHORT_VERSION: '26.9.4'", "BUNDLE_BUILD_VERSION: '2609.4.3'", "APP_VERSION: '26.09.04.03'", 'HVP2PReleaseVersion')),
 'complete release preserves all original SRVR ZIPs': 'three untouched native ZIPs' in wf and 'HV P2P SRVR v26.09.04.03 macOS Intel.zip' in wf and 'HV P2P SRVR v26.09.04.03 macOS Apple Silicon.zip' in wf and 'HV P2P SRVR v26.09.04.03 Windows x64.zip' in wf,
 'macOS matrix architecture verified': 'test "$(uname -m)" = "$EXPECTED_ARCH"' in wf and "platform.machine() == os.environ['EXPECTED_ARCH']" in wf and 'file "$ROUNDTRIP_EXE" | grep -q "$EXPECTED_ARCH"' in wf,
 'Windows source and frozen smoke tests': 'python main.py --smoke-test' in wf and 'Frozen Windows smoke test failed' in wf,
 'Windows native config path regression present': 'LOCALAPPDATA' in (ROOT/'SRVR_GitHub_v26.09.04.03'/'backend.py').read_text() and '_dialog_path' in (ROOT/'SRVR_GitHub_v26.09.04.03'/'backend.py').read_text(),
 'Speed mode contract included in source suite': "test_speed_mode_contract.py" in (ROOT/'tools'/'run_all_source_checks.py').read_text(),
 'complete release internal SHA256 manifest': "manifest=root/'SHA256SUMS.txt'" in wf and "sha256(p)" in wf,
 'complete release external SHA256': "Path(str(out)+'.sha256')" in wf and 'HV P2P v26.09.04.03 Complete Release.zip.sha256' in wf,
}
failed=[k for k,v in checks.items() if not v]
for k,v in checks.items(): print(('OK  ' if v else 'FAIL')+k)
if failed: raise SystemExit('BUILD_PIPELINE_VALIDATION_FAIL: '+', '.join(failed))
print(f'BUILD_PIPELINE_VALIDATION_PASS ({len(checks)} checks)')
