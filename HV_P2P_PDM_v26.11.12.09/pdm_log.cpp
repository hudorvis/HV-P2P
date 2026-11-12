#include "pdm_log.h"

#include <SD_MMC.h>
#include <esp_task_wdt.h>
#include <esp_timer.h>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

namespace {
constexpr char MOUNT[] = "/sdcard";
constexpr char LOG_DIR[] = "/sdcard/pdm_logs";
constexpr char LEGACY_FILE[] = "/sdcard/pdm_log.csv";
constexpr char HEADER[] = "t_ms,utc_ms,v48_1,v48_2,v24,v12\n";
constexpr uint64_t SEGMENT_MS = 15ULL * 60 * 1000;
constexpr uint64_t HOUR_MS = 3600000;
constexpr uint64_t MAX_TIMESTAMP = 9007199254740990ULL;
constexpr unsigned RING_SIZE = 240;
constexpr size_t LINE_BYTES = 128;
constexpr uint64_t MAX_INVALID_BYTES = 64 * 1024;
constexpr uint32_t REMOUNT_MS = 5000;
constexpr uint32_t MAINTENANCE_MS = 60000;
constexpr uint64_t MIN_UTC_MS = 1577836800000ULL;
constexpr uint64_t MAX_UTC_MS = 4102444800000ULL;

struct LegacyInfo {
  uint64_t latest = 0;
  uint64_t rawLatest = 0;
  uint64_t size = 0;
  unsigned scale = 1;
  bool utc = false;
};

portMUX_TYPE stateLock = portMUX_INITIALIZER_UNLOCKED;
StaticSemaphore_t ioMutexStorage;
SemaphoreHandle_t ioMutex = nullptr;

// FatFs requires the writer and readers of a segment to open it separately.
// This lock is only held for bounded SD I/O, never during a socket write.
class LogIoLock {
 public:
  LogIoLock() { xSemaphoreTake(ioMutex, portMAX_DELAY); }
  ~LogIoLock() { xSemaphoreGive(ioMutex); }
  LogIoLock(const LogIoLock&) = delete;
  LogIoLock& operator=(const LogIoLock&) = delete;
};
Sample ring[RING_SIZE];
uint64_t published = 0;
uint64_t timeBase = 0;
uint64_t storedThrough = 0;
uint32_t generation = 0;
uint32_t dropped = 0;
unsigned readers = 0;
bool mounted = false;
bool healthy = false;
bool exclusive = false;
std::atomic<uint8_t> logHours{12};
TaskHandle_t logTaskHandle = nullptr;
std::atomic<bool> pauseRequested{false};
std::atomic<bool> writerPaused{false};

// Only the SD worker writes this index, while no HTTP lease exists.
LegacyInfo legacy;

uint64_t oldestSequence() {
  return published > RING_SIZE ? published - RING_SIZE + 1 : 1;
}

Sample timelineSample(uint64_t seq) {
  Sample sample = ring[(seq - 1) % RING_SIZE];
  sample.t += timeBase;
  return sample;
}

bool decimal(const char* text, uint64_t& value) {
  if (!text || !*text) return false;
  value = 0;
  for (; *text; ++text) {
    if (*text < '0' || *text > '9') return false;
    const unsigned digit = *text - '0';
    if (value > (MAX_TIMESTAMP - digit) / 10) return false;
    value = value * 10 + digit;
  }
  return true;
}

bool parseRecord(char* line, Sample& sample, bool old) {
  const size_t len = strlen(line);
  if (len && line[len - 1] == '\r') line[len - 1] = '\0';
  char* fields[6];
  const unsigned count = old ? 5 : 6;
  for (unsigned i = 0; i < count; ++i) {
    fields[i] = line;
    char* comma = strchr(line, ',');
    if ((i + 1 < count) != (comma != nullptr)) return false;
    if (comma) {
      *comma = '\0';
      line = comma + 1;
    }
  }
  if (!decimal(fields[0], sample.t) || (old && sample.t > UINT32_MAX)) return false;
  sample.utc = 0;
  if (!old && (!decimal(fields[1], sample.utc) ||
      (sample.utc && (sample.utc < MIN_UTC_MS || sample.utc >= MAX_UTC_MS)))) return false;
  for (unsigned i = 0; i < 4; ++i) {
    const char* text = fields[i + count - 4];
    if (!*text && !old) {
      sample.v[i] = NAN;
      continue;
    }
    char* end = nullptr;
    sample.v[i] = strtof(text, &end);
    if (end == text || *end || !isfinite(sample.v[i]) || sample.v[i] < 0 || sample.v[i] > 1000) return false;
  }
  return true;
}

void pathForBucket(uint64_t bucket, char* path, size_t size) {
  snprintf(path, size, "%s/%llu.csv", LOG_DIR, (unsigned long long)bucket);
}

bool bucketFromName(const char* name, uint64_t& bucket) {
  char digits[24];
  const size_t size = strlen(name);
  if (size <= 4 || size >= sizeof digits || strcmp(name + size - 4, ".csv") != 0) return false;
  memcpy(digits, name, size - 4);
  digits[size - 4] = '\0';
  if (digits[0] == '0' && digits[1]) return false;
  return decimal(digits, bucket) && bucket <= MAX_TIMESTAMP / SEGMENT_MS;
}

// Snapshot the file length and read short blocks without leaving a FatFs
// file open while an HTTP client consumes them.
class LogFile {
 public:
  explicit LogFile(const char* name) {
    snprintf(path, sizeof path, "%s", name);
    LogIoLock lock;
    struct stat info;
    if (stat(path, &info) == 0) {
      if (S_ISREG(info.st_mode) && info.st_size >= 0) size = (uint64_t)info.st_size;
      else failed = true;
    } else failed = errno != ENOENT;
  }

