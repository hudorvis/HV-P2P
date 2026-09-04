#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import hashlib, re, struct, sys

ROOT = Path(__file__).resolve().parents[1]
VER = '26.09.04.02'
CTRL = ROOT / f'HV_P2P_CTRL_EDGEBOX_v{VER}' / f'HV_P2P_CTRL_EDGEBOX_v{VER}.ino'
W1P = ROOT / f'HV_P2P_W1P_EDGEBOX_v{VER}' / f'HV_P2P_W1P_EDGEBOX_v{VER}.ino'
TS = ROOT / f'HV_P2P_CTRL_TS_v{VER}' / f'HV_P2P_CTRL_TS_v{VER}.ino'
FRAME_CTRL = ROOT / f'HV_P2P_CTRL_EDGEBOX_v{VER}' / 'HV_P2P_RS485_Frame.h'
FRAME_TS = ROOT / f'HV_P2P_CTRL_TS_v{VER}' / 'HV_P2P_RS485_Frame.h'
IMG_HDR = ROOT / f'HV_P2P_CTRL_EDGEBOX_v{VER}' / 'HV_P2P_CTRL_TS_Firmware_Image.h'
SRVR_DIR = ROOT / 'SRVR_GitHub_v26.09.04.02'
SRVR = SRVR_DIR / 'backend.py'
MAIN = SRVR_DIR / 'main.py'
SETUP_QML = SRVR_DIR / 'qml' / 'pages' / 'SetupPage.qml'
SPAN_QML = SRVR_DIR / 'qml' / 'components' / 'SpanDiagram.qml'
CTRL_PARTITIONS = ROOT / f'HV_P2P_CTRL_EDGEBOX_v{VER}' / 'partitions.csv'
TS_PARTITIONS = ROOT / f'HV_P2P_CTRL_TS_v{VER}' / 'partitions.csv'
W1P_PARTITIONS = ROOT / f'HV_P2P_W1P_EDGEBOX_v{VER}' / 'partitions.csv'

passed=[]

def must(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)
    passed.append(msg)

def read(p: Path) -> str:
    must(p.is_file(), f'exists: {p.relative_to(ROOT)}')
    return p.read_text(errors='replace')

def strip_cpp(src: str) -> str:
    out=[]; i=0; n=len(src); state='code'; quote=''
    while i<n:
        c=src[i]; d=src[i+1] if i+1<n else ''
        if state=='code':
            if c=='/' and d=='/': state='line'; out.extend('  '); i+=2; continue
            if c=='/' and d=='*': state='block'; out.extend('  '); i+=2; continue
            if c in ('"', "'"): state='str'; quote=c; out.append(' '); i+=1; continue
            out.append(c); i+=1; continue
        if state=='line':
            if c=='\n': state='code'; out.append('\n')
            else: out.append(' ')
            i+=1; continue
        if state=='block':
            if c=='*' and d=='/': state='code'; out.extend('  '); i+=2
            else: out.append('\n' if c=='\n' else ' '); i+=1
            continue
        if c=='\\': out.extend('  ' if i+1<n else ' '); i+=2; continue
        if c==quote: state='code'; out.append(' '); i+=1; continue
        out.append('\n' if c=='\n' else ' '); i+=1
    return ''.join(out)

def balanced(src: str, name: str):
    clean=strip_cpp(src); stack=[]; pairs={')':'(',']':'[','}':'{'}
    for pos,ch in enumerate(clean):
        if ch in '([{': stack.append((ch,pos))
        elif ch in ')]}':
            if not stack: raise AssertionError(f'{name}: unmatched closing {ch} at {pos}')
            op,_=stack.pop()
            if op != pairs[ch]: raise AssertionError(f'{name}: mismatched nesting at {pos}')
    must(not stack, f'{name}: all (), [], {{}} balanced')

def extract_func(src: str, name: str) -> str:
    pat=re.compile(r'(?m)^\s*(?:static\s+)?(?:inline\s+)?[\w:<>&*]+(?:\s+[\w:<>&*]+)*\s+'+re.escape(name)+r'\s*\([^;]*?\)\s*\{')
    m=pat.search(src)
    if not m: raise AssertionError(f'function not found: {name}')
    brace=src.find('{',m.start(),m.end()); depth=0; i=brace; state='code'; quote=''
    while i<len(src):
        c=src[i]; d=src[i+1] if i+1<len(src) else ''
        if state=='code':
            if c=='/' and d=='/': state='line'; i+=2; continue
            if c=='/' and d=='*': state='block'; i+=2; continue
            if c in ('"',"'"): state='str'; quote=c; i+=1; continue
            if c=='{': depth+=1
            elif c=='}':
                depth-=1
                if depth==0: return src[m.start():i+1]
            i+=1; continue
        if state=='line':
            if c=='\n': state='code'
            i+=1; continue
        if state=='block':
            if c=='*' and d=='/': state='code'; i+=2
            else: i+=1
            continue
        if c=='\\': i+=2; continue
        if c==quote: state='code'
        i+=1
    raise AssertionError(f'unclosed function: {name}')

def normalized_func_hash(src: str, name: str) -> str:
    f=extract_func(src,name)
    f=re.sub(r'/\*.*?\*/','',f,flags=re.S)
    f=re.sub(r'//[^\n]*','',f)
    f=re.sub(r'v\d+\.\d+\.\d+\.\d+','VERSION',f)
    f=re.sub(r'\s+',' ',f).strip()
    return hashlib.sha256(f.encode()).hexdigest()

