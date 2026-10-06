#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import hashlib, re, struct, sys

ROOT = Path(__file__).resolve().parents[1]
VER = '26.10.06.08'
CTRL = ROOT / f'HV_P2P_CTRL_EDGEBOX_v{VER}' / f'HV_P2P_CTRL_EDGEBOX_v{VER}.ino'
W1P = ROOT / f'HV_P2P_W1P_EDGEBOX_v{VER}' / f'HV_P2P_W1P_EDGEBOX_v{VER}.ino'
TS = ROOT / f'HV_P2P_CTRL_TS_v{VER}' / f'HV_P2P_CTRL_TS_v{VER}.ino'
FRAME_CTRL = ROOT / f'HV_P2P_CTRL_EDGEBOX_v{VER}' / 'HV_P2P_RS485_Frame.h'
FRAME_TS = ROOT / f'HV_P2P_CTRL_TS_v{VER}' / 'HV_P2P_RS485_Frame.h'
IMG_HDR = ROOT / f'HV_P2P_CTRL_EDGEBOX_v{VER}' / 'HV_P2P_CTRL_TS_Firmware_Image.h'
SRVR_DIR = ROOT / 'SRVR_GitHub_v26.10.06.08'
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

# CTRL E-stop: commissioned AI0 voltage input, 5 V NC loop, fail-unsafe semantics; AI1 is joystick.
must('SGM_CONFIG_AI0_CONT_800SPS_6V144 = 0x40E3' in c and 'sampleCtrlEstopAI0' in c, 'CTRL E-stop uses SGM58031 AI0 voltage input')
must('CTRL_ESTOP_HEALTHY_MIN_V = 3.5f' in c and 'g_ctrlEstopActive = true' in c, 'CTRL AI0 E-stop has healthy threshold and fail-unsafe default')
must('CTRL_ESTOP_HEALTHY_CONFIRM_SAMPLES = 3' in c and 'E-stop assertion is immediate' in c, 'CTRL AI0 E-stop clears only after consecutive healthy samples')
must('AI0 carries the CTRL E-stop status' in c and 'AI1 carries the APEM 0-5 V joystick signal' in c, 'CTRL final AI0 E-stop / AI1 joystick mapping')
must('PIN_LOCAL_ESTOP = 4' in w and 'LOCAL_ESTOP_HEALTHY_LEVEL = HIGH' in w, 'W1P E-stop uses DI0 HIGH=healthy')
must('bool active = (raw != LOCAL_ESTOP_HEALTHY_LEVEL);' in w, 'W1P open/pressed DI0 resolves unsafe')

# CTRL analog path: direct EdgeBox SGM58031, correct 0-10V divider scaling.
for tok in ['SDA_PIN 20','SCL_PIN 19','ADS_ADDR = 0x48','SGM_REG_CONVERSION = 0x00','SGM_REG_CONFIG     = 0x01','SGM_REG_CONFIG1    = 0x04','SGM_CONFIG_AI0_CONT_800SPS_6V144 = 0x40E3','SGM_CONFIG_AI1_CONT_800SPS_6V144 = 0x50E3']:
    must(tok in c, f'CTRL SGM58031 contract: {tok}')
must('Adafruit_ADS1X15' not in c and '#include <Adafruit_ADS' not in c, 'CTRL no longer depends on external ADS1115 library/hardware')
must('EDGEBOX_JOY_5V_COUNTS = 13333.3f' in c, 'CTRL 0-5V field endpoint accounts for EdgeBox ~2:1 divider')
expected_counts=(2.5/6.144)*32768.0
must(abs(expected_counts-13333.3)<1.0, f'ADC scaling math: 5V field -> ~{expected_counts:.1f} counts')
must('SRVR calibration authoritative' in c and 'Set Left / Set Centre / Set Right' in c, 'SRVR remains joystick Left/Centre/Right calibration authority')
must('JOY_SAMPLES = 5' in c and 'CONTROL_INTERVAL_MS   25' in c and 'trimmedSum' in c and 'minRaw' in c and 'maxRaw' in c, 'CTRL joystick uses 25 ms / 5-sample low-latency trimmed-mean acquisition')
must('sgmEnsureChannelVerified(SGM_CONFIG_AI1_CONT_800SPS_6V144, "AI1 joystick")' in c and '(0.20f * g_joy_filtered) + (0.80f * axis)' in c, 'CTRL preserves verified AI1 identity while using low-latency joystick filtering')
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
must('const bool hmi_safety = !hmiLinkConnected();' in c and 'const bool firmware_safety = !g_srvrFirmwareMatched;' in c and 'if(estop_active) flags_out |= FLAG_ESTOP_PRESSED;' in c and 'if(hmi_safety) flags_out |= FLAG_CTRL_HMI_FAULT;' in c and 'if(firmware_safety) flags_out |= FLAG_CTRL_FW_FAULT;' in c, 'CTRL preserves physical AI0 E-stop identity while CTRL-TS/firmware faults remain fail-safe on dedicated bits')
must('CTRL is always the bus master' in fc and 'CTRL-TS transmits only as a direct response' in fc, 'RS485 framing documents deterministic master/slave rule')
must('MAX_PAYLOAD = 3072' in fc and 'RX_INTERBYTE_TIMEOUT_MS = 250' in fc, 'RS485 framing has bounded payload and inter-byte timeout')
for typ in ['HELLO_REQ','HELLO_RESP','COMPATIBLE','TEXT','POLL','EVENT','FW_BEGIN','FW_BLOCK','FW_END','FW_RESULT','REBOOT']:
    must(typ in fc, f'RS485 frame type defined: {typ}')

