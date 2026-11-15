"use strict";

const prefix = "/srvr-web/";
const statusLine = document.getElementById("status");
const surface = document.getElementById("surface");
const screen = document.getElementById("screen");
const specialKeys = new Set([
    "Backspace", "Delete", "Enter", "Escape", "Tab", "ArrowLeft", "ArrowRight",
    "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown",
]);
const pointActions = new Set(["click", "double", "drag", "wheel"]);
const focusKeys = new Set(["Enter", "Escape", "Tab", "Backtab", "PageUp", "PageDown"]);

let viewer = "";
let frame = 0;
let frameUrl = "";
let frameSeen = 0;
let control = false;
let pollTimer = 0;
let generation = 0;
let gesture = null;
let previousClick = null;
let pendingHover = null;
let inputBusy = false;
let pointBusy = false;
let pointFence = 0;
const inputs = [];

function refreshesView(packet) {
    return pointActions.has(packet.kind) || (packet.kind === "key" && focusKeys.has(packet.key));
}

function status(message) {
    if (statusLine.textContent !== message) statusLine.textContent = message;
}

function resetInput() {
    gesture = null;
    previousClick = null;
    pendingHover = null;
    inputs.length = 0;
    pointBusy = false;
}

function setControl(ready) {
    control = ready;
    screen.classList.toggle("control", ready);
    if (!ready) resetInput();
}

function resetFrame() {
    surface.hidden = true;
    frame = 0;
    screen.removeAttribute("src");
    if (frameUrl) URL.revokeObjectURL(frameUrl);
    frameUrl = "";
}

function forgetViewer() {
    viewer = "";
    setControl(false);
    resetFrame();
    pointFence = 0;
}

function request(path, options = {}) {
    const headers = new Headers(options.headers);
    if (viewer) headers.set("X-SRVR-Viewer", viewer);
    if (options.body) headers.set("Content-Type", "application/json");
    return fetch(prefix + path, {
        ...options, headers, cache: "no-store", credentials: "omit",
        signal: options.keepalive ? undefined : AbortSignal.timeout(1800),
    });
}

async function sync(turn) {
    try {
        if (!viewer) {
            const response = await request("session", { method: "POST", body: "{}" });
            if (!response.ok) throw new Error("SRVR unavailable");
            const connected = await response.json();
            if (turn !== generation) return;
            viewer = connected.viewer;
        }
        const activeViewer = viewer;
        const response = await request("frame", {
            headers: { "X-SRVR-Frame": String(frame), "X-SRVR-Foreground": document.hidden ? "0" : "1" },
        });
        if (turn !== generation || activeViewer !== viewer) return;
        if (response.status === 410) {
            forgetViewer();
            status("Reconnecting to SRVR…");
            return;
        }
        if (!response.ok) throw new Error("SRVR unavailable");

        const waiting = response.headers.get("X-SRVR-Wait");
        const ready = response.headers.get("X-SRVR-Input") === "ready" && !document.hidden;
        if (waiting === "frame") {
            setControl(ready);
        } else if (waiting === "window") {
            resetFrame();
            setControl(false);
            status("Restore the SRVR window on its computer.");
        } else if (response.headers.has("X-SRVR-Frame")) {
            if (response.status === 200) {
                const url = URL.createObjectURL(await response.blob());
                const next = new Image();
                next.src = url;
                try {
                    await next.decode();
                } catch (error) {
                    URL.revokeObjectURL(url);
                    throw error;
                }
                if (turn !== generation || activeViewer !== viewer) {
                    URL.revokeObjectURL(url);
                    return;
                }
                if (frameUrl) URL.revokeObjectURL(frameUrl);
                frameUrl = url;
                screen.src = url;
                frame = Number(response.headers.get("X-SRVR-Frame"));
                frameSeen = performance.now();
            }
            surface.hidden = false;
            setControl(ready);
            status("");
        } else {
            resetFrame();
            setControl(false);
            status("Waiting for the live SRVR window…");
        }
    } catch {
        if (turn === generation) {
            resetFrame();
            setControl(false);
            status("Connecting to SRVR…");
        }
    } finally {
        if (turn === generation) pollTimer = setTimeout(() => sync(turn), viewer ? 165 : 750);
    }
}

window.addEventListener("pagehide", () => {
    generation++;
    clearTimeout(pollTimer);
    if (viewer) request("disconnect", { method: "POST", body: "{}", keepalive: true }).catch(() => {});
    forgetViewer();
});
window.addEventListener("pageshow", (event) => {
    if (event.persisted) void sync(generation);
});
document.addEventListener("visibilitychange", () => {
    if (document.hidden) setControl(false);
});

function canControl() {
    return viewer && control && !document.hidden && frame && performance.now() - frameSeen < 1000;
}

