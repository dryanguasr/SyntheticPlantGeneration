#!/usr/bin/env bash
# Compila y ejecuta los simuladores nativos. Requiere g++ (por ejemplo en WSL)
# y haber ejecutado antes: python scripts/prepare_drv8833_wifi.py
#
# Compila desde una copia sin wifi_config.h: los simuladores usan siempre la
# configuración de test/, nunca las claves locales.
set -euo pipefail
cd "$(dirname "$0")/../../.."
fw=firmware/drv8833_wifi
for generated in drv8833_core.h servo_map.h; do
  test -f "$fw/$generated" || {
    echo "Falta $generated: ejecuta python scripts/prepare_drv8833_wifi.py" >&2
    exit 1
  }
done
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/test"
cp "$fw/drv8833_wifi.ino" "$fw/pca9685_servos.h" "$fw/drv8833_core.h" "$fw/servo_map.h" "$work/"
cp "$fw"/test/*.cpp "$work/test/"
mock=contributions/physalisharvest/firmware/bench_2wd/drv8833_ros/test

# Protocolo, motores y servos con dos canales de prueba (test/wifi_config.h).
g++ -std=c++17 -Wall -Wextra -Werror -I "$fw/test" -I "$mock" \
  "$work/test/wifi_mock.cpp" -o "$work/wifi-mock"
"$work/wifi-mock"

# Brazo de 5 GDL con el servo_map.h generado (test/arm/wifi_config.h).
g++ -std=c++17 -Wall -Wextra -Werror -I "$fw/test/arm" -I "$fw/test" -I "$mock" \
  "$work/test/arm_map_mock.cpp" -o "$work/arm-mock"
"$work/arm-mock"