c=read(CTRL); w=read(W1P); t=read(TS); fc=read(FRAME_CTRL); ft=read(FRAME_TS); ih=read(IMG_HDR); s=read(SRVR); m=read(MAIN); q=read(SETUP_QML); span=read(SPAN_QML); ctrl_part=read(CTRL_PARTITIONS); ts_part=read(TS_PARTITIONS); w1p_part=read(W1P_PARTITIONS)

# Basic sketch/package integrity.
for p in (CTRL,W1P,TS):
    must(p.parent.name==p.stem, f'Arduino same-name sketch folder: {p.parent.name}')
for name,src in [('CTRL',c),('W1P',w),('CTRL-TS',t)]:
    balanced(src,name)
    must(f'v{VER}' in src, f'{name}: release version v{VER}')
must(fc==ft, 'CTRL and CTRL-TS use byte-identical RS485 framing header')
must(not any(ROOT.glob('HV_P2P_W1P_TS*')), 'W1P-TS remains excluded')

# EdgeBox hardware mapping and W5500 transport.
edge_eth=['EDGEBOX_ETH_CS   10','EDGEBOX_ETH_MISO 11','EDGEBOX_ETH_MOSI 12','EDGEBOX_ETH_SCLK 13','EDGEBOX_ETH_INT  14','EDGEBOX_ETH_RST  15']
for tok in edge_eth: must(tok in c, f'CTRL EdgeBox Ethernet pin: {tok}')
for tok,val in [('EDGEBOX_ETH_CS',10),('EDGEBOX_ETH_MISO',11),('EDGEBOX_ETH_MOSI',12),('EDGEBOX_ETH_SCLK',13),('EDGEBOX_ETH_INT',14),('EDGEBOX_ETH_RST',15)]:
    must(re.search(rf'{tok}\s*=\s*{val}\b',w) is not None, f'W1P EdgeBox Ethernet {tok}={val}')
for name,src in [('CTRL',c),('W1P',w)]:
    must('ETH.begin(ETH_PHY_W5500' in src and 'SPI2_HOST' in src, f'{name}: W5500 SPI Ethernet init')
    must('ETH.config(' in src, f'{name}: static IPv4 configuration retained')
must(re.search(r'IPAddress\s+local_IP\(172,\s*20,\s*1,\s*101\)', c) is not None, 'CTRL remains 172.20.1.101')
must(re.search(r'IPAddress\s+server_IP\(172,\s*20,\s*1,\s*100\)', c) is not None, 'CTRL SRVR target remains 172.20.1.100')
must('LOCAL_IP(172, 20, 1, 102)' in w and 'SRVR_IP(172, 20, 1, 100)' in w, 'W1P remains 172.20.1.102 -> SRVR .100')
must('#define UDP_PORT 5000' in c and 'TCP_PORT = 5000' in w, 'UDP port 5000 retained')

# E-stop: isolated EdgeBox DI0 GPIO4 and fail-open field loop semantics.
must('#define CTRL_ESTOP_PIN 4' in c and 'digitalRead(CTRL_ESTOP_PIN)' in c, 'CTRL E-stop uses EdgeBox DI0/GPIO4')
must('CTRL_ESTOP_HEALTHY_LEVEL = HIGH' in c and '(estop_raw != CTRL_ESTOP_HEALTHY_LEVEL)' in c, 'CTRL DI0 HIGH=healthy / LOW-open=unsafe')
must('PIN_LOCAL_ESTOP = 4' in w and 'LOCAL_ESTOP_HEALTHY_LEVEL = HIGH' in w, 'W1P E-stop uses DI0 HIGH=healthy')
must('bool active = (raw != LOCAL_ESTOP_HEALTHY_LEVEL);' in w, 'W1P open/pressed DI0 resolves unsafe')

# CTRL analog path: direct EdgeBox SGM58031, correct 0-10V divider scaling.
for tok in ['SDA_PIN 20','SCL_PIN 19','ADS_ADDR = 0x48','SGM_REG_CONVERSION = 0x00','SGM_REG_CONFIG     = 0x01','SGM_REG_CONFIG1    = 0x04','SGM_CONFIG_AI0_CONT_800SPS_6V144 = 0x40E3']:
    must(tok in c, f'CTRL SGM58031 contract: {tok}')
must('Adafruit_ADS1X15' not in c and '#include <Adafruit_ADS' not in c, 'CTRL no longer depends on external ADS1115 library/hardware')
must('EDGEBOX_JOY_5V_COUNTS = 13333.3f' in c, 'CTRL 0-5V field endpoint accounts for EdgeBox ~2:1 divider')
expected_counts=(2.5/6.144)*32768.0
must(abs(expected_counts-13333.3)<1.0, f'ADC scaling math: 5V field -> ~{expected_counts:.1f} counts')
must('SRVR calibration authoritative' in c and 'Set Left / Set Centre / Set Right' in c, 'SRVR remains joystick Left/Centre/Right calibration authority')
must('if(!g_ads_inited) flags |= FLAG_ADS1115_FAULT;' in c, 'EdgeBox analogue/I2C fault reuses wire-compatible CTRL analogue fault flag')

