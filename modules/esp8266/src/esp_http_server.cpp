#include "esp_http_server.hpp"

#include "motion.hpp"

EspHttpServer::EspHttpServer(ESP8266WebServer &server, MotorController &motors,
                             const HubLogger &logger)
    : server_{server}, motors_{motors}, logger_{logger} {}

void EspHttpServer::begin() {
  server_.on("/health", HTTP_GET, [this] { handle_health(); });
  server_.on("/motion", HTTP_POST, [this] { handle_motion(); });
  server_.begin();
  logger_.info(String{"http listening on port "} + http_port);
}

void EspHttpServer::handle_client() { server_.handleClient(); }

void EspHttpServer::send_response(const int status, const char *body) {
  server_.sendHeader("connection", "keep-alive");
  server_.send(status, "text/plain", body);
}

void EspHttpServer::handle_health() { send_response(200, "ok"); }

void EspHttpServer::handle_motion() {
  const String body = server_.arg("plain");
  if (body.length() == 0) {
    motors_.stop();
    send_response(400, "empty-motion");
    return;
  }

  for (std::size_t i = 0; i < body.length(); ++i) {
    const auto motion = decode_motion(static_cast<std::uint8_t>(body[i]));
    if (!motion.has_value()) {
      motors_.stop();
      logger_.warn("invalid motion command");
      send_response(400, "invalid-motion");
      return;
    }

    motors_.apply(*motion);
    if (*motion != Motion::stop && i + 1 < body.length()) {
      delay(queued_motion_ms);
      motors_.stop();
    }
  }

  send_response(200, "ok");
}