# Exact Waveshare SKU27078 transport pins and display geometry.
must('#define HMI_UART_RX 15' in t and '#define HMI_UART_TX 16' in t, 'CTRL-TS SKU27078 official Arduino demo uses RX GPIO15 / TX GPIO16')
must('SPLASH_CANVAS_W = 800' in t and 'SPLASH_CANVAS_H = 480' in t, 'CTRL-TS uses actual SKU27078 800x480 display geometry')
must('CTRL-TS never initiates traffic' in t and 'frame.type == HVP2PRS485::POLL' in t, 'CTRL-TS only transmits in master response slots')
must('RS485_SLAVE_TURNAROUND_US = 2500' in t and 'delayMicroseconds(RS485_SLAVE_TURNAROUND_US)' in t, 'CTRL-TS has conservative explicit master-release turnaround guard')
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
must('esp_ota_get_boot_partition' in t and 'fw_meta_key' in t and ('commit marker' in t or 'commit key' in t), 'CTRL-TS firmware identity metadata is committed per OTA partition')
must('FW_MAX_IMAGE_SIZE = 0x380000' in t and 'imageSize > FW_MAX_IMAGE_SIZE' in t, 'CTRL-TS receiver enforces the conservative 0x380000 OTA slot')
must('CTRL_TS_SEMVER' in t and 'storedVersion == CTRL_TS_SEMVER' in t, 'CTRL-TS reported/stored version derives from one release semantic-version token')
must('Do NOT change g_fw_image_hash while the old application is still running' in t and 'return verify;' in t, 'CTRL-TS does not claim the staged image hash before reboot')
must('MAX_IMAGE = 0x380000' in read(ROOT/'tools'/'embed_ctrl_ts_firmware.py'), 'CTRL-TS embed helper enforces the conservative 0x380000 target OTA slot')

# Lock the reviewed v26.10.06.08 W1P safety-critical implementations via normalized function hashes.
# Safety-facing functions intentionally extended in v26.10.06.08 are hash-locked separately below.
expected_w1p={
'modbusCRC16':'2d54f956989bcfd6a5b539664c14228f13046f16daca4911cd6467fcafe6cd3e',
'modbusWaitForSilentGap':'46cb53133b81b90bcc184ace784e64e1f807823485cd1ea29ad3b228a4b94cb8',
'modbusWriteSingleRegister':'6676bd5a93f21336c687e124c6ac39cb4e6de0cbcd7fcb356ce518ededb550c6',
'modbusWriteMultipleRegisters':'3eaa8f8024407feebb1d8b1bb05202e13e1f365d130afa46af175938de41fe2d',
'modbusReadHoldingRegisters':'e5d0be35fa23f7dfb65fd7e1f99b525838fe3321273c009f654664aa5c07eb2d',
'driveConfigureMotionProfile':'16d009b4021a35bfac853e26180c877d43be1785aee09383bd98e188bdbafb4c',
'driveWriteVelocityCommandMps':'9aad44b460554af641e5ea3bc8007e22920dc23d8c1fc6ad3b0c4061d0b1df7e',
'driveSendEmergencyStop':'dd6f292ac097e31e00184a42983032e2d70d91e25a65c4b910d7a3202fa5ed8c',
'serviceMotionProfile':'fbad116e5b9f9ee1d07e049d7014647713d503ec96d107a7fad75690556ce18e',
'limitVelocityForSoftLimits':'d881fbb4b568b0f223aad36c10fffae7d8a32b3f9e33c9b63b26e9ac6421182d',
'predictiveLimitSpeedCap':'78aa12aea8baa400d2ef7df0e05cb6eacdda511e2bffbb977b8faa1573e85ccc',
'driveStopNow':'ed4b91222340b12c83ca0371d4501cc77dfe135ac687e432b219ad8553b6bb96',
'servicePeerTimeout':'81d5f57232771f48dbe5edd46161f75a8f5adf2aee370e9bc6180d64d61a48ff',
'preserveDisplayedPositionForMotorDirectionChange':'e78aafbc76eb48601a04eed3703372a0dfd1f2c19070e891fdbd1952984942a0',
}
for fn,h in expected_w1p.items(): must(normalized_func_hash(w,fn)==h, f'W1P reviewed v26.10.06.08 safety-critical logic preserved: {fn}')

