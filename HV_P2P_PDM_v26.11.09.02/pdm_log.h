#pragma once

#include <Arduino.h>

struct Sample {
  uint64_t t;
  uint64_t utc;
  float v[4];
};

constexpr unsigned RECENT_PAGE = 32;

struct LiveSnapshot {
  Sample latest;
  uint64_t now;
  uint64_t storedThrough;
  uint32_t generation;
  uint32_t dropped;
  unsigned count;
  bool hasSample;
  bool sdMounted;
  bool logHealthy;
  bool gap;
  bool more;
};

struct HistoryPage {
  uint64_t before = 0;
  uint64_t legacyOffset = 0;
  unsigned count = 0;
  bool ok = true;
};

// The lease protects open HTTP files against card unmount and segment deletion.
// FATFS serializes individual file operations. No lease is needed by the writer.
class SdReadLease {
 public:
  SdReadLease();
  ~SdReadLease();
  SdReadLease(const SdReadLease&) = delete;
  SdReadLease& operator=(const SdReadLease&) = delete;
  explicit operator bool() const { return held; }
 private:
  bool held;
};

using SampleVisitor = bool (*)(const Sample&, void*);

uint64_t uptimeMs();
uint64_t utcMs();
bool startLogWorker(uint8_t hours);
bool pauseLogForUpdate(uint32_t timeoutMs);
void resumeLogAfterUpdate();
void setLogHours(uint8_t hours);
void publishSample(const Sample& sample);
LiveSnapshot liveSnapshot(uint64_t after = 0, Sample* recent = nullptr);
HistoryPage readHistoryPage(uint64_t end, uint64_t cutoff, uint64_t before,
                            uint64_t legacyOffset, unsigned limit, SampleVisitor visit, void* context);
bool readHistoryForward(uint64_t end, uint64_t cutoff, SampleVisitor visit, void* context);
