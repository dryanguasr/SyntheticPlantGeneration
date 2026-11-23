// Original project code, MIT. Exercise production controller, not a Python copy.
#include "../PositionForceController.hh"
#include <iostream>
#include <limits>
#include <stdexcept>

void Check(bool value, const char *message)
{
  if (!value) throw std::runtime_error(message);
}
int main()
{
  using uchuva::PositionForceController;
  using uchuva::PositionForceParameters;
  try
  {
    PositionForceParameters parameters{.2, 0, .01, 0, 0, -.02, .02, .2, -.4, .4, 0};
    PositionForceController controller(parameters);
    Check(!controller.SetTarget(std::numeric_limits<double>::quiet_NaN()), "NaN target admitted");
    Check(!controller.SetTarget(.400001), "Out-of-range target admitted");
    Check(controller.Target() == 0, "Rejected target changed reference destination");
    Check(controller.SetTarget(.04), "Valid target rejected");
    const auto first = controller.Step(0, 0, .0001);
    Check(std::abs(first.reference-2e-5) < 1e-15, "Native rate bound violated");
    Check(std::abs(first.unsaturatedForce-4e-6) < 1e-15, "Target jump caused derivative kick");
    const auto moving = controller.Step(first.reference, .5, .0001);
    Check(moving.force < 0, "Measured positive velocity is not damped");
    const auto saturated = controller.Step(-.4, -10, .0001);
    Check(saturated.force == .02 && saturated.saturated && saturated.unsaturatedForce > .02,
          "Raw effort/clamped effort/saturation not distinguished");
    for (int index=0; index<3000; ++index)
    {
      const auto step = controller.Step(.04, 0, .0001);
      Check(std::abs(step.referenceRate) <= .2+1e-12 && step.reference <= .04,
            "Ramp exceeded speed or target");
    }
    Check(std::abs(controller.Reference()-.04) < 1e-14, "Ramp never reached target");
    controller.Reset();
    Check(controller.Reference() == 0 && controller.Target() == 0, "Reset changed CAD initial reference");
    bool rejected=false;
    try { controller.Step(0, 0, 0); } catch (const std::invalid_argument &) { rejected=true; }
    Check(rejected, "Zero timestep admitted");
    rejected=false;
    try { controller.Step(0, std::numeric_limits<double>::infinity(), .001); }
    catch (const std::invalid_argument &) { rejected=true; }
    Check(rejected, "Non-finite observation admitted");
    parameters.p=0; parameters.i=1; parameters.d=0;
    parameters.integralMin=-.005; parameters.integralMax=.005;
    PositionForceController integral(parameters);
    for (int index=0; index<10000; ++index) integral.Step(-.1, 0, .001);
    Check(std::abs(integral.Step(-.1, 0, .001).unsaturatedForce-.005) < 1e-14,
          "Configured integral clamp did not limit windup");
    std::cout << "PASS: target rejection, native ramp, measured D sign/no target kick, "
              << "effort saturation, reset, state rejection and configured integral clamp\n";
    return 0;
  }
  catch (const std::exception &error)
  {
    std::cerr << "FAIL: " << error.what() << '\n'; return 1;
  }
}