expected_w1p_v07_safety={
'driveAutoEnableReady':'ce2cd73df1636f1ba2dd7ba23da9eca4f983ba3ee6a179dd9b5398ad831dc78f',
'handleCommand':'eddc02983dec382ff0370f7b34fb244f855bfd45571836de9a217217ab83da2b',  # reviewed .05.11 SRVR authority-session revalidation
'sendStatusLine':'00091e4a517a4196739f6307b8fea1a80afcc9bf405361bb4bfea1d6768aa397',
'serviceVelocityCommandWatchdog':'a6dc0d9244bf1c7b64d28291c56c8fcd20abb21af5566a5bf396e1723fdd9111',
'hvPrepareSafeServiceState':'92026ffa3126d53e57d9f111583d11f7ef52b19b16528af82b970108bf4eb8ab',
}
for fn,h in expected_w1p_v07_safety.items(): must(normalized_func_hash(w,fn)==h, f'W1P v26.10.06.08 reviewed safety extension hash locked: {fn}')

# Leadshine contract.
for tok in ['RS485_BAUD = 115200','DRIVE_MODBUS_ID = 1','SERIAL_8N1','MODBUS_REPLY_TIMEOUT_MS = 50','MODBUS_READ_RETRIES = 3','MODBUS_INTERFRAME_GAP_US = 2000','W1P_PEER_TIMEOUT_MS = 750']:
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

# v26.10.06.08 independent W1P command-deadman and service safety gate.
wd=extract_func(w,'serviceVelocityCommandWatchdog')
must('W1P_VEL_COMMAND_TIMEOUT_MS = 500' in w, 'W1P independent VEL watchdog timeout is 500ms')
must('lastVelocityCommandMs' in wd and 'lastPeerPacketMs' not in wd, 'W1P VEL watchdog keys only from VEL freshness, not generic peer traffic')
must(all(tok in wd for tok in ('driveStopNow();','g.drive_writes_enabled = false','requestSoftwareSrvonInhibit(true, "VEL_WATCHDOG")')), 'W1P VEL watchdog stops, locks drive writes and drops software Servo Enable')
must('serviceVelocityCommandWatchdog();' in extract_func(w,'loop'), 'W1P main loop services the independent VEL watchdog')
must('VEL_WD=' in w and 'SERVICE_LOCK=' in w and 'VEL_AGE_MS=' in w, 'W1P status exposes watchdog/service safety state to SRVR')
service_gate=extract_func(w,'hvPrepareSafeServiceState')
must(all(tok in service_gate for tok in ('driveStopNow();','g.drive_writes_enabled = false','requestSoftwareSrvonInhibit(true, "WEB_SERVICE")','modbusReadFeedbackBlock','rawUnitsDeltaToDisplayMps','OUTPUT_DO3_MASK','OUTPUT_DO4_MASK','stableSamples >= 2','lastDriveFeedbackMs','LEADSHINE_SRVON_DISABLED_VALUE')), 'W1P service gate uses fresh post-stop EL7 samples and proves stopped/SRV-ST-off/BRK-OFF-off state')
must(w.count('hvPrepareSafeServiceState(reason)') >= 2 and 'hvPrepareSafeServiceState(hvUploadError)' in w, 'W1P OTA/reboot/reset all enter the safe service gate')
must('SERVICE_REARM' in w and 'STOP_CLEAR_LATCH' in w, 'W1P service/watchdog latch requires STOP re-arm path')