# AUX is touchscreen only, and A7 packet remains byte-for-byte compatible.
must('AUX1..AUX5 touchscreen-only; no physical AUX GPIO module' in c, 'CTRL has no physical AUX inputs')
must('#define FLAG_AUX5                 0x0400' in c, 'CTRL AUX5 remains 0x0400')
must('pkt[0] = 0xA7' in c and 'pkt[1] = (uint8_t)((flags >> 8) & 0xFF)' in c and 'pkt[2] = (uint8_t)(flags & 0xFF)' in c, 'CTRL A7 16-bit flags wire format unchanged')
must('pkt[3] = u.b[3]' in c and 'pkt[6] = u.b[0]' in c, 'CTRL joystick float remains big-endian on UDP wire')
for i in range(1,6): must(f'"AUX{i}"' in c, f'CTRL handles CTRL-TS AUX{i} event')

# HMI safety gate and deterministic framed RS485.
for src,name in [(c,'CTRL'),(w,'W1P')]:
    must('EDGEBOX_RS485_TX' in src and '17' in src and 'EDGEBOX_RS485_RX' in src and '18' in src and 'EDGEBOX_RS485_RTS' in src and '8' in src, f'{name}: EdgeBox RS485 pin mapping present')
must('UART_MODE_RS485_HALF_DUPLEX' in c and 'HMI.setMode' in c, 'CTRL uses ESP32 hardware RTS half-duplex RS485')
must('UART_MODE_RS485_HALF_DUPLEX' in w and 'DriveSerial.setMode' in w, 'W1P uses ESP32 hardware RTS half-duplex RS485')
must('return g_hmiCompatible &&' in c and 'HMI_LINK_TIMEOUT_MS = 3000' in c, 'CTRL HMI compatibility/link timeout gate')
must('const bool hmi_safety = !hmiLinkConnected();' in c and 'if(estop_active || hmi_safety) flags_out |= FLAG_ESTOP_PRESSED;' in c, 'Missing/incompatible CTRL-TS asserts existing CTRL E-stop flag')
must('CTRL is always the bus master' in fc and 'CTRL-TS transmits only as a direct response' in fc, 'RS485 framing documents deterministic master/slave rule')
must('MAX_PAYLOAD = 3072' in fc and 'RX_INTERBYTE_TIMEOUT_MS = 250' in fc, 'RS485 framing has bounded payload and inter-byte timeout')
for typ in ['HELLO_REQ','HELLO_RESP','COMPATIBLE','TEXT','POLL','EVENT','FW_BEGIN','FW_BLOCK','FW_END','FW_RESULT','REBOOT']:
    must(typ in fc, f'RS485 frame type defined: {typ}')

# Exact Waveshare SKU27078 transport pins and display geometry.
must('#define HMI_UART_RX 15' in t and '#define HMI_UART_TX 16' in t, 'CTRL-TS SKU27078 official Arduino demo uses RX GPIO15 / TX GPIO16')
must('SPLASH_CANVAS_W = 800' in t and 'SPLASH_CANVAS_H = 480' in t, 'CTRL-TS uses actual SKU27078 800x480 display geometry')
must('CTRL-TS never initiates traffic' in t and 'frame.type == HVP2PRS485::POLL' in t, 'CTRL-TS only transmits in master response slots')
must('rs485_slave_turnaround_guard' in t and 'delayMicroseconds(150)' in t, 'CTRL-TS has explicit master-release turnaround guard')
must('SPLASH_FILENAME = "/splash.jpg"' in t and 'show_boot_splash' in t, 'Existing splash.jpg boot sequence retained')

# CTRL-owned automatic HMI updater. The checked-in source must be in one of two
# explicit states: (1) a hard build guard that makes an incomplete CTRL impossible
# to compile, or (2) a real generated carrier produced from a native CTRL-TS .bin.
build_guard = '#error "CTRL-TS firmware image has not been staged.' in ih
img_m = re.search(r'HV_CTRL_TS_IMAGE_AVAILABLE\s*=\s*(true|false)', ih)
img_available = bool(img_m and img_m.group(1) == 'true')
if build_guard:
    must(img_m is None, 'unstaged CTRL uses a hard compile-time guard, not a false/zero-byte carrier placeholder')
    must('BUILD GUARD' in ih and 'embed_ctrl_ts_firmware.py' in ih, 'CTRL carrier build guard explains the mandatory native HMI staging step')
else:
    must(img_available, 'staged CTRL carrier explicitly marks a real CTRL-TS image available')
    ver_m = re.search(r'HV_CTRL_TS_REQUIRED_VERSION\s*=\s*"([^"]+)"', ih)
    sha_m = re.search(r'HV_CTRL_TS_REQUIRED_SHA256\s*=\s*"([0-9a-fA-F]{64})"', ih)
    size_m = re.search(r'HV_CTRL_TS_IMAGE_SIZE\s*=\s*(\d+)', ih)
    hw_m = re.search(r'HV_CTRL_TS_REQUIRED_HW\s*=\s*"([^"]+)"', ih)
    proto_m = re.search(r'HV_CTRL_TS_REQUIRED_PROTOCOL\s*=\s*(\d+)', ih)
    must(ver_m is not None and ver_m.group(1) == f'v{VER}', 'CTRL embedded HMI carrier requires current release version')
    must(hw_m is not None and hw_m.group(1) == 'WS-ESP32S3-7', 'staged CTRL carrier is bound to the approved Waveshare hardware id')
    must(proto_m is not None and int(proto_m.group(1)) == 1, 'staged CTRL carrier is bound to RS485 protocol v1')
    must(sha_m is not None and size_m is not None, 'CTRL-TS carrier exposes SHA-256 and byte size')
    must(0 < int(size_m.group(1)) <= 0x380000, 'staged CTRL-TS carrier fits the conservative 0x380000 target slot')
    must('AUTO-GENERATED FROM A NATIVE CTRL-TS APPLICATION BINARY' in ih, 'staged CTRL-TS carrier was generated from a native application binary')
