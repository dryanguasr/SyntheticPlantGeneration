cmake_minimum_required(VERSION 3.16)
project(UchuvaHarvestSystem LANGUAGES CXX)

# Gazebo Harmonic / ROS 2 Jazzy. Keep this runtime independent of Python's
# morphology exporter and of a particular robot description.
find_package(gz-plugin2 REQUIRED COMPONENTS register)
find_package(gz-sim8 REQUIRED)
find_package(gz-transport13 REQUIRED)
find_package(gz-msgs10 REQUIRED)

add_library(UchuvaHarvestSystem SHARED HarvestSystem.cc)
target_compile_features(UchuvaHarvestSystem PRIVATE cxx_std_17)
target_compile_options(UchuvaHarvestSystem PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(UchuvaHarvestSystem PRIVATE
  gz-plugin2::gz-plugin2
  gz-sim8::gz-sim8
  gz-transport13::gz-transport13
  gz-msgs10::gz-msgs10
)

install(TARGETS UchuvaHarvestSystem LIBRARY DESTINATION lib)

add_library(UchuvaRobotTelemetrySystem SHARED RobotTelemetrySystem.cc)
target_compile_features(UchuvaRobotTelemetrySystem PRIVATE cxx_std_17)
target_compile_options(UchuvaRobotTelemetrySystem PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(UchuvaRobotTelemetrySystem PRIVATE
  gz-plugin2::gz-plugin2 gz-sim8::gz-sim8
  gz-transport13::gz-transport13 gz-msgs10::gz-msgs10)
install(TARGETS UchuvaRobotTelemetrySystem LIBRARY DESTINATION lib)

add_library(UchuvaClosedLoopSystem SHARED ClosedLoopSystem.cc)
target_compile_features(UchuvaClosedLoopSystem PRIVATE cxx_std_17)
target_compile_options(UchuvaClosedLoopSystem PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(UchuvaClosedLoopSystem PRIVATE
  gz-plugin2::gz-plugin2 gz-sim8::gz-sim8)
install(TARGETS UchuvaClosedLoopSystem LIBRARY DESTINATION lib)

add_library(UchuvaGearCouplingSystem SHARED GearCouplingSystem.cc)
target_compile_features(UchuvaGearCouplingSystem PRIVATE cxx_std_17)
target_compile_options(UchuvaGearCouplingSystem PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(UchuvaGearCouplingSystem PRIVATE
  gz-plugin2::gz-plugin2 gz-sim8::gz-sim8
  gz-transport13::gz-transport13 gz-msgs10::gz-msgs10)
install(TARGETS UchuvaGearCouplingSystem LIBRARY DESTINATION lib)

add_library(UchuvaJointPositionForceSystem SHARED JointPositionForceSystem.cc)
target_compile_features(UchuvaJointPositionForceSystem PRIVATE cxx_std_17)
target_compile_options(UchuvaJointPositionForceSystem PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(UchuvaJointPositionForceSystem PRIVATE
  gz-plugin2::gz-plugin2 gz-sim8::gz-sim8
  gz-transport13::gz-transport13 gz-msgs10::gz-msgs10)
install(TARGETS UchuvaJointPositionForceSystem LIBRARY DESTINATION lib)

include(CTest)
if(BUILD_TESTING)
  add_executable(PositionForceControllerTest tests/PositionForceControllerTest.cc)
  target_compile_features(PositionForceControllerTest PRIVATE cxx_std_17)
  target_link_libraries(PositionForceControllerTest PRIVATE gz-sim8::gz-sim8)
  add_test(NAME PositionForceControllerContracts COMMAND PositionForceControllerTest)
endif()