  int at(uint64_t index) {
    if (failed || index >= size) return -1;
    if (index < blockStart || index >= blockStart + blockSize) {
      blockStart = index / sizeof block * sizeof block;
      const size_t want = min((uint64_t)sizeof block, size - blockStart);
      LogIoLock lock;
      const int fd = open(path, O_RDONLY);
      ssize_t n = -1;
      if (fd >= 0) {
        if (lseek(fd, (off_t)blockStart, SEEK_SET) >= 0) n = read(fd, block, want);
        if (close(fd) != 0) n = -1;
      }
      if (n != (ssize_t)want) {
        failed = true;
        return -1;
      }
      blockSize = want;
    }
    return (unsigned char)block[index - blockStart];
  }

  bool forward(uint64_t& pos, Sample& sample, bool old, uint64_t end) {
    const uint64_t start = pos;
    while (pos < end && !failed && pos - start < MAX_INVALID_BYTES) {
      char line[LINE_BYTES];
      size_t n = 0;
      bool complete = false;
      while (pos < end && pos - start < MAX_INVALID_BYTES) {
        const int c = at(pos++);
        if (c < 0) break;
        if (c == '\n') { complete = true; break; }
        if (n < sizeof line - 1) line[n] = (char)c;
        if (n < sizeof line) ++n;
      }
      if (complete && n < sizeof line) {
        line[n] = '\0';
        if (parseRecord(line, sample, old)) return true;
      }
    }
    if (pos < end && pos - start >= MAX_INVALID_BYTES) failed = true;
    return false;
  }

  uint64_t size = 0;
  bool failed = false;
 private:
  char path[64];
  char block[1024];
  uint64_t blockStart = 0;
  size_t blockSize = 0;
};

// The reverse cursor is a byte offset at the start of the last returned line.
class ReverseLines {
 public:
  explicit ReverseLines(const char* path, uint64_t beforeOffset = 0) : file(path) {
    pos = beforeOffset ? beforeOffset : file.size;
    if (pos > file.size) { file.failed = true; return; }
    const uint64_t start = pos;
    // A record without its terminating LF was never complete.
    while (pos && file.at(pos - 1) != '\n' && !file.failed && start - pos < MAX_INVALID_BYTES) --pos;
    if (start - pos >= MAX_INVALID_BYTES) file.failed = true;
  }

