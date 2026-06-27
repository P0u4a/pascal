#pragma once

#include "hub_logger.hpp"
#include "motion.hpp"

#include <cstdint>

class MotorController {
public:
  MotorController(MotorPins pins, const HubLogger &logger);

  void begin() const;
  void apply(Motion motion);
  void stop();
  void stop_if_timed_out(std::uint32_t now);

private:
  void write(PinState state) const;

  MotorPins pins_;
  const HubLogger &logger_;
  std::uint32_t last_command_ms_{};
};
