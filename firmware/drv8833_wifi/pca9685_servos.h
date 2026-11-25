// Servos por PCA9685 (I2C) para el transporte WiFi del ESP32.
//
// Órdenes, solo tras AUTH y sin pasar por el sketch de motores:
//   SV <canal> <us>  ancho de pulso objetivo en microsegundos
//   SVOFF            corta el pulso de todos los canales (servos sin par)
//   SVQ              estado: canal:actual/objetivo de los canales activos
//
// Seguridad:
//   - Cada canal tiene un rango [mín, máx] en wifi_config.h; fuera de él la
//     orden se rechaza, no se recorta.
//   - El movimiento se limita a SERVO_SLEW_US_PER_S para evitar golpes.
//   - Al perder el cliente: SERVO_HOLD_ON_DISCONNECT 0 corta el pulso (por
//     defecto); 1 mantiene la última posición.
//   - Al arrancar, todos los canales quedan sin pulso hasta la primera orden.
//
// Los valores por defecto son genéricos (estimated), no medidos en el brazo.
#pragma once

#include <Arduino.h>
#include <Wire.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef SERVO_ENABLED
#define SERVO_ENABLED 1
#endif
#ifndef PCA9685_ADDRESS
#define PCA9685_ADDRESS 0x40
#endif
#ifndef PCA9685_SDA
#define PCA9685_SDA 21
#endif
#ifndef PCA9685_SCL
#define PCA9685_SCL 22
#endif
#ifndef PCA9685_OSC_HZ
#define PCA9685_OSC_HZ 25000000UL
#endif
#ifndef SERVO_FREQUENCY_HZ
#define SERVO_FREQUENCY_HZ 50
#endif
#ifndef SERVO_CHANNELS
#define SERVO_CHANNELS 16
#endif
#ifndef SERVO_MIN_US
#define SERVO_MIN_US 1000
#endif
#ifndef SERVO_MAX_US
#define SERVO_MAX_US 2000
#endif
#ifndef SERVO_SLEW_US_PER_S
#define SERVO_SLEW_US_PER_S 500
#endif
#ifndef SERVO_HOLD_ON_DISCONNECT
#define SERVO_HOLD_ON_DISCONNECT 0
#endif

struct ServoLimit {
  uint16_t minUs;
  uint16_t maxUs;
};

#ifdef SERVO_LIMITS
// Rango por canal, en orden desde el canal 0: {{mín, máx}, ...}
constexpr ServoLimit servoLimits[] = SERVO_LIMITS;
constexpr uint8_t servoCount = sizeof(servoLimits) / sizeof(servoLimits[0]);
#else
constexpr uint8_t servoCount = SERVO_CHANNELS;
#endif

static_assert(servoCount >= 1 && servoCount <= 16, "El PCA9685 tiene 16 canales (0-15)");
static_assert(SERVO_FREQUENCY_HZ >= 40 && SERVO_FREQUENCY_HZ <= 400, "Frecuencia de servo fuera de 40-400 Hz");
static_assert(SERVO_SLEW_US_PER_S > 0, "SERVO_SLEW_US_PER_S debe ser positivo");

constexpr ServoLimit servoLimit(uint8_t channel) {
#ifdef SERVO_LIMITS
  return servoLimits[channel];
#else
  return (void)channel, ServoLimit{SERVO_MIN_US, SERVO_MAX_US};
#endif
}

constexpr bool limitsValid(uint8_t channel = 0) {
  return channel >= servoCount ||
         (servoLimit(channel).minUs >= 500 && servoLimit(channel).maxUs <= 2500 &&
          servoLimit(channel).minUs < servoLimit(channel).maxUs &&
          servoLimit(channel).maxUs < 1000000UL / SERVO_FREQUENCY_HZ && limitsValid(channel + 1));
}
static_assert(limitsValid(), "Cada rango de servo debe estar dentro de 500-2500 us, con mín < máx");

namespace pca9685 {
constexpr uint8_t mode1 = 0x00;
constexpr uint8_t mode2 = 0x01;
constexpr uint8_t led0OnL = 0x06;
constexpr uint8_t allLedOffH = 0xFD;
constexpr uint8_t prescale = 0xFE;
constexpr uint8_t sleep = 0x10;
constexpr uint8_t autoIncrement = 0x20;
constexpr uint8_t restart = 0x80;
constexpr uint8_t outdrv = 0x04;
constexpr uint8_t fullOff = 0x10;
constexpr uint32_t prescaleValue =
    (PCA9685_OSC_HZ + 2048UL * SERVO_FREQUENCY_HZ) / (4096UL * SERVO_FREQUENCY_HZ) - 1;
static_assert(prescaleValue >= 3 && prescaleValue <= 255, "Frecuencia fuera del rango del PCA9685");
}  // namespace pca9685

bool servoReady = false;
uint16_t servoCurrent[16] = {};  // 0 = sin pulso
uint16_t servoTarget[16] = {};
uint32_t servoUpdatedAt = 0;

bool pcaWrite(const uint8_t* data, size_t size) {
  Wire.beginTransmission(PCA9685_ADDRESS);
  Wire.write(data, size);
  return Wire.endTransmission() == 0;
}

bool pcaRegister(uint8_t reg, uint8_t value) {
  const uint8_t data[] = {reg, value};
  return pcaWrite(data, sizeof(data));
}

