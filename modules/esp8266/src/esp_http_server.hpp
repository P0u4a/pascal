#pragma once

#include "hub_logger.hpp"
#include "motor_controller.hpp"

#include <ESP8266WebServer.h>

class EspHttpServer {
public:
  EspHttpServer(ESP8266WebServer &server, MotorController &motors,
                const HubLogger &logger);

  void begin();
  void handle_client();

private:
  void send_response(int status, const char *body);
  void handle_health();
  void handle_motion();

  ESP8266WebServer &server_;
  MotorController &motors_;
  const HubLogger &logger_;
};