# v26.10.06.08 closes the W1P Setup-IP semantic gap with a coordinated safe
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
must('config_schema_version' in s and 'position_reference_persistent' in s and 'self._not_calibrated = True' in s, 'SRVR position reference is explicitly non-persistent across sessions')
must('_goto_approach_dir' in s and '_goto_velocity_for_distance' in s, 'SRVR Goto anti-hunt approach logic retained')


# SRVR/CTRL-TS interface-alignment and Free-D diagram regression guards.
must('text:"Link"' in q and 'text:"RS485"' in q and 'text:"E-Stop"' in q and 'text:"Firmware"' in q, 'Setup uses locked generic CTRL/W1P status row labels')
must('W1P-TS Link' not in q, 'Setup does not expose the excluded W1P-TS')
must('CTRL_HMI_ARCH "EdgeBox ESP-100' in c and 'EdgeBox-ESP-100' in w, 'CTRL and W1P source identify the EdgeBox-ESP-100 hardware baseline')
must('▣  CTRL-TS' in q and 'CTRL-TS / FIRMWARE' not in q and 'ctrlTsFirmwareDisplay' in q and 'Detected' not in q[q.index('▣  CTRL-TS'):q.index('Panel {', q.index('▣  CTRL-TS')+1)] and 'Required' not in q[q.index('▣  CTRL-TS'):q.index('Panel {', q.index('▣  CTRL-TS')+1)] and 'W1P-TS AUX ASSIGN' not in q, 'Setup preserves approved CTRL-TS panel with one Firmware value field')
must('profileValue(Number(gp.x), key)' in span, 'Free-D geometry markers are sampled from the exact rendered cable path')


