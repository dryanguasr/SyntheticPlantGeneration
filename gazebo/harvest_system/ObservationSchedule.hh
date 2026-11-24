// Original project code, MIT. Observation only; never changes physics steps.
#pragma once
#include <cmath>
#include <stdexcept>

namespace uchuva
{
inline double NextObservationTime(double time, double period)
{
  if (!std::isfinite(time) || time < 0 || !std::isfinite(period) || period <= 0)
    throw std::invalid_argument("Invalid observation clock");
  // Anchor publications at simulation zero. Scheduling from the first step
  // would offset every joint message by dt relative to PosePublisher. Both
  // publishers share the grid when its period is an integer number of steps.
  return (std::floor((time + 1e-12) / period) + 1) * period;
}
}