async function sendInput() {
    if (inputBusy || !canControl()) return;
    const packet = inputs.shift() || pendingHover;
    if (!packet) return;
    if (packet === pendingHover) pendingHover = null;
    const activeViewer = viewer;
    inputBusy = true;
    try {
        const response = await request("input", { method: "POST", body: JSON.stringify(packet) });
        if (activeViewer !== viewer) return;
        if (response.status === 410) forgetViewer();
        else if (response.status === 409 && refreshesView(packet)) status("The SRVR view changed. Try again.");
        if (refreshesView(packet)) {
            pointFence = Math.max(pointFence, Number(response.headers.get("X-SRVR-Input-Frame") || 0));
        }
    } catch {
        resetInput();
    } finally {
        inputBusy = false;
        if (refreshesView(packet)) pointBusy = false;
        if (canControl() && (inputs.length || pendingHover)) void sendInput();
    }
}

function enqueue(kind, data, number = frame) {
    if (!canControl()) return;
    const packet = { kind, frame: number, ...data };
    if (kind === "hover") pendingHover = packet;
    else if (inputs.length < 16) {
        if (refreshesView(packet)) {
            if (pointBusy || frame <= pointFence) return;
            pointBusy = true;
        }
        pendingHover = null;
        inputs.push(packet);
    }
    void sendInput();
}

function point(event) {
    const bounds = screen.getBoundingClientRect();
    const limit = (value) => Math.min(1, Math.max(0, value));
    return [limit((event.clientX - bounds.left) / bounds.width),
            limit((event.clientY - bounds.top) / bounds.height)];
}

screen.addEventListener("pointerdown", (event) => {
    if (!canControl() || pointBusy || frame <= pointFence || event.button !== 0 || !event.isPrimary) return;
    screen.focus({ preventScroll: true });
    screen.setPointerCapture(event.pointerId);
    gesture = { id: event.pointerId, frame, points: [point(event)], x: event.clientX, y: event.clientY };
    event.preventDefault();
});

let lastHover = 0;
screen.addEventListener("pointermove", (event) => {
    if (!canControl()) return;
    if (gesture?.id === event.pointerId) {
        const moved = Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) >= 4;
        if (moved && gesture.points.length < 23) gesture.points.push(point(event));
    } else if (performance.now() - lastHover >= 85) {
        lastHover = performance.now();
        enqueue("hover", { points: [point(event)] });
    }
});

screen.addEventListener("pointerup", (event) => {
    if (gesture?.id !== event.pointerId) return;
    const action = gesture;
    const bounds = screen.getBoundingClientRect();
    gesture = null;
    if (!canControl() || event.clientX < bounds.left || event.clientX >= bounds.right ||
        event.clientY < bounds.top || event.clientY >= bounds.bottom) return;
    const last = point(event);
    if (action.points.length > 1) {
        enqueue("drag", { points: [...action.points, last] }, action.frame);
        previousClick = null;
        return;
    }
    const now = performance.now();
    const double = previousClick && now - previousClick.time < 400 &&
        Math.hypot(event.clientX - previousClick.x, event.clientY - previousClick.y) < 4;
    // Only setup file and text widgets need a second click. A normal double
    // tap on a button should never execute a command twice on the same frame.
    enqueue(double ? "double" : "click", { points: [last] }, action.frame);
    previousClick = double ? null : { time: now, x: event.clientX, y: event.clientY };
});
screen.addEventListener("pointercancel", () => { gesture = null; });
screen.addEventListener("lostpointercapture", () => { gesture = null; });
screen.addEventListener("pointerleave", () => enqueue("leave", {}));

screen.addEventListener("wheel", (event) => {
    if (!canControl() || pointBusy || frame <= pointFence || event.ctrlKey) return;
    event.preventDefault();
    const steps = event.deltaMode === 0 ? event.deltaY : 40 * event.deltaY;
    enqueue("wheel", { points: [point(event)], delta: Math.round(Math.max(-480, Math.min(480, -steps))) });
}, { passive: false });

screen.addEventListener("keydown", (event) => {
    if (!canControl()) return;
    const { key } = event;
    if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "a") {
        enqueue("key", { key: "SelectAll", shift: false });
    } else if (event.altKey || event.ctrlKey || event.metaKey || event.isComposing) {
        return;
    } else if (specialKeys.has(key)) {
        enqueue("key", { key: key === "Tab" && event.shiftKey ? "Backtab" : key, shift: event.shiftKey });
    } else if ([...key].length === 1) {
        enqueue("text", { text: key });
    } else {
        return;
    }
    event.preventDefault();
});
screen.addEventListener("paste", (event) => {
    if (!canControl()) return;
    const value = event.clipboardData.getData("text/plain").replace(/[\u0000-\u001f\u007f]/g, "").slice(0, 1024);
    if (value) enqueue("text", { text: value });
    event.preventDefault();
});

void sync(generation);
