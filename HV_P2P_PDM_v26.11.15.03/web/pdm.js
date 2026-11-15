'use strict';

const byId = id => document.getElementById(id);
const channels = [1, 2, 3, 4];
const keys = ['v48_1', 'v48_2', 'v24', 'v12'];
const traceColor = '#26d5ff';
const defaultNames = ['48v Input #1', '48v Input #2', '24v Output', '12v Output'];
const names = [...defaultNames];
const HOUR_MS = 3600000;
const HISTORY_LIMIT = 12 * 3600 * 4 + 512;
const HISTORY_HEADER = 't_ms,utc_ms,v48_1,v48_2,v24,v12';

const logSettings = { hours: 12, interval: 500 };
const calibration = {
  offsets: [0, 0, 0, 0],
  actuals: [null, null, null, null],
  thresholds: [[42, 52], [42, 52], [20, 28], [10.5, 14.5]].map(([low, high]) => ({ low, high, saved: false })),
  version: null
};
const charts = [];
const stats = channels.map(() => ({ min: null, max: null }));
const cards = names.map(name => {
  const card = byId('channel-template').content.firstElementChild.cloneNode(true);
  const title = card.querySelector('.channel-name');
  title.textContent = name;
  byId('channels').append(card);
  return {
    title, settings: card.querySelector('.channel-settings'),
    volts: card.querySelector('.live'), extrema: card.querySelector('.extrema'),
    alarm: card.querySelector('.alarm'), trace: card.querySelector('.trace')
  };
});
let toastTimer;
let plotTimer;
let pollTimer;
let pollBusy = false;
let pollSoon = false;
let reading = null;
let online = null;
let lastRx = 0;
let sampleTime = null;
let historyStatus = 'Waiting for PDM';
let meta = null;
let timelineKey = '';
let cursor = 0;
let historyJob = null;
let historyGap = false;
let clockAttempt = '';
let calibrationRead = null;
let calibrationSaving = false;
let calibrationReady = false;
let namesEpoch = 0;
let nextNamesAt = 0;
let logSaving = false;
let logEpoch = 0;
let historyRetryAt = 0;
let lastLogWarning = false;
let channelDraft = null;
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

}

let history = new Readings();
let demo = null;
let demoAt = 0;
let demoTimer;
const active = () => demo || history;

function anchorFor(j) {
  return { t: j.now_t, epoch: validTime(j.now_utc_ms) ? j.now_utc_ms : Date.now() };
}

function timeText(ms, { date = false, seconds = true, fractions = false } = {}) {
  const time = new Date(ms);
  const pad = value => String(value).padStart(2, '0');
  const month = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][time.getMonth()];
  const prefix = date ? `${pad(time.getDate())} ${month} ` : '';
  const minute = `${prefix}${pad(time.getHours())}:${pad(time.getMinutes())}`;
  const whole = seconds ? `${minute}:${pad(time.getSeconds())}` : minute;
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
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 3000);
}

function hasFreshReading() {
  if (!online || !reading || !meta) return false;
  const age = meta.now_t - reading[0];
  return age >= 0 && age <= Math.max(2000, 2 * logSettings.interval) &&
    performance.now() - lastRx <= Math.max(2500, 2.5 * logSettings.interval);
}

function alarmState(ch, voltage) {
  if (!Number.isFinite(voltage)) return '--';
  const { low, high } = calibration.thresholds[ch];
  if (voltage <= low + 0.000001) return 'LOW';
  if (voltage >= high - 0.000001) return 'HIGH';
  return 'OK';
}

const voltsText = value => Number.isFinite(value) ? value.toFixed(2) + ' V' : '— V';

