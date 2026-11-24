#include <Arduino.h>
#include <string.h>

constexpr uint8_t forwardPin = 27, reversePin = 14;
constexpr uint8_t duty = 89;
constexpr uint32_t frequencyHz = 10000, runMs = 1000, pauseMs = 250;
constexpr uint32_t armMs = 2000, linkMs = 300;
enum class Phase { Idle, Armed, Forward, Pause, Reverse };
Phase phase = Phase::Idle;
uint32_t since = 0, lastKeep = 0;
bool ready = false, used = false;
char line[24];
size_t length = 0;
bool overlong = false;

void zeroPwm() {
  ledcWrite(forwardPin, 0);
  ledcWrite(reversePin, 0);
}

void report(const char* label) {
  // LEDC applies the new duty at a PWM-period boundary.
  delayMicroseconds(300);
  Serial.printf("%s %lu HZ %lu DUTY %lu %lu\n", label,
                static_cast<unsigned long>(since),
                static_cast<unsigned long>((phase == Phase::Reverse ? ledcReadFreq(reversePin) : ledcReadFreq(forwardPin))),
                static_cast<unsigned long>(ledcRead(forwardPin)),
                static_cast<unsigned long>(ledcRead(reversePin)));
}

void transition(Phase next, const char* label, uint32_t now) {
  zeroPwm();
  phase = next;
  since = now;
  if ((next == Phase::Forward && !ledcWrite(forwardPin, duty)) ||
      (next == Phase::Reverse && !ledcWrite(reversePin, duty))) {
    zeroPwm();
    phase = Phase::Idle;
    report("ERR_OUTPUT");
    return;
  }
  report(label);
}

void service(uint32_t now) {
  if (phase == Phase::Idle) return;
  if (phase == Phase::Armed) {
    if (now - since >= armMs) transition(Phase::Idle, "ARM_EXPIRED", now);
    return;
  }
  if (now - lastKeep >= linkMs) transition(Phase::Idle, "LINK_LOST", now);
  else if (phase == Phase::Forward && now - since >= runMs) transition(Phase::Pause, "PAUSE", now);
  else if (phase == Phase::Pause && now - since >= pauseMs) transition(Phase::Reverse, "REVERSE", now);
  else if (phase == Phase::Reverse && now - since >= runMs) transition(Phase::Idle, "STOPPED", now);
}

void handle(uint32_t now) {
  line[length] = 0;
  if (!strcmp(line, "STATUS")) {
    Serial.println(ready ? "READY PWM10 R" : "ERR INIT");
  } else if (!strcmp(line, "STOP")) {
    transition(Phase::Idle, "CANCELLED", now);
  } else if (!strcmp(line, "KEEP")) {
    if (phase == Phase::Forward || phase == Phase::Pause || phase == Phase::Reverse) lastKeep = now;
  } else if (!strcmp(line, "ARM PWM10 R") && ready && !used && phase == Phase::Idle) {
    transition(Phase::Armed, "ARMED", now);
  } else if (!strcmp(line, "RUN") && ready && !used && phase == Phase::Armed &&
             now - since < armMs) {
    used = true;
    lastKeep = now;
    transition(Phase::Forward, "FORWARD", now);
  } else {
    Serial.println("ERR STATE");
  }
}

void setup() {
  for (uint8_t pin : {forwardPin, reversePin, uint8_t(25), uint8_t(26)}) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  const bool a = ledcAttach(forwardPin, frequencyHz, 8);
  const bool b = ledcAttach(reversePin, frequencyHz, 8);
  zeroPwm();
  ready = a && b;
  Serial.begin(115200);
}

void loop() {
  service(millis());
  for (int count = 0; count < 32 && Serial.available(); ++count) {
    int byte = Serial.read();
    if (byte == '\n') {
      if (!overlong) handle(millis());
      length = 0;
      overlong = false;
    } else if (byte != '\r') {
      if (length < sizeof(line) - 1) line[length++] = static_cast<char>(byte);
      else overlong = true;
    }
  }
  delay(1);
}
