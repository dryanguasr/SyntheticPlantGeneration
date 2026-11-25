#!/usr/bin/env bash
# Compila y ejecuta el simulador nativo. Requiere g++ (por ejemplo en WSL) y
# haber ejecutado antes: python scripts/prepare_drv8833_wifi.py
set -euo pipefail
cd "$(dirname "$0")/../../.."
test -f firmware/drv8833_wifi/drv8833_core.h || {
  echo "Falta drv8833_core.h: ejecuta python scripts/prepare_drv8833_wifi.py" >&2
  exit 1
}
g++ -std=c++17 -Wall -Wextra -Werror \
  -I firmware/drv8833_wifi/test \
  -I contributions/physalisharvest/firmware/bench_2wd/drv8833_ros/test \
  firmware/drv8833_wifi/test/wifi_mock.cpp -o /tmp/drv8833-wifi-mock
/tmp/drv8833-wifi-mock
