#!/usr/bin/env python3
from pathlib import Path
import subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
checks=[
    ['python3',str(ROOT/'tools'/'validate_edgebox_integration.py')],
    ['python3',str(ROOT/'tools'/'test_rs485_frame_host.py')],
    ['python3',str(ROOT/'tools'/'test_hmi_fw_retry_contract.py')],
    ['python3',str(ROOT/'tools'/'test_hmi_target_gate.py')],
    ['python3',str(ROOT/'tools'/'test_embed_tool.py')],
    ['python3',str(ROOT/'tools'/'validate_build_pipeline.py')],
    ['python3',str(ROOT/'tools'/'test_modbus_contract_host.py')],
    ['python3',str(ROOT/'tools'/'test_srvr_wire_contract.py')],
    ['python3',str(ROOT/'tools'/'test_speed_mode_contract.py')],
    ['python3','-m','py_compile',str(ROOT/'SRVR_GitHub_v26.09.04.02'/'backend.py'),str(ROOT/'SRVR_GitHub_v26.09.04.02'/'main.py')],
    ['python3',str(ROOT/'SRVR_GitHub_v26.09.04.02'/'tools'/'validate_project.py')],
]
for cmd in checks:
    print('\n==>', ' '.join(cmd), flush=True)
    subprocess.run(cmd,check=True,cwd=ROOT)
print('\nALL_SOURCE_CHECKS_PASS')
print('NOTE: Native Arduino compilation is performed by .github/workflows/complete-build.yml; physical RS485/EL7/motion tests remain bench commissioning gates.')
