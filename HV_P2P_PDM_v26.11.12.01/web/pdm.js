'use strict';

const byId = id => document.getElementById(id);
const channels = [1, 2, 3, 4];
const keys = ['v48_1', 'v48_2', 'v24', 'v12'];
const colours = ['#26d5ff', '#7c5cff', '#ff7ac2', '#e7c94a'];
const names = ['48v Input #1', '48v Input #2', '24v Output', '12v Output'];
const HOUR_MS = 3600000;
const HISTORY_LIMIT = 12 * 3600 * 4 + 512;
const HISTORY_HEADER = 't_ms,utc_ms,v48_1,v48_2,v24,v12';

const logSettings = { hours: 12, interval: 500 };
const calibration = {
  offsets: [0, 0, 0, 0],
  actuals: [null, null, null, null],
  thresholds: channels.map(ch => ({
    low: Number(byId(`ch${ch}-low`).value),
    high: Number(byId(`ch${ch}-high`).value),
    saved: false
  })),
  version: null
};
const charts = [];
const stats = channels.map(() => ({ min: null, max: null }));
const dismissedAlarms = new Set();
let visibleAlarms = [];
let toastTimer;
let plotTimer;
let pollTimer;
let pollBusy = false;
let pollSoon = false;
let reading = null;
let online = false;
let meta = null;
let timelineKey = '';
let cursor = 0;
let historyJob = null;
let historyGap = false;
let clockAttempt = '';
let calibrationBusy = false;
let calibrationReady = false;
let nameBusy = false;
let logSaving = false;
let logEpoch = 0;
let historyRetryAt = 0;
let lastLogWarning = false;
let currentChannel = 0;
let actualEdited = false;
let networkDraft = null;

const volts = value => typeof value === 'number' && Number.isFinite(value)
  ? Math.round(value * 1000) / 1000 : NaN;
const validTime = value => Number.isSafeInteger(value) && value > 0;

class Readings {
  constructor(limit = HISTORY_LIMIT) {
    this.limit = limit;
    this.head = 0;
    this.length = 0;
    this.stamp = new Float64Array(limit);
    this.when = new Float64Array(limit);
    this.estimated = new Uint8Array(limit);
    this.raw = channels.map(() => new Float32Array(limit));
  }

  slot(i) { return (this.head + i) % this.limit; }
  timeAt(i) { return this.when[this.slot(i)]; }
  stampAt(i) { return this.stamp[this.slot(i)]; }
  rawAt(i, ch) { return this.raw[ch][this.slot(i)]; }

  write(slot, row, anchor, adjacent, before) {
    const [t, utc, ...values] = row;
    let inferred = !validTime(utc);
    let time = inferred ? anchor.epoch + (t - anchor.t) : utc;
    if (adjacent !== null) {
      const projected = this.when[adjacent] + (t - this.stamp[adjacent]);
      if ((before && inferred) || (before ? time >= this.when[adjacent] : time <= this.when[adjacent])) {
        time = projected;
        inferred = true;
      }
    }
    this.stamp[slot] = t;
    this.when[slot] = time;
    this.estimated[slot] = inferred ? 1 : 0;
    values.forEach((value, i) => { this.raw[i][slot] = volts(value); });
  }

  add(row, anchor, before = false) {
    const t = row[0];
    if (!validTime(t)) return;
    const adjacent = this.length ? this.slot(before ? 0 : this.length - 1) : null;
    if (adjacent !== null && (before ? t >= this.stamp[adjacent] : t <= this.stamp[adjacent])) return;
    if (this.length === this.limit) {
      if (before) return;
      this.head = this.slot(1);
      --this.length;
    }
    if (before) this.head = (this.head + this.limit - 1) % this.limit;
    const slot = before ? this.head : this.slot(this.length);
    this.write(slot, row, anchor, adjacent, before);
    ++this.length;
  }

  trim(anchor, hours) {
    const window = hours * HOUR_MS;
    while (this.length && (this.stamp[this.head] < anchor.t - window ||
           this.when[this.head] < anchor.epoch - window)) {
      this.head = this.slot(1);
      --this.length;
    }
  }

  after(t, visit) {
    let first = this.length;
    while (first > 0 && this.stampAt(first - 1) > t) --first;
    for (let i = first; i < this.length; ++i) {
      const slot = this.slot(i);
      visit([this.stamp[slot], this.estimated[slot] ? 0 : this.when[slot],
             ...this.raw.map(values => volts(values[slot]))]);
    }
  }

  nearest(time) {
    let low = 0;
    let high = this.length - 1;
    if (high < 0) return -1;
    while (low < high) {
      const mid = (low + high) >>> 1;
      if (this.timeAt(mid) < time) low = mid + 1;
      else high = mid;
    }
    return low > 0 && time - this.timeAt(low - 1) < this.timeAt(low) - time ? low - 1 : low;
  }
}

