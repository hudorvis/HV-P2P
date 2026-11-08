#!/usr/bin/env python3
"""Exercise the GitHub Actions install and board checks with a fake CLI."""
import os
from pathlib import Path
import subprocess
import tempfile
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / '.github/workflows/complete-build.yml').read_text()


def step_script(name):
    heading = f'      - name: {name}\n'
    step = workflow.split(heading, 1)[1].split('\n      - name: ', 1)[0]
    assert '        shell: bash\n' in step
    return dedent(step.split('        run: |\n', 1)[1])


install = step_script('Install ESP32 Arduino core 3.3.8')
verify = step_script('Verify ESP32 firmware board targets')
assert 'ARDUINO_BOARD_MANAGER_ADDITIONAL_URLS: https://espressif.github.io/arduino-esp32/package_esp32_index.json' in workflow
assert 'ARDUINO_NETWORK_CONNECTION_TIMEOUT: 120s' in workflow

fake_cli = """#!/usr/bin/env python3
import os
from pathlib import Path
import sys

command = " ".join(sys.argv[1:])
log = Path(os.environ["ARDUINO_TEST_LOG"])
previous = log.read_text().splitlines()
with log.open("a") as stream:
    stream.write(command + "\\n")

threshold = {
    "core update-index": os.environ["ARDUINO_TEST_INDEX_FAILURES"],
    "core install esp32:esp32@3.3.8": os.environ["ARDUINO_TEST_INSTALL_FAILURES"],
}.get(command, "0")
if previous.count(command) < int(threshold) or command == os.environ["ARDUINO_TEST_MISSING_BOARD"]:
    print("CLI detail for " + command, file=sys.stderr)
    sys.exit(1)
"""


with tempfile.TemporaryDirectory(prefix='hvp2p-arduino-ci-') as directory:
    scratch = Path(directory)
    for name, body in [('arduino-cli', fake_cli), ('sleep', '#!/bin/sh\nexit 0\n')]:
        executable = scratch / name
        executable.write_text(body)
        executable.chmod(0o755)
    call_log = scratch / 'calls.log'

    def run(script, *, index_failures=0, install_failures=0, missing_board=''):
        call_log.write_text('')
        env = dict(os.environ, PATH=f'{scratch}{os.pathsep}{os.environ["PATH"]}',
                   ARDUINO_TEST_LOG=str(call_log), ARDUINO_TEST_INDEX_FAILURES=str(index_failures),
                   ARDUINO_TEST_INSTALL_FAILURES=str(install_failures), ARDUINO_TEST_MISSING_BOARD=missing_board)
        result = subprocess.run(
            ['bash', '--noprofile', '--norc', '-e', '-o', 'pipefail', '-c', script],
            env=env, capture_output=True, text=True, check=False,
        )
        return result, call_log.read_text().splitlines()

    index = 'core update-index'
    package = 'core install esp32:esp32@3.3.8'
    result, calls = run(install, index_failures=2, install_failures=1)
    assert result.returncode == 0, result.stderr
    assert calls == ['version', index, index, index, package, package, 'core list'], calls
    assert result.stdout.count('::warning::') == 3

    result, calls = run(install, index_failures=3)
    assert result.returncode != 0 and calls == ['version', index, index, index], calls
    assert 'CLI detail for core update-index' in result.stderr
    assert '::error::arduino-cli core update-index failed after 3 attempts' in result.stderr

    result, calls = run(install, install_failures=3)
    assert result.returncode != 0 and calls == ['version', index, package, package, package], calls
    assert f'::error::arduino-cli {package} failed after 3 attempts' in result.stderr

    edgebox = 'board details --fqbn esp32:esp32:Edgebox-ESP-100'
    hmi = 'board details --fqbn esp32:esp32:esp32s3'
    result, calls = run(verify)
    assert result.returncode == 0 and calls == [edgebox, hmi], calls
    for missing, expected_calls in [(edgebox, [edgebox]), (hmi, [edgebox, hmi])]:
        result, calls = run(verify, missing_board=missing)
        assert result.returncode != 0 and calls == expected_calls, calls
        assert missing in result.stderr

print('ARDUINO_CI_INSTALL_RETRY_AND_BOARD_GATES_PASS')
