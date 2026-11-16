#!/usr/bin/env python3
"""Exercise the production W1P DI0 sampler with a simulated input and clock."""
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sketch = next(ROOT.glob("HV_P2P_W1P_EDGEBOX_v*/*.ino")).read_text()
names = (
    "PIN_W1P_ESTOP_DI0", "W1P_ESTOP_HEALTHY_CONFIRM_SAMPLES",
    "W1P_ESTOP_SAMPLE_INTERVAL_MS", "W1P_ESTOP_DIAG_INTERVAL_MS",
    "g_w1pEstopHealthySamples", "g_w1pEstopLastSampleMs", "g_w1pEstopLastDiagMs",
)
declarations = [re.search(rf"^static [^\n;]+\b{name}\s*=[^;]+;", sketch, re.M).group()
                for name in names]
sampler = re.search(r"^static void updateLocalInputs\(\) \{\n.*?^\}", sketch, re.M | re.S).group()
setup = re.search(r"^void setup\(\) \{\n.*?^\}", sketch, re.M | re.S).group()
assert "bool local_estop = true;" in sketch
assert "digitalWrite(PIN_EDGEBOX_BRAKE_DO0, LOW);" in setup
assert setup.index("g.local_estop = true;") < setup.index("pinMode(PIN_W1P_ESTOP_DI0, INPUT);")
assert "g.drive_writes_enabled = false;" in setup and "g.software_srvon_inhibit = true;" in setup

harness = r"""
#include <cassert>
#include <cstdint>
#include <cstring>
static constexpr int LOW = 0, HIGH = 1;
static int pinLevel = LOW, stopCalls = 0, inhibitCalls = 0, readCalls = 0, statusCalls = 0;
static bool reportedEstop = false;
static uint32_t nowMs = 100;
static uint32_t millis() { return nowMs; }
static int digitalRead(int pin) {
  assert(pin == 4);
  ++readCalls;
  return pinLevel;
}
static struct {
  bool local_estop = true, drive_writes_enabled = false, software_srvon_inhibit = true;
} g;
static void driveStopNow() {
  assert(g.local_estop);
  ++stopCalls;
}
static void requestSoftwareSrvonInhibit(bool inhibit, const char *reason) {
  assert(inhibit && !g.drive_writes_enabled && std::strcmp(reason, "W1P_ESTOP") == 0);
  g.software_srvon_inhibit = true;
  ++inhibitCalls;
}
static void sendStatusLine(bool force) {
  assert(force && g.software_srvon_inhibit && !g.drive_writes_enabled);
  ++statusCalls;
  reportedEstop = g.local_estop;
}
static struct {
  void println(const char *) {}
  void printf(const char *, const char *) {}
} Serial;
"""

exercise = r"""
static void sample(uint32_t t, int level) {
  nowMs = t;
  pinLevel = level;
  updateLocalInputs();
}

int main() {
  // Open circuit at boot and a brief closed pulse both leave W1P inhibited.
  sample(100, LOW);
  sample(110, HIGH);
  sample(111, HIGH);
  sample(115, HIGH);
  assert(readCalls == 2 && g.local_estop);
  sample(120, HIGH);
  sample(130, LOW);
  assert(g.local_estop && stopCalls == 0 && inhibitCalls == 0 && statusCalls == 0);

  // Three consecutive samples prove a closed contact. SRVR still owns re-arm.
  sample(140, HIGH);
  sample(150, HIGH);
  assert(g.local_estop);
  sample(160, HIGH);
  assert(!g.local_estop && g.software_srvon_inhibit && !g.drive_writes_enabled);
  assert(statusCalls == 1 && !reportedEstop);

  // Simulate normal re-arm, then interrupt the field loop.
  g.software_srvon_inhibit = false;
  g.drive_writes_enabled = true;
  sample(170, LOW);
  assert(g.local_estop && g.software_srvon_inhibit && !g.drive_writes_enabled);
  assert(stopCalls == 1 && inhibitCalls == 1);
  assert(statusCalls == 2 && reportedEstop);
  sample(180, LOW);
  assert(stopCalls == 1 && inhibitCalls == 1 && statusCalls == 2);

  // A release across clock rollover needs the same three healthy samples.
  sample(UINT32_MAX - 4, HIGH);
  sample(4, HIGH);
  assert(g.local_estop && g_w1pEstopHealthySamples == 1);
  sample(5, HIGH);
  assert(g.local_estop && g_w1pEstopHealthySamples == 2);
  sample(15, HIGH);
  assert(!g.local_estop && g.software_srvon_inhibit && !g.drive_writes_enabled);
  assert(stopCalls == 1 && inhibitCalls == 1);
  assert(statusCalls == 3 && !reportedEstop);
}
"""

with TemporaryDirectory(prefix="hvp2p-w1p-di0-") as directory:
    test_src = Path(directory) / "di0.cpp"
    test_binary = test_src.with_suffix("")
    test_src.write_text("\n".join([harness, *declarations, sampler, exercise]))
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(test_src), "-o", str(test_binary)], check=True)
    subprocess.run([str(test_binary)], check=True)
print("W1P_DI0_ESTOP_RUNTIME_PASS")
