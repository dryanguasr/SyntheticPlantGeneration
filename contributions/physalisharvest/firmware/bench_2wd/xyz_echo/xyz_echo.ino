#include <Arduino.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

char line[96];
size_t length = 0;
bool overflow = false;

void handleLine() {
  line[length] = '\0';
  if (strcmp(line, "HELLO XYZ1") == 0) {
    Serial.println("READY XYZ1");
    return;
  }
  unsigned long id;
  float x, y, z;
  char extra;
  if (sscanf(line, "XYZ1 %lu %f %f %f %c", &id, &x, &y, &z, &extra) != 4 ||
      id == 0 || !isfinite(x) || !isfinite(y) || !isfinite(z) || z <= 0) {
    Serial.println("ERR FORMAT");
    return;
  }
  Serial.printf("ECHO %lu %.6f %.6f %.6f\n", id, x, y, z);
}

void setup() {
  Serial.begin(115200);
}

void loop() {
  while (Serial.available()) {
    int byte = Serial.read();
    if (byte == '\n') {
      if (overflow) Serial.println("ERR LENGTH");
      else handleLine();
      length = 0;
      overflow = false;
    } else if (byte != '\r') {
      if (length < sizeof(line) - 1) line[length++] = static_cast<char>(byte);
      else overflow = true;
    }
  }
}
