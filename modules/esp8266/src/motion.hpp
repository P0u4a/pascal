#pragma once

#include <Arduino.h>

#include <algorithm>
#include <array>
#include <cstdint>
#include <optional>
#include <string_view>

#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

#ifndef HUB_LOG_URL
#define HUB_LOG_URL ""
#endif

constexpr std::uint16_t http_port = 80;
constexpr std::uint32_t command_timeout_ms = 500;
constexpr std::uint32_t queued_motion_ms = 500;
constexpr std::uint32_t wifi_timeout_ms = 20'000;

struct MotorPins {
  std::uint8_t forward;
  std::uint8_t backward;
  std::uint8_t rotate_left;
  std::uint8_t rotate_right;
};

constexpr MotorPins motor_pins{
    .forward = D2,
    .backward = D1,
    .rotate_left = D5,
    .rotate_right = D6,
};

enum class Motion : std::uint8_t {
  stop = 0x00,
  forward = 0x01,
  backward = 0x02,
  rotate_left = 0x03,
  rotate_right = 0x04,
};

struct PinState {
  bool forward{};
  bool backward{};
  bool rotate_left{};
  bool rotate_right{};
};

struct MotionConfig {
  Motion motion;
  std::string_view name;
  PinState pins;
};

constexpr std::array motion_configs{
    MotionConfig{Motion::stop, "stop", {}},
    MotionConfig{Motion::forward, "forward", {.forward = true}},
    MotionConfig{Motion::backward, "backward", {.backward = true}},
    MotionConfig{Motion::rotate_left, "rotate-left", {.rotate_left = true}},
    MotionConfig{Motion::rotate_right, "rotate-right", {.rotate_right = true}},
};

constexpr const MotionConfig *find_motion_config(const Motion motion) {
  for (const auto &config : motion_configs) {
    if (config.motion == motion) {
      return &config;
    }
  }
  return nullptr;
}

constexpr std::optional<Motion> decode_motion(const std::uint8_t value) {
  const auto motion = static_cast<Motion>(value);
  return find_motion_config(motion) == nullptr ? std::nullopt
                                               : std::optional{motion};
}

inline String to_string(const std::string_view value) {
  char text[16]{};
  const auto count = std::min(value.length(), sizeof(text) - 1);
  for (std::size_t i = 0; i < count; ++i) {
    text[i] = value[i];
  }
  return String{text};
}
