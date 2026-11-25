// Simulador del brazo de 5 GDL: el firmware aplica el servo_map.h generado
// desde configs/robots/brazo_5gdl_servos.json (rango y velocidad por canal).
// Las comprobaciones leen el mapa compilado, así siguen valiendo si el JSON cambia.
#include <cassert>
#include <cstdio>
#include <string>

#include "../drv8833_wifi.ino"

#ifndef SERVO_SLEW_LIMITS
#error "El simulador del brazo necesita el servo_map.h generado"
#endif

static const std::string token = std::string("AUTH ") + BRIDGE_TOKEN + "\n";
static uint32_t clockMs = 100;

std::string say(const std::shared_ptr<MockConnection>& link, const std::string& text) {
  link->send(text);
  simulatedMs = clockMs += 10;
  loop();
  return link->take();
}

std::string order(uint8_t channel, long us) {
  return "SV " + std::to_string(channel) + " " + std::to_string(us) + "\n";
}

int main() {
  setup();
  auto bridge = connectClient();
  assert(say(bridge, token) == "AUTH OK\n");

  uint8_t used = 0;
  for (uint8_t channel = 0; channel < servoCount; ++channel) {
    if (!channelUsed(channel)) {
      assert(say(bridge, order(channel, 1500)) == "ERR SV CANAL\n");
      continue;
    }
    ++used;
    const ServoLimit limit = servoLimit(channel);
    char range[48];
    std::snprintf(range, sizeof(range), "ERR SV RANGO %u-%u\n", limit.minUs, limit.maxUs);
    assert(say(bridge, order(channel, limit.minUs - 1)) == range);
    assert(say(bridge, order(channel, limit.maxUs + 1)) == range);
    assert(say(bridge, order(channel, limit.minUs)) == "OK " + order(channel, limit.minUs));
  }
  assert(used >= 1);
  assert(say(bridge, order(servoCount, 1500)) == "ERR SV CANAL\n");

  // Velocidad propia de cada canal: de mín a máx en pasos de su SERVO_SLEW_LIMITS.
  for (int tick = 0; tick < 3; ++tick) say(bridge, "SVQ\n");
  for (uint8_t channel = 0; channel < servoCount; ++channel) {
    if (!channelUsed(channel)) continue;
    assert(servoCurrent[channel] == servoLimit(channel).minUs);
    assert(say(bridge, order(channel, servoLimit(channel).maxUs)) ==
           "OK " + order(channel, servoLimit(channel).maxUs));
    const uint16_t start = servoCurrent[channel];
    const uint32_t since = servoUpdatedAt;
    simulatedMs = clockMs += 400;
    loop();
    const uint32_t expected = start + (simulatedMs - since) * servoSlew(channel) / 1000;
    assert(servoCurrent[channel] ==
           (expected < servoLimit(channel).maxUs ? expected : servoLimit(channel).maxUs));
  }

  // Al perder el puente, todo el brazo queda sin pulso.
  bridge->open = false;
  simulatedMs = clockMs += 1;
  loop();
  for (uint8_t channel = 0; channel < 16; ++channel) assert(pca.offTicks(channel) == -1);

  std::printf("PASS brazo 5 GDL: %u articulaciones en %u canales\n", used, servoCount);
}
