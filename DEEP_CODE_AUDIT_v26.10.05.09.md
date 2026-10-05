# HV P2P v26.10.05.09 deep code audit

Date: 2026-10-05

## Audit basis

Rebuilt and re-audited from the user-supplied `HV P2P v26.10.05.06.zip`. This
revision deliberately does not use the `.05.08` carrier redesign.

## Root causes and corrections

### 1. CTRL-TS verified update could finish without proving a reboot

`.05.06` called `hmiFwReset()` as soon as the final REBOOT command was ACKed. An
ACK proves only that the currently running safe updater received the command. It
does not prove that ESP restart occurred. Older headless safe-updater firmware can
therefore ACK and remain black until a manual reset.

Correction: ACK transitions to `HMI_FW_WAIT_REBOOT_CONFIRM`. CTRL retains the
pre-update boot identity, continues bounded REBOOT enforcement and interleaved
HELLO requests, and completes only on exact target version/SHA plus reboot proof.
Changed `boot_id` is preferred; legacy peers that supplied no pre-update boot ID
may use exact target identity because the running updater never reports the staged
image as active.

### 2. Near/Far text and Preset labels shared the same pixel band

`.05.06` placed endpoint distance text near y=22 while the upper Preset lane was
around y=27/28 using the same 10 px font. This is deterministic geometric overlap,
not font rendering drift.

Correction: shorter AUX row, taller travel panel, and separated readout/track/
Preset lanes. Montserrat 10 remains the minimum small font.

### 3. CTRL-TS Settings subheading was a stale literal

`SetupPage.qml` and its validators explicitly required `CTRL-TS Link`.

Correction: both UI and validation contracts now require `Link`.

### 4. Calibration placeholder and cancellation were incomplete

The touchscreen substituted an em dash for uncaptured values, but the compiled
Montserrat font did not contain that glyph, producing the replacement rectangle.
There was also no touchscreen calibration-cancel protocol path.

More importantly, `.05.06` Limit Calibration was non-transactional: Near/Far and
motor-direction decisions could mutate live state before the Ref step, so a simple
Cancel button would have left partial calibration behind.

Correction: ASCII `-`; retry/ACK-safe `CAL_CANCEL`; Joystick Calibration retains
its staged values; Limit Calibration stages Near/Far/Ref/raw captures and inferred
motor direction and commits all state only at Ref. Cancel stops motion, requires
neutral before re-arm, releases service mode and leaves prior valid calibration
unchanged.

### 5. False red calibration status was caused by destructive W1P snapshot invalidation

`.05.06` invalidated the complete W1P safety snapshot before validating each new
STATUS and also invalidated it on PONG. If a frame was incomplete/corrupt or a
non-authoritative PONG arrived, the next motion tick could briefly see W1P safety
as failed and publish a real red E-stop state. The next valid STATUS restored it,
creating the visible flash.

Correction: STATUS is validate-before-commit; malformed frames are rejected and
rate-limited in the log while the previous complete snapshot remains authoritative
until its normal 0.75 s freshness timeout. PONG no longer clears STATUS authority.
Genuine stale telemetry, E-stop, watchdog, firmware mismatch or Leadshine/RS485
faults still fail red normally.

The source proves this false-transition mechanism. It does not prove what external
packet/event produced the user's approximate 30-second cadence; rejected-frame
logging is retained so future bench evidence identifies that trigger rather than
masking it.

### 6. SRVR background focus left too little CTRL liveness margin

CTRL's peer timeout is 750 ms while the normal SRVR presence traffic was emitted
from Qt-driven work. Background/App-Nap scheduling can delay that UI/event loop and
cause a false CTRL/SRVR disconnect even though the SRVR process is still alive.

Correction: a dedicated background worker sends `SRVR_ALIVE` every 250 ms. It
contains no motion or safety state. Clean shutdown stops the worker first and sends
three serialized `SRVR_OFFLINE` datagrams so explicit offline remains final.

### 7. Random Limit Calibration stops were the correct neutral latch responding to false stops

After any safety interruption SRVR intentionally stops W1P and sets the joystick-
neutral re-arm latch. The operator must return the stick through zero before motion
can resume. That interlock is correct and is retained. The problem was false/transient
safety interruptions, including the W1P snapshot issue and occasional GUI-scheduled
VEL refresh delay.

Correction: remove the false W1P state invalidation and allow the existing W1P UDP
worker to bridge a missed non-zero VEL refresh under a short producer lease. The
normal command cadence remains ~150 ms and W1P's independent 500 ms freshness
watchdog is unchanged.

### 8. Intermediate `.05.07`/`.05.08` native compile failure

GitHub exposed a source error in the new reboot-confirmation code: `newBootId` was
declared in an inner block then referenced later in the same HELLO_RESP handler.
This was not a carrier-size failure.

Correction: `newBootId` and reset reason now live at HELLO_RESP scope. A dedicated
`.05.09` regression locks that declaration placement. The `.05.08` external carrier
experiment is intentionally absent.

## Safety invariants rechecked

- W1P `W1P_VEL_COMMAND_TIMEOUT_MS = 500` unchanged.
- Normal SRVR non-zero VEL keepalive remains 0.15 s.
- AI0 E-stop / AI1 joystick mapping unchanged.
- Predictive stopping, normal hard-limit envelope and service-mode limit bypass
  semantics unchanged.
- Leadshine velocity/Modbus architecture unchanged.
- CTRL-TS RS485 remains single-flight with EVENT ACK/retry and bounded recovery.
- Virtual mode still inhibits physical W1P Servo Enable/non-zero VEL.
- Current Speed display remains magnitude-only; internal/wire velocity remains signed.