# v26.10.06.08 locked Run/Setup revision and Virtual demo-source contract.
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
must('if self.position_source == "Virtual"' in virt_send and 'self._virtual_velocity_mps = vel' in virt_send and 'cmd = "VEL 0" if abs(vel) < .001 else f"VEL {vel:.3f}"' in virt_send and 'self.w1p.send(cmd)' in virt_send, 'Virtual mode simulates requested velocity locally while physical VEL emission remains Encoder-only')
must('virtual_demo = (self.position_source == "Virtual")' in s and '((not virtual_demo) and w1p_safety)' in s, 'Virtual demo can run without W1P while physical W1P faults remain authoritative in Encoder mode')
must('if "POS_M" in fields and self.position_source != "Virtual"' in s and 'if "VEL_MPS" in fields and self.position_source != "Virtual"' in s, 'Physical W1P feedback cannot overwrite Virtual demo position/speed')
must('if not self.smoke_test and self.position_source != "Virtual"' in s and 'SYNC_POS' in s, 'Virtual Slip/re-reference does not rewrite physical W1P position')
must('FLAG_CTRL_HMI_FAULT = 0x0800' in s and 'FLAG_CTRL_FW_FAULT = 0x1000' in s, 'SRVR preserves distinct CTRL interface/firmware fault bits')
must('def systemStatusLevel' in s and 'System | Uncalibrated' in s, 'SRVR exposes red/yellow/green status priority with uncalibrated below faults')
must('BOOT_ID=' in w and 'g_boot_session_id' in w and '_invalidate_position_reference' in s, 'W1P boot-session changes invalidate SRVR position reference')
must('fw_ensure_update_screen' in t and 'if(!fw_display_owned())' in t, 'CTRL-TS firmware update owns a stable dedicated display state')
must('if(g_srvrFirmwareMatched) return;' in c and 'FW_AUTH_MATCHED_RECHECK_MS' not in c and 'static bool applySrvrFirmwareBeacon' in c and 'line.startsWith("SRVR_FW|")' in c and 'line.startsWith("DSP1|")' in c, 'CTRL notices a newer SRVR through dedicated/normal UDP release beacons without healthy-loop HTTP polling')
must('if(g_srvrFirmwareMatched) return;' in w and 'FW_AUTH_MATCHED_RECHECK_MS' not in w and 'if (line.startsWith("SRVR_FW|"))' in w, 'W1P notices a newer SRVR through its UDP firmware beacon without healthy-loop HTTP polling')
must('f"srvr_fw={self._current_firmware_version()}"' in s and 'def _send_ctrl_firmware_beacon' in s and 'def _send_w1p_firmware_beacon' in s and 'SRVR_FW|version=' in s, 'SRVR publishes non-blocking release-change beacons to CTRL and W1P')
must('stale_release_report' in s and 'reported_match and version_current and authority_current' in s, 'SRVR rejects stale old-release CTRL firmware-match claims')
must('return self._current_firmware_version()' in s and '"Update required"' in s, 'SRVR firmware diagnostics use the running SRVR release as authority')
must('g_fw_screen = lv_obj_create(NULL);' in t and 'lv_obj_set_style_bg_opa(g_fw_screen, LV_OPA_COVER, 0);' in t and 'lv_scr_load(g_fw_screen);' in t and 'lv_refr_now(NULL);' in t, 'CTRL-TS uses a dedicated opaque firmware dashboard before entering safe self-update mode')
must('fw_stage_safe_update_handoff' in t and 'fw_prepare_headless_mode' in t and 'fw_headless_blackout' in t and 'fw_safe_reboot_retry' in t and 'if(!g_fw_headless_mode)' in t, 'CTRL-TS self-update stages target in internal RAM and reboots into a display-off headless updater before flash programming')
must('#include <esp_attr.h>' in t and '__NOINIT_ATTR' in t and 'FW_SAFE_HANDOFF_MAGIC' in t and 'esp_reset_reason() != ESP_RST_SW' in t, 'CTRL-TS safe-update handoff survives only deliberate software restart and is guarded in no-init internal RAM')
must(all(tok not in t for tok in ('putString("upd_target"','putString("upd_sha"','putBool("upd_mode"')), 'CTRL-TS live-display safe-update handoff performs no NVS flash writes')
must('\"|safe_ota=2\"' in t and 'g_hmiSafeOtaLevel' in c and 'g_hmiSafeOtaCapable = g_hmiSafeOtaLevel >= 2' in c, 'CTRL-TS advertises safe OTA capability level 2 and CTRL requires it')
must('manual USB bootstrap to v26.10.03.04 or newer required' in c and 'if(!g_hmiSafeOtaCapable)' in c, 'CTRL refuses automatic self-flash of level-0/1 CTRL-TS receivers that lack fixed safe OTA capability')
must('g_hmiSafeRebootHoldUntilMs = millis() + 3000;' in c and 'safeRebootHold' in c, 'CTRL holds HMI rediscovery during CTRL-TS safe reboot so FW_BEGIN cannot starve the restart')
must('if(g_fw_safe_reboot_due_ms)' in t and 'duplicate FW_BEGIN' in t, 'CTRL-TS duplicate FW_BEGIN cannot move an already scheduled safe reboot deadline')
must('fw_compare_release_versions' in t and 'fw_downgrade_blocked' in t and 'if(releaseRelation < 0)' in t, 'manually recovered .04+ CTRL-TS rejects downgrade attempts from an older CTRL carrier')
must('no firmware transfer started for 60 s' in t and 'lastActivity = last_hmi_rx' not in t, 'headless recovery timeout cannot be held black forever by HELLO-only traffic')
for tok in ('esp_lcd_rgb_panel_set_pclk', 'esp_lcd_rgb_panel_restart', 'FW_RGB_PCLK_HZ', 'NORMAL_RGB_PCLK_HZ'):
    must(tok not in t, f'CTRL-TS self-update does not manipulate active RGB pipeline: {tok}')
must('if(pct == g_fw_last_display_pct' in t and 'return;' in t[t.index('if(pct == g_fw_last_display_pct'):t.index('if(pct == g_fw_last_display_pct')+180], 'CTRL-TS redraws update progress only when integer percentage/phase changes')
must('g_status_text = "E-Stop | " + src;' in t and 'detail.startsWith("E-Stop / ")' in t and 'while(detail.startsWith("/"))' in t, 'CTRL-TS E-stop banner reconstructs delimiter-safe source text without slash typo')
for glyph in ('◇','⚙','◴','⌖'):
    must(glyph not in t, f'CTRL-TS compiled-font UI contains no unsupported glyph {glyph!r}')