for tok in ('HMI_FW_WAIT_READY','HMI_FW_WAIT_BLOCK_ACK','HMI_FW_WAIT_RESULT','HMI_FW_WAIT_REBOOT_ACK','hmiFwStart','hmiFwSendBlock','FW_BEGIN','FW_BLOCK','FW_END','FW_RESULT','REBOOT'):
    must(tok in c, f'CTRL automatic HMI updater sender present: {tok}')
for tok in ('#include <Update.h>','#include <Preferences.h>','#include <mbedtls/sha256.h>','Update.begin(imageSize, U_FLASH)','Update.write','mbedtls_sha256_update','mbedtls_sha256_finish','sha_mismatch','Update.end(true)','save_fw_identity','FW_BEGIN','FW_BLOCK','FW_END','FW_RESULT','REBOOT'):
    must(tok in t, f'CTRL-TS automatic HMI updater receiver present: {tok}')
must('g_ctrl_fw_compatible = false' in t, 'CTRL-TS firmware transfer enters fail-safe incompatible state')
must('hmiTransportCompatible()' in c and 'g_hmiReportedHw == HV_CTRL_TS_REQUIRED_HW' in c and 'g_hmiReportedProto == HV_CTRL_TS_REQUIRED_PROTOCOL' in c, 'CTRL gates automatic HMI flashing on exact hardware id and carrier protocol')
must('Automatic update BLOCKED: peer hardware/protocol is not the approved CTRL-TS target.' in c, 'CTRL refuses automatic flashing of an unexpected RS485 peer')
must('\"hw=\"' in c and 'HV_CTRL_TS_REQUIRED_PROTOCOL' in c and 'FW_BEGIN' in c, 'CTRL FW_BEGIN carries explicit target hardware/protocol metadata')
must('targetHw != CTRL_TS_HW_ID || proto != HVP2PRS485::PROTOCOL_VERSION' in t and 'fw_begin_wrong_target' in t, 'CTRL-TS independently rejects FW_BEGIN for wrong hardware/protocol')
must('if(!HV_CTRL_TS_IMAGE_AVAILABLE' in c and 'strlen(HV_CTRL_TS_REQUIRED_SHA256) != 64' in c, 'CTRL updater refuses any missing/unmeasured carrier identity')
must('frame.seq != g_hmiFwSeq' in c and 'ignored stale response' in c, 'CTRL updater correlates every response to the outstanding RS485 sequence')
must('reported != expectedNext' in c and 'FW_ACK missing next offset' in c, 'CTRL updater accepts only the exact next firmware block offset')
must('reportedSize == HV_CTRL_TS_IMAGE_SIZE' in c and 'sha.length() == 64' in c and 'rejected final image identity' in c, 'CTRL requires exact final size and SHA-256 from CTRL-TS')
must('CTRL-TS did not accept FW_BEGIN' in c, 'CTRL requires explicit FW_READY acceptance before transfer')
must('if(g_fw_finalized)' in t and 'FW_END is deliberately idempotent' in t, 'CTRL-TS repeats successful FW_RESULT after a lost final response')
must('reboot_without_verified_image' in t, 'CTRL-TS refuses updater reboot before a verified finalized image exists')
must('esp_ota_get_running_partition' in t and 'esp_ota_set_boot_partition' in t, 'CTRL-TS restores current boot partition if firmware identity metadata cannot persist')
must('esp_ota_get_boot_partition' in t and 'fw_meta_key' in t and 'commit marker' in t, 'CTRL-TS firmware identity metadata is committed per OTA partition')
must('FW_MAX_IMAGE_SIZE = 0x380000' in t and 'imageSize > FW_MAX_IMAGE_SIZE' in t, 'CTRL-TS receiver enforces the conservative 0x380000 OTA slot')
must('CTRL_TS_SEMVER' in t and 'storedVersion == CTRL_TS_SEMVER' in t, 'CTRL-TS reported/stored version derives from one release semantic-version token')
must('Do NOT change g_fw_image_hash while the old application is still running' in t and 'return verify;' in t, 'CTRL-TS does not claim the staged image hash before reboot')
must('MAX_IMAGE = 0x380000' in read(ROOT/'tools'/'embed_ctrl_ts_firmware.py'), 'CTRL-TS embed helper enforces the conservative 0x380000 target OTA slot')