  bool next(Sample& sample, bool old = false) {
    const uint64_t start = pos;
    while (pos && !file.failed && start - pos < MAX_INVALID_BYTES) {
      --pos;
      char line[LINE_BYTES];
      size_t n = 0;
      while (pos && !file.failed && start - pos < MAX_INVALID_BYTES) {
        const int c = file.at(pos - 1);
        if (c == '\n') break;
        --pos;
        if (n < sizeof line - 1) line[n] = (char)c;
        if (n < sizeof line) ++n;
      }
      if (file.failed || n >= sizeof line || start - pos >= MAX_INVALID_BYTES) continue;
      for (size_t i = 0; i < n / 2; ++i) {
        const char c = line[i];
        line[i] = line[n - 1 - i];
        line[n - 1 - i] = c;
      }
      line[n] = '\0';
      if (parseRecord(line, sample, old)) return true;
    }
    if (pos && start - pos >= MAX_INVALID_BYTES) file.failed = true;
    return false;
  }

  LogFile file;
  uint64_t pos = 0;
};

LegacyInfo inspectLegacy() {
  LegacyInfo result;
  ReverseLines lines(LEGACY_FILE);
  Sample sample;
  if (!lines.next(sample, true)) return result;
  result.size = lines.file.size;
  const uint64_t latest = sample.t;
  uint64_t previous = latest;
  unsigned shortDeltas = 0;
  unsigned deltas = 0;
  for (unsigned i = 0; i < 12 && lines.next(sample, true); ++i) {
    if (sample.t > previous) break;
    const uint64_t delta = previous - sample.t;
    if (delta) {
      ++deltas;
      if (delta <= 5) ++shortDeltas;
    }
    previous = sample.t;
  }
  if (deltas && shortDeltas * 2 > deltas) result.scale = 1000;
  result.rawLatest = latest * result.scale;
  // Reserve room for previous uptime-only sessions. The original CSV is kept.
  result.latest = result.rawLatest + 12 * HOUR_MS;
  result.utc = result.scale == 1000 && result.rawLatest >= MIN_UTC_MS && result.rawLatest < MAX_UTC_MS;
  return result;
}

uint64_t legacyDelta(uint64_t older, uint64_t newer) {
  if (newer >= older) return newer - older;
  // A 32-bit millis rollover is distinguishable close to the wrap boundary.
  if (legacy.scale == 1 && older > UINT32_MAX - 12 * HOUR_MS && newer < 12 * HOUR_MS) {
    return UINT32_MAX + 1ULL - older + newer;
  }
  // The first sample's uptime is known. Time spent unpowered is unavailable.
  return max(1ULL, (unsigned long long)newer);
}

void assignLegacyTime(Sample& sample, uint64_t logical, uint64_t raw) {
  sample.t = logical;
  sample.utc = legacy.utc && raw >= MIN_UTC_MS && raw < MAX_UTC_MS ? raw : 0;
}

class LegacyReverse {
 public:
  explicit LegacyReverse(uint64_t offset = 0, uint64_t timestamp = 0)
      : lines(LEGACY_FILE, offset ? offset : legacy.size),
        previousRaw(legacy.rawLatest), logical(offset ? timestamp : legacy.latest) {
    if (offset) {
      Sample boundary;
      if (lines.file.forward(offset, boundary, true, legacy.size)) previousRaw = boundary.t * legacy.scale;
      else lines.file.failed = true;
    }
  }

  bool next(Sample& sample) {
    if (!lines.next(sample, true)) return false;
    const uint64_t raw = sample.t * legacy.scale;
    const uint64_t delta = legacyDelta(raw, previousRaw);
    if (delta >= logical) return false;
    previousRaw = raw;
    logical -= delta;
    assignLegacyTime(sample, logical, raw);
    return true;
  }

