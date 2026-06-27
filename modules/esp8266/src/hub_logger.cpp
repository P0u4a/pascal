#include "hub_logger.hpp"

#include "motion.hpp"

#include <ESP8266HTTPClient.h>
#include <ESP8266WiFi.h>

#include <string_view>

namespace {
String json_escape(const String &value) {
  String escaped;
  escaped.reserve(value.length() + 8);
  for (std::size_t i = 0; i < value.length(); ++i) {
    const char c = value[i];
    if (c == '"' || c == '\\') {
      escaped += '\\';
    }
    escaped += c;
  }
  return escaped;
}
} // namespace

void HubLogger::info(const String &message) const { forward("info", message); }

void HubLogger::warn(const String &message) const { forward("warn", message); }

void HubLogger::forward(const char *level, const String &message) const {
  Serial.println(message);

  if (std::string_view{HUB_LOG_URL}.empty() || WiFi.status() != WL_CONNECTED) {
    return;
  }

  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client, HUB_LOG_URL)) {
    return;
  }

  http.addHeader("content-type", "application/json");
  const String body = String{"{\"level\":\""} + level +
                      "\",\"subsystem\":\"esp\",\"message\":\"" +
                      json_escape(message) + "\"}";
  http.POST(body);
  http.end();
}