let history = new Readings();
let demo = null;
let demoAt = 0;
let demoTimer;
const active = () => demo || history;

function anchorFor(j) {
  return { t: j.now_t, epoch: validTime(j.now_utc_ms) ? j.now_utc_ms : Date.now() };
}

function timeText(ms, fractions = false) {
  const time = new Date(ms);
  const pad = value => String(value).padStart(2, '0');
  const whole = `${pad(time.getHours())}:${pad(time.getMinutes())}:${pad(time.getSeconds())}`;
  return fractions ? `${whole}.${String(time.getMilliseconds()).padStart(3, '0')}` : whole;
}

async function request(path, { body, signal, text = false, timeout = 8000 } = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal) {
    if (signal.aborted) abort();
    else signal.addEventListener('abort', abort, { once: true });
  }
  const timer = setTimeout(abort, timeout);
  try {
    const options = { cache: 'no-store', signal: controller.signal };
    if (body !== undefined) {
      options.method = 'POST';
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const error = new Error(payload.error || `HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    if (text) return await response.text();
    const data = await response.json();
    if (body !== undefined && data.ok !== true) throw new Error(data.error || 'Save was not acknowledged');
    return data;
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener('abort', abort);
  }
}

function showToast(message) {
  const toast = byId('toast');
  toast.textContent = message;
  toast.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.style.display = 'none'; }, 3000);
}

function setOnline(value, data = meta) {
  online = value;
  const pill = byId('status-pill');
  pill.classList.toggle('offline', !value);
  byId('status-text').textContent = value ? 'Online' : 'Offline';
  if (data) {
    pill.title = [
      data.adc_ok ? 'ADC ready' : 'ADC unavailable',
      data.log_healthy ? 'SD logging' : 'SD logging unavailable',
      data.routing_state ? `Routing ${data.routing_state}` : '',
      data.log_dropped ? `${data.log_dropped} dropped samples` : ''
    ].filter(Boolean).join(' · ');
  }
}

function alarmState(ch, voltage) {
  if (!Number.isFinite(voltage)) return '--';
  const { low, high } = calibration.thresholds[ch];
  if (voltage <= low + 0.000001) return 'LOW';
  if (voltage >= high - 0.000001) return 'HIGH';
  return 'OK';
}

function alarmBanner(message, state) {
  const banner = byId('alarm-banner');
  byId('alarm-banner-text').textContent = message;
  banner.classList.remove('low', 'high', 'show');
  if (message) banner.classList.add('show', state === 'HIGH' ? 'high' : 'low');
}

function paintCards() {
  const current = demo ? (demo.length ? demo.raw.map(values => values[demo.slot(demo.length - 1)]) : null)
    : online && reading ? reading.slice(2) : null;
  const alarms = [];
  channels.forEach((ch, i) => {
    const voltage = current ? volts(current[i]) + calibration.offsets[i] : NaN;
    byId(`ch${ch}-voltage`).innerHTML =
      `${Number.isFinite(voltage) ? voltage.toFixed(2) : '--.--'}<span class="unit">V</span>`;
    const { min, max } = stats[i];
    byId(`ch${ch}-stats`).textContent = min === null
      ? 'Min: --.-- V · Max: --.-- V'
      : `Min: ${(volts(min) + calibration.offsets[i]).toFixed(2)} V · Max: ${(volts(max) + calibration.offsets[i]).toFixed(2)} V`;

    const deviceAlarm = !demo && online && calibration.version === meta?.calibration_version ? meta.alarms?.[i] : null;
    const state = Number.isFinite(voltage) && ['LOW', 'HIGH', 'OK'].includes(deviceAlarm)
      ? deviceAlarm : alarmState(i, voltage);
    byId(`ch${ch}-dot`).style.color = state === 'OK' ? 'var(--ok)' : state === '--' ? colours[i] : 'var(--err)';
    if (state === 'LOW' || state === 'HIGH') {
      const name = byId(`ch${ch}-name`).value || `Channel ${ch}`;
      alarms.push({ key: `${ch}:${state}`, state, text: `${name}: ${state} Voltage Alarm` });
    }
  });
  const activeKeys = new Set(alarms.map(alarm => alarm.key));
  for (const key of dismissedAlarms) if (!activeKeys.has(key)) dismissedAlarms.delete(key);
  visibleAlarms = alarms.filter(alarm => !dismissedAlarms.has(alarm.key));
  alarmBanner(visibleAlarms.map(alarm => alarm.text).join('  |  '),
              visibleAlarms.some(alarm => alarm.state === 'HIGH') ? 'HIGH' : 'LOW');
}

function makeChart(ch, colour) {
  const canvas = byId(`ch${ch}-chart`);
  const chart = new Chart(canvas, {
    type: 'line',
    data: {
      datasets: [
        { label: 'Voltage', data: [], tension: 0.15, borderWidth: 2, pointRadius: 0, borderColor: colour, backgroundColor: 'rgba(38,213,255,0.12)' },
        { label: 'High alarm', data: [], borderWidth: 1, borderDash: [4,4], pointRadius: 0, borderColor: 'rgba(239,87,87,0.9)' },
        { label: 'Low alarm', data: [], borderWidth: 1, borderDash: [4,4], pointRadius: 0, borderColor: 'rgba(255,179,71,0.9)' }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      parsing: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: {
          type: 'linear',
          grid: { color: 'rgba(255,255,255,0.03)' },
          ticks: {
            color: '#aeb4b1',
            maxRotation: 0,
            callback(value) { return timeText(value, this.max - this.min < 10000); }
          }
        },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#aeb4b1' } }
      }
    }
  });
  const label = byId(`ch${ch}-crosshair`);
  const clear = () => { label.textContent = 'Time: --:--:-- · V: --.-- · State: --'; };
  const show = event => {
    const bounds = canvas.getBoundingClientRect();
    if (!chart.scales.x || !bounds.width) return;
    const x = (event.clientX - bounds.left) * chart.width / bounds.width;
    const buffer = active();
    const i = buffer.nearest(chart.scales.x.getValueForPixel(x));
    if (i < 0) { clear(); return; }
    const slot = buffer.slot(i);
    const value = volts(buffer.raw[ch - 1][slot]) + calibration.offsets[ch - 1];
    const prefix = buffer.estimated[slot] ? '~' : '';
    const stamp = timeText(buffer.when[slot], buffer.when[slot] % 1000 !== 0);
    label.textContent = `Time: ${prefix}${stamp} · V: ${Number.isFinite(value) ? value.toFixed(2) : '--.--'} · State: ${alarmState(ch - 1, value)}`;
  };
  canvas.addEventListener('pointermove', show);
  canvas.addEventListener('pointerdown', show);
  canvas.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse') clear(); });
  return chart;
}

function plotChannel(buffer, index, pixelBudget) {
  const dataset = [];
  const count = buffer.length;
  if (!count) {
    stats[index] = { min: null, max: null };
    return dataset;
  }
  const valueAt = i => buffer.rawAt(i, index);
  const timeAt = i => buffer.timeAt(i);
  const offset = calibration.offsets[index];
  const firstTime = timeAt(0);
  const span = Math.max(1, timeAt(count - 1) - firstTime);
  const decimate = count > pixelBudget * 2;
  const gapLimit = Math.max(6000, 4 * logSettings.interval);
  let min = Infinity;
  let max = -Infinity;
  let bucket = -1;
  let start = -1, low = -1, high = -1, gap = -1, tail = -1, timeGap = 0;
  let priorTime = 0;

  function flush() {
    if (start < 0) return;
    const positions = [...new Set([start, low, high, gap, tail].filter(i => i >= 0))].sort((a,b) => a-b);
    for (const i of positions) {
      const x = timeAt(i);
      if (timeGap && timeGap < x) {
        dataset.push({ x: timeGap, y: null });
        timeGap = 0;
      }
      const value = volts(valueAt(i));
      dataset.push({ x, y: Number.isFinite(value) ? value + offset : null });
    }
  }

  for (let i = 0; i < count; ++i) {
    const time = timeAt(i);
    const value = valueAt(i);
    if (Number.isFinite(value)) {
      if (value < min) min = value;
      if (value > max) max = value;
    }
    const nextBucket = decimate ? Math.min(pixelBudget - 1, Math.floor((time - firstTime) * pixelBudget / span)) : i;
    if (nextBucket !== bucket) {
      flush();
      bucket = nextBucket;
      start = i;
      low = high = gap = -1;
    }
    if (priorTime && time - priorTime > gapLimit) timeGap = priorTime + 1;
    priorTime = time;
    tail = i;
    if (Number.isFinite(value)) {
      if (low < 0 || value < valueAt(low)) low = i;
      if (high < 0 || value > valueAt(high)) high = i;
    } else if (gap < 0) gap = i;
  }
  flush();
  stats[index] = { min: min === Infinity ? null : min, max: max === -Infinity ? null : max };
  return dataset;
}

function renderPlots() {
  const buffer = active();
  channels.forEach((ch, i) => {
    const chart = charts[i];
    const points = plotChannel(buffer, i, Math.max(120, Math.min(720, Math.round((chart?.width || 1000) / 2))));
    if (!chart) return;
    const xAxis = chart.options.scales.x;
    chart.data.datasets[0].data = points;
    if (buffer.length) {
      const first = buffer.timeAt(0);
      const last = buffer.timeAt(buffer.length - 1);
      xAxis.min = first === last ? first - logSettings.interval : first;
      xAxis.max = first === last ? last + logSettings.interval : last;
      chart.data.datasets[1].data = [{ x: xAxis.min, y: calibration.thresholds[i].high }, { x: xAxis.max, y: calibration.thresholds[i].high }];
      chart.data.datasets[2].data = [{ x: xAxis.min, y: calibration.thresholds[i].low }, { x: xAxis.max, y: calibration.thresholds[i].low }];
    } else {
      delete xAxis.min;
      delete xAxis.max;
      chart.data.datasets[1].data = [];
      chart.data.datasets[2].data = [];
    }
    chart.update('none');
  });
  paintCards();
}

function schedulePlots(force = false) {
  if (force) {
    clearTimeout(plotTimer);
    plotTimer = undefined;
    renderPlots();
  } else if (plotTimer === undefined) {
    plotTimer = setTimeout(() => {
      plotTimer = undefined;
      renderPlots();
    }, active().length > 1500 ? 1000 : 0);
  }
}

function rateText(ms) { return `${ms / 1000}s`; }

function applyLogConfig(data) {
  if (!Number.isInteger(data.log_hours) || data.log_hours < 1 || data.log_hours > 12 ||
      ![250, 500, 1000, 2000].includes(data.sample_period_ms)) return false;
  const hoursChanged = logSettings.hours !== data.log_hours;
  const intervalChanged = logSettings.interval !== data.sample_period_ms;
  logSettings.hours = data.log_hours;
  logSettings.interval = data.sample_period_ms;
  if (demo && intervalChanged) startDemoTimer();
  channels.forEach(ch => { byId(`ch${ch}-sample-rate`).textContent = `Sample: ${rateText(logSettings.interval)}`; });
  return hoursChanged;
}

function applyCalibration(data) {
  if (!Array.isArray(data.offsets) || !Array.isArray(data.actuals) || !Array.isArray(data.thresholds) ||
      data.offsets.length !== 4 || data.actuals.length !== 4 || data.thresholds.length !== 4) return;
  data.offsets.forEach((offset, i) => {
    calibration.offsets[i] = Number.isFinite(offset) ? offset : 0;
    calibration.actuals[i] = Number.isFinite(data.actuals[i]) ? data.actuals[i] : null;
    const limits = data.thresholds[i];
    if (limits && Number.isFinite(limits.low) && Number.isFinite(limits.high) && limits.low < limits.high) {
      calibration.thresholds[i] = { low: limits.low, high: limits.high, saved: limits.saved === true };
    }
    const ch = i + 1;
    byId(`ch${ch}-offset`).value = calibration.offsets[i];
    byId(`ch${ch}-actual`).value = calibration.actuals[i] ?? '';
    byId(`ch${ch}-low`).value = calibration.thresholds[i].low;
    byId(`ch${ch}-high`).value = calibration.thresholds[i].high;
  });
  calibration.version = data.calibration_version;
  calibrationReady = true;
  schedulePlots(true);
}

async function syncCalibration(migrate = false) {
  if (calibrationBusy) return;
  calibrationBusy = true;
  const key = timelineKey;
  try {
    const data = await request('/api/calibration');
    if (key !== timelineKey) return;
    applyCalibration(data);
    if (!migrate || !calibrationReady) return;
    for (const ch of channels) {
      if (calibration.thresholds[ch - 1].saved) continue;
      let low, high;
      try {
        low = localStorage.getItem(`hv_pdm_ch${ch}_low`);
        high = localStorage.getItem(`hv_pdm_ch${ch}_high`);
      } catch {
        break;
      }
      if (low === null || high === null || !low.trim() || !high.trim() ||
          !Number.isFinite(Number(low)) || !Number.isFinite(Number(high)) || Number(low) >= Number(high)) continue;
      const migrated = await request('/api/calibration', {
        body: { channel: ch, low: Number(low), high: Number(high), migrate: true }
      });
      if (key !== timelineKey) return;
      applyCalibration(migrated);
    }
  } catch (error) {
    if (migrate) showToast(`Channel settings load failed. ${error.message}`);
  } finally {
    calibrationBusy = false;
  }
}

function parseHistoryPage(text, before, buffer, anchor) {
  const lines = text.trimEnd().split('\n');
  if (lines.shift() !== HISTORY_HEADER) throw new Error('Invalid history header');
  const end = /^#end,(\d+),(\d+)$/.exec(lines.pop() || '');
  if (!end) throw new Error('Incomplete history page');
  const next = Number(end[1]);
  const offset = Number(end[2]);
  if (!Number.isSafeInteger(next) || !Number.isSafeInteger(offset) || next >= before || lines.length > 1536) {
    throw new Error('Invalid history cursor');
  }
  let previous = before;
  for (const line of lines) {
    const values = line.split(',');
    if (values.length !== 6) throw new Error('Invalid history row');
    const t = Number(values[0]);
    const utc = Number(values[1]);
    const rails = values.slice(2).map(value => value === '' ? NaN : Number(value));
    if (!validTime(t) || t >= previous || (!validTime(utc) && utc !== 0)) throw new Error('Out-of-order history row');
    if (values.slice(2).some((value, i) => value !== '' && !Number.isFinite(rails[i]))) throw new Error('Invalid historical voltage');
    buffer.add([t, utc, ...rails], anchor, true);
    previous = t;
  }
  if (next && (lines.length === 0 || next !== previous)) throw new Error('History page did not advance');
  return { next, offset };
}

function stopHistory() {
  if (historyJob) historyJob.abort();
  historyJob = null;
}

async function loadHistory(showFailure = false) {
  if (!meta || !meta.sd_ok) {
    if (showFailure) showToast('SD history unavailable.');
    return false;
  }
  stopHistory();
  const controller = new AbortController();
  historyJob = controller;
  historyRetryAt = 0;
  const { now_t: end, stored_through: durable, generation } = meta;
  const hours = logSettings.hours;
  const anchor = anchorFor(meta);
  const staged = new Readings();
  let before = durable + 1;
  let offset = 0;
  let pages = 0;
  try {
    do {
      if (++pages > Math.ceil(HISTORY_LIMIT / 1536) + 3) throw new Error('History limit exceeded');
      const query = new URLSearchParams({ format: 'csv', hours, end, before, offset, generation });
      let text;
      for (let attempt = 0; ; ++attempt) {
        try {
          text = await request(`/api/history?${query}`, { text: true, signal: controller.signal, timeout: 23000 });
          break;
        } catch (error) {
          if (error.status !== 503 || attempt === 2 || controller.signal.aborted) throw error;
          await new Promise(resolve => setTimeout(resolve, 300));
        }
      }
      const page = parseHistoryPage(text, before, staged, anchor);
      before = page.next;
      offset = page.offset;
    } while (before && !controller.signal.aborted);
    if (historyJob !== controller || controller.signal.aborted) return false;
    const latestAnchor = anchorFor(meta);
    history.after(durable, row => staged.add(row, latestAnchor));
    staged.trim(latestAnchor, hours);
    history = staged;
    historyGap = false;
    schedulePlots(true);
    return true;
  } catch (error) {
    if (!controller.signal.aborted) {
      historyRetryAt = Date.now() + 5000;
      if (showFailure) showToast(`History load failed. ${error.message}`);
    }
    return false;
  } finally {
    if (historyJob === controller) historyJob = null;
  }
}

function requestPoll() {
  if (pollBusy) {
    pollSoon = true;
    return;
  }
  clearTimeout(pollTimer);
  pollTimer = setTimeout(poll, 0);
}

async function poll() {
  if (pollBusy) return;
  pollBusy = true;
  const start = performance.now();
  const currentLogEpoch = logEpoch;
  let more = false;
  try {
    const data = await request(`/api/voltages?after=${cursor}`, { timeout: 6500 });
    if (!data || typeof data.boot !== 'string' || !Number.isSafeInteger(data.now_t) ||
        !Number.isSafeInteger(data.stored_through)) throw new Error('Invalid device sample');
    const key = `${data.boot}:${data.generation}`;
    const changed = timelineKey !== key;
    const wasOnline = online;
    const firstBoot = !timelineKey || meta.boot !== data.boot;
    const nowSynced = !changed && !validTime(meta.now_utc_ms) && validTime(data.now_utc_ms);
    const hoursChanged = !logSaving && currentLogEpoch === logEpoch && applyLogConfig(data);
    if (changed) {
      stopHistory();
      history = new Readings();
      timelineKey = key;
      cursor = 0;
      historyGap = true;
      historyRetryAt = 0;
      if (firstBoot) calibration.version = null;
    }
    meta = data;
    const anchor = anchorFor(data);
    setOnline(true, data);
    const t = data.t;
    if (validTime(t)) {
      reading = [t, data.utc_ms, ...keys.map(key => volts(data[key]))];
      if (changed || data.gap || !Array.isArray(data.recent)) {
        history.add(reading, anchor);
        cursor = t;
      } else {
        for (const row of data.recent) {
          if (!Array.isArray(row) || row.length !== 6 || !validTime(row[0]) || row[0] <= cursor) continue;
          history.add(row, anchor);
          cursor = row[0];
        }
        more = data.more === true;
      }
      if (!demo) byId('last-update-time').textContent = timeText(validTime(reading[1]) ? reading[1] : anchor.epoch + (t - anchor.t));
    }
    history.trim(anchor, logSettings.hours);
    if (data.gap || hoursChanged || nowSynced || !wasOnline) historyGap = true;
    if (historyGap && !historyJob && !demo && data.sd_ok && Date.now() >= historyRetryAt) void loadHistory();
    if (!validTime(data.now_utc_ms) && clockAttempt !== data.boot) {
      clockAttempt = data.boot;
      void request('/api/time', { body: { utc_ms: Date.now() } }).catch(() => {
        setTimeout(() => { if (clockAttempt === data.boot) clockAttempt = ''; }, 10000);
      });
    }
    if (data.calibration_version !== calibration.version && !calibrationBusy) void syncCalibration(!calibrationReady);
    if (!data.log_healthy && data.t > 0) {
      if (!lastLogWarning) showToast('SD logging unavailable. Live readings continue.');
      lastLogWarning = true;
    } else if (data.log_healthy) lastLogWarning = false;
    if (!demo) {
      paintCards();
      schedulePlots();
    }
  } catch {
    setOnline(false);
    if (!demo) paintCards();
  } finally {
    pollBusy = false;
    const delay = more || pollSoon ? 0 : Math.max(0, logSettings.interval - (performance.now() - start));
    pollSoon = false;
    clearTimeout(pollTimer);
    pollTimer = setTimeout(poll, delay);
  }
}

function startDemoTimer() {
  clearInterval(demoTimer);
  demoTimer = setInterval(tickDemo, logSettings.interval);
}

function tickDemo() {
  if (!demo) return;
  const now = Math.max(Date.now(), demoAt + 1);
  demoAt = now;
  const noise = range => (Math.random() - 0.5) * range;
  const anchor = { t: now, epoch: now };
  demo.add([now, now, 48.5 + noise(1), 48.9 + noise(1), 24.2 + noise(0.4), 12.4 + noise(0.25)], anchor);
  demo.trim(anchor, logSettings.hours);
  byId('last-update-time').textContent = timeText(now);
  paintCards();
  schedulePlots();
}

function openModal(id) { byId(id).classList.add('open'); }

function closeModal(id) {
  const modal = byId(id);
  if (modal.dataset.saving !== 'true') modal.classList.remove('open');
}

async function saveModal(id, button, action) {
  const modal = byId(id);
  if (modal.dataset.saving === 'true' || button.disabled) return;
  modal.dataset.saving = 'true';
  button.disabled = true;
  try {
    await action();
    modal.classList.remove('open');
  } catch (error) {
    showToast(error.message);
  } finally {
    modal.dataset.saving = 'false';
    button.disabled = false;
  }
}

async function loadNames() {
  try {
    const data = await request('/api/names');
    channels.forEach(ch => {
      const input = byId(`ch${ch}-name`);
      if (document.activeElement !== input && input.dataset.pending !== 'true' && typeof data[`ch${ch}`] === 'string') {
        input.value = data[`ch${ch}`];
        input.dataset.saved = input.value;
      }
    });
  } catch {
    // Defaults and local unsaved edits stay visible if the device is unreachable.
  }
}

function bindName(ch) {
  const input = byId(`ch${ch}-name`);
  input.dataset.saved = input.value;
  const save = async () => {
    const key = `ch${ch}`;
    const value = input.value;
    if (value === input.dataset.saved || input.dataset.pending === 'true') return;
    input.dataset.pending = 'true';
    let again = false;
    try {
      const data = await request('/api/names', { body: { [key]: value } });
      const saved = typeof data[key] === 'string' ? data[key] : value || names[ch - 1];
      input.dataset.saved = saved;
      again = input.value !== value && document.activeElement !== input;
      if (input.value === value) input.value = saved;
      showToast('Channel name saved.');
      paintCards();
    } catch (error) {
      showToast(`Channel name save failed. ${error.message}`);
    } finally {
      input.dataset.pending = 'false';
      if (again) void save();
    }
  };
  input.addEventListener('change', save);
  input.addEventListener('blur', save);
  input.addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.isComposing) return;
    event.preventDefault();
    input.blur();
  });
}

function disableIpFields(prefix, disabled) {
  for (const field of ['ip', 'subnet', 'gateway']) {
    const input = byId(`${prefix}-${field}`);
    input.disabled = disabled;
    input.style.opacity = disabled ? 0.5 : 1;
  }
}

let networkOpenToken = 0;
async function openNetwork(prefix) {
  const token = ++networkOpenToken;
  const id = `${prefix}-modal`;
  const button = byId(`${prefix}-save`);
  const fields = byId(id).querySelectorAll('input,select');
  networkDraft = null;
  fields.forEach(el => { el.disabled = true; });
  button.disabled = true;
  openModal(id);
  try {
    const data = await request(`/api/${prefix === 'lan' ? 'net' : 'wifi'}`);
    if (token !== networkOpenToken || !byId(id).classList.contains('open')) return;
    networkDraft = data;
    if (prefix === 'lan') {
      const mode = data.ipMode === 'DHCP' || (data.ipMode === 'Unknown' && data.configured_ipMode === 'DHCP') ? 'DHCP' : 'Static';
      byId('lan-ip-mode').disabled = false;
      byId('lan-ip-mode').value = mode;
      for (const field of ['ip', 'subnet', 'gateway']) {
        const actual = data[field];
        byId(`lan-${field}`).value = mode === 'Static' && (!data.eth_config_ok || actual === '0.0.0.0')
          ? data[`configured_${field}`] || actual : actual;
      }
      disableIpFields('lan', mode === 'DHCP');
      if (!data.eth_config_ok) showToast('Ethernet configuration unavailable. Saved addresses shown.');
    } else {
      byId('wifi-mode').value = 'AP';
      byId('wifi-ip-mode').value = 'Static';
      byId('wifi-ssid').value = data.ap_ssid ?? '';
      byId('wifi-password').value = data.ap_pass ?? '';
      byId('wifi-ssid').disabled = false;
      byId('wifi-password').disabled = false;
      for (const field of ['ip', 'subnet', 'gateway']) byId(`wifi-${field}`).value = data[`ap_${field}`] ?? '';
      disableIpFields('wifi', false);
    }
    button.disabled = false;
  } catch (error) {
    if (token === networkOpenToken && byId(id).classList.contains('open')) showToast(`Settings load failed. ${error.message}`);
  }
}

function readNetworkFields(prefix) {
  const result = { ipMode: byId(`${prefix}-ip-mode`).value };
  for (const key of ['ip', 'subnet', 'gateway']) result[key] = byId(`${prefix}-${key}`).value.trim();
  return result;
}

function exportCSV() {
  if (historyJob && !demo) { showToast('History is loading. Export is available when it finishes.'); return; }
  const buffer = active();
  const parts = ['timestamp,channel,name,voltage\n'];
  channels.forEach((ch, i) => {
    const input = byId(`ch${ch}-name`).value || `CH${ch}`;
    const safeName = (/^[\s]*[=+@-]|^[\t\r\n]/.test(input) ? "'" + input : input).replace(/"/g, '""');
    const offset = calibration.offsets[i];
    let rows = [];
    for (let j = 0; j < buffer.length; ++j) {
      const t = new Date(buffer.timeAt(j)).toISOString();
      const v = volts(buffer.rawAt(j, i)) + offset;
      rows.push(`${t},${ch},"${safeName}",${Number.isFinite(v) ? v.toFixed(3) : ''}\n`);
      if (rows.length === 1024) {
        parts.push(rows.join(''));
        rows = [];
      }
    }
    if (rows.length) parts.push(rows.join(''));
  });
  const url = URL.createObjectURL(new Blob(parts, { type: 'text/csv;charset=utf-8;' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `hv_p2p_pdm_log_${new Date().toISOString().replace(/[:.]/g, '-')}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  showToast('Exported CSV log.');
}

function bindControls() {
  document.querySelectorAll('[data-close-modal]').forEach(button => {
    button.addEventListener('click', () => closeModal(button.dataset.closeModal));
  });
  byId('btn-log-settings').addEventListener('click', () => {
    byId('log-hours').value = logSettings.hours;
    byId('log-interval').value = logSettings.interval;
    openModal('log-modal');
  });
  const logButton = byId('log-save');
  logButton.addEventListener('click', () => saveModal('log-modal', logButton, async () => {
    logSaving = true;
    try {
      const body = { log_hours: Number(byId('log-hours').value), sample_period_ms: Number(byId('log-interval').value) };
      const data = await request('/api/logcfg', { body });
      ++logEpoch;
      applyLogConfig(data);
      if (meta) history.trim(anchorFor(meta), logSettings.hours);
      schedulePlots(true);
      requestPoll();
      void loadHistory(true);
      showToast(`Log Settings applied. ${logSettings.hours}h @ ${rateText(logSettings.interval)}`);
    } finally {
      logSaving = false;
    }
  }));

  byId('btn-export-csv').addEventListener('click', exportCSV);
  byId('btn-refresh').addEventListener('click', async () => {
    requestPoll();
    void loadNames();
    if (await loadHistory(true)) showToast(`Reloaded ${logSettings.hours} hour history.`);
  });
  byId('btn-reset').addEventListener('click', async () => {
    dismissedAlarms.clear();
    if (demo) {
      demo = new Readings();
      demoAt = 0;
      tickDemo();
    } else {
      const reset = await loadHistory(true);
      if (reset) showToast(`Reloaded ${logSettings.hours} hour history.`);
      requestPoll();
    }
  });
  const selfTest = byId('btn-self-test');
  selfTest.addEventListener('click', async () => {
    if (selfTest.disabled) return;
    selfTest.disabled = true;
    try {
      const data = await request('/api/self-test');
      showToast([
        data.adc_ok ? 'ADC OK' : 'ADC unavailable',
        data.log_healthy ? 'SD logging OK' : 'SD logging unavailable',
        data.eth_link ? 'LAN link up' : 'LAN link down',
        `AP routing ${data.routing_state}`,
        `${data.sample_missed || 0} missed, ${data.log_dropped || 0} dropped`
      ].join(' · '));
    } catch (error) {
      showToast(`Self Test failed. ${error.message}`);
    } finally {
      selfTest.disabled = false;
    }
  });

  byId('btn-lan-settings').addEventListener('click', () => openNetwork('lan'));
  byId('btn-wifi-settings').addEventListener('click', () => openNetwork('wifi'));
  byId('lan-ip-mode').addEventListener('change', event => {
    const dhcp = event.target.value === 'DHCP';
    if (!dhcp && networkDraft?.ipMode === 'DHCP') {
      for (const key of ['ip', 'subnet', 'gateway']) byId(`lan-${key}`).value = networkDraft[`configured_${key}`] || byId(`lan-${key}`).value;
    }
    disableIpFields('lan', dhcp);
  });
  for (const prefix of ['lan', 'wifi']) {
    const button = byId(`${prefix}-save`);
    button.addEventListener('click', () => saveModal(`${prefix}-modal`, button, async () => {
      const body = readNetworkFields(prefix);
      if (prefix === 'wifi') {
        body.enabled = true;
        body.bridge = networkDraft?.bridge_enabled ?? true;
        body.hidden = networkDraft?.ap_hidden ?? false;
        body.ssid = byId('wifi-ssid').value;
        body.pass = byId('wifi-password').value;
        if (networkDraft && networkDraft.ap_gateway === networkDraft.ap_ip &&
            body.gateway === networkDraft.ap_gateway) body.gateway = body.ip;
      }
      const result = await request(`/api/${prefix === 'lan' ? 'net' : 'wifi'}`, { body });
      showToast(`${prefix === 'lan' ? 'LAN' : 'WIFI'} settings saved.${result.rebooting ? ' Rebooting device…' : ''}`);
    }));
  }

  const banner = byId('alarm-banner');
  const dismiss = () => {
    visibleAlarms.forEach(alarm => dismissedAlarms.add(alarm.key));
    alarmBanner('', '');
  };
  banner.addEventListener('click', dismiss);
  banner.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      dismiss();
    }
  });

  byId('demo-mode-toggle').addEventListener('change', event => {
    dismissedAlarms.clear();
    if (event.target.checked) {
      demo = new Readings();
      demoAt = 0;
      tickDemo();
      startDemoTimer();
    } else {
      clearInterval(demoTimer);
      demo = null;
      if (historyGap && !historyJob) void loadHistory();
      requestPoll();
    }
    schedulePlots(true);
    showToast(event.target.checked ? 'Demo Mode ON' : 'Demo Mode OFF');
  });

  const actual = byId('modal-actual');
  actual.addEventListener('input', () => { actualEdited = true; });
  document.querySelectorAll('[data-channel-settings]').forEach(button => {
    button.addEventListener('click', () => {
      currentChannel = Number(button.dataset.channelSettings);
      const index = currentChannel - 1;
      const limits = calibration.thresholds[index];
      const fallback = reading && online && !demo ? volts(reading[index + 2]) + calibration.offsets[index] : NaN;
      const measured = calibration.actuals[index] ?? fallback;
      byId('channel-settings-title').textContent = `Channel ${currentChannel} Settings`;
      byId('modal-low').value = limits.low;
      byId('modal-high').value = limits.high;
      actual.value = Number.isFinite(measured) ? measured.toFixed(2) : '';
      actualEdited = false;
      openModal('channel-settings-modal');
    });
  });
  const channelButton = byId('channel-settings-save');
  channelButton.addEventListener('click', () => saveModal('channel-settings-modal', channelButton, async () => {
    if (calibrationBusy) throw new Error('Channel settings are loading. Try again.');
    const lowField = byId('modal-low').value;
    const highField = byId('modal-high').value;
    const low = Number(lowField);
    const high = Number(highField);
    if (!lowField || !highField || !Number.isFinite(low) || !Number.isFinite(high) || low >= high) {
      throw new Error('Enter a low alarm below the high alarm.');
    }
    const body = { channel: currentChannel, low, high };
    if (actualEdited) {
      if (demo) throw new Error('Exit Demo Mode before calibrating.');
      body.actual = actual.value === '' ? null : Number(actual.value);
    }
    calibrationBusy = true;
    try {
      applyCalibration(await request('/api/calibration', { body }));
      showToast(`Updated Channel ${currentChannel} settings.`);
    } finally {
      calibrationBusy = false;
    }
  }));
  channels.forEach(bindName);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) requestPoll(); });
}

bindControls();
if (typeof Chart === 'function') {
  channels.forEach((ch, i) => {
    try { charts[i] = makeChart(ch, colours[i]); }
    catch (error) { console.warn('Chart initialization failed', error); }
  });
} else showToast('Chart asset unavailable. Voltage and settings controls remain available.');
applyLogConfig({ log_hours: 12, sample_period_ms: 500 });
void loadNames();
requestPoll();
