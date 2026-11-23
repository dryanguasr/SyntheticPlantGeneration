// Original project code, MIT. Native DART split-and-weld loop adapter.
// gz-physics7_7.8.0/dartsim/src/JointFeatures.cc AttachFixedJoint supports
// a non-tree fixed closure via SplitAndWeldLink / WeldJointConstraint.
// The moving closure joint remains a real SDF revolute/prismatic tree joint;
// this system only rigidly reunites its mass-partitioned auxiliary body.
#include <gz/common/Console.hh>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/DetachableJoint.hh>
#include <sdf/Element.hh>
#include <cmath>
#include <set>
#include <string>
#include <vector>

namespace uchuva
{
class ClosedLoopSystem final : public gz::sim::System,
    public gz::sim::ISystemConfigure, public gz::sim::ISystemPreUpdate,
    public gz::sim::ISystemReset
{
  struct Closure
  {
    std::string name, body, auxiliary;
    gz::sim::Entity entity{gz::sim::kNullEntity};
  };
  public: void Configure(const gz::sim::Entity &_entity,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &, gz::sim::EventManager &) override
  {
    this->model = gz::sim::Model(_entity);
    auto config = _sdf->Clone();
    if (!config->HasElement("closure"))
    {
      gzerr << "ClosedLoopSystem: no closures configured\n";
      return;
    }
    std::set<std::string> names, auxiliaries;
    for (auto row = config->GetElement("closure"); row;
         row = row->GetNextElement("closure"))
    {
      Closure closure;
      closure.name = row->Get<std::string>("name");
      closure.body = row->Get<std::string>("body");
      closure.auxiliary = row->Get<std::string>("auxiliary");
      if (closure.name.empty() || closure.body.empty() ||
          closure.auxiliary.empty() || closure.body == closure.auxiliary ||
          !names.insert(closure.name).second ||
          !auxiliaries.insert(closure.auxiliary).second)
      {
        gzerr << "ClosedLoopSystem: invalid or duplicate closure\n";
        return;
      }
      this->closures.push_back(closure);
    }
    this->valid = true;
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &_info,
      gz::sim::EntityComponentManager &_ecm) override
  {
    if (!this->valid || this->initialized || _info.paused) return;
    // Resolve and validate all links before creating any constraint. The
    // exporter partitions inertia at identical frames; a displaced auxiliary
    // is a malformed package, not a target to teleport or silently accept.
    for (const auto &closure : this->closures)
    {
      const auto body = this->model.LinkByName(_ecm, closure.body);
      const auto auxiliary = this->model.LinkByName(_ecm, closure.auxiliary);
      if (body == gz::sim::kNullEntity || auxiliary == gz::sim::kNullEntity)
      {
        gzerr << "ClosedLoopSystem: missing body/auxiliary for " << closure.name << "\n";
        this->valid = false;
        return;
      }
      const auto relative = gz::sim::worldPose(body, _ecm).Inverse() *
          gz::sim::worldPose(auxiliary, _ecm);
      const auto &rotation = relative.Rot();
      const double sineHalfAngle = std::sqrt(rotation.X()*rotation.X() +
          rotation.Y()*rotation.Y() + rotation.Z()*rotation.Z());
      if (relative.Pos().Length() > 1e-9 || sineHalfAngle > 5e-10)
      {
        gzerr << "ClosedLoopSystem: auxiliary is not coincident at initialization: "
              << closure.name << "\n";
        this->valid = false;
        return;
      }
    }
    for (auto &closure : this->closures)
    {
      closure.entity = _ecm.CreateEntity();
      _ecm.CreateComponent(closure.entity,
          gz::sim::components::DetachableJoint({
            this->model.LinkByName(_ecm, closure.body),
            this->model.LinkByName(_ecm, closure.auxiliary), "fixed"}));
      gzmsg << "ClosedLoopSystem: requested native split-and-weld closure "
            << closure.name << "\n";
    }
    this->initialized = true;
  }

  public: void Reset(const gz::sim::UpdateInfo &,
      gz::sim::EntityComponentManager &_ecm) override
  {
    for (auto &closure : this->closures)
    {
      if (closure.entity != gz::sim::kNullEntity)
        _ecm.RequestRemoveEntity(closure.entity);
      closure.entity = gz::sim::kNullEntity;
    }
    this->initialized = false;
  }
  private: gz::sim::Model model;
  private: std::vector<Closure> closures;
  private: bool valid{false}, initialized{false};
};
}
GZ_ADD_PLUGIN(uchuva::ClosedLoopSystem, gz::sim::System,
    uchuva::ClosedLoopSystem::ISystemConfigure,
    uchuva::ClosedLoopSystem::ISystemPreUpdate,
    uchuva::ClosedLoopSystem::ISystemReset)
GZ_ADD_PLUGIN_ALIAS(uchuva::ClosedLoopSystem, "uchuva::ClosedLoopSystem")
