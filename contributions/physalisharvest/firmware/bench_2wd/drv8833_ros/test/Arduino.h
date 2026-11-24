#pragma once

#include <cstdint>
#include <cstdio>
#include <deque>
#include <string>

// MOCK nativo. El reloj y los GPIO son valores en memoria.
constexpr int LOW = 0;
constexpr int HIGH = 1;
constexpr int OUTPUT = 1;
inline uint32_t simulatedMs = 0;
inline int levels[40] = {};
inline uint32_t millis() { return simulatedMs; }
inline void delay(unsigned int) {}
inline void pinMode(int, int) {}
inline void digitalWrite(int pin, int value) { levels[pin] = value; }
inline int digitalRead(int pin) { return levels[pin]; }
inline bool attached[40] = {};
inline uint32_t duties[40] = {};
inline int failPwmPin = -1;
inline bool ledcAttach(int pin, uint32_t, uint8_t) { return attached[pin] = true; }
inline bool ledcDetach(int pin) {
  attached[pin] = false;
  duties[pin] = 0;
  return true;
}
inline bool ledcWrite(int pin, uint32_t duty) {
  if (!attached[pin] || pin == failPwmPin) return false;
  duties[pin] = duty;
  return true;
}

struct MockSerial {
  std::deque<char> input;
  std::string output;
  void begin(int) {}
  bool available() { return !input.empty(); }
  int read() {
    const auto value = input.front();
    input.pop_front();
    return value;
  }
  void println(const char* text) { output = std::string(text) + "\n"; }
  template <typename... Args>
  void printf(const char* format, Args... args) {
    char text[128];
    std::snprintf(text, sizeof(text), format, args...);
    output = text;
  }
};

inline MockSerial Serial;
