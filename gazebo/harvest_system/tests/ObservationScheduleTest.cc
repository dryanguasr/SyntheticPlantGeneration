#include "../ObservationSchedule.hh"
#include <cmath>
#include <limits>
#include <vector>

void require(bool condition)
{
  if (!condition) throw std::runtime_error("Observation schedule contract failed");
}

int main()
{
  for (double dt : {.0001, .00005})
  {
    double next=0;
    std::vector<double> emitted;
    for (int i=1; i<=static_cast<int>(std::round(.03/dt)); ++i)
    {
      const double time=i*dt;
      if (time+1e-12 < next) continue;
      emitted.push_back(time);
      next=uchuva::NextObservationTime(time,.01);
    }
    require(emitted.size()==4);
    require(emitted.front()==dt);
    for (int i=1; i<4; ++i) require(std::abs(emitted[i]-.01*i)<1e-12);
    // Step-rate diagnostics must retain every observation.
    for (int i=1; i<100; ++i)
      require(std::abs(uchuva::NextObservationTime(i*dt,dt)-(i+1)*dt)<1e-12);
  }
  bool rejected=false;
  try { uchuva::NextObservationTime(0,std::numeric_limits<double>::quiet_NaN()); }
  catch (const std::invalid_argument &) { rejected=true; }
  require(rejected);
}