  ReverseLines lines;
  uint64_t previousRaw;
  uint64_t logical;
};

bool newestInBucket(uint64_t bucket, Sample& sample) {
  char path[64];
  pathForBucket(bucket, path, sizeof path);
  ReverseLines lines(path);
  while (lines.next(sample)) {
    if (sample.t / SEGMENT_MS == bucket) return true;
  }
  return false;
}

uint64_t newestOnDisk() {
  uint64_t newest = legacy.latest;
  DIR* dir = opendir(LOG_DIR);
  if (!dir) return newest;
  while (dirent* entry = readdir(dir)) {
    uint64_t bucket;
    Sample sample;
    if (bucketFromName(entry->d_name, bucket) && bucket >= newest / SEGMENT_MS &&
        newestInBucket(bucket, sample) && sample.t > newest) newest = sample.t;
  }
  closedir(dir);
  return newest;
}

bool takeExclusive() {
  portENTER_CRITICAL(&stateLock);
  const bool available = !readers && !exclusive;
  if (available) exclusive = true;
  portEXIT_CRITICAL(&stateLock);
  return available;
}

void endExclusive() {
  portENTER_CRITICAL(&stateLock);
  exclusive = false;
  portEXIT_CRITICAL(&stateLock);
}

bool mountCard(uint64_t lastAttempted) {
  if (!takeExclusive()) return false;
  // Mark the card unavailable before closing the VFS. Existing leases drained
  // before takeExclusive succeeded.
  portENTER_CRITICAL(&stateLock);
  mounted = false;
  healthy = false;
  portEXIT_CRITICAL(&stateLock);
  SD_MMC.end();
  const bool ready = SD_MMC.begin(MOUNT, true, false, BOARD_MAX_SDMMC_FREQ, 8);
  bool logReady = false;
  uint64_t newest = 0;
  if (ready) {
    const LegacyInfo oldLegacy = legacy;
    legacy = inspectLegacy();
    logReady = mkdir(LOG_DIR, 0775) == 0 || errno == EEXIST;
    struct stat directory;
    logReady = logReady && stat(LOG_DIR, &directory) == 0 && S_ISDIR(directory.st_mode);
    if (logReady) newest = newestOnDisk();
    else newest = legacy.latest;
    portENTER_CRITICAL(&stateLock);
    const bool rebase = newest > lastAttempted && newest > timeBase;
    if (!generation || rebase || newest < storedThrough || oldLegacy.size != legacy.size ||
        oldLegacy.latest != legacy.latest) ++generation;
    if (rebase) timeBase = newest;
    storedThrough = newest;
    mounted = true;
    portEXIT_CRITICAL(&stateLock);
  }
  endExclusive();
  Serial.println(ready ? (logReady ? "SD: mounted" : "SD: mounted, log directory unavailable")
                       : "SD: mount failed, retry pending");
  return logReady;
}

bool nextSample(uint64_t& sequence, Sample& sample, uint64_t& durable) {
  portENTER_CRITICAL(&stateLock);
  const uint64_t oldest = oldestSequence();
  if (sequence < oldest) {
    const uint64_t loss = oldest - sequence;
    dropped = loss > UINT32_MAX - dropped ? UINT32_MAX : dropped + (uint32_t)loss;
    sequence = oldest;
  }
  const bool available = sequence <= published;
  if (available) sample = timelineSample(sequence);
  durable = storedThrough;
  portEXIT_CRITICAL(&stateLock);
  return available;
}

void writeStatus(bool ok, uint64_t timestamp = 0) {
  portENTER_CRITICAL(&stateLock);
  healthy = ok;
  if (ok && timestamp > storedThrough) storedThrough = timestamp;
  portEXIT_CRITICAL(&stateLock);
}

void numberText(float value, char* text, size_t size) {
  if (isfinite(value)) snprintf(text, size, "%.3f", (double)value);
  else text[0] = '\0';
}

bool append(const Sample& sample, bool checkTail) {
  const uint64_t bucket = sample.t / SEGMENT_MS;
  char path[64];
  pathForBucket(bucket, path, sizeof path);
  LogIoLock lock;
  const int fd = open(path, O_CREAT | O_RDWR | O_APPEND, 0664);
  if (fd < 0) return false;

  bool ok = true;
  if (checkTail) {
    const off_t size = lseek(fd, 0, SEEK_END);
    if (size < 0) ok = false;
    else if (size == 0) ok = write(fd, HEADER, sizeof HEADER - 1) == sizeof HEADER - 1;
    else {
      char last = 0;
      ok = lseek(fd, -1, SEEK_END) >= 0 && read(fd, &last, 1) == 1;
      // Terminate a torn tail with a marker that cannot parse as a reading.
      if (ok && last != '\n') ok = write(fd, "!\n", 2) == 2;
    }
  }
  if (ok) {
    char voltage[4][18];
    for (unsigned ch = 0; ch < 4; ++ch) numberText(sample.v[ch], voltage[ch], sizeof voltage[ch]);
    char line[LINE_BYTES];
    const int length = snprintf(line, sizeof line, "%llu,%llu,%s,%s,%s,%s\n",
                                (unsigned long long)sample.t, (unsigned long long)sample.utc,
                                voltage[0], voltage[1], voltage[2], voltage[3]);
    ok = length > 0 && length < (int)sizeof line &&
         write(fd, line, length) == length && fsync(fd) == 0;
  }
  const bool closed = close(fd) == 0;
  return ok && closed;
}

bool pruneExpired(uint64_t now) {
  if (!takeExclusive()) return false;
  const uint64_t span = logHours.load() * HOUR_MS;
  const uint64_t expiredBefore = now > span ? now - span : 0;
  const uint64_t wall = utcMs();
  DIR* dir = opendir(LOG_DIR);
  if (dir) {
    while (dirent* entry = readdir(dir)) {
      uint64_t bucket;
      if (!bucketFromName(entry->d_name, bucket) || bucket >= now / SEGMENT_MS) continue;
      bool expired = (bucket + 1) * SEGMENT_MS <= expiredBefore;
      if (!expired && wall && wall > span) {
        Sample tail;
        expired = newestInBucket(bucket, tail) && tail.utc && tail.utc <= wall - span;
      }
      if (expired) {
        char path[64];
        pathForBucket(bucket, path, sizeof path);
        if (unlink(path) != 0) Serial.printf("SD: could not rotate %s\n", path);
      }
    }
    closedir(dir);
  }
  endExclusive();
  return dir != nullptr;
}

void logWorker(void*) {
  const bool watched = esp_task_wdt_add(nullptr) == ESP_OK;
  if (!watched) Serial.println("WDT: SD worker enrollment failed");
  uint64_t sequence = 1;
  uint64_t lastAttempted = 0;
  uint64_t lastBucket = UINT64_MAX;
  uint64_t retryAt = 0;
  uint64_t rotateAt = 0;
  uint8_t lastHours = logHours.load();
  unsigned failures = 0;
  bool ready = false;
  while (true) {
    if (watched) esp_task_wdt_reset();
    if (pauseRequested.load()) {
      writerPaused.store(true);
      ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(50));
      continue;
    }
    writerPaused.store(false);
    const uint64_t now = uptimeMs();
    if (!ready && now >= retryAt) {
      ready = mountCard(lastAttempted);
      retryAt = ready ? uptimeMs() : uptimeMs() + REMOUNT_MS;
      lastBucket = UINT64_MAX;
      rotateAt = 0;
    }
    if (ready && (now >= rotateAt || lastHours != logHours.load())) {
      const uint64_t logicalNow = liveSnapshot().now;
      if (pruneExpired(logicalNow)) {
        rotateAt = now + MAINTENANCE_MS;
        lastHours = logHours.load();
      }
    }
    Sample sample;
    uint64_t durable;
    // Keep accounting for overflow while the card is away.
    const bool available = nextSample(sequence, sample, durable);
    if (ready && available && now >= retryAt) {
      if (sample.t <= durable) {
        ++sequence;
        continue;
      }
      const uint64_t bucket = sample.t / SEGMENT_MS;
      lastAttempted = sample.t;
      if (append(sample, lastBucket != bucket || failures != 0)) {
        ++sequence;
        lastBucket = bucket;
        failures = 0;
        writeStatus(true, sample.t);
        // Give other low-priority tasks a turn during a backlog replay.
        vTaskDelay(1);
        continue;
      }
      writeStatus(false);
      if (!failures) Serial.println("SD: log append failed, retry pending");
      ++failures;
      pruneExpired(liveSnapshot().now);
      if (failures >= 3) {
        ready = false;
        retryAt = uptimeMs() + REMOUNT_MS;
      } else {
        // A fully written row can be visible even when close/flush reports
        // failure. Retry after remount to recover its on-card sequence.
        ready = false;
        retryAt = uptimeMs() + 1000;
      }
    }
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(100));
  }
}

