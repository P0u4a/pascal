#include <Arduino.h>
#include <ESP8266WebServer.h>
#include <ESP8266WiFi.h>

#include "esp_http_server.hpp"
#include "hub_logger.hpp"
#include "motor_controller.hpp"
#include "motion.hpp"

namespace {
void connect_wifi(const HubLogger &logger) {
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.printf("connecting to wifi ssid='%s'\n", WIFI_SSID);
  const std::uint32_t start_ms = millis();
  while (WiFi.status() != WL_CONNECTED &&
         millis() - start_ms < wifi_timeout_ms) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("wifi connection failed after %u ms, status=%d\n",
                  static_cast<unsigned int>(wifi_timeout_ms),
                  static_cast<int>(WiFi.status()));
    Serial.println(
        "check that the SSID is 2.4 GHz and credentials are correct");
    return;
  }

  logger.info(String{"connected: "} + WiFi.localIP().toString());
  Serial.printf("gateway: %s\n", WiFi.gatewayIP().toString().c_str());
  Serial.printf("mac: %s\n", WiFi.macAddress().c_str());
}

ESP8266WebServer web_server{http_port};
HubLogger logger;
MotorController motors{motor_pins, logger};
EspHttpServer esp_server{web_server, motors, logger};
} // namespace

void setup() {
  Serial.begin(115200);
  Serial.println();

  motors.begin();
  connect_wifi(logger);
  esp_server.begin();
}

void loop() {
  esp_server.handle_client();
  motors.stop_if_timed_out(millis());
}