function paintCards() {
  const fresh = hasFreshReading();
  const current = demo ? (demo.length ? demo.raw.map(values => values[demo.slot(demo.length - 1)]) : null)
    : fresh ? reading.slice(2) : null;
  const status = byId('status-text');
  if (demo) {
    status.textContent = 'Demo';
    status.dataset.state = 'live';
  } else if (fresh) {
    status.textContent = 'Live';
    status.dataset.state = 'live';
  } else if (online) {
    status.textContent = 'Stale data';
    status.dataset.state = 'stale';
  } else {
    status.textContent = online === null ? 'Connecting' : 'Offline';
    status.dataset.state = '';
  }

  const version = meta?.fw_version || '—';
  const update = meta?.fw_update;
  const showUpdate = online && update && !['—', 'Looking for SRVR', 'Waiting for idle'].includes(update);
  byId('firmware').textContent = 'Firmware ' + version + (showUpdate ? '  •  ' + update : '');
  const progress = online ? Math.max(0, Math.min(100, Number(meta?.fw_progress) || 0)) : 0;
  byId('progress').value = progress;
  byId('progress').hidden = !progress;
  byId('progress-text').textContent = progress + '%';
  byId('progress-text').hidden = !progress;
  const latestTime = demo ? demoAt : sampleTime?.when;
  byId('sample-time').textContent = latestTime
    ? 'Last sample ' + timeText(latestTime, { date: true }) + (!demo && sampleTime.estimated ? ' (estimated)' : '')
    : 'Waiting for samples';
  byId('history-status').textContent = (demo ? 'Demo readings' : historyStatus) + '  •  ' +
    logSettings.hours + ' h  •  ' + active().length.toLocaleString() + ' samples' +
    (online ? '  •  PDM ' + (meta.log_healthy ? 'logging' : 'logging unavailable') : '');

  cards.forEach((card, i) => {
    const offset = calibration.offsets[i];
    const voltage = current ? volts(current[i]) + offset : NaN;
    const { min, max } = stats[i];
    card.volts.textContent = 'Live ' + voltsText(voltage);
    card.extrema.textContent = 'Min ' + voltsText(volts(min) + offset) + '  •  Max ' + voltsText(volts(max) + offset);
    const deviceAlarm = !demo && fresh && calibration.version === meta?.calibration_version ? meta.alarms?.[i] : null;
    const alarm = Number.isFinite(voltage) && ['LOW', 'HIGH', 'OK'].includes(deviceAlarm)
      ? deviceAlarm : alarmState(i, voltage);
    card.alarm.hidden = alarm !== 'LOW' && alarm !== 'HIGH';
    card.alarm.textContent = card.alarm.hidden ? '' : alarm;
    card.title.disabled = card.settings.disabled = !online;
  });
}

// Draw the same scale, line and readout as the SRVR PowerTrace component.
class PowerTrace {
  constructor(trace) {
    this.canvas = trace.querySelector('canvas');
    this.marker = trace.querySelector('.trace-marker');
    this.readout = trace.querySelector('.trace-readout');
    this.points = [];
    this.pointer = null;
    this.axis = null;
    const move = event => {
      this.pointer = event.clientX - this.canvas.getBoundingClientRect().left;
      this.showHover();
    };
    this.canvas.addEventListener('pointermove', move);
    this.canvas.addEventListener('pointerdown', move);
    this.canvas.addEventListener('pointerleave', event => {
      if (event.pointerType === 'mouse') this.clearHover();
    });
    this.canvas.addEventListener('pointercancel', () => this.clearHover());
  }

