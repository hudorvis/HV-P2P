#pragma once
#include <Arduino.h>

// HV P2P point-to-point RS485 framing used only between CTRL and CTRL-TS.
// CTRL is always the bus master. CTRL-TS transmits only as a direct response.
namespace HVP2PRS485 {

static constexpr uint8_t MAGIC[4] = { 'H', 'V', 'P', '2' };
static constexpr uint8_t PROTOCOL_VERSION = 1;
static constexpr size_t MAX_PAYLOAD = 3072;
static constexpr size_t HEADER_SIZE = 10; // magic4 + version + type + seq2 + len2
static constexpr size_t CRC_SIZE = 4;
static constexpr uint32_t RX_INTERBYTE_TIMEOUT_MS = 250;

enum FrameType : uint8_t {
  HELLO_REQ  = 0x01,
  HELLO_RESP = 0x02,
  COMPATIBLE = 0x03,
  TEXT       = 0x10,
  POLL       = 0x11,
  EVENT      = 0x12,
  ACK        = 0x13,
  ERROR_MSG  = 0x14,
  FW_BEGIN   = 0x20,
  FW_READY   = 0x21,
  FW_BLOCK   = 0x22,
  FW_ACK     = 0x23,
  FW_END     = 0x24,
  FW_RESULT  = 0x25,
  REBOOT     = 0x26,
};

struct Frame {
  uint8_t version = 0;
  uint8_t type = 0;
  uint16_t seq = 0;
  uint16_t length = 0;
  uint8_t payload[MAX_PAYLOAD];
};

static inline uint32_t crc32Update(uint32_t crc, const uint8_t *data, size_t len) {
  crc = ~crc;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; ++b) crc = (crc >> 1) ^ (0xEDB88320UL & (0UL - (crc & 1UL)));
  }
  return ~crc;
}

static inline uint32_t frameCrc(uint8_t version, uint8_t type, uint16_t seq, uint16_t len, const uint8_t *payload) {
  uint8_t h[6] = {
    version, type,
    uint8_t(seq >> 8), uint8_t(seq),
    uint8_t(len >> 8), uint8_t(len)
  };
  uint32_t crc = crc32Update(0, h, sizeof(h));
  if (len && payload) {
    // crc32Update() complements at both ends, so continue by un-complementing prior result.
    uint32_t raw = ~crc;
    for (uint16_t i = 0; i < len; ++i) {
      raw ^= payload[i];
      for (uint8_t b = 0; b < 8; ++b) raw = (raw >> 1) ^ (0xEDB88320UL & (0UL - (raw & 1UL)));
    }
    crc = ~raw;
  }
  return crc;
}

static inline bool sendFrame(Stream &port, uint8_t type, uint16_t seq, const uint8_t *payload = nullptr, uint16_t len = 0) {
  if (len > MAX_PAYLOAD) return false;
  uint8_t header[HEADER_SIZE] = {
    MAGIC[0], MAGIC[1], MAGIC[2], MAGIC[3],
    PROTOCOL_VERSION, type,
    uint8_t(seq >> 8), uint8_t(seq),
    uint8_t(len >> 8), uint8_t(len)
  };
  const uint32_t crc = frameCrc(PROTOCOL_VERSION, type, seq, len, payload);
  if (port.write(header, sizeof(header)) != sizeof(header)) return false;
  if (len && payload && port.write(payload, len) != len) return false;
  uint8_t c[4] = { uint8_t(crc >> 24), uint8_t(crc >> 16), uint8_t(crc >> 8), uint8_t(crc) };
  if (port.write(c, sizeof(c)) != sizeof(c)) return false;
  port.flush();
  return true;
}

static inline bool sendText(Stream &port, uint8_t type, uint16_t seq, const String &text) {
  if (text.length() > MAX_PAYLOAD) return false;
  return sendFrame(port, type, seq, reinterpret_cast<const uint8_t*>(text.c_str()), uint16_t(text.length()));
}

static inline String payloadString(const Frame &frame) {
  String s;
  s.reserve(frame.length + 1);
  for (uint16_t i = 0; i < frame.length; ++i) s += char(frame.payload[i]);
  return s;
}

class Parser {
public:
  Parser() { reset(); }

  void reset() {
    state_ = SEEK_MAGIC;
    magicIndex_ = 0;
    headerIndex_ = 0;
    payloadIndex_ = 0;
    crcIndex_ = 0;
    expectedLength_ = 0;
    lastByteMs_ = 0;
  }

  bool feed(uint8_t b, Frame &out) {
    const uint32_t now = millis();
    if (lastByteMs_ && (now - lastByteMs_) > RX_INTERBYTE_TIMEOUT_MS) reset();
    lastByteMs_ = now;

    if (state_ == SEEK_MAGIC) {
      if (b == MAGIC[magicIndex_]) {
        magic_[magicIndex_++] = b;
        if (magicIndex_ == sizeof(MAGIC)) {
          state_ = READ_HEADER;
          headerIndex_ = 0;
        }
      } else {
        magicIndex_ = (b == MAGIC[0]) ? 1 : 0;
        if (magicIndex_) magic_[0] = b;
      }
      return false;
    }

    if (state_ == READ_HEADER) {
      header_[headerIndex_++] = b;
      if (headerIndex_ < 6) return false;
      const uint8_t version = header_[0];
      expectedLength_ = (uint16_t(header_[4]) << 8) | header_[5];
      if (version != PROTOCOL_VERSION || expectedLength_ > MAX_PAYLOAD) {
        reset();
        return false;
      }
      payloadIndex_ = 0;
      crcIndex_ = 0;
      state_ = expectedLength_ ? READ_PAYLOAD : READ_CRC;
      return false;
    }

    if (state_ == READ_PAYLOAD) {
      payload_[payloadIndex_++] = b;
      if (payloadIndex_ >= expectedLength_) state_ = READ_CRC;
      return false;
    }

    crc_[crcIndex_++] = b;
    if (crcIndex_ < 4) return false;

    const uint8_t version = header_[0];
    const uint8_t type = header_[1];
    const uint16_t seq = (uint16_t(header_[2]) << 8) | header_[3];
    const uint16_t len = expectedLength_;
    const uint32_t got = (uint32_t(crc_[0]) << 24) | (uint32_t(crc_[1]) << 16) | (uint32_t(crc_[2]) << 8) | uint32_t(crc_[3]);
    const uint32_t want = frameCrc(version, type, seq, len, payload_);
    if (got != want) {
      reset();
      return false;
    }

    out.version = version;
    out.type = type;
    out.seq = seq;
    out.length = len;
    if (len) memcpy(out.payload, payload_, len);
    reset();
    return true;
  }

private:
  enum State : uint8_t { SEEK_MAGIC, READ_HEADER, READ_PAYLOAD, READ_CRC };
  State state_;
  uint8_t magic_[4];
  uint8_t magicIndex_;
  uint8_t header_[6];
  uint8_t headerIndex_;
  uint8_t payload_[MAX_PAYLOAD];
  uint16_t payloadIndex_;
  uint16_t expectedLength_;
  uint8_t crc_[4];
  uint8_t crcIndex_;
  uint32_t lastByteMs_;
};

} // namespace HVP2PRS485
