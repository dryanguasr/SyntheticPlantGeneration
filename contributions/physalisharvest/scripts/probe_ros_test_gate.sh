#!/usr/bin/env bash
# A disposable CMake package exercises the same test gate as the ROS job.
set -eo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace=$(mktemp -d "${RUNNER_TEMP:-/tmp}/ros-gate.XXXXXX")
trap 'rm -rf -- "$workspace"' EXIT
mkdir -p "$workspace/src/ci_gate_probe" "${1:?log directory required}"
logs=$1
cat > "$workspace/src/ci_gate_probe/package.xml" <<'XML'
<?xml version="1.0"?>
<package format="3"><name>ci_gate_probe</name><version>0.0.0</version><description>Disposable CI gate probe</description><maintainer email="ci@example.invalid">CI</maintainer><license>UNLICENSED</license><export><build_type>cmake</build_type></export></package>
XML
cat > "$workspace/src/ci_gate_probe/CMakeLists.txt" <<'CMAKE'
cmake_minimum_required(VERSION 3.16)
project(ci_gate_probe)
enable_testing()
add_test(NAME probe COMMAND ${CMAKE_COMMAND} -P ${CMAKE_CURRENT_SOURCE_DIR}/probe.cmake)
CMAKE
echo 'message(FATAL_ERROR "intentional failure")' > "$workspace/src/ci_gate_probe/probe.cmake"
(cd "$workspace" && colcon build) 2>&1 | tee "$logs/probe-build.log"
if bash "$root/scripts/run_ros_tests.sh" "$workspace" "$logs/failure"; then
  echo 'FAIL: la prueba intencionalmente fallida no detuvo la puerta ROS.'
  exit 1
fi
if ! grep -qi 'intentional failure' "$logs/failure/test.log" "$logs/failure/test-result.log"; then
  echo 'FAIL: no se encontró evidencia de la prueba intencional; no atribuir el error a la puerta.'
  exit 1
fi
echo 'PASS: la prueba ROS fallida produjo salida distinta de cero.'
echo 'message(STATUS "intentional success")' > "$workspace/src/ci_gate_probe/probe.cmake"
if ! bash "$root/scripts/run_ros_tests.sh" "$workspace" "$logs/success"; then
  echo 'FAIL: la prueba corregida no pasó.'
  exit 1
fi
echo 'PASS: la prueba ROS corregida pasó.'