# Preserve unchanged W1P core control implementation from proven v26.08.19.01 via normalized function hashes.
# Safety-facing functions intentionally extended in v26.09.04.02 are hash-locked separately below.
expected_w1p={
'modbusCRC16':'2d54f956989bcfd6a5b539664c14228f13046f16daca4911cd6467fcafe6cd3e',
'modbusWaitForSilentGap':'46cb53133b81b90bcc184ace784e64e1f807823485cd1ea29ad3b228a4b94cb8',
'modbusWriteSingleRegister':'3c92128a0d472dce97948064d2a86f2029ab940a124b7ada987fbd47594d4c4d',
'modbusWriteMultipleRegisters':'e57848c9a7a17ed26ab9339ea507d518d512c34a31af9c6b51affbcbe50dc9a1',
'modbusReadHoldingRegisters':'2e16a70077c9b05a06405e84bf7f7d7357f51adcdaa52a0cb69bd5043f6c56d0',
'driveConfigureMotionProfile':'fa4f428da8a39ef6005811250dc66ec065baf011036e2ef054d3745cb1107044',
'driveWriteVelocityCommandMps':'e33a8a6d1121f48600a797b9ad21067a90bf0dc3ab1ec210a7101bd7784b3598',
'driveSendEmergencyStop':'9a3687a43eb79c27bbd5350500ce344290a044eab88355799ae0bcd2eb566de1',
'serviceMotionProfile':'fbad116e5b9f9ee1d07e049d7014647713d503ec96d107a7fad75690556ce18e',
'limitVelocityForSoftLimits':'fcd63bf9ac8bfb41c855c79d57d42cdf0119584f8142c2f27b4c914d98014066',
'driveStopNow':'ed4b91222340b12c83ca0371d4501cc77dfe135ac687e432b219ad8553b6bb96',
'servicePeerTimeout':'81d5f57232771f48dbe5edd46161f75a8f5adf2aee370e9bc6180d64d61a48ff',
'preserveDisplayedPositionForMotorDirectionChange':'e78aafbc76eb48601a04eed3703372a0dfd1f2c19070e891fdbd1952984942a0',
}
for fn,h in expected_w1p.items(): must(normalized_func_hash(w,fn)==h, f'W1P proven v26.08.19.01 logic preserved: {fn}')

expected_w1p_v07_safety={
'driveAutoEnableReady':'ce2cd73df1636f1ba2dd7ba23da9eca4f983ba3ee6a179dd9b5398ad831dc78f',
'handleCommand':'6f6b14a0ba61bdb8ea20de54f6fa855c89f7d9644a7ac3886d3567592529d507',
'sendStatusLine':'4770463812c84bc2351d04a58a84e912cd714fd8fc4512e11f7c872d35ca56f0',
'serviceVelocityCommandWatchdog':'a6dc0d9244bf1c7b64d28291c56c8fcd20abb21af5566a5bf396e1723fdd9111',
'hvPrepareSafeServiceState':'92026ffa3126d53e57d9f111583d11f7ef52b19b16528af82b970108bf4eb8ab',
}
for fn,h in expected_w1p_v07_safety.items(): must(normalized_func_hash(w,fn)==h, f'W1P v26.09.04.02 reviewed safety extension hash locked: {fn}')

# Leadshine contract.
for tok in ['RS485_BAUD = 115200','DRIVE_MODBUS_ID = 1','SERIAL_8N1','MODBUS_REPLY_TIMEOUT_MS = 50','MODBUS_READ_RETRIES = 3','MODBUS_INTERFRAME_GAP_US = 1500','W1P_PEER_TIMEOUT_MS = 750']:
    must(tok in w, f'W1P Leadshine/safety contract: {tok}')
for tok in ['REG_RS485_MODE = 0x053B','REG_RS485_BAUD = 0x053D','REG_RS485_ADDRESS = 0x053F','EXPECTED_RS485_MODE = 4','EXPECTED_RS485_BAUD_CODE = 6','EXPECTED_RS485_ADDRESS = 1']:
    must(tok in w, f'EL7 RS485 config contract: {tok}')
for tok in ['REG_DO2_ASSIGN = 0x0417','REG_DO3_ASSIGN = 0x0419','REG_DO4_ASSIGN = 0x041B','REG_DO5_ASSIGN = 0x041D','EXPECTED_DO2_READY_ASSIGN = 2','EXPECTED_DO3_ENABLED_ASSIGN = 0x12','EXPECTED_DO4_BRAKE_ASSIGN = 3','EXPECTED_DO5_FAULT_ASSIGN = 1']:
    must(tok in w, f'EL7 DO map retained: {tok}')
must('DriveSerial.write(req' in w and 'DriveSerial.flush();' in w, 'Modbus TX waits for queued UART bytes before reply collection')
must('UART_MODE_RS485_HALF_DUPLEX' in w, 'ESP32 UART driver owns DE/RTS release after final transmitted bit')

# W1P safety semantics.
must('SRVR peer timeout - stopping drive, locking writes and dropping software Servo Enable' in w, 'W1P 750ms peer fail-safe stops and drops software Servo Enable')
must('driveStopNow();' in extract_func(w,'servicePeerTimeout'), 'W1P peer-timeout code directly stops drive')
must('if (line == "STOP")' in w and 'parseFloatArg(line, "SW_SRVON", val)' in w, 'W1P STOP and SW_SRVON command contract retained')
must('Do not torque-enable the servo while the output map is still being migrated' in w and '!g.do4_brake_assignment_ok' in w, 'SW Servo Enable waits for verified BRK-OFF/output map')

