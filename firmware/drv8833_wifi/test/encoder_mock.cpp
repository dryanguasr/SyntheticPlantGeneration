// Simulador de los encoders AS5600 por WiFi: TCA9548A y sensores MOCK en el
// mismo bus que el PCA9685, como en el test 01 de encoders del equipo.
#include <cassert>
#include <cstdio>
#include <string>

#include "../drv8833_wifi.ino"

static const std::string token = std::string("AUTH ") + BRIDGE_TOKEN + "\n";
static uint32_t clockMs = 100;

std::string say(const std::shared_ptr<MockConnection>& link, const std::string& text) {
  link->send(text);
  simulatedMs = clockMs += 10;
  loop();
  return link->take();
}

int main() {
  setup();
  assert(Wire.clock == 100000 && Wire.sdaPin == 21 && Wire.sclPin == 22);
  assert(!encoderMux && !encoderDirect);

  auto bridge = connectClient();
  assert(say(bridge, token) == "AUTH OK\n");

  // Sin sensores en el bus.
  assert(say(bridge, "ENQ\n") == "ERR EN SIN SENSORES\n");

  // Multiplexor conectado después del arranque: se detecta en la siguiente
  // consulta. Cada estado del imán como en el test 01; el canal 2 sin sensor.
  muxPresent = true;
  muxEncoders[0].set(1024, 0x20);         // imán OK
  muxEncoders[1].set(0xF000 | 4095, 0x08);  // muy cerca; bits altos ignorados
  muxEncoders[3].set(0, 0x10);            // muy lejos
  muxEncoders[4].set(2048, 0x00);         // no detectado
  assert(say(bridge, "ENQ\n") == "OK ENQ 0:1024:OK 1:4095:MH 2:-- 3:0:ML 4:2048:NM\n");
  assert(encoderMux && muxSelection == 0);  // canales cerrados tras leer

  // Un AS5600 en el canal 5 no se consulta: solo J1-J5 llevan encoder.
  muxEncoders[5].set(77, 0x20);
  assert(say(bridge, "ENQ\n") == "OK ENQ 0:1024:OK 1:4095:MH 2:-- 3:0:ML 4:2048:NM\n");

  // El PCA9685 del bus principal sigue respondiendo con el multiplexor presente.
  assert(say(bridge, "SV 0 1500\n") == "OK SV 0 1500\n");
  simulatedMs = clockMs += 30;
  loop();
  assert(pca.offTicks(0) == 307);

  // Las consultas de encoder no llegan al sketch de motores ni lo alimentan.
  assert(say(bridge, "ENQ X\n") == "ERR COMMAND\n");

  // Modo directo: un solo AS5600 sin multiplexor es el encoder 0.
  muxPresent = false;
  for (auto& encoder : muxEncoders) encoder = MockAs5600{};
  directEncoder.set(512, 0x20);
  encoderDetect();
  assert(encoderDirect && !encoderMux);
  assert(say(bridge, "ENQ\n") == "OK ENQ 0:512:OK 1:-- 2:-- 3:-- 4:--\n");

  // Sensor que deja de responder: se informa sin bloquear el resto.
  directEncoder.present = false;
  assert(say(bridge, "ENQ\n") == "OK ENQ 0:-- 1:-- 2:-- 3:-- 4:--\n");

  std::puts("PASS encoders AS5600");
}
