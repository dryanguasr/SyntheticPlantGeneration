// Original project code, MIT. Moves a collision-free Gazebo RGB observer.
#include <gz/common/Console.hh>
#include <gz/math/Pose3.hh>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/World.hh>
#include <gz/sim/components/Collision.hh>
#include <gz/sim/components/ParentEntity.hh>
#include <gz/sim/components/Pose.hh>
#include <gz/sim/components/Static.hh>
#include <sdf/Element.hh>

#include <chrono>
#include <cmath>
#include <string>

namespace uchuva
{
class HarvestDemoCameraSystem final : public gz::sim::System,
    public gz::sim::ISystemConfigure, public gz::sim::ISystemPreUpdate
{
  public: void Configure(const gz::sim::Entity &entity,
      const std::shared_ptr<const sdf::Element> &config,
      gz::sim::EntityComponentManager &, gz::sim::EventManager &) override
  {
    const auto eye = config->Get<gz::math::Vector3d>("eye_offset",
        gz::math::Vector3d(-1.58, -.90, 1.42)).first;
    const auto look = config->Get<gz::math::Vector3d>("look_offset",
        gz::math::Vector3d(.23, .04, .23)).first;
    if (!eye.IsFinite() || !look.IsFinite() || (look - eye).Length() < .1)
    {
      gzerr << "HarvestDemoCameraSystem has invalid framing\n";
      return;
    }
    this->observer = entity;
    this->robotName = config->Get<std::string>("robot_name", "harvester").first;
    this->eyeOffset = eye;
    this->lookOffset = look;
  }

  private: bool Resolve(const gz::sim::EntityComponentManager &ecm)
  {
    // Models and descendants may still be loading when Configure is called.
    const gz::sim::Model model(this->observer);
    const auto *parent = ecm.Component<gz::sim::components::ParentEntity>(this->observer);
    const auto *stationary = ecm.Component<gz::sim::components::Static>(this->observer);
    if (!model.Valid(ecm) || model.Name(ecm) != "harvest_video_observer" ||
        !parent || !stationary || !stationary->Data())
    {
      gzerr << "HarvestDemoCameraSystem requires a static harvest_video_observer\n";
      return false;
    }
    const auto links = model.Links(ecm);
    if (links.size() != 1 || !ecm.ChildrenByComponents(links.front(),
        gz::sim::components::Collision()).empty())
    {
      gzerr << "HarvestDemoCameraSystem requires a single collision-free observer link\n";
      return false;
    }
    const gz::sim::World world(parent->Data());
    const auto target = world.ModelByName(ecm, this->robotName);
    if (!world.Valid(ecm) || target == gz::sim::kNullEntity || target == this->observer)
    {
      gzerr << "HarvestDemoCameraSystem has an invalid target\n";
      return false;
    }
    this->target = target;
    return true;
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &info,
      gz::sim::EntityComponentManager &ecm) override
  {
    if (info.paused || this->observer == gz::sim::kNullEntity ||
        info.simTime < this->nextUpdate)
      return;
    if (this->target == gz::sim::kNullEntity && !this->Resolve(ecm))
    {
      this->observer = gz::sim::kNullEntity;
      return;
    }
    this->nextUpdate = info.simTime + std::chrono::milliseconds(16);
    const auto position = gz::sim::worldPose(this->target, ecm).Pos();
    if (!position.IsFinite())
      return;
    // Keep the camera outside the crop regardless of the robot's heading.
    const auto delta = this->lookOffset - this->eyeOffset;
    const auto pitch = std::atan2(-delta.Z(), std::hypot(delta.X(), delta.Y()));
    const auto yaw = std::atan2(delta.Y(), delta.X());
    // The observer is static and has no collision geometry. It is already
    // parented to the world, so its model pose is the camera rig's world pose.
    if (ecm.SetComponentData<gz::sim::components::Pose>(this->observer,
        gz::math::Pose3d(position + this->eyeOffset, gz::math::Quaterniond(0, pitch, yaw))))
    {
      ecm.SetChanged(this->observer, gz::sim::components::Pose::typeId,
          gz::sim::ComponentState::OneTimeChange);
    }
  }

  private: gz::sim::Entity observer{gz::sim::kNullEntity};
  private: gz::sim::Entity target{gz::sim::kNullEntity};
  private: std::string robotName;
  private: gz::math::Vector3d eyeOffset;
  private: gz::math::Vector3d lookOffset;
  private: std::chrono::steady_clock::duration nextUpdate{0};
};
}

GZ_ADD_PLUGIN(uchuva::HarvestDemoCameraSystem, gz::sim::System,
    uchuva::HarvestDemoCameraSystem::ISystemConfigure,
    uchuva::HarvestDemoCameraSystem::ISystemPreUpdate)