  draw(points) {
    this.points = points;
    this.axis = null;
    const { clientWidth: width, clientHeight: height } = this.canvas;
    const dpr = window.devicePixelRatio || 1;
    const pixelsWide = Math.round(width * dpr), pixelsHigh = Math.round(height * dpr);
    if (this.canvas.width !== pixelsWide) this.canvas.width = pixelsWide;
    if (this.canvas.height !== pixelsHigh) this.canvas.height = pixelsHigh;
    const ctx = this.canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.font = '11px ' + getComputedStyle(this.canvas).fontFamily;
    ctx.fillStyle = '#aeb4b1';
    let low = Infinity, high = -Infinity;
    for (const point of points) {
      if (Number.isFinite(point.y)) {
        low = Math.min(low, point.y);
        high = Math.max(high, point.y);
      }
    }
    if (!Number.isFinite(low)) {
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('No readings', width / 2, height / 2);
      this.showHover();
      return;
    }
    const left = 54, right = width - 4, top = 8, bottom = height - 22;
    if (right <= left || bottom <= top) {
      this.showHover();
      return;
    }
    const padding = Math.max(0.05, (high - low) * 0.08);
    low -= padding;
    high += padding;
    const first = points[0].x, last = points[points.length - 1].x;
    const span = Math.max(1, last - first);
    this.axis = { left, right, top, bottom, low, high, first, span };
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.strokeStyle = '#384146';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; ++i) {
      const fraction = i / 4;
      const y = top + fraction * (bottom - top);
      ctx.fillText((high - fraction * (high - low)).toFixed(2), left - 5, y);
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.stroke();
    }
    const format = { date: span >= 120000, seconds: span < 120000, fractions: span < 10000 };
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText(timeText(first, format), left, height);
    if (first !== last) {
      ctx.textAlign = 'right';
      ctx.fillText(timeText(last, format), right, height);
    }
    ctx.strokeStyle = ctx.fillStyle = traceColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let penDown = false;
    for (const point of points) {
      if (!Number.isFinite(point.y)) {
        penDown = false;
        continue;
      }
      const [x, y] = this.position(point);
      if (penDown) ctx.lineTo(x, y);
      else {
        ctx.fillRect(x - 1, y - 1, 2, 2);
        ctx.moveTo(x, y);
      }
      penDown = true;
    }
    ctx.stroke();
    this.showHover();
  }

  position(point) {
    const { left, right, top, bottom, low, high, first, span } = this.axis;
    return [left + (point.x - first) * (right - left) / span,
      top + (high - point.y) * (bottom - top) / (high - low)];
  }

  nearestSample() {
    if (!this.axis || this.pointer === null) return null;
    const { left, right, first, span } = this.axis;
    if (this.pointer < left || this.pointer > right) return null;
    const stamp = first + (this.pointer - left) * span / (right - left);
    let lo = 0, hi = this.points.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.points[mid].x < stamp) lo = mid + 1;
      else hi = mid;
    }
    const after = this.points[lo];
    if (lo === 0 || stamp === after.x) return Number.isFinite(after.y) ? after : null;
    const before = this.points[lo - 1];
    const nearby = stamp - before.x <= after.x - stamp ? before : after;
    if (!Number.isFinite(nearby.y)) return null;
    if (Number.isFinite(before.y) && Number.isFinite(after.y)) return nearby;
    return Math.abs(nearby.x - stamp) * (right - left) / span <= 5 ? nearby : null;
  }

  clearHover() {
    this.pointer = null;
    this.showHover();
  }

  showHover() {
    const point = this.nearestSample();
    this.marker.hidden = this.readout.hidden = !point;
    if (!point) return;
    const [x, y] = this.position(point);
    this.marker.style.left = (x - 3.5) + 'px';
    this.marker.style.top = (y - 3.5) + 'px';
    this.readout.textContent = voltsText(point.y) + '  •  ' + timeText(point.x, { date: true, fractions: true });
    this.readout.style.left = Math.max(0, Math.min(this.canvas.clientWidth - this.readout.offsetWidth, x + 9)) + 'px';
    this.readout.style.top = (y > this.readout.offsetHeight + 8 ? y - this.readout.offsetHeight - 8 : y + 9) + 'px';
  }
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
  charts.forEach((chart, i) => {
    const pixelBudget = Math.max(120, Math.min(720, Math.round(chart.canvas.clientWidth / 2)));
    chart.draw(plotChannel(buffer, i, pixelBudget));
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

function applyLogConfig(data) {
  if (!Number.isInteger(data.log_hours) || data.log_hours < 1 || data.log_hours > 12 ||
      ![250, 500, 1000, 2000].includes(data.sample_period_ms)) return false;
  const hoursChanged = logSettings.hours !== data.log_hours;
  const intervalChanged = logSettings.interval !== data.sample_period_ms;
  logSettings.hours = data.log_hours;
  logSettings.interval = data.sample_period_ms;
  if (demo && intervalChanged) startDemoTimer();
  return hoursChanged;
}

function applyCalibration(data) {
  if (!Array.isArray(data.offsets) || !Array.isArray(data.actuals) || !Array.isArray(data.thresholds) ||
      data.offsets.length !== 4 || data.actuals.length !== 4 || data.thresholds.length !== 4) return false;
  data.offsets.forEach((offset, i) => {
    calibration.offsets[i] = Number.isFinite(offset) ? offset : 0;
    calibration.actuals[i] = Number.isFinite(data.actuals[i]) ? data.actuals[i] : null;
    const limits = data.thresholds[i];
    if (limits && Number.isFinite(limits.low) && Number.isFinite(limits.high) && limits.low < limits.high) {
      calibration.thresholds[i] = { low: limits.low, high: limits.high, saved: limits.saved === true };
    }
  });
  calibration.version = data.calibration_version;
  calibrationReady = true;
  schedulePlots(true);
  return true;
}

function syncCalibration(migrate = false) {
  if (calibrationRead) return calibrationRead;
  const key = timelineKey;
  calibrationRead = (async () => {
    try {
      const data = await request('/api/calibration');
      if (key !== timelineKey || !applyCalibration(data)) return false;
      if (!migrate) return true;
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
        if (key !== timelineKey) return false;
        applyCalibration(migrated);
      }
      return true;
    } catch (error) {
      if (migrate) showToast(`Channel settings load failed. ${error.message}`);
      return false;
    }
  })().finally(() => { calibrationRead = null; });
  return calibrationRead;
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
    historyStatus = 'SD history unavailable';
    paintCards();
    if (showFailure) showToast('SD history unavailable.');
    return false;
  }
  stopHistory();
  const controller = new AbortController();
  historyJob = controller;
  historyStatus = 'Loading retained history…';
  paintCards();
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
    historyStatus = history.length ? 'Retained history loaded' : 'No retained samples';
    schedulePlots(true);
    return true;
  } catch (error) {
    if (!controller.signal.aborted) {
      historyRetryAt = Date.now() + 5000;
      historyStatus = 'History interrupted • retrying';
      paintCards();
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
      reading = sampleTime = null;
      timelineKey = key;
      cursor = 0;
      historyGap = true;
      historyRetryAt = 0;
      if (firstBoot) {
        calibration.version = null;
        nextNamesAt = 0;
      }
    }
    meta = data;
    const anchor = anchorFor(data);
    online = true;
    lastRx = performance.now();
    if (Date.now() >= nextNamesAt) {
      nextNamesAt = Date.now() + 5000;
      void loadNames();
    }
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
      sampleTime = validTime(reading[1]) ? { when: reading[1], estimated: false }
        : { when: anchor.epoch + (t - anchor.t), estimated: true };
    }
    history.trim(anchor, logSettings.hours);
    if (data.gap || hoursChanged || nowSynced || !wasOnline) historyGap = true;
    if (!data.sd_ok) historyStatus = 'SD history unavailable';
    else if (historyGap && !historyJob && !demo && Date.now() >= historyRetryAt) void loadHistory();
    if (!validTime(data.now_utc_ms) && clockAttempt !== data.boot) {
      clockAttempt = data.boot;
      void request('/api/time', { body: { utc_ms: Date.now() } }).catch(() => {
        setTimeout(() => { if (clockAttempt === data.boot) clockAttempt = ''; }, 10000);
      });
    }
    if (data.calibration_version !== calibration.version && !calibrationSaving) void syncCalibration(!calibrationReady);
    if (!data.log_healthy && data.t > 0) {
      if (!lastLogWarning) showToast('SD logging unavailable. Live readings continue.');
      lastLogWarning = true;
    } else if (data.log_healthy) lastLogWarning = false;
    paintCards();
    if (!demo) schedulePlots();
  } catch {
    online = false;
    paintCards();
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
  paintCards();
  schedulePlots();
}

