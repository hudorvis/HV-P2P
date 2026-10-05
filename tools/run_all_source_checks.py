#!/usr/bin/env python3
from pathlib import Path
import os, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
checks=[
    ['python3',str(ROOT/'tools'/'test_audit_regressions.py')],
    ['python3',str(ROOT/'tools'/'validate_edgebox_integration.py')],
    ['python3',str(ROOT/'tools'/'test_rs485_frame_host.py')],
    ['python3',str(ROOT/'tools'/'test_hmi_fw_retry_contract.py')],
    ['python3',str(ROOT/'tools'/'test_hmi_target_gate.py')],
    ['python3',str(ROOT/'tools'/'test_hmi_transport_contract.py')],
    ['python3',str(ROOT/'tools'/'test_hmi_bus_serialization_contract.py')],
    ['python3',str(ROOT/'tools'/'test_runtime_regression_contract.py')],
    ['python3',str(ROOT/'tools'/'test_bench_regression_0304.py')],
    ['python3',str(ROOT/'tools'/'test_end_to_end_comm_contract_0305.py')],
    ['python3',str(ROOT/'tools'/'test_ctrl_ts_aux_confirm_crash_0401.py')],
    ['python3',str(ROOT/'tools'/'test_ctrl_ts_progress_and_ramp_0402.py')],
    ['python3',str(ROOT/'tools'/'test_settings_virtual_firmware_0403.py')],
    ['python3',str(ROOT/'tools'/'test_limit_ramp_geometry_0404.py')],
    ['python3',str(ROOT/'tools'/'test_bench_regression_0405.py')],
    ['python3',str(ROOT/'tools'/'test_bench_regression_0406.py')],
    ['python3',str(ROOT/'tools'/'test_limit_calibration_runtime_contract_0407.py')],
    ['python3',str(ROOT/'tools'/'test_bench_regression_0501.py')],
    ['python3',str(ROOT/'tools'/'test_backend_status_runtime_contract_0502.py')],
    ['python3',str(ROOT/'tools'/'test_firmware_coordinator_0503.py')],
    ['python3',str(ROOT/'tools'/'test_firmware_update_convergence_0506.py')],
    ['python3',str(ROOT/'tools'/'test_bench_regression_0507.py')],
    ['python3',str(ROOT/'tools'/'test_bench_regression_0504.py')],
    ['python3',str(ROOT/'tools'/'test_ctrl_ts_parser_diagnostics_contract.py')],
    ['python3',str(ROOT/'tools'/'test_ctrl_ts_safe_update_contract.py')],
    ['python3',str(ROOT/'tools'/'test_splash_render_contract.py')],
    ['python3',str(ROOT/'tools'/'test_leadshine_commissioning_contract.py')],
    ['python3',str(ROOT/'tools'/'test_auto_ota_contract.py')],
    ['python3',str(ROOT/'tools'/'test_srvr_authority_server.py')],
    ['python3',str(ROOT/'tools'/'test_embed_tool.py')],
    ['python3',str(ROOT/'tools'/'test_native_build_orchestration.py')],
    ['python3',str(ROOT/'tools'/'validate_build_pipeline.py')],
    ['python3',str(ROOT/'tools'/'test_modbus_contract_host.py')],
    ['python3',str(ROOT/'tools'/'test_srvr_wire_contract.py')],
    ['python3',str(ROOT/'tools'/'test_speed_mode_contract.py')],
    ['python3',str(ROOT/'tools'/'test_motion_innovations_contract.py')],
    ['python3',str(ROOT/'tools'/'test_release_consistency.py')],
    ['python3',str(ROOT/'tools'/'test_source_hygiene.py')],
    ['python3',str(ROOT/'tools'/'test_python_syntax.py')],
    ['python3',str(ROOT/'SRVR_GitHub_v26.10.05.07'/'tools'/'validate_project.py')],
]
env=os.environ.copy(); env['PYTHONDONTWRITEBYTECODE']='1'
for cmd in checks:
    print('\n==>', ' '.join(cmd), flush=True)
    subprocess.run(cmd,check=True,cwd=ROOT,env=env)
# Backend runtime tests require PySide6 and run in the desktop CI jobs after
# dependencies are installed. Run locally too when the module is available.
try:
    import PySide6  # noqa: F401
except Exception:
    print('\nBACKEND_RUNTIME_TEST_SKIPPED: PySide6 not installed in source-audit environment')
else:
    cmd=['python3',str(ROOT/'SRVR_GitHub_v26.10.05.07'/'tools'/'test_backend_logic.py')]
    print('\n==>', ' '.join(cmd), flush=True)
    subprocess.run(cmd,check=True,cwd=ROOT,env=env)
print('\nALL_SOURCE_CHECKS_PASS')
print('NOTE: Native Arduino and frozen desktop compilation remain GitHub Actions gates; physical RS485/EL7/motion tests remain bench commissioning gates.')