bool visitForwardFile(const char* path, uint64_t pos, uint64_t stopOffset,
                      bool old, uint64_t bucket, uint64_t cutoff, uint64_t end,
                      uint64_t firstTime, SampleVisitor visit, void* context) {
  LogFile file(path);
  const uint64_t stop = stopOffset ? min(file.size, stopOffset) : file.size;
  uint64_t previous = 0;
  uint64_t previousRaw = 0;
  Sample sample;
  while (file.forward(pos, sample, old, stop)) {
    if (old) {
      const uint64_t raw = sample.t * legacy.scale;
      const uint64_t logical = previous ? previous + legacyDelta(previousRaw, raw) : firstTime;
      previousRaw = raw;
      assignLegacyTime(sample, logical, raw);
    } else if (sample.t / SEGMENT_MS != bucket) continue;
    if (sample.t > end) break;
    if (previous && sample.t <= previous) continue;
    previous = sample.t;
    if (sample.t >= cutoff && !visit(sample, context)) return false;
  }
  return !file.failed;
}

bool findLegacyStart(uint64_t cutoff, uint64_t& start, uint64_t& time) {
  LegacyReverse file;
  Sample sample;
  while (file.next(sample) && sample.t >= cutoff) {
    start = file.lines.pos;
    time = sample.t;
  }
  return !file.lines.file.failed;
}
}  // namespace

