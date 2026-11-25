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

  // ---- Servos por PCA9685 ----
  // Arranque: 50 Hz (prescaler 121 con oscilador de 25 MHz), reinicio con
  // auto-incremento y todos los canales sin pulso.
  assert(servoReady && Wire.sdaPin == 21 && Wire.sclPin == 22);
  assert(pca.registers[0xFE] == 121 && pca.registers[0x00] == 0xA0);
  for (int channel = 0; channel < 16; ++channel) assert(pca.offTicks(channel) == -1);
  assert(pulseTicks(1500) == 307 && pulseTicks(1000) == 205 && pulseTicks(2000) == 410);

  auto arm = connectClient();
  assert(say(arm, 7000, token) == "AUTH OK\n");
  assert(say(arm, 7010, "SVQ\n") == "OK SVQ -\n");

  // Primera orden de un canal: va directa al objetivo (posición previa desconocida).
  assert(say(arm, 7020, "SV 0 1500\n") == "OK SV 0 1500\n");
  at(7040);
  assert(pca.offTicks(0) == 307 && pca.offTicks(1) == -1);

  // Después, el pulso avanza como máximo 500 us/s.
  assert(say(arm, 7060, "SV 0 2000\n") == "OK SV 0 2000\n");
  at(7080);
  assert(servoCurrent[0] == 1520);
  at(7580);
  assert(servoCurrent[0] == 1770);
  assert(say(arm, 7600, "SVQ\n") == "OK SVQ 0:1770/2000\n");
  at(8100);
  assert(servoCurrent[0] == 2000 && pca.offTicks(0) == 410);

  // Rango por canal, canal inexistente y formato: se rechazan sin mover nada.
  assert(say(arm, 8110, "SV 1 1900\n") == "ERR SV RANGO 1200-1800\n");
  assert(say(arm, 8120, "SV 1 1100\n") == "ERR SV RANGO 1200-1800\n");
  assert(say(arm, 8130, "SV 2 1500\n") == "ERR SV CANAL\n");
  assert(say(arm, 8140, "SV 0 abc\n") == "ERR SV FORMATO\n");
  assert(say(arm, 8150, "SV 0\n") == "ERR SV FORMATO\n");
  assert(say(arm, 8160, "SV 0 1500 9\n") == "ERR SV FORMATO\n");
  assert(say(arm, 8170, "SV -1 1500\n") == "ERR SV FORMATO\n");
  assert(servoTarget[0] == 2000 && servoTarget[1] == 0 && pca.offTicks(1) == -1);

  // Las órdenes de servo no alimentan el watchdog de los motores.
  assert(say(arm, 8300, "CF\n") == "OK CF 1010\n");
  assert(say(arm, 8400, "SV 1 1500\n") == "OK SV 1 1500\n");
  at(8549);
  assert(active == 'F');
  at(8550);
  assert(active == 'S' && !armed && motorsLow());
  assert(servoTarget[1] == 1500);  // los servos no dependen del watchdog de motores

  // Una línea larga sigue llegando al sketch, que aplica su desbordamiento.
  // El sketch lee como máximo 32 bytes por ciclo, igual que por USB.
  arm->send(std::string(60, 'F') + "\n");
  for (uint32_t time = 8600; time < 8604; ++time) at(time);
  assert(arm->take() == "ERR COMMAND\n");
  assert(!armed);

  // SVOFF corta el pulso de todos los canales.
  assert(say(arm, 8700, "SVOFF\n") == "OK SVOFF\n");
  assert(pca.offTicks(0) == -1 && pca.offTicks(1) == -1 && servoTarget[0] == 0);
  assert(say(arm, 8710, "SVQ\n") == "OK SVQ -\n");

  // Al desconectarse el puente, los servos quedan sin pulso.
  assert(say(arm, 8800, "SV 1 1500\n") == "OK SV 1 1500\n");
  at(8820);
  assert(pca.offTicks(1) == 307);
  arm->open = false;
  at(8821);
  assert(pca.offTicks(1) == -1 && servoTarget[1] == 0 && servoCurrent[1] == 0);

  // Sin PCA9685 en el bus: las órdenes de posición se rechazan.
  pca.present = false;
  servoReady = false;
  servoSetup();
  auto missing = connectClient();
  assert(say(missing, 9000, token) == "AUTH OK\n");
  assert(say(missing, 9010, "SV 0 1500\n") == "ERR SV PCA9685\n");
  assert(say(missing, 9020, "SVOFF\n") == "OK SVOFF\n");
  assert(say(missing, 9030, "ID\n") == "DRV8833_ROS_V5\n");

  std::puts("PASS drv8833_wifi mock");
}
