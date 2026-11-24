// Original project code, MIT. Native observation guard, not a contact model.
#ifndef UCHUVA_JAW_STATE_GUARD_HH_
#define UCHUVA_JAW_STATE_GUARD_HH_

#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>

namespace uchuva
{
struct JawGuardParameters
{
  double openPosition{0}, closedPosition{0}, positionTolerance{0};
  double maxSpeed{0}, stableTime{0};
};

// All coordinates are measured prismatic SI coordinates (m, m/s). A requested
// target, a fixed joint or an unavailable native state cannot satisfy the guard.
class JawStateGuard
{
  public: explicit JawStateGuard(const JawGuardParameters &_parameters)
      : parameters(_parameters)
  {
    const auto &p = this->parameters;
    if (!std::isfinite(p.openPosition) || !std::isfinite(p.closedPosition) ||
        !std::isfinite(p.positionTolerance) || p.positionTolerance <= 0 ||
        !std::isfinite(p.maxSpeed) || p.maxSpeed <= 0 ||
        !std::isfinite(p.stableTime) || p.stableTime <= 0 ||
        std::abs(p.openPosition - p.closedPosition) <= 2*p.positionTolerance)
      throw std::invalid_argument("Invalid or overlapping prismatic jaw guard limits");
  }

  public: void Observe(double _position, double _velocity, double _time,
      std::uint64_t _iteration)
  {
    const bool finite = std::isfinite(_position) && std::isfinite(_velocity) &&
                        std::isfinite(_time);
    const bool continuous = this->available && _iteration == this->iteration+1 &&
                            _time > this->time;
    if (!continuous) this->openSince = this->closedSince = Unknown;
    this->available = finite;
    this->position = _position;
    this->velocity = _velocity;
    this->time = _time;
    this->iteration = _iteration;
    const bool still = finite && std::abs(_velocity) <= this->parameters.maxSpeed;
    this->UpdateSince(still && std::abs(_position-this->parameters.openPosition) <=
                      this->parameters.positionTolerance, this->openSince);
    this->UpdateSince(still && std::abs(_position-this->parameters.closedPosition) <=
                      this->parameters.positionTolerance, this->closedSince);
  }

  public: bool Fresh(std::uint64_t _currentIteration) const
  {
    // PostUpdate consumes the current sample; the following PreUpdate consumes
    // that same completed physics sample. A missing step fails closed.
    return this->available && (_currentIteration == this->iteration ||
                              _currentIteration == this->iteration+1);
  }

  public: double StableSeconds(bool _open) const
  {
    const double since = _open ? this->openSince : this->closedSince;
    return this->available && std::isfinite(since) ? this->time-since : 0;
  }

  public: std::string Reason(bool _open, std::uint64_t _currentIteration) const
  {
    if (!this->Fresh(_currentIteration)) return "jaw_observation_unavailable_or_stale";
    if (std::abs(this->velocity) > this->parameters.maxSpeed) return "jaw_speed_too_high";
    const double target = _open ? this->parameters.openPosition : this->parameters.closedPosition;
    if (std::abs(this->position-target) > this->parameters.positionTolerance)
      return _open ? "jaw_not_open" : "jaw_not_closed";
    if (this->StableSeconds(_open) + 1e-12 < this->parameters.stableTime)
      return _open ? "jaw_open_stable_time_not_reached" : "jaw_closed_stable_time_not_reached";
    return "";
  }

  public: JawGuardParameters parameters;
  public: double position{Unknown}, velocity{Unknown}, time{Unknown};
  public: std::uint64_t iteration{0};
  public: bool available{false};
  private: static constexpr double Unknown = std::numeric_limits<double>::quiet_NaN();
  private: double openSince{Unknown}, closedSince{Unknown};
  private: void UpdateSince(bool _valid, double &_since)
  {
    if (!_valid) _since = Unknown;
    else if (!std::isfinite(_since)) _since = this->time;
  }
};
}
#endif