uint64_t uptimeMs() {
  return (uint64_t)(esp_timer_get_time() / 1000);
}

bool pauseLogForUpdate(uint32_t timeoutMs) {
  if (!logTaskHandle) return true;
  pauseRequested.store(true);
  xTaskNotifyGive(logTaskHandle);
  const uint64_t deadline = uptimeMs() + timeoutMs;
  while (!writerPaused.load() && uptimeMs() < deadline) delay(10);
  if (writerPaused.load()) return true;
  resumeLogAfterUpdate();
  return false;
}

void resumeLogAfterUpdate() {
  pauseRequested.store(false);
  if (logTaskHandle) xTaskNotifyGive(logTaskHandle);
}

uint64_t utcMs() {
  timeval now;
  if (gettimeofday(&now, nullptr) != 0 || now.tv_sec < 0) return 0;
  const uint64_t ms = (uint64_t)now.tv_sec * 1000 + now.tv_usec / 1000;
  return ms >= MIN_UTC_MS && ms < MAX_UTC_MS ? ms : 0;
}

bool startLogWorker(uint8_t hours) {
  ioMutex = xSemaphoreCreateMutexStatic(&ioMutexStorage);
  if (!ioMutex) return false;
  setLogHours(hours);
  return xTaskCreatePinnedToCore(logWorker, "pdm-sd", 6144, nullptr, 1, &logTaskHandle, ARDUINO_RUNNING_CORE) == pdPASS;
}

void setLogHours(uint8_t hours) {
  logHours.store(hours);
}

void publishSample(const Sample& sample) {
  portENTER_CRITICAL(&stateLock);
  ring[published % RING_SIZE] = sample;
  ++published;
  portEXIT_CRITICAL(&stateLock);
  if (logTaskHandle) xTaskNotifyGive(logTaskHandle);
}

