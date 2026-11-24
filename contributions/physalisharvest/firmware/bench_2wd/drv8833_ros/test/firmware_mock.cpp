#include <cassert>
#include "../drv8833_ros.ino"

void at(uint32_t time) {
  simulatedMs = time;
  loop();
}

std::string command(uint32_t time, const std::string& text) {
  for (char value : text + "\n") Serial.input.push_back(value);
  at(time);
  return Serial.output;
}

int main() {
  setup();
  assert(command(100, "F") == "ERR COMMAND\n");
  assert(command(110, "ID") == "DRV8833_ROS_V5\n");
  assert(command(120, "CF") == "OK CF 1010\n");
  assert(duties[25] == 242 && duties[27] == 255);
  assert(command(130, "L") == "OK L 0000\n");
  at(229);
  assert(active == 'S');
  assert(command(230, "L") == "OK L 0110\n");
  assert(duties[26] == 255 && duties[27] == 255);
  assert(command(240, "R") == "OK R 0000\n");
  assert(command(340, "R") == "OK R 1001\n");
  assert(duties[25] == 255 && duties[14] == 255);
  at(589);
  assert(active == 'R' && armed);
  at(590);
  assert(active == 'S' && !armed);
  assert(command(591, "F") == "ERR COMMAND\n");
  assert(command(700, "CF") == "OK CF 1010\n");
  assert(command(710, "AAAAAAAAAAAAAAAAAAAA") == "ERR COMMAND\n");
  assert(active == 'S' && !armed);
  assert(command(820, "CF") == "OK CF 1010\n");
  for (uint32_t now = 920; now <= 60820; now += 100)
    assert(command(now, "F") == "OK F 1010\n");
  assert(command(61070, "F") == "ERR COMMAND\n");
  assert(active == 'S' && !armed);
  assert(command(UINT32_MAX - 50, "CR") == "OK CR 1001\n");
  at(199);
  assert(active == 'S' && !armed);
  assert(command(201, "S") == "OK S 0000\n");
  assert(command(300, "CQ") == "OK CQ 0110\n");
  assert(duties[26] == 255 && duties[27] == 255 && !duties[25] && !duties[14]);
  assert(command(350, "Q") == "OK Q 0110\n");
  assert(command(450, "S") == "OK S 0000\n");
  assert(!duties[26] && !duties[27]);
  failPwmPin = 27;
  assert(command(550, "CQ") == "ERR PWM\n");
  assert(!armed && !duties[26] && !duties[27]);
  assert(command(551, "ID") == "ERR PWM\n");
}
