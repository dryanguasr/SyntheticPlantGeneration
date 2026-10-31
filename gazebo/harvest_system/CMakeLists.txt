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