# v26.09.04.02 independent W1P command-deadman and service safety gate.
wd=extract_func(w,'serviceVelocityCommandWatchdog')
must('W1P_VEL_COMMAND_TIMEOUT_MS = 650' in w, 'W1P independent VEL watchdog timeout is 650ms')
must('lastVelocityCommandMs' in wd and 'lastPeerPacketMs' not in wd, 'W1P VEL watchdog keys only from VEL freshness, not generic peer traffic')
must(all(tok in wd for tok in ('driveStopNow();','g.drive_writes_enabled = false','requestSoftwareSrvonInhibit(true, "VEL_WATCHDOG")')), 'W1P VEL watchdog stops, locks drive writes and drops software Servo Enable')
must('serviceVelocityCommandWatchdog();' in extract_func(w,'loop'), 'W1P main loop services the independent VEL watchdog')
must('VEL_WD=' in w and 'SERVICE_LOCK=' in w and 'VEL_AGE_MS=' in w, 'W1P status exposes watchdog/service safety state to SRVR')
service_gate=extract_func(w,'hvPrepareSafeServiceState')
must(all(tok in service_gate for tok in ('driveStopNow();','g.drive_writes_enabled = false','requestSoftwareSrvonInhibit(true, "WEB_SERVICE")','modbusReadFeedbackBlock','rawUnitsDeltaToDisplayMps','OUTPUT_DO3_MASK','OUTPUT_DO4_MASK','stableSamples >= 2','lastDriveFeedbackMs','LEADSHINE_SRVON_DISABLED_VALUE')), 'W1P service gate uses fresh post-stop EL7 samples and proves stopped/SRV-ST-off/BRK-OFF-off state')
must(w.count('hvPrepareSafeServiceState(reason)') >= 2 and 'hvPrepareSafeServiceState(hvUploadError)' in w, 'W1P OTA/reboot/reset all enter the safe service gate')
must('SERVICE_REARM' in w and 'STOP_CLEAR_LATCH' in w, 'W1P service/watchdog latch requires STOP re-arm path')

# v26.09.04.02 closes the W1P Setup-IP semantic gap with a coordinated safe
# readdress: the old address remains active until W1P proves stopped/braked,
# persists the new local IP, acknowledges, then reboots.
network_cmd=extract_func(w,'handleCommand')
must('line.startsWith("SET_NETWORK|")' in network_cmd and 'hvGetPipeField(line, "w1p_ip")' in network_cmd, 'W1P exposes explicit local-IP readdress command')
must('hvPrepareSafeServiceState(reason)' in network_cmd and 'saveW1pLocalIpForReboot(nextIp, reason)' in network_cmd and 'ESP.restart();' in network_cmd, 'W1P readdress reuses verified safe-service gate then persists/reboots')
must('OK SET_NETWORK W1P_IP=' in network_cmd and 'ERR SET_NETWORK' in network_cmd, 'W1P readdress has explicit success/failure acknowledgement')
must(all(tok in w for tok in ('ip_pending','ip_prev','NETWORK_READDRESS_CONFIRM_TIMEOUT_MS = 10000','saveW1pLocalIpForReboot','confirmNetworkReaddress','serviceNetworkReaddressRollback')), 'W1P readdress is transactional with previous-IP rollback state')
must('if (NETWORK_READDRESS_PENDING) confirmNetworkReaddress();' in extract_func(w,'serviceUdp') and 'serviceNetworkReaddressRollback();' in extract_func(w,'loop'), 'W1P commits only after SRVR reaches provisional IP and services rollback timeout')
must('np.putString("w1p_ip", ipToString(rollbackIp))' in extract_func(w,'serviceNetworkReaddressRollback') and 'ESP.restart();' in extract_func(w,'serviceNetworkReaddressRollback'), 'W1P restores previous IP and reboots when provisional address is not confirmed')
must(' IP=' in extract_func(w,'sendStatusLine') and 'ETH.localIP()' in extract_func(w,'sendStatusLine'), 'W1P STATUS reports actual live local IP')
must('def _request_w1p_readdress' in s and 'SET_NETWORK|w1p_ip=' in s and 'OK SET_NETWORK' in s and 'ERR SET_NETWORK' in s, 'SRVR safely requests and confirms W1P local-IP changes before retargeting')
must('def _probe_w1p_address' in s and 'self._parse_pipe_fields(line)' in s and 'if self._probe_w1p_address(new_ip)' in s and 'answered with its live IP' in s, 'SRVR recovers a lost SET_NETWORK acknowledgement by proving the provisional W1P address')
must('if new_w1p_ip != self.w1p_ip and not self._request_w1p_readdress(new_w1p_ip)' in s, 'Setup Apply fails closed if W1P local-IP change is not confirmed')

# SRVR persistence and Free-D data-integrity fixes.
must('_atomic_write_text(self._config_path' in s and 'os.replace(temp, path)' in s and 'os.fsync(fh.fileno())' in s, 'SRVR private config uses fsync + atomic rename')
must('.with_suffix(self._config_path.suffix + ".bak")' in s and 'recovered previous-good backup' in s, 'SRVR recovers private config from previous-good backup')
must('def _u24be' in s and 'def _lens24be' in s and 'str(lens_type).lower() == "u24"' in s, 'Free-D u24 lens output has true unsigned 24-bit encoder')
must('_freed_checksum_valid(data)' in s and 'sum(data[:29])' in s, 'Free-D D1 input validates checksum before consuming telemetry')

