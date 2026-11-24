#include <Arduino.h>
#include <atomic>
#include <esp_timer.h>
#include <string.h>

constexpr uint8_t leftPwm = 25, rightPwm = 27;
constexpr uint8_t pins[] = {leftPwm, 26, rightPwm, 14};
constexpr uint8_t duty = 89;  // 35% of the 8-bit range.
constexpr uint32_t pulseUs = 150000, armMs = 2000;
const char* armedSide = nullptr;
uint32_t armedAt = 0;
bool ready = false, used = false;
std::atomic<bool> ended{false};
esp_timer_handle_t cutoff = nullptr;
char input[24];
size_t length = 0;
bool overlong = false;

void zeroOutputs() {
  ledcWrite(leftPwm, 0);
  ledcWrite(rightPwm, 0);
}

void endPulse(void*) {
  zeroOutputs();
  ended.store(true);
}

void command() {
  input[length] = 0;
  if (!strcmp(input, "STATUS")) {
    Serial.println(ready ? "READY PULSE1 150ms 35%" : "ERR INIT");
  } else if (!strcmp(input, "STOP")) {
    armedSide = nullptr;
    zeroOutputs();
    if (cutoff) esp_timer_stop(cutoff);
    Serial.println("STOPPED");
  } else if ((!strcmp(input, "ARM L") || !strcmp(input, "ARM R")) && ready && !used) {
    armedSide = input[4] == 'L' ? "L" : "R";
    armedAt = millis();
    Serial.printf("ARMED %s\n", armedSide);
  } else if (!strcmp(input, "PULSE") && ready && !used && armedSide &&
             millis() - armedAt < armMs) {
    const uint8_t pin = *armedSide == 'L' ? leftPwm : rightPwm;
    armedSide = nullptr;
    used = true;  // One pulse per reset. ROS and coordinates are ignored.
    if (esp_timer_start_once(cutoff, pulseUs) != ESP_OK) {
      Serial.println("ERR TIMER");
      return;
    }
    if (!ledcWrite(pin, duty)) {
      zeroOutputs();
      esp_timer_stop(cutoff);
      Serial.println("ERR OUTPUT");
      return;
    }
    Serial.println("PULSE START");
  } else {
    Serial.println("ERR COMMAND OR STATE");
  }
}

void setup() {
  for (const uint8_t pin : pins) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  bool left = ledcAttach(leftPwm, 1000, 8);
  bool right = ledcAttach(rightPwm, 1000, 8);
  zeroOutputs();
  esp_timer_create_args_t timer{};
  timer.callback = endPulse;
  timer.dispatch_method = ESP_TIMER_TASK;
  timer.name = "motor_cutoff";
  ready = left && right && esp_timer_create(&timer, &cutoff) == ESP_OK;
  Serial.begin(115200);
}

void loop() {
  if (ended.exchange(false)) Serial.println("PULSE END");
  for (int count = 0; count < 32 && Serial.available(); ++count) {
    const int byte = Serial.read();
    if (byte == '\n') {
      if (!overlong) command();
      length = 0;
      overlong = false;
    } else if (byte != '\r') {
      if (length < sizeof(input) - 1) input[length++] = static_cast<char>(byte);
      else overlong = true;
    }
  }
  delay(1);
}