must('const char *aux_heads[AUX_COUNT]={"AUX 1","AUX 2","AUX 3","AUX 4","AUX 5"}' in t and 'make_label(drive,"DRIVE"' in t and 'make_label(speed,"SPEED"' in t and 'make_label(position,"POSITION"' in t, 'CTRL-TS AUX/Drive/Speed/Position headings are plain supported text')
must('static void service_runtime_connection_screen()' in t and 'const char *msg = ctrl_link_alive ? "Waiting for SRVR" : "Waiting for CTRL";' in t and 'lv_scr_load(boot_scr);' in t and 'lv_scr_load(g_main_scr);' in t, 'CTRL-TS returns to the resident startup splash on runtime SRVR/CTRL loss')
must(q.index('"Joystick Calibration"') < q.index('"Limit Calibration"') < q.index('"Winch Calibration"'), 'CTRL AUX Assign calibration actions are exposed in alphabetical order')
aux_handler=s[s.index('def _handle_aux_action'):s.index('def _display_field', s.index('def _handle_aux_action'))]
must('self.calibration_open and self.calibration_type == "Limit"' in aux_handler and 'self.calibration_open and self.calibration_type == "Winch"' in aux_handler and 'self.joystick_calibration_open' in aux_handler, 'AUX calibration confirmations advance open wizards instead of reopening step 1')
must('g_last_cal_overlay_kind' in t and 'g_last_cal_overlay_step' in t and 'kind != g_last_cal_overlay_kind || step != g_last_cal_overlay_step' in t, 'CTRL-TS clears AUX Confirm latch on every calibration kind/step transition')
must('queue_aux_touch' in t and 'service_aux_touch_events' in t and 'g_aux_touch_queue[8]' in t, 'CTRL-TS touch callbacks defer AUX state/protocol work into a fixed main-loop queue')
aux_cb=t[t.index('static void aux_event_cb'):t.index('static void service_aux_touch_events', t.index('static void aux_event_cb'))]
must('queue_aux_touch' in aux_cb and 'confirm_aux_idx' not in aux_cb and 'send_hmi_command' not in aux_cb, 'CTRL-TS LVGL AUX callback is heap-free and cannot directly execute a confirmed action')
must('g_settings_reset_due_ms' not in t, 'ordinary CTRL-TS settings/AUX UI has no dormant self-reboot timer')
must('|boot_id=' in t and '|reset_reason=' in t and 'g_boot_id = esp_random()' in t, 'CTRL-TS HELLO reports per-boot reset diagnostics')
must('g_hmiReportedBootId' in c and 'g_hmiReportedResetReason' in c and '|boot_id=' in c and '|reset_reason=' in c, 'CTRL relays CTRL-TS boot/reset diagnostics to SRVR')
must('hmiFwProgressPct()' in c and '|fw_pct=' in c, 'CTRL relays CTRL-TS headless firmware progress to SRVR')
must('replace_comma=False' in s and 'Hold Joystick Left, then Press Confirm' in s and 'Release Joystick to Centre, then Press Confirm' in s and 'Hold Joystick Right, then Press Confirm' in s, 'CTRL-TS joystick calibration instructions preserve exact comma/Press wording')
must('pos_frac=' in s and 'ref_frac=' in s and 'def _span_fraction' in s, 'SRVR publishes one canonical normalized position/reference coordinate')
must('g_pos_frac' in t and 'g_ref_frac' in t and 'constrain(g_ref_frac' in t, 'CTRL-TS travel bar consumes SRVR canonical normalized position/reference coordinates')
must('currentFraction:backend.positionFraction' in main_qml and 'refFraction:backend.refFraction' in main_qml and 'property real refFraction: -1' in span, 'SRVR Top/Side views consume the same canonical position/reference fractions as CTRL-TS')
must('text:backend.bannerText' in main_qml and '♢' not in main_qml and '◇' not in main_qml, 'SRVR top status bar contains no unsupported leading diamond glyph')
must('def _legacy_firmware_push_worker' in s and 'HTTPConnection' in s and '"/update/app"' in s and 'multipart/form-data' in s and 'daemon=True' in s and 'def _firmware_version_is_older' in s, 'SRVR has asynchronous backwards-compatible OTA push for older pre-beacon .01 field nodes without downgrading newer firmware')
must('ctrl_present = bool(self._ctrl_connected() or self._ctrl_authority_fresh())' in s, 'legacy CTRL firmware bridge accepts either fresh control telemetry or fresh authority/HMI status presence')
must('firmware_bundle=authority.bundle' in m, 'SRVR backend receives the already validated immutable firmware bundle for legacy OTA bridging')
must('ctrl_version=v26.10.06.08' in c and 'FW=" + String(FW_VERSION)' in w, 'CTRL and W1P publish actual firmware identity for Setup')
must('ctrlFirmwareVersion' in s and 'w1pFirmwareVersion' in s and 'ctrlEStopActive' in s and 'w1pEStopActive' in s, 'SRVR exposes locked CTRL/W1P Setup diagnostics')
must('text:"Link"' in q and 'backend.ctrlTsRs485Active?"Active":"Disconnected"' in q, 'CTRL-TS Link uses physical RS485 Active/Disconnected semantics')
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