# App OTA device-role identity is content verified, so a renamed wrong-role app is rejected.
for src,role in ((c,'CTRL'),(w,'W1P')):
    must(f'HV_UPDATE_ROLE_SIGNATURE = "HV_P2P_FW_ROLE={role};"' in src, f'{role} OTA embeds expected app role signature')
    must('hvScanUploadRoleSignature(upload.buf, upload.currentSize)' in src and '!hvUploadRoleMatched' in src, f'{role} OTA scans uploaded app contents for role identity')
    must('Update.abort();' in src and 'firmware contents do not contain expected role signature' in src, f'{role} OTA aborts a wrong-content app before activation')
    must('Build identity: %s' in src and 'HV_UPDATE_BUILD_TOKEN' in src, f'{role} compiled app retains role/version build identity token')

# SRVR must promote new W1P internal safety states into the existing motion safety/re-arm path.
must('fields.get("VEL_WD", "0") == "1"' in s and 'fields.get("SERVICE_LOCK", "0") == "1"' in s, 'SRVR parses W1P watchdog/service safety flags')
must('self._w1p_internal_safety = self.winch_vel_watchdog_fault or self.winch_service_safety_lock' in s, 'SRVR consolidates W1P internal motion safety state')
must('def _motion_tick(self):' in s and 'or self._w1p_internal_safety' in s, 'SRVR motion tick treats W1P watchdog/service lock as safety stop')
must('or self._w1p_internal_safety' in s and 'w1p_fault = bool(' in s, 'SRVR operator/CTRL-TS status classifies W1P watchdog/service lock as W1P fault')

# CTRL-TS is intentionally visually redesigned to the approved SRVR-family theme.
must('#define AUX_COUNT 5' in t, 'CTRL-TS retains five AUX touch tiles')
for tok in ('0x0f1316','0x171c20','0x4a4f52','0x26d5ff','0x72ed21','0xef5757'):
    must(tok in t, f'CTRL-TS shared SRVR-family palette token present: {tok}')
for tok in ('CTRL','W1P','SRVR TIME','UPTIME','DRIVE','SPEED','POSITION','E-STOP'):
    must(tok in t, f'CTRL-TS approved operator layout token present: {tok}')
for tok in ('drive_mode','accel_mode','battery_change','srvr_time','uptime','ctrl_ip','w1p_ip'):
    must(tok in t and tok in s, f'SRVR -> CTRL-TS display field shared: {tok}')

# SRVR control/wire contract stays compatible while its display payload/theme is extended.
for cmd in ('SET_UNITS_PER_M','SET_MOTOR_REVERSE','SET_ACCEL','SET_DECEL','SET_CROSSOVER','SET_STOP_DECEL','SET_ACCEL_MODE','SET_SPAN','SET_LIMIT_NEAR','SET_LIMIT_FAR','SERVICE_MODE','VEL','SYNC_POS','STOP','SW_SRVON'):
    must(cmd in w and cmd in s, f'SRVR/W1P shared command: {cmd}')
must('FLAG_AUX5 = 0x0400' in s, 'SRVR AUX5 flag matches CTRL 0x0400')
must('0xA7' in s and 'struct.unpack("!f"' in s, 'SRVR still parses A7 big-endian joystick float')
must('aboutToQuit.connect(backend.shutdown)' in m, 'SRVR app close remains wired to shutdown safety')
for token in ('Accel Mode |','Drive Mode |','Battery Change |'):
    must(token in s, f'SRVR dynamic HMI label preserved: {token}')
must('config_schema_version' in s and 'not_calibrated_mode' in s, 'SRVR config migration/calibrated-state persistence retained')
must('_goto_approach_dir' in s and '_goto_velocity_for_distance' in s, 'SRVR Goto anti-hunt approach logic retained')


# SRVR/CTRL-TS interface-alignment and Free-D diagram regression guards.
must('text:"Link"' in q and 'text:"RS485"' in q and 'text:"E-Stop"' in q and 'text:"Firmware"' in q, 'Setup uses locked generic CTRL/W1P status row labels')
must('W1P-TS Link' not in q, 'Setup does not expose the excluded W1P-TS')
must('CTRL_HMI_ARCH "EdgeBox ESP-100' in c and 'EdgeBox-ESP-100' in w, 'CTRL and W1P source identify the EdgeBox-ESP-100 hardware baseline')
must('▣  CTRL-TS' in q and 'CTRL-TS / FIRMWARE' not in q and 'ctrlTsFirmwareState' in q and 'W1P-TS AUX ASSIGN' not in q, 'Setup preserves approved three-panel grid with locked CTRL-TS status panel')
must('profileValue(Number(gp.x), key)' in span, 'Free-D geometry markers are sampled from the exact rendered cable path')


# v26.09.04.02 locked Run/Setup revision and Virtual demo-source contract.
main_qml = read(SRVR_DIR / 'qml' / 'Main.qml')
must('text:"HV P2P\\nSRVR"' in main_qml and 'HV P2P  |  SRVR' not in main_qml and 'P2P°\\nSRVR' not in main_qml, 'Run/Setup shared header uses locked two-line HV P2P / SRVR logo only')
must('pendingShortcutAction' in main_qml and 'shortcutConfirmRemaining = 5' in main_qml and 'Confirm? ' in main_qml and 'shortcutConfirmTimer' in main_qml, 'Run Save/Recall/Slip use one global five-second two-step confirmation state')
for token in ('preset:save:', 'preset:recall:', 'limit:save:Near', 'limit:recall:Near', 'limit:slip:Near', 'limit:save:Far', 'limit:recall:Far', 'limit:slip:Far', 'limit:save:Ref', 'limit:recall:Ref', 'limit:slip:Ref'):
    must(token in main_qml, f'Run confirmation action covered: {token}')
