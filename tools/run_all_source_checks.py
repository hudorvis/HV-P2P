#!/usr/bin/env python3
from pathlib import Path
import os, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
checks=[
    ['python3',str(ROOT/'tools'/'test_release_consistency.py')],
    ['python3',str(ROOT/'tools'/'test_source_package_hygiene.py')],
    ['python3',str(ROOT/'tools'/'validate_edgebox_integration.py')],
    ['python3',str(ROOT/'tools'/'test_rs485_frame_host.py')],
    ['python3',str(ROOT/'tools'/'test_hmi_fw_retry_contract.py')],
    ['python3',str(ROOT/'tools'/'test_hmi_target_gate.py')],
    ['python3',str(ROOT/'tools'/'test_embed_tool.py')],
    ['python3',str(ROOT/'tools'/'test_firmware_authority_server.py')],
    ['python3',str(ROOT/'tools'/'test_firmware_bundle_builder.py')],
    ['python3',str(ROOT/'tools'/'test_srvr_automatic_ota_contract.py')],
    ['python3',str(ROOT/'tools'/'test_frozen_firmware_packaging_contract.py')],
    ['python3',str(ROOT/'tools'/'test_native_build_orchestration.py')],
    ['python3',str(ROOT/'tools'/'test_backend_logic_headless.py')],
    ['python3',str(ROOT/'tools'/'validate_build_pipeline.py')],
    ['python3',str(ROOT/'tools'/'test_modbus_contract_host.py')],
    ['python3',str(ROOT/'tools'/'test_srvr_wire_contract.py')],
    ['python3',str(ROOT/'tools'/'test_speed_mode_contract.py')],
    ['python3',str(ROOT/'tools'/'test_python_syntax.py')],
    ['python3',str(ROOT/'SRVR_GitHub_v26.09.15.02'/'tools'/'validate_project.py')],
]
env=os.environ.copy()
env['PYTHONDONTWRITEBYTECODE']='1'
for cmd in checks:
    print('\n==>', ' '.join(cmd), flush=True)
    subprocess.run(cmd,check=True,cwd=ROOT,env=env)
print('\nALL_SOURCE_CHECKS_PASS')
print('NOTE: Native Arduino compilation is performed by .github/workflows/complete-build.yml; physical RS485/EL7/motion tests remain bench commissioning gates.')