// Microsegundos a cuentas de 12 bits con la frecuencia real del prescaler.
uint16_t pulseTicks(uint16_t us) {
  const uint64_t ticks = (static_cast<uint64_t>(us) * PCA9685_OSC_HZ +
                          500000ULL * (pca9685::prescaleValue + 1)) /
                         (1000000ULL * (pca9685::prescaleValue + 1));
  return static_cast<uint16_t>(ticks > 4095 ? 4095 : ticks);
}

bool writePulse(uint8_t channel, uint16_t us) {
  const uint16_t off = us ? pulseTicks(us) : 0;
  const uint8_t data[] = {static_cast<uint8_t>(pca9685::led0OnL + 4 * channel), 0, 0,
                          static_cast<uint8_t>(off & 0xFF),
                          static_cast<uint8_t>(us ? off >> 8 : pca9685::fullOff)};
  return pcaWrite(data, sizeof(data));
}

void servosOff() {
  for (uint8_t channel = 0; channel < 16; ++channel) servoCurrent[channel] = servoTarget[channel] = 0;
  if (servoReady) pcaRegister(pca9685::allLedOffH, pca9685::fullOff);
}

void servoSetup() {
  if (!SERVO_ENABLED) return;
  Wire.begin(PCA9685_SDA, PCA9685_SCL);
  Wire.beginTransmission(PCA9685_ADDRESS);
  if (Wire.endTransmission() != 0) return;  // sin placa: SV responde ERR SV PCA9685
  // Salidas apagadas antes de despertar el oscilador.
  servoReady = pcaRegister(pca9685::allLedOffH, pca9685::fullOff) &&
               pcaRegister(pca9685::mode1, pca9685::sleep) &&
               pcaRegister(pca9685::prescale, static_cast<uint8_t>(pca9685::prescaleValue)) &&
               pcaRegister(pca9685::mode2, pca9685::outdrv) &&
               pcaRegister(pca9685::mode1, pca9685::autoIncrement);
  if (!servoReady) return;
  delay(1);  // el oscilador necesita 500 us
  servoReady = pcaRegister(pca9685::mode1, pca9685::restart | pca9685::autoIncrement);
}

// Acerca cada canal a su objetivo sin superar la velocidad configurada.
void servoUpdate(uint32_t now) {
  if (!servoReady || now - servoUpdatedAt < 20) return;
  const uint32_t step = (now - servoUpdatedAt) * SERVO_SLEW_US_PER_S / 1000;
  servoUpdatedAt = now;
  for (uint8_t channel = 0; channel < servoCount; ++channel) {
    const uint16_t current = servoCurrent[channel];
    const uint16_t target = servoTarget[channel];
    if (!target || current == target) continue;
    uint16_t next = target;
    if (current) {
      const uint32_t distance = current < target ? target - current : current - target;
      if (distance > step) next = current < target ? current + step : current - step;
    }
    if (writePulse(channel, next)) servoCurrent[channel] = next;
  }
}

void servoReleaseOnDisconnect() {
  if (!SERVO_HOLD_ON_DISCONNECT) servosOff();
}

bool isServoLine(const char* line) {
  return strncmp(line, "SV", 2) == 0 && (line[2] == '\0' || line[2] == ' ' ||
                                         strcmp(line, "SVOFF") == 0 || strcmp(line, "SVQ") == 0);
}

bool parseNumber(const char* text, long& value) {
  if (!*text || strlen(text) > 5) return false;
  for (const char* p = text; *p; ++p) {
    if (*p < '0' || *p > '9') return false;
  }
  value = strtol(text, nullptr, 10);
  return true;
}

// Responde por la misma vía que el resto del protocolo.
template <typename Reply>
void handleServo(const char* line, Reply reply) {
  char text[200];
  if (strcmp(line, "SVOFF") == 0) {
    servosOff();
    reply("OK SVOFF");
    return;
  }
  if (!servoReady) {
    reply("ERR SV PCA9685");
    return;
  }
  if (strcmp(line, "SVQ") == 0) {
    size_t used = snprintf(text, sizeof(text), "OK SVQ");
    bool any = false;
    for (uint8_t channel = 0; channel < servoCount; ++channel) {
      if (!servoTarget[channel]) continue;
      any = true;
      used += snprintf(text + used, sizeof(text) - used, " %u:%u/%u", channel,
                       servoCurrent[channel], servoTarget[channel]);
    }
    if (!any) snprintf(text + used, sizeof(text) - used, " -");
    reply(text);
    return;
  }
  char copy[24];
  if (strlen(line) >= sizeof(copy)) {
    reply("ERR SV FORMATO");
    return;
  }
  strcpy(copy, line);
  char* channelText = strtok(copy + 2, " ");
  char* usText = strtok(nullptr, " ");
  long channel = 0;
  long us = 0;
  if (!channelText || !usText || strtok(nullptr, " ") || !parseNumber(channelText, channel) ||
      !parseNumber(usText, us)) {
    reply("ERR SV FORMATO");
    return;
  }
  if (channel >= servoCount) {
    reply("ERR SV CANAL");
    return;
  }
  const ServoLimit limit = servoLimit(static_cast<uint8_t>(channel));
  if (us < limit.minUs || us > limit.maxUs) {
    snprintf(text, sizeof(text), "ERR SV RANGO %u-%u", limit.minUs, limit.maxUs);
    reply(text);
    return;
  }
  servoTarget[channel] = static_cast<uint16_t>(us);
  snprintf(text, sizeof(text), "OK SV %ld %ld", channel, us);
  reply(text);
}
