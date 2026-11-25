// Simulador nativo del transporte WiFi. Reloj, GPIO y red son MOCK.
// Ejecutar con: python scripts/prepare_drv8833_wifi.py && bash firmware/drv8833_wifi/test/run.sh
#include <cassert>
#include <cstdio>
#include <string>

#include "../drv8833_wifi.ino"

static const std::string token = std::string("AUTH ") + BRIDGE_TOKEN + "\n";

void at(uint32_t time) {
  simulatedMs = time;
  loop();
}

std::string say(const std::shared_ptr<MockConnection>& link, uint32_t time, const std::string& text) {
  link->send(text);
  at(time);
  return link->take();
}

bool motorsLow() { return !duties[25] && !duties[26] && !duties[27] && !duties[14]; }

int main() {
  setup();
  at(1);
  assert(Serial.output.find("DRV8833_WIFI ") == 0);  // dirección por USB

  // Sin AUTH, una orden válida no llega al firmware y la conexión se cierra.
  auto intruder = connectClient();
  assert(say(intruder, 10, "CF\n") == "AUTH ERR\n");
  assert(!intruder->open && !armed && motorsLow());

  // Token incorrecto.
  auto wrong = connectClient();
  assert(say(wrong, 20, "AUTH otro-token-cualquiera\n") == "AUTH ERR\n");
  assert(!wrong->open);

  // Línea de autenticación desbordada.
  auto flood = connectClient();
  assert(say(flood, 30, std::string(80, 'A')) == "AUTH ERR\n");
  assert(!flood->open);

  // Cliente legítimo: mismo protocolo y acuses que por USB. El sketch original
  // exige 100 ms tras una parada antes de mover (directionPauseMs).
  auto bridge = connectClient();
  assert(say(bridge, 200, token) == "AUTH OK\n");
  assert(bridge->noDelay);
  assert(say(bridge, 210, "ID\n") == "DRV8833_ROS_V5\n");
  assert(say(bridge, 220, "CF\n") == "OK CF 1010\n");
  assert(armed && duties[25] == 242 && duties[27] == 255);

  // Un segundo cliente no puede tomar el control.
  auto rival = connectClient();
  at(230);
  assert(rival->take() == "ERR BUSY\n" && !rival->open);
  assert(armed && bridge->open);

  // El watchdog original de 250 ms sigue activo sobre WiFi.
  assert(say(bridge, 300, "F\n") == "OK F 1010\n");
  at(549);
  assert(active == 'F');
  at(550);
  assert(active == 'S' && !armed && motorsLow());

  // Desconexión con los motores en marcha: parada inmediata.
  assert(say(bridge, 700, "CR\n") == "OK CR 1001\n");
  assert(armed && duties[25] == 255 && duties[14] == 255);
  bridge->open = false;
  at(701);
  assert(!armed && active == 'S' && motorsLow());

  // La ranura queda libre tras la desconexión.
  auto next = connectClient();
  assert(say(next, 800, token) == "AUTH OK\n");

  // Una orden a medias del cliente anterior no se mezcla con la siguiente.
  next->send("C");
  at(810);
  next->open = false;
  at(811);
  auto fresh = connectClient();
  assert(say(fresh, 820, token) == "AUTH OK\n");
  assert(say(fresh, 830, "S\n") == "OK S 0000\n");

  // Cliente autenticado inactivo: se libera a los 3 s.
  at(3829);
  assert(fresh->open);
  at(3830);
  assert(!fresh->open && !armed);

  // Cliente sin AUTH: se libera a los 2 s.
  auto silent = connectClient();
  at(4000);
  at(5999);
  assert(silent->open);
  at(6000);
  assert(!silent->open);

  std::puts("PASS drv8833_wifi mock");
}
