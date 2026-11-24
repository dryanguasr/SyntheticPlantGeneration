#include <Arduino.h>
#include <driver/gpio.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

constexpr gpio_num_t pins[] = {GPIO_NUM_25, GPIO_NUM_26, GPIO_NUM_27, GPIO_NUM_14};
constexpr uint32_t motionMs = 1000;
constexpr uint32_t pauseMs = 250;
constexpr uint32_t armMs = 2000;
constexpr uint32_t linkMs = 500;
enum class Phase { Idle, Armed, Forward, Pause, Reverse };
Phase phase = Phase::Idle;
uint32_t since = 0, heartbeat = 0;
bool gpioReady = false;
char line[96];
size_t length = 0;
bool overflow = false;

void transition(Phase next, const char* label, uint32_t now) {
  phase = next;
  since = now;
  Serial.printf("DRY %s %lu GPIO", label, static_cast<unsigned long>(now));
  for (gpio_num_t pin : pins) Serial.printf(" %d=%d", static_cast<int>(pin), gpio_get_level(pin));
  Serial.println();
}

void service(uint32_t now) {
  if (phase == Phase::Idle) return;
  if (phase == Phase::Armed) {
    if (now - since >= armMs) transition(Phase::Idle, "ARM_EXPIRED", now);
    return;
  }
  if (now - heartbeat >= linkMs) transition(Phase::Idle, "LINK_LOST", now);
  else if (phase == Phase::Forward && now - since >= motionMs) transition(Phase::Pause, "PAUSE", now);
  else if (phase == Phase::Pause && now - since >= pauseMs) transition(Phase::Reverse, "REVERSE", now);
  else if (phase == Phase::Reverse && now - since >= motionMs) transition(Phase::Idle, "STOP", now);
}

void handleLine(uint32_t now) {
  line[length] = '\0';
  if (strcmp(line, "HELLO DRY1") == 0) {
    Serial.println(gpioReady ? "READY DRY1" : "ERR GPIO");
  } else if (strcmp(line, "STOP") == 0) {
    transition(Phase::Idle, "CANCEL", now);
  } else if (strcmp(line, "KEEP") == 0) {
    if (phase == Phase::Forward || phase == Phase::Pause || phase == Phase::Reverse) heartbeat = now;
  } else if (strcmp(line, "ARM DRY1") == 0) {
    if (gpioReady && phase == Phase::Idle) transition(Phase::Armed, "ARMED", now);
    else Serial.println("ERR STATE");
  } else {
    unsigned long id;
    float x, y, z;
    char extra;
    if (sscanf(line, "XYZ1 %lu %f %f %f %c", &id, &x, &y, &z, &extra) != 4 ||
        id == 0 || !isfinite(x) || !isfinite(y) || !isfinite(z) || z <= 0) {
      Serial.println("ERR FORMAT");
    } else if (phase != Phase::Armed) {
      Serial.println("ERR NOT_ARMED");
    } else {
      Serial.printf("ECHO %lu %.6f %.6f %.6f\n", id, x, y, z);
      heartbeat = now;
      transition(Phase::Forward, "FORWARD", now);
    }
  }
}

void setup() {
  Serial.begin(115200);
  gpio_config_t config{};
  for (gpio_num_t pin : pins) {
    gpio_set_level(pin, 0);
    config.pin_bit_mask |= 1ULL << pin;
  }
  config.mode = GPIO_MODE_INPUT_OUTPUT;
  config.pull_down_en = GPIO_PULLDOWN_ENABLE;
  gpioReady = gpio_config(&config) == ESP_OK;
  transition(Phase::Idle, "BOOT", millis());
}

void loop() {
  service(millis());
  for (int count = 0; count < 64 && Serial.available(); ++count) {
    int byte = Serial.read();
    if (byte == '\n') {
      if (overflow) Serial.println("ERR LENGTH");
      else handleLine(millis());
      length = 0;
      overflow = false;
    } else if (byte != '\r') {
      if (length < sizeof(line) - 1) line[length++] = static_cast<char>(byte);
      else overflow = true;
    }
  }
  delay(1);
}
