// Original project code, MIT. Pure controller, with no simulator state writes.
#pragma once
#include <gz/math/PID.hh>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <stdexcept>

namespace uchuva
{
struct PositionForceParameters
{
  double p, i, d, integralMin, integralMax, commandMin, commandMax;
  double velocity, lower, upper, initial;
};

struct PositionForceStep
{
  double reference, referenceRate, unsaturatedForce, force;
  bool saturated;
};

class PositionForceController
{
  public: explicit PositionForceController(const PositionForceParameters &_p)
      : parameters(_p), reference(_p.initial), target(_p.initial)
  {
    for (double value : {_p.p, _p.i, _p.d, _p.integralMin, _p.integralMax,
         _p.commandMin, _p.commandMax, _p.velocity, _p.lower, _p.upper, _p.initial})
      if (!std::isfinite(value)) throw std::invalid_argument("Non-finite controller parameter");
    if (_p.p < 0 || _p.i < 0 || _p.d < 0 || _p.integralMin > _p.integralMax ||
        _p.commandMin >= _p.commandMax || _p.commandMin > 0 || _p.commandMax < 0 ||
        _p.velocity <= 0 || _p.lower >= _p.upper || _p.initial < _p.lower || _p.initial > _p.upper)
      throw std::invalid_argument("Invalid controller bounds or gains");
    // Disable only the PID output clamp so the raw effort remains observable;
    // clamp the actual command below using the same configured motor limits.
    this->pid.Init(_p.p, _p.i, _p.d, _p.integralMax, _p.integralMin, -1, 0);
  }
  public: bool SetTarget(double _target)
  {
    if (!std::isfinite(_target) || _target < this->parameters.lower ||
        _target > this->parameters.upper) return false;
    this->target = _target;
    return true;
  }
  public: PositionForceStep Step(double _position, double _velocity, double _dt)
  {
    if (!std::isfinite(_position) || !std::isfinite(_velocity) ||
        !std::isfinite(_dt) || _dt <= 0)
      throw std::invalid_argument("Missing or non-finite native state / step");
    const double increment = std::clamp(this->target-this->reference,
        -this->parameters.velocity*_dt, this->parameters.velocity*_dt);
    this->reference += increment;
    // D on the measurement: a transported target step cannot create D kick.
    const double raw = this->pid.Update(_position-this->reference, _velocity,
        std::chrono::duration<double>(_dt));
    if (!std::isfinite(raw)) throw std::runtime_error("Non-finite controller effort");
    const double force = std::clamp(raw, this->parameters.commandMin, this->parameters.commandMax);
    return {this->reference, increment/_dt, raw, force, raw != force};
  }
  public: void Reset()
  {
    this->pid.Reset();
    this->reference = this->target = this->parameters.initial;
  }
  public: double Target() const { return this->target; }
  public: double Reference() const { return this->reference; }
  private: PositionForceParameters parameters;
  private: gz::math::PID pid;
  private: double reference, target;
};
}
