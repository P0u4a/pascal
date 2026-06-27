#include "motor_controller.hpp"

MotorController::MotorController(MotorPins pins, const HubLogger &logger)
    : pins_{pins}, logger_{logger} {}

void MotorController::begin() const {
  pinMode(pins_.forward, OUTPUT);
  pinMode(pins_.backward, OUTPUT);
  pinMode(pins_.rotate_left, OUTPUT);
  pinMode(pins_.rotate_right, OUTPUT);
  write({});
}

void MotorController::apply(const Motion motion) {
  const auto *config = find_motion_config(motion);
  if (config == nullptr) {
    stop();
    return;
  }

  last_command_ms_ = millis();
  logger_.info(String{"motion: "} + to_string(config->name));
  write(config->pins);
}

void MotorController::stop() {
  write({});
  last_command_ms_ = 0;
}

void MotorController::stop_if_timed_out(const std::uint32_t now) {
  if (last_command_ms_ != 0 && now - last_command_ms_ > command_timeout_ms) {
    stop();
  }
}

void MotorController::write(const PinState state) const {
  digitalWrite(pins_.forward, state.forward ? HIGH : LOW);
  digitalWrite(pins_.backward, state.backward ? HIGH : LOW);
  digitalWrite(pins_.rotate_left, state.rotate_left ? HIGH : LOW);
  digitalWrite(pins_.rotate_right, state.rotate_right ? HIGH : LOW);
}