function setDialogStatus(id, message = '', error = false) {
  const status = byId(id).querySelector('.dialog-status');
  status.textContent = message;
  status.dataset.error = error;
}

function openModal(id) {
  charts.forEach(chart => chart.clearHover());
  setDialogStatus(id);
  byId(id).showModal();
}

function closeModal(id) {
  const modal = byId(id);
  if (modal.dataset.saving !== 'true') modal.close();
}

async function saveModal(id, button, action) {
  const modal = byId(id);
  if (modal.dataset.saving === 'true' || button.disabled) return;
  modal.dataset.saving = 'true';
  button.disabled = true;
  setDialogStatus(id, 'Saving settings…');
  try {
    await action();
    modal.close();
  } catch (error) {
    setDialogStatus(id, error.message, true);
  } finally {
    modal.dataset.saving = 'false';
    button.disabled = false;
  }
}

function applyNames(data) {
  cards.forEach((card, i) => {
    const value = data['ch' + (i + 1)];
    if (typeof value === 'string' && value && !value.includes('\0')) names[i] = value;
    card.title.textContent = names[i];
    card.trace.querySelector('canvas').setAttribute('aria-label', names[i] + ' history');
  });
}

async function loadNames() {
  const epoch = namesEpoch;
  try {
    const data = await request('/api/names');
    if (epoch === namesEpoch) applyNames(data);
    return true;
  } catch {
    return false;
  }
}

