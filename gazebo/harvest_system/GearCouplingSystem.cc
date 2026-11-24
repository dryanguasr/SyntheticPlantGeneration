// Original project code, MIT. A passive, compliant ideal-ratio gear reduction.
// This is a finite torsional spring/damper, NOT DART's unsupported mimic joint,
// a position command, a second motor, or a validated hardware gear stiffness.
#include <gz/common/Console.hh>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Joint.hh>
#include <gz/sim/Link.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/transport/Node.hh>
#include <sdf/Element.hh>
#include <sdf/Joint.hh>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <locale>
#include <sstream>
#include <string>

namespace uchuva
{
class GearCouplingSystem final : public gz::sim::System,
    public gz::sim::ISystemConfigure,
    public gz::sim::ISystemConfigurePriority,
    public gz::sim::ISystemPreUpdate,
    public gz::sim::ISystemReset
{
  // After the motor controller (0), before command observation (100).
  public: gz::sim::System::PriorityType ConfigurePriority() override { return 50; }
  public: void Configure(const gz::sim::Entity &_entity,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &_ecm, gz::sim::EventManager &) override
  {
    const gz::sim::Model model(_entity);
    auto config = _sdf->Clone();
    this->driver = gz::sim::Joint(model.JointByName(_ecm, config->Get<std::string>("driver")));
    this->follower = gz::sim::Joint(model.JointByName(_ecm, config->Get<std::string>("follower")));
    this->ratio = config->Get<double>("ratio");
    this->offset = config->Get<double>("offset", 0).first;
    this->stiffness = config->Get<double>("stiffness_nm_rad");
    this->damping = config->Get<double>("damping_nms_rad");
    this->maximumStep = config->Get<double>("maximum_step_s");
    const double publishRate = config->Get<double>("publish_rate", 100).first;
    this->hash = config->Get<std::string>("robot_spec_sha256", "").first;
    if (!this->driver.Valid(_ecm) || !this->follower.Valid(_ecm) ||
        this->driver.Entity() == this->follower.Entity() || this->hash.empty() ||
        !std::isfinite(this->ratio) || std::abs(this->ratio) < 1e-12 ||
        !std::isfinite(this->offset) || !std::isfinite(this->stiffness) ||
        this->stiffness <= 0 || !std::isfinite(this->damping) || this->damping < 0 ||
        !std::isfinite(this->maximumStep) || this->maximumStep <= 0 ||
        !std::isfinite(publishRate) || publishRate <= 0 || publishRate > 10000)
    {
      gzerr << "GearCouplingSystem: invalid explicit gear parameters\n";
      return;
    }
    this->publishPeriod = 1/publishRate;
    this->driver.EnablePositionCheck(_ecm);
    this->driver.EnableVelocityCheck(_ecm);
    this->follower.EnablePositionCheck(_ecm);
    this->follower.EnableVelocityCheck(_ecm);
    if (!this->ResolveTorquePair(this->driver, model, _ecm, this->driverPair) ||
        !this->ResolveTorquePair(this->follower, model, _ecm, this->followerPair))
    {
      gzerr << "GearCouplingSystem: requires resolved revolute axes and two physical links per joint\n";
      return;
    }
    this->publisher = this->node.Advertise<gz::msgs::StringMsg>(
        config->Get<std::string>("topic", "/harvester/gear_coupling").first);
    this->valid = true;
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &_info,
      gz::sim::EntityComponentManager &_ecm) override
  {
    if (!this->valid || _info.paused) return;
    const double dt = std::chrono::duration<double>(_info.dt).count();
    if (dt <= 0 || dt > this->maximumStep * (1+1e-9))
    {
      gzerr << "GearCouplingSystem: simulation step exceeds validated coupling step\n";
      this->valid = false;
      return;
    }
    const auto a = this->driver.Position(_ecm), b = this->follower.Position(_ecm);
    const auto da = this->driver.Velocity(_ecm), db = this->follower.Velocity(_ecm);
    if (!a || !b || !da || !db || a->empty() || b->empty() || da->empty() || db->empty()) return;
    const double error = b->at(0) - this->ratio*a->at(0) - this->offset;
    const double rate = db->at(0) - this->ratio*da->at(0);
    const double reaction = this->stiffness*error + this->damping*rate;
    if (!std::isfinite(reaction))
    {
      gzerr << "GearCouplingSystem: non-finite state, coupling disabled\n";
      this->valid = false;
      return;
    }
    // e=q_f-r*q_d-offset; U=.5*k*e^2. These generalized forces satisfy
    // tau_d*dq_d+tau_f*dq_f = -dU/dt-c*(de/dt)^2. No motor-like energy input.
    // Internal torque pairs act on links, separate from the single motor's
    // JointForceCmd. Parent reactions conserve angular momentum and cannot be
    // clipped by the motor effort limit or overwrite a motor controller.
    this->AddTorquePair(this->driverPair, this->ratio*reaction, _ecm);
    this->AddTorquePair(this->followerPair, -reaction, _ecm);
    const double time = std::chrono::duration<double>(_info.simTime).count();
    if (time - this->lastPublish + 1e-12 < this->publishPeriod) return;
    this->lastPublish = time;
    std::ostringstream out;
    out.imbue(std::locale::classic()); out << std::setprecision(17);
    out << "{\"robot_spec_sha256\":\"" << this->hash << "\",\"sim_time\":" << time
        << ",\"sample_phase\":\"pre_physics\",\"application\":\"internal_link_torque_pairs\",\"error_rad\":" << error
        << ",\"relative_velocity_rad_s\":" << rate
        << ",\"driver_constraint_torque_nm\":" << this->ratio*reaction
        << ",\"follower_constraint_torque_nm\":" << -reaction
        << ",\"elastic_energy_j\":" << .5*this->stiffness*error*error
        << ",\"dissipation_w\":" << this->damping*rate*rate
        << ",\"constraint_power_w\":" << -reaction*rate
        << ",\"elastic_energy_rate_w\":" << this->stiffness*error*rate << "}";
    gz::msgs::StringMsg message; message.set_data(out.str());
    this->publisher.Publish(message);
  }
  public: void Reset(const gz::sim::UpdateInfo &,
      gz::sim::EntityComponentManager &) override { this->lastPublish = -1; }
  private: struct TorquePair
  {
    gz::sim::Link parent, child;
    gz::math::Vector3d axisInChild;
  };
  private: static bool ResolveTorquePair(const gz::sim::Joint &_joint,
      const gz::sim::Model &_model, const gz::sim::EntityComponentManager &_ecm,
      TorquePair &_pair)
  {
    const auto parentName = _joint.ParentLinkName(_ecm);
    const auto childName = _joint.ChildLinkName(_ecm);
    const auto axes = _joint.Axis(_ecm);
    const auto pose = _joint.Pose(_ecm);
    const auto type = _joint.Type(_ecm);
    if (!parentName || !childName || !axes || axes->size() != 1 || !pose ||
        !type || *type != sdf::JointType::REVOLUTE ||
        !axes->at(0).XyzExpressedIn().empty()) return false;
    _pair.parent = gz::sim::Link(_model.LinkByName(_ecm, *parentName));
    _pair.child = gz::sim::Link(_model.LinkByName(_ecm, *childName));
    // SdfEntityCreator resolves Axis into joint frame and Pose into child
    // frame. The rotational axis is invariant under its own revolute motion.
    _pair.axisInChild = pose->Rot().RotateVector(axes->at(0).Xyz());
    return _pair.parent.Valid(_ecm) && _pair.child.Valid(_ecm) &&
        std::abs(_pair.axisInChild.Length()-1) < 1e-8;
  }
  private: static void AddTorquePair(const TorquePair &_pair, double _torque,
      gz::sim::EntityComponentManager &_ecm)
  {
    const auto worldTorque = gz::sim::worldPose(_pair.child.Entity(), _ecm)
        .Rot().RotateVector(_pair.axisInChild) * _torque;
    _pair.child.AddWorldWrench(_ecm, gz::math::Vector3d::Zero, worldTorque);
    _pair.parent.AddWorldWrench(_ecm, gz::math::Vector3d::Zero, -worldTorque);
  }
  private: gz::sim::Joint driver, follower;
  private: TorquePair driverPair, followerPair;
  private: gz::transport::Node node;
  private: gz::transport::Node::Publisher publisher;
  private: double ratio{0}, offset{0}, stiffness{0}, damping{0}, maximumStep{0}, lastPublish{-1}, publishPeriod{.01};
  private: std::string hash;
  private: bool valid{false};
};
}
GZ_ADD_PLUGIN(uchuva::GearCouplingSystem, gz::sim::System,
    uchuva::GearCouplingSystem::ISystemConfigure,
    uchuva::GearCouplingSystem::ISystemConfigurePriority,
    uchuva::GearCouplingSystem::ISystemPreUpdate,
    uchuva::GearCouplingSystem::ISystemReset)
GZ_ADD_PLUGIN_ALIAS(uchuva::GearCouplingSystem, "uchuva::GearCouplingSystem")
