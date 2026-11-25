// Encoders magnéticos AS5600 de J1-J5 para el transporte WiFi del ESP32.
//
// Montaje del test 01 del equipo (firmware/hardware_tests/01_test_encoders_as5600):
// multiplexor TCA9548A en 0x70 y encoders en sus canales 0-4 (J1-J5; la pinza
// no lleva encoder). Sin multiplexor, un solo AS5600 directo en 0x36 se lee
// como encoder 0. Comparte el bus I2C (GPIO 21/22) con el PCA9685, que debe
// estar en el bus principal, no detrás del multiplexor.
//
// Orden, solo tras AUTH:
//   ENQ  ->  OK ENQ <canal>:<raw>:<imán> ...   (raw 0-4095 por vuelta)
//            imán: OK, MH (muy cerca), ML (muy lejos), NM (no detectado)
//            un canal sin sensor aparece como <canal>:--
//
// Lee registros, sin librerías externas. El valor es el ángulo del imán, no
// el de la articulación: cero, sentido y relación de transmisión están sin
// calibrar. Solo se lee a petición; no interviene en el control.
#pragma once

#include <Arduino.h>
#include <Wire.h>
#include <stdio.h>
#include <string.h>

#ifndef ENCODER_ENABLED
#define ENCODER_ENABLED 1
#endif
#ifndef TCA9548A_ADDRESS
#define TCA9548A_ADDRESS 0x70
#endif
#ifndef ENCODER_COUNT
#define ENCODER_COUNT 5
#endif

static_assert(ENCODER_COUNT >= 1 && ENCODER_COUNT <= 8, "El TCA9548A tiene 8 canales (0-7)");

namespace as5600 {
constexpr uint8_t address = 0x36;
constexpr uint8_t status = 0x0B;
constexpr uint8_t rawAngle = 0x0C;
constexpr uint8_t magnetDetected = 0x20;
constexpr uint8_t magnetTooWeak = 0x10;
constexpr uint8_t magnetTooStrong = 0x08;
}  // namespace as5600

bool encoderMux = false;     // TCA9548A presente
bool encoderDirect = false;  // un AS5600 directo en el bus principal

bool i2cPresent(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void encoderDetect() {
  encoderMux = ENCODER_ENABLED && i2cPresent(TCA9548A_ADDRESS);
  encoderDirect = ENCODER_ENABLED && !encoderMux && i2cPresent(as5600::address);
}

bool selectEncoder(uint8_t channel) {
  if (encoderDirect) return channel == 0;
  if (!encoderMux) return false;
  const uint8_t mask = static_cast<uint8_t>(1u << channel);
  Wire.beginTransmission(TCA9548A_ADDRESS);
  Wire.write(&mask, 1);
  return Wire.endTransmission() == 0;
}

void releaseEncoders() {
  if (!encoderMux) return;
  const uint8_t none = 0;
  Wire.beginTransmission(TCA9548A_ADDRESS);
  Wire.write(&none, 1);
  Wire.endTransmission();
}

bool readRegisters(uint8_t reg, uint8_t* data, uint8_t size) {
  Wire.beginTransmission(as5600::address);
  Wire.write(&reg, 1);
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom(as5600::address, size) != size) return false;
  for (uint8_t i = 0; i < size; ++i) data[i] = static_cast<uint8_t>(Wire.read());
  return true;
}

const char* magnetState(uint8_t value) {
  if (value & as5600::magnetDetected) return "OK";
  if (value & as5600::magnetTooStrong) return "MH";
  if (value & as5600::magnetTooWeak) return "ML";
  return "NM";
}

bool isEncoderLine(const char* line) { return strcmp(line, "ENQ") == 0; }

template <typename Reply>
void handleEncoder(const char*, Reply reply) {
  if (!encoderMux && !encoderDirect) encoderDetect();  // conectado después del arranque
  if (!encoderMux && !encoderDirect) {
    reply("ERR EN SIN SENSORES");
    return;
  }
  char text[160];
  size_t used = snprintf(text, sizeof(text), "OK ENQ");
  for (uint8_t channel = 0; channel < ENCODER_COUNT; ++channel) {
    uint8_t state = 0;
    uint8_t angle[2] = {};
    if (selectEncoder(channel) && readRegisters(as5600::status, &state, 1) &&
        readRegisters(as5600::rawAngle, angle, 2)) {
      const unsigned raw = ((angle[0] & 0x0F) << 8) | angle[1];
      used += snprintf(text + used, sizeof(text) - used, " %u:%u:%s", channel, raw, magnetState(state));
    } else {
      used += snprintf(text + used, sizeof(text) - used, " %u:--", channel);
    }
  }
  releaseEncoders();
  reply(text);
}
