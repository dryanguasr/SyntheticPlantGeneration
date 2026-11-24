#include <Arduino.h>
#include <string.h>

// STBY se habilita externamente. 00 en cada puente deja el motor libre.
constexpr uint8_t pins[] = {25, 26, 27, 14};
constexpr uint32_t watchdogMs = 250;
constexpr uint32_t directionPauseMs = 100;
constexpr uint32_t pwmHz = 1000;
constexpr uint8_t pwmBits = 8;
constexpr uint8_t motorDuty = 255;
constexpr uint8_t leftForwardDuty = 242;
bool pwmReady = true;

bool armed = false;
uint32_t lastContact = 0;
uint32_t stoppedAt = 0;
char requested = 'S';
char active = 'S';
char buffer[16];
size_t length = 0;
bool overflow = false;

void stopOutputs(uint32_t now) {
  for (uint8_t pin : pins) {
    if (!ledcWrite(pin, 0)) {
      ledcDetach(pin);
      digitalWrite(pin, LOW);
      pinMode(pin, OUTPUT);
      pwmReady = false;
    }
  }
  if (active != 'S') stoppedAt = now;
  active = 'S';
}

void disarm(uint32_t now) {
  stopOutputs(now);
  armed = false;
  requested = 'S';
}

void expire(uint32_t now) {
  if (armed && now - lastContact >= watchdogMs) {
    disarm(now);
  }
}

void updateMotion(uint32_t now) {
  expire(now);
  if (armed && requested != active) {
    if (active != 'S') {
      stopOutputs(now);
    } else if (now - stoppedAt >= directionPauseMs) {
      const bool left = requested == 'L' || requested == 'Q';
      const uint8_t leftDuty = requested == 'F' ? leftForwardDuty : motorDuty;
      if (!pwmReady || !ledcWrite(pins[left ? 1 : 0], leftDuty) ||
          !ledcWrite(pins[requested == 'R' ? 3 : 2], motorDuty)) {
        pwmReady = false;
        disarm(now);
        return;
      }
      active = requested;
    }
  }
}

bool isDirection(char value) {
  return value == 'F' || value == 'L' || value == 'R' || value == 'Q';
}

void handle(uint32_t now) {
  expire(now);
  buffer[length] = '\0';
  if (!overflow && strcmp(buffer, "ID") == 0) {
    disarm(now);
    Serial.println(pwmReady ? "DRV8833_ROS_V5" : "ERR PWM");
    return;
  }
  if (!overflow && length == 1 && buffer[0] == 'S') {
    disarm(now);
  } else if (pwmReady && !overflow && length == 2 && buffer[0] == 'C' &&
             isDirection(buffer[1]) && !armed) {
    armed = true;
    requested = buffer[1];
    lastContact = now;
  } else if (pwmReady && !overflow && length == 1 && isDirection(buffer[0]) && armed) {
    requested = buffer[0];
    lastContact = now;
  } else {
    disarm(now);
    Serial.println("ERR COMMAND");
    return;
  }
  updateMotion(now);
  if (!pwmReady) {
    Serial.println("ERR PWM");
    return;
  }
  const char* outputs = "0000";
  if (active == 'F') outputs = "1010";
  else if (active == 'L' || active == 'Q') outputs = "0110";
  else if (active == 'R') outputs = "1001";
  Serial.printf("OK %s %s\n", buffer, outputs);
}

void setup() {
  for (uint8_t pin : pins) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
    if (!ledcAttach(pin, pwmHz, pwmBits)) pwmReady = false;
  }
  disarm(millis());
  Serial.begin(115200);
}

void loop() {
  for (int count = 0; count < 32 && Serial.available(); ++count) {
    const int byte = Serial.read();
    if (byte == '\n') {
      handle(millis());
      length = 0;
      overflow = false;
    } else if (byte != '\r') {
      if (length < sizeof(buffer) - 1) buffer[length++] = byte;
      else overflow = true;
    }
  }
  updateMotion(millis());
  delay(1);
}
