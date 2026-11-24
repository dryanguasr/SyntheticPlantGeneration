#include "../JawStateGuard.hh"
#include <stdexcept>
#include <limits>

void Check(bool value) { if (!value) throw std::runtime_error("Jaw guard contract failed"); }
int main()
{
  const uchuva::JawGuardParameters p{.006, 0, .0001, .001, .2};
  uchuva::JawStateGuard g(p);
  Check(!g.Reason(true, 0).empty());
  for (unsigned i=1; i<=22; ++i) g.Observe(.006, 0, i*.01, i);
  Check(g.Reason(true, 22).empty());
  Check(g.Reason(true, 23).empty());
  Check(!g.Reason(true, 24).empty());
  Check(g.Reason(false, 22)=="jaw_not_closed");
  g.Observe(0, 0, .23, 23);
  Check(g.Reason(false, 23)=="jaw_closed_stable_time_not_reached");
  for (unsigned i=24; i<=44; ++i) g.Observe(0, 0, i*.01, i);
  Check(g.Reason(false, 44).empty());
  g.Observe(0, .002, .45, 45);
  Check(g.Reason(false, 45)=="jaw_speed_too_high");
  g.Observe(0, 0, .46, 46);
  Check(g.Reason(false, 46)=="jaw_closed_stable_time_not_reached");
  g.Observe(0, 0, .70, 70); // skipped native steps cannot accrue stable time
  Check(g.StableSeconds(false)==0);
  g.Observe(0, 0, .70, 70); // repeated/paused observation cannot accrue time
  Check(g.StableSeconds(false)==0);
  g.Observe(0, std::numeric_limits<double>::quiet_NaN(), .71, 71);
  Check(!g.available && !g.Reason(false, 71).empty());
  bool rejected=false;
  try { uchuva::JawStateGuard invalid({.0001,0,.0001,.001,.2}); }
  catch (const std::invalid_argument &) { rejected=true; }
  Check(rejected);
}