LiveSnapshot liveSnapshot(uint64_t after, Sample* recent) {
  LiveSnapshot state{};
  const uint64_t now = uptimeMs();
  portENTER_CRITICAL(&stateLock);
  state.now = timeBase + now;
  state.storedThrough = storedThrough;
  state.generation = generation;
  state.dropped = dropped;
  state.sdMounted = mounted;
  state.logHealthy = healthy;
  state.hasSample = published > 0;
  if (state.hasSample) {
    state.latest = timelineSample(published);
    state.now = max(state.now, state.latest.t);
  }
  if (recent && state.hasSample && after <= state.latest.t) {
    const uint64_t oldest = oldestSequence();
    state.gap = published > RING_SIZE && after < timelineSample(oldest).t;
    if (!state.gap) {
      // Find the first record newer than the client's cursor.
      uint64_t lo = oldest;
      uint64_t hi = published + 1;
      while (lo < hi) {
        const uint64_t mid = lo + (hi - lo) / 2;
        if (timelineSample(mid).t <= after) lo = mid + 1;
        else hi = mid;
      }
      while (lo <= published && state.count < RECENT_PAGE) recent[state.count++] = timelineSample(lo++);
      state.more = lo <= published;
    }
  }
  portEXIT_CRITICAL(&stateLock);
  return state;
}

SdReadLease::SdReadLease() {
  portENTER_CRITICAL(&stateLock);
  held = mounted && !exclusive;
  if (held) ++readers;
  portEXIT_CRITICAL(&stateLock);
}

SdReadLease::~SdReadLease() {
  if (!held) return;
  portENTER_CRITICAL(&stateLock);
  --readers;
  portEXIT_CRITICAL(&stateLock);
}

HistoryPage readHistoryPage(uint64_t end, uint64_t cutoff, uint64_t before,
                            uint64_t legacyOffset, unsigned limit, SampleVisitor visit, void* context) {
  HistoryPage page;
  if (!limit || !before || end < cutoff) return page;
  uint64_t bound = before;
  Sample sample;
  const uint64_t newest = min(end, before - 1);
  if (!legacyOffset && newest >= cutoff && newest > legacy.latest) {
    char path[64];
    for (uint64_t bucket = newest / SEGMENT_MS; ; --bucket) {
      pathForBucket(bucket, path, sizeof path);
      ReverseLines file(path);
      while (file.next(sample)) {
        if (sample.t / SEGMENT_MS != bucket || sample.t > end || sample.t >= bound) continue;
        if (sample.t < cutoff) break;
        if (!visit(sample, context)) { page.ok = false; return page; }
        bound = sample.t;
        if (++page.count == limit) { page.before = bound; return page; }
      }
      if (file.file.failed) { page.ok = false; return page; }
      if (bucket <= cutoff / SEGMENT_MS || bucket <= legacy.latest / SEGMENT_MS) break;
    }
  }
  if (legacy.size && legacy.latest >= cutoff && bound > cutoff) {
    LegacyReverse file(legacyOffset, before);
    while (file.next(sample)) {
      if (sample.t < cutoff) break;
      if (sample.t > end || sample.t >= bound) continue;
      if (!visit(sample, context)) { page.ok = false; return page; }
      bound = sample.t;
      if (++page.count == limit) {
        if (file.lines.pos) {
          page.before = bound;
          page.legacyOffset = file.lines.pos;
        }
        return page;
      }
    }
    if (file.lines.file.failed) page.ok = false;
  }
  return page;
}

bool readHistoryForward(uint64_t end, uint64_t cutoff, SampleVisitor visit, void* context) {
  if (end < cutoff) return true;
  if (legacy.size && legacy.latest >= cutoff) {
    uint64_t start = legacy.size;
    uint64_t firstTime = 0;
    if (!findLegacyStart(cutoff, start, firstTime)) return false;
    if (start < legacy.size && !visitForwardFile(LEGACY_FILE, start, legacy.size, true, 0,
                                                 cutoff, end, firstTime, visit, context)) return false;
  }
  if (end > legacy.latest) {
    char path[64];
    const uint64_t first = max(cutoff, legacy.latest + 1) / SEGMENT_MS;
    for (uint64_t bucket = first; bucket <= end / SEGMENT_MS; ++bucket) {
      pathForBucket(bucket, path, sizeof path);
      if (!visitForwardFile(path, 0, 0, false, bucket, cutoff, end, 0, visit, context)) return false;
    }
  }
  return true;
}
