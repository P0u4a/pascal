#pragma once

#include <Arduino.h>

class HubLogger {
public:
  void info(const String &message) const;
  void warn(const String &message) const;

private:
  void forward(const char *level, const String &message) const;
};