let logOpenToken = 0;
async function openLogSettings() {
  const id = 'log-modal';
  const token = ++logOpenToken;
  const button = byId('log-save');
  button.disabled = true;
  byId('monitor-ip').value = meta?.eth_has_ip ? meta.ip : location.hostname;
  byId('log-hours').value = logSettings.hours;
  byId('log-interval').value = logSettings.interval;
  openModal(id);
  setDialogStatus(id, 'Reading settings…');
  try {
    const data = await request('/api/logcfg');
    if (token !== logOpenToken || !byId(id).open) return;
    byId('log-hours').value = data.log_hours;
    byId('log-interval').value = data.sample_period_ms;
    button.disabled = !byId('log-hours').value || !byId('log-interval').value;
    setDialogStatus(id, button.disabled ? 'Invalid log settings' : '', button.disabled);
  } catch (error) {
    if (token === logOpenToken && byId(id).open) setDialogStatus(id, error.message, true);
  }
}

let channelOpenToken = 0;
async function openChannel(channel, focusName = false) {
  const id = 'channel-settings-modal';
  const token = ++channelOpenToken;
  const index = channel - 1;
  const fields = byId(id).querySelectorAll('input');
  const button = byId('channel-settings-save');
  button.disabled = true;
  for (const field of fields) {
    field.value = '';
    field.disabled = true;
  }
  channelDraft = null;
  byId('channel-settings-title').textContent = names[index] + ' Settings';
  openModal(id);
  setDialogStatus(id, 'Reading settings…');
  const [nameOk, voltageOk] = await Promise.all([loadNames(), syncCalibration(!calibrationReady)]);
  if (token !== channelOpenToken || !byId(id).open) return;
  if (!nameOk || !voltageOk) {
    setDialogStatus(id, 'Unable to read channel settings', true);
    return;
  }

  const { low, high } = calibration.thresholds[index];
  channelDraft = { channel, name: names[index], low, high };
  byId('channel-settings-title').textContent = names[index] + ' Settings';
  byId('channel-name').value = channelDraft.name;
  byId('modal-low').value = low;
  byId('modal-high').value = high;
  const live = hasFreshReading() && !demo ? volts(reading[index + 2]) + calibration.offsets[index] : NaN;
  const measured = calibration.actuals[index] ?? live;
  byId('modal-actual').value = Number.isFinite(measured) ? measured.toFixed(2) : '';
  actualEdited = false;
  for (const field of fields) field.disabled = false;
  button.disabled = false;
  setDialogStatus(id);
  if (focusName) {
    byId('channel-name').focus();
    byId('channel-name').select();
  }
}

