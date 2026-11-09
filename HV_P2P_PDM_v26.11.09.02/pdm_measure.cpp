#include "pdm_measure.h"
#include "pdm_log.h"

#include <Wire.h>
#include <atomic>
#include <cmath>
#include <esp_task_wdt.h>

namespace {
constexpr int I2C_SDA = 13;
constexpr int I2C_SCL = 16;
constexpr uint8_t ADS_ADDRESS = 0x48;
constexpr uint8_t ADS_CONVERSION = 0;
constexpr uint8_t ADS_CONFIG = 1;
constexpr uint16_t ADS_START = 0x8000;
constexpr uint16_t ADS_SINGLE = 0x0100;
constexpr uint16_t ADS_RATE_475 = 0x00C0;
constexpr uint16_t ADS_COMPARATOR_OFF = 0x0003;
constexpr float ADC_LSB = 6.144f / 32768.0f;
constexpr float INPUT_SCALE[4] = {
    (330000.0f + 27000.0f) / 27000.0f,
    (330000.0f + 27000.0f) / 27000.0f,
    (68000.0f + 10000.0f) / 10000.0f,
    (33000.0f + 10000.0f) / 10000.0f,
};
constexpr unsigned AVERAGE_COUNT = 8;
constexpr uint64_t CONVERSION_TIMEOUT_MS = 12;
std::atomic<uint32_t> period{500};
std::atomic<uint32_t> missed{0};
TaskHandle_t samplerHandle = nullptr;

bool readRegister(uint8_t reg, uint16_t& value) {
  Wire.beginTransmission(ADS_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(ADS_ADDRESS, (size_t)2) != 2) return false;
  const int high = Wire.read();
  const int low = Wire.read();
  if (high < 0 || low < 0) return false;
  value = ((uint16_t)high << 8) | (uint16_t)low;
  return true;
}

bool readConversion(unsigned ch, int16_t& result) {
  // Single-ended MUX 100..111, PGA 000 (±6.144 V), single shot, 475 SPS.
  const uint16_t mux = (uint16_t)((4 + ch) << 12);
  const uint16_t config = ADS_START | mux | ADS_SINGLE | ADS_RATE_475 | ADS_COMPARATOR_OFF;
  Wire.beginTransmission(ADS_ADDRESS);
  Wire.write(ADS_CONFIG);
  Wire.write((uint8_t)(config >> 8));
  Wire.write((uint8_t)config);
  if (Wire.endTransmission() != 0) return false;

  const uint64_t deadline = uptimeMs() + CONVERSION_TIMEOUT_MS;
  // Datasheet nominal conversion time is ~2.1 ms at 475 SPS.
  vTaskDelay(pdMS_TO_TICKS(2));
  do {
    uint16_t status;
    if (!readRegister(ADS_CONFIG, status) || (status & 0x7000) != mux) return false;
    if (status & ADS_START) {
      uint16_t raw;
      if (!readRegister(ADS_CONVERSION, raw)) return false;
      result = (int16_t)raw;
      return true;
    }
    vTaskDelay(1);
  } while (uptimeMs() < deadline);
  return false;
}

float channelVoltage(unsigned ch) {
  int32_t total = 0;
  for (unsigned i = 0; i < AVERAGE_COUNT; ++i) {
    int16_t raw;
    if (!readConversion(ch, raw)) return NAN;
    total += raw;
  }
  const float mean = max(0.0f, (float)total / AVERAGE_COUNT);
  // Use the same 1 mV raw value in live replies and SD records.
  return roundf(mean * ADC_LSB * INPUT_SCALE[ch] * 1000.0f) / 1000.0f;
}

void sampler(void*) {
  const bool watched = esp_task_wdt_add(nullptr) == ESP_OK;
  if (!watched) Serial.println("WDT: sampler enrollment failed");
  bool wireReady = Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setTimeOut(5);
  bool adcReady = false;
  bool adcReported = false;
  uint32_t currentPeriod = period.load();
  uint64_t next = uptimeMs();
  uint64_t lastStart = 0;
  bool first = true;

  while (true) {
    if (watched) esp_task_wdt_reset();
    const uint32_t requestedPeriod = period.load();
    if (requestedPeriod != currentPeriod) {
      currentPeriod = requestedPeriod;
      if (!first) next = lastStart + currentPeriod;
    }
    const uint64_t now = uptimeMs();
    if (now < next) {
      ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS((uint32_t)(next - now)));
      continue;
    }
    // Skip missed slots instead of recording a burst of fake timestamps.
    const uint64_t late = (now - next) / currentPeriod;
    if (late) missed.fetch_add((uint32_t)late);
    next += (late + 1) * currentPeriod;
    lastStart = now;
    first = false;

    Sample sample{max(1ULL, (unsigned long long)now), utcMs(), {NAN, NAN, NAN, NAN}};
    if (!wireReady) wireReady = Wire.begin(I2C_SDA, I2C_SCL);
    bool complete = wireReady;
    for (unsigned ch = 0; wireReady && ch < 4; ++ch) {
      sample.v[ch] = channelVoltage(ch);
      complete = complete && isfinite(sample.v[ch]);
    }
    if (!adcReported || complete != adcReady) {
      adcReported = true;
      adcReady = complete;
      Serial.println(adcReady ? "ADS1115: ready @0x48, 475 SPS" : "ADS1115: read failed");
    }
    publishSample(sample);
  }
}
}  // namespace

bool startSampler(uint32_t periodMs) {
  period.store(periodMs);
  return xTaskCreatePinnedToCore(sampler, "pdm-sample", 4096, nullptr, 2, &samplerHandle, ARDUINO_RUNNING_CORE) == pdPASS;
}

void setSamplePeriod(uint32_t periodMs) {
  period.store(periodMs);
  if (samplerHandle) xTaskNotifyGive(samplerHandle);
}

uint32_t missedSampleSlots() {
  return missed.load();
}
