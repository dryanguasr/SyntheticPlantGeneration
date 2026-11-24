#include <Arduino.h>
#include <string.h>

struct Motor {
  uint8_t input1;
  uint8_t input2;
  bool forwardOnInput1;
};

// Ajustar cada polaridad tras observar el avance f?sico de su rueda.
constexpr Motor motors[] = {{25, 26, true}, {27, 14, true}};
constexpr uint32_t phaseMs = 1000;
constexpr uint32_t coastMs = 250;
constexpr uint32_t armMs = 2000;
constexpr uint32_t linkMs = 300;

enum class Stage { Idle, Armed, Forward, Coast, Reverse };
Stage stage = Stage::Idle;
uint32_t startedAt = 0;
uint32_t heartbeatAt = 0;
bool consumed = false;
char commandBuffer[24];
size_t commandLength = 0;
bool overflow = false;

void allLow() {
  for (const Motor& motor : motors) {
    digitalWrite(motor.input1, LOW);
    digitalWrite(motor.input2, LOW);
  }
}

void transition(Stage next, const char* label, uint32_t now) {
  allLow();
  stage = next;
  startedAt = now;
  if (next == Stage::Forward || next == Stage::Reverse) {
    const bool forward = next == Stage::Forward;
    for (const Motor& motor : motors) {
      digitalWrite(forward == motor.forwardOnInput1 ? motor.input1 : motor.input2, HIGH);
    }
  }
  Serial.printf("%s %lu GPIO %d %d %d %d\n", label, static_cast<unsigned long>(now),
                digitalRead(25), digitalRead(26), digitalRead(27), digitalRead(14));
}

bool running() {
  return stage == Stage::Forward || stage == Stage::Coast || stage == Stage::Reverse;
}

void advance(uint32_t now) {
  const uint32_t elapsed = now - startedAt;
  if (stage == Stage::Armed && elapsed >= armMs) {
    transition(Stage::Idle, "ARM_EXPIRED", now);
  } else if (running() && now - heartbeatAt >= linkMs) {
    transition(Stage::Idle, "LINK_LOST", now);
  } else if (stage == Stage::Forward && elapsed >= phaseMs) {
    transition(Stage::Coast, "COAST", now);
  } else if (stage == Stage::Coast && elapsed >= coastMs) {
    transition(Stage::Reverse, "REVERSE", now);
  } else if (stage == Stage::Reverse && elapsed >= phaseMs) {
    transition(Stage::Idle, "STOPPED", now);
  }
}

void handle(uint32_t now) {
  commandBuffer[commandLength] = '\0';
  if (strcmp(commandBuffer, "STATUS") == 0) {
    Serial.println(consumed ? "USED BOTH_FULL" : "READY BOTH_FULL");
  } else if (strcmp(commandBuffer, "STOP") == 0) {
    transition(Stage::Idle, "CANCELLED", now);
  } else if (strcmp(commandBuffer, "KEEP") == 0 && running()) {
    heartbeatAt = now;
  } else if (strcmp(commandBuffer, "ARM BOTH_FULL") == 0 &&
             stage == Stage::Idle && !consumed) {
    transition(Stage::Armed, "ARMED", now);
  } else if (strcmp(commandBuffer, "RUN") == 0 && stage == Stage::Armed &&
             !consumed && now - startedAt < armMs) {
    consumed = true;
    heartbeatAt = now;
    transition(Stage::Forward, "FORWARD", now);
  } else if (strcmp(commandBuffer, "KEEP") != 0) {
    Serial.println("ERR STATE");
  }
}

void setup() {
  allLow();
  for (const Motor& motor : motors) {
    pinMode(motor.input1, OUTPUT);
    pinMode(motor.input2, OUTPUT);
  }
  allLow();
  Serial.begin(115200);
}

void loop() {
  advance(millis());
  for (int count = 0; count < 32 && Serial.available(); ++count) {
    const int byte = Serial.read();
    if (byte == '\n') {
      if (!overflow) handle(millis());
      else Serial.println("ERR LENGTH");
      commandLength = 0;
      overflow = false;
    } else if (byte != '\r') {
      if (commandLength < sizeof(commandBuffer) - 1) commandBuffer[commandLength++] = byte;
      else overflow = true;
    }
  }
  delay(1);
}