async function saveChannel() {
  const { channel, name, low: savedLow, high: savedHigh } = channelDraft;
  const nextName = byId('channel-name').value;
  const lowText = byId('modal-low').value, highText = byId('modal-high').value;
  const low = Number(lowText), high = Number(highText);
  if (!lowText || !highText || !Number.isFinite(low) || !Number.isFinite(high) || low >= high ||
      low < -1000 || high > 1000) throw new Error('Enter a low alarm below the high alarm.');
  if (nextName !== name && new TextEncoder().encode(nextName).length > 128) {
    throw new Error('Channel name must fit in 128 UTF-8 bytes.');
  }
  const body = { channel, low, high };
  if (actualEdited) {
    if (demo) throw new Error('Exit Demo Mode before calibrating.');
    const actual = byId('modal-actual').value;
    if (byId('modal-actual').validity.badInput) throw new Error('Enter a valid actual voltage.');
    body.actual = actual === '' ? null : Number(actual);
    if (body.actual !== null && !Number.isFinite(body.actual)) throw new Error('Enter a valid actual voltage.');
  }

  const saveVoltage = actualEdited || low !== savedLow || high !== savedHigh;
  calibrationSaving = saveVoltage;
  let nameSaved = false;
  try {
    if (calibrationRead && saveVoltage) await calibrationRead;
    if (nextName !== name) {
      const result = await request('/api/names', { body: { ['ch' + channel]: nextName } });
      ++namesEpoch;
      applyNames(result);
      channelDraft.name = names[channel - 1];
      nameSaved = true;
    }
    if (saveVoltage && !applyCalibration(await request('/api/calibration', { body }))) {
      throw new Error('Invalid calibration response.');
    }
  } catch (error) {
    if (nameSaved) throw new Error('Channel name saved. ' + error.message);
    throw error;
  } finally {
    calibrationSaving = false;
  }
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
    if (token !== networkOpenToken || !byId(id).open) return;
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
      if (!data.eth_config_ok) setDialogStatus(id, 'Ethernet configuration unavailable. Saved addresses shown.', true);
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
    if (token === networkOpenToken && byId(id).open) setDialogStatus(id, error.message, true);
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
    const input = names[i] || 'CH' + ch;
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
  document.querySelectorAll('dialog').forEach(dialog => {
    dialog.addEventListener('cancel', event => {
      if (dialog.dataset.saving === 'true') event.preventDefault();
    });
  });
  byId('btn-log-settings').addEventListener('click', openLogSettings);
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
      showToast('Log settings applied.');
    } finally {
      logSaving = false;
    }
  }));

  byId('btn-export-csv').addEventListener('click', exportCSV);
  byId('btn-refresh').addEventListener('click', async () => {
    requestPoll();
    void loadNames();
    setDialogStatus('log-modal', 'Loading retained history…');
    const loaded = await loadHistory();
    setDialogStatus('log-modal', loaded ? historyStatus : 'Unable to load retained history', !loaded);
  });
  byId('btn-reset').addEventListener('click', async () => {
    if (demo) {
      demo = new Readings();
      demoAt = 0;
      tickDemo();
      setDialogStatus('log-modal', 'Demo readings reset.');
    } else {
      const loaded = await loadHistory();
      setDialogStatus('log-modal', loaded ? historyStatus : 'Unable to load retained history', !loaded);
      requestPoll();
    }
  });
  const selfTest = byId('btn-self-test');
  selfTest.addEventListener('click', async () => {
    if (selfTest.disabled) return;
    selfTest.disabled = true;
    try {
      const data = await request('/api/self-test');
      setDialogStatus('log-modal', [
        data.adc_ok ? 'ADC OK' : 'ADC unavailable',
        data.log_healthy ? 'SD logging OK' : 'SD logging unavailable',
        data.eth_link ? 'LAN link up' : 'LAN link down',
        'AP routing ' + data.routing_state,
        (data.sample_missed || 0) + ' missed, ' + (data.log_dropped || 0) + ' dropped'
      ].join(' · '));
    } catch (error) {
      setDialogStatus('log-modal', 'Self Test failed. ' + error.message, true);
    } finally {
      selfTest.disabled = false;
    }
  });

  byId('btn-lan-settings').addEventListener('click', () => openNetwork('lan'));
  byId('btn-wifi-settings').addEventListener('click', () => openNetwork('wifi'));
  byId('lan-ip-mode').addEventListener('change', event => {
    const dhcp = event.target.value === 'DHCP';
    if (!dhcp && networkDraft?.ipMode === 'DHCP') {
      for (const key of ['ip', 'subnet', 'gateway']) byId('lan-' + key).value = networkDraft['configured_' + key] || byId('lan-' + key).value;
    }
    disableIpFields('lan', dhcp);
  });
  for (const prefix of ['lan', 'wifi']) {
    const button = byId(prefix + '-save');
    button.addEventListener('click', () => saveModal(prefix + '-modal', button, async () => {
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
      const result = await request('/api/' + (prefix === 'lan' ? 'net' : 'wifi'), { body });
      showToast((prefix === 'lan' ? 'LAN' : 'Wifi') + ' settings saved.' + (result.rebooting ? ' Rebooting device…' : ''));
    }));
  }

  byId('demo-mode-toggle').addEventListener('change', event => {
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
  });

  byId('modal-actual').addEventListener('input', () => { actualEdited = true; });
  cards.forEach((card, i) => {
    card.title.addEventListener('click', () => openChannel(i + 1, true));
    card.settings.addEventListener('click', () => openChannel(i + 1));
  });
  const channelButton = byId('channel-settings-save');
  channelButton.addEventListener('click', () => saveModal('channel-settings-modal', channelButton, saveChannel));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) requestPoll(); });
}

cards.forEach(card => charts.push(new PowerTrace(card.trace)));
applyNames({});
bindControls();
const graphSize = new ResizeObserver(() => schedulePlots());
cards.forEach(card => graphSize.observe(card.trace));
setInterval(paintCards, 1000);
requestPoll();