must('width:f(70); height:parent.height; text:"Mode 1"' in main_qml and 'width:f(70); height:parent.height; text:"Mode 2"' in main_qml, 'Run System Mode 1/Mode 2 labels are fully readable')
must('Text { width:f(150)' in main_qml and 'Item{width:parent.width-f(150)' in main_qml, 'Run System action columns share the locked left alignment')
must(main_qml.count('Row { anchors.centerIn:parent; spacing:f(7)') >= 2, 'Run To Near/To Far units sit beside their numeric values')
must('model:["Encoder","Virtual"]' in q and 'backend.setSetupPositionSource(currentText)' in q, 'Setup exposes Encoder and Virtual position sources')
must('def _virtual_output_inhibit' in s and 'self.w1p.send("SW_SRVON 0")' in s and 'self.w1p.send("STOP")' in s, 'Virtual mode positively stops W1P and inhibits physical Servo Enable')
virt_send = s[s.index('    def _send_velocity'):s.index('    @staticmethod\n    def _normalise_aux_action_name')]
must('if self.position_source == "Virtual"' in virt_send and 'self._virtual_velocity_mps = vel' in virt_send and 'self.w1p.send("VEL 0" if abs(vel) < .001 else f"VEL {vel:.3f}")' in virt_send, 'Virtual mode simulates requested velocity locally while physical VEL emission remains Encoder-only')
must('physical_winch_required = self.position_source != "Virtual"' in s, 'Virtual demo mode does not require W1P/EL7 health to exercise CTRL/CTRL-TS input')
must('if "POS_M" in fields and self.position_source != "Virtual"' in s and 'if "VEL_MPS" in fields and self.position_source != "Virtual"' in s, 'Physical W1P feedback cannot overwrite Virtual demo position/speed')
must('if not self.smoke_test and self.position_source != "Virtual"' in s and 'SYNC_POS' in s, 'Virtual Slip/re-reference does not rewrite physical W1P position')
must('ctrl_version=v26.09.04.02' in c and 'FW=" + String(FW_VERSION)' in w, 'CTRL and W1P publish actual firmware identity for Setup')
must('ctrlFirmwareVersion' in s and 'w1pFirmwareVersion' in s and 'ctrlEStopActive' in s and 'w1pEStopActive' in s, 'SRVR exposes locked CTRL/W1P Setup diagnostics')
must('text:"CTRL-TS Link"' in q and 'backend.ctrlTsConnected?"Active":"Disconnected"' in q, 'CTRL-TS Link uses the same Active/Disconnected dot status model as node links')
must('anchors.rightMargin:root.f(15)' in q and 'anchors.leftMargin:root.f(15)' in q and q.count('width:(parent.width-root.f(1))/2') >= 2, 'Motion Profiles centre divider has even Mode 1/Mode 2 spacing')

# OTA partition layouts must leave two app slots on both the 16 MB CTRL carrier
# and the 8 MB Waveshare so updates can be staged without overwriting the running app.
for tok in ('app0,     app,  ota_0', 'app1,     app,  ota_1', '0x600000'):
    must(tok in ctrl_part, f'CTRL carrier dual-OTA partition token: {tok}')
for tok in ('app0,     app,  ota_0', 'app1,     app,  ota_1', '0x380000'):
    must(tok in ts_part, f'CTRL-TS dual-OTA partition token: {tok}')
for tok in ('app0,     app,  ota_0', 'app1,     app,  ota_1', '0x600000'):
    must(tok in w1p_part, f'W1P EdgeBox dual-OTA partition token: {tok}')

# HMI_STATUS must expose the actual Waveshare identity/update state to SRVR, not
# mistakenly mirror the CTRL build version.
for tok in ('g_hmiReportedVersion', 'HV_CTRL_TS_REQUIRED_VERSION', 'hmiFwStateText()', 'HV_CTRL_TS_IMAGE_AVAILABLE'):
    must(tok in extract_func(c,'sendHmiStatusToSrvr'), f'CTRL HMI_STATUS diagnostic field source: {tok}')
for tok in ('_ctrl_ts_required_version', '_ctrl_ts_fw_state', '_ctrl_ts_image_available', 'def ctrlTsFirmwareState', 'def ctrlTsRequiredVersion', 'def joystickInputConnected'):
    must(tok in s, f'SRVR exposes CTRL-TS firmware diagnostic: {tok}')

# A7 host-side binary sanity check.
axis=0.375; flags=0x0410
native=struct.pack('<f',axis)
pkt=bytes([0xA7,(flags>>8)&255,flags&255])+native[::-1]+bytes(3)
must(pkt[0]==0xA7 and pkt[1:3]==b'\x04\x10' and abs(struct.unpack('>f',pkt[3:7])[0]-axis)<1e-7, 'A7 host sanity: 16-bit flags + big-endian float decode')

print(f'HV P2P EdgeBox v{VER} source-level integration validation PASS')
print(f'Checks passed: {len(passed)}')
for x in passed: print('  OK:',x)
