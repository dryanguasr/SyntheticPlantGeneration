// Original project code, MIT. Gazebo Harmonic native observation, not motor sensing.
#include "ObservationSchedule.hh"
#include <gz/common/Console.hh>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Joint.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/components/JointForceCmd.hh>
#include <gz/transport/Node.hh>
#include <sdf/Element.hh>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>
#include <string>
#include <vector>

namespace uchuva
{
namespace
{
std::string Number(double x)
{
  if (!std::isfinite(x)) return "null";
  std::ostringstream out;
  out.imbue(std::locale::classic());
  out << std::setprecision(15) << x;
  return out.str();
}
std::string Quote(const std::string &s)
{
  std::ostringstream out;
  out << '"';
  for (unsigned char c : s)
  {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32) out << "\\u" << std::hex << std::setw(4)
                        << std::setfill('0') << unsigned(c) << std::dec;
    else out << c;
  }
  out << '"';
  return out.str();
}
template<class T> std::string Vector(const T &v)
{
  return "[" + Number(v.x()) + "," + Number(v.y()) + "," + Number(v.z()) + "]";
}
constexpr double Unknown = std::numeric_limits<double>::quiet_NaN();
struct ObservedJoint
{
  std::string name;
  gz::sim::Entity entity{gz::sim::kNullEntity};
  double effortLimit{0}, command{Unknown}, maxCommand{0}, maxVelocity{0};
  std::uint64_t saturatedSteps{0};
};
}

class RobotTelemetrySystem final : public gz::sim::System,
    public gz::sim::ISystemConfigure,
    public gz::sim::ISystemConfigurePriority,
    public gz::sim::ISystemPreUpdate,
    public gz::sim::ISystemPostUpdate,
    public gz::sim::ISystemReset
{
  // Controllers use priority 0. Sample their commands after PreUpdate and before
  // Physics::Update. PostUpdate reads the response from that same physics step.
  public: gz::sim::System::PriorityType ConfigurePriority() override { return 100; }

  public: void Configure(const gz::sim::Entity &entity,
      const std::shared_ptr<const sdf::Element> &sdf,
      gz::sim::EntityComponentManager &ecm, gz::sim::EventManager &) override
  {
    this->model = gz::sim::Model(entity);
    auto config = sdf->Clone();
    this->hash = config->Get<std::string>("robot_spec_sha256", "").first;
    const auto topic = config->Get<std::string>("topic", "/harvester/robot_telemetry").first;
    const double rate = config->Get<double>("publish_rate", 100).first;
    if (this->hash.empty() || !std::isfinite(rate) || rate <= 0)
    {
      gzerr << "RobotTelemetrySystem requires robot_spec_sha256 and positive publish_rate\n";
      return;
    }
    this->period = 1.0 / rate;
    if (config->HasElement("joint"))
    {
      for (auto item = config->GetElement("joint"); item;
           item = item->GetNextElement("joint"))
      {
        ObservedJoint joint;
        joint.name = item->Get<std::string>("name");
        joint.effortLimit = item->Get<double>("effort_limit", 0).first;
        if (joint.name.empty() || !std::isfinite(joint.effortLimit) || joint.effortLimit < 0)
        {
          gzerr << "Invalid telemetry joint entry\n";
          return;
        }
        this->joints.push_back(joint);
      }
    }
    this->publisher = this->node.Advertise<gz::msgs::StringMsg>(topic);
    this->valid = !this->joints.empty();
    this->Resolve(ecm);
  }

  private: void Resolve(gz::sim::EntityComponentManager &ecm)
  {
    for (auto &item : this->joints)
    {
      if (item.entity != gz::sim::kNullEntity) continue;
      item.entity = this->model.JointByName(ecm, item.name);
      if (item.entity == gz::sim::kNullEntity) continue;
      gz::sim::Joint joint(item.entity);
      joint.EnablePositionCheck(ecm);
      joint.EnableVelocityCheck(ecm);
      joint.EnableTransmittedWrenchCheck(ecm);
    }
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &info,
      gz::sim::EntityComponentManager &ecm) override
  {
    if (!this->valid || info.paused) return;
    this->Resolve(ecm);
    this->commandTime = std::chrono::duration<double>(info.simTime - info.dt).count();
    this->commandIteration = info.iterations;
    for (auto &item : this->joints)
    {
      item.command = Unknown;
      const auto *force = ecm.Component<gz::sim::components::JointForceCmd>(item.entity);
      if (force && force->Data().size() == 1 && std::isfinite(force->Data()[0]))
      {
        item.command = force->Data()[0];
        item.maxCommand = std::max(item.maxCommand, std::abs(item.command));
        if (item.effortLimit > 0 && std::abs(item.command) >= item.effortLimit * (1 - 1e-6))
          ++item.saturatedSteps;
      }
    }
  }

  public: void PostUpdate(const gz::sim::UpdateInfo &info,
      const gz::sim::EntityComponentManager &ecm) override
  {
    if (!this->valid || info.paused || info.iterations != this->commandIteration) return;
    const double now = std::chrono::duration<double>(info.simTime).count();
    ++this->samples;
    for (auto &item : this->joints)
    {
      const auto velocity = gz::sim::Joint(item.entity).Velocity(ecm);
      if (velocity && velocity->size() == 1 && std::isfinite((*velocity)[0]))
        item.maxVelocity = std::max(item.maxVelocity, std::abs((*velocity)[0]));
    }
    if (now + 1e-12 < this->nextPublish) return;
    std::ostringstream out;
    out << "{\"schema_version\":\"robot-telemetry/1.1\",\"robot_spec_sha256\":"
        << Quote(this->hash) << ",\"sim_time\":" << Number(now)
        << ",\"iteration\":" << info.iterations << ",\"reset_count\":" << this->resets
        << ",\"commanded_before_step_time\":" << Number(this->commandTime)
        << ",\"measured_after_step_time\":" << Number(now)
        << ",\"pose_joint_time_field\":\"measured_after_step_time\""
        << ",\"publication_grid\":\"update_info_sim_time/1.0\""
        << ",\"sample_count\":" << this->samples
        << ",\"wrench_semantics\":\"simulated_transmitted_joint_frame_not_motor_torque\",\"joints\":[";
    bool first = true;
    for (auto &item : this->joints)
    {
      if (!first) out << ',';
      first = false;
      gz::sim::Joint joint(item.entity);
      const auto position = joint.Position(ecm);
      const auto velocity = joint.Velocity(ecm);
      const auto wrench = joint.TransmittedWrench(ecm);
      const double q = position && position->size() == 1 ? (*position)[0] : Unknown;
      const double qd = velocity && velocity->size() == 1 ? (*velocity)[0] : Unknown;
      const bool hasWrenchComponent = wrench && wrench->size() == 1;
      // An unsupported closed-loop joint can retain the default wrench
      // component although Physics never creates a corresponding joint.
      // Require native coordinates as well before treating it as observed.
      const bool hasWrench = hasWrenchComponent && std::isfinite(q) && std::isfinite(qd)
          && std::isfinite((*wrench)[0].force().x())
          && std::isfinite((*wrench)[0].force().y())
          && std::isfinite((*wrench)[0].force().z())
          && std::isfinite((*wrench)[0].torque().x())
          && std::isfinite((*wrench)[0].torque().y())
          && std::isfinite((*wrench)[0].torque().z());
      out << "{\"name\":" << Quote(item.name)
          << ",\"position\":" << Number(q) << ",\"velocity\":" << Number(qd)
          << ",\"force_command\":" << Number(item.command)
          << ",\"position_available\":" << (std::isfinite(q) ? "true" : "false")
          << ",\"velocity_available\":" << (std::isfinite(qd) ? "true" : "false")
          << ",\"force_command_available\":" << (std::isfinite(item.command) ? "true" : "false")
          << ",\"wrench_component_available\":" << (hasWrenchComponent ? "true" : "false")
          << ",\"wrench_available\":" << (hasWrench ? "true" : "false")
          << ",\"transmitted_wrench\":";
      if (hasWrench) out << "{\"force\":" << Vector((*wrench)[0].force())
                        << ",\"torque\":" << Vector((*wrench)[0].torque()) << '}';
      else out << "null";
      out << ",\"effort_limit\":" << Number(item.effortLimit)
          << ",\"max_abs_force_command_window\":" << Number(item.maxCommand)
          << ",\"max_abs_velocity_window\":" << Number(item.maxVelocity)
          << ",\"saturated_steps\":" << item.saturatedSteps << '}';
      item.maxCommand = item.maxVelocity = 0;
      item.saturatedSteps = 0;
    }
    out << "]}";
    gz::msgs::StringMsg message;
    message.set_data(out.str());
    this->publisher.Publish(message);
    this->samples = 0;
    this->nextPublish = NextObservationTime(now, this->period);
  }

  public: void Reset(const gz::sim::UpdateInfo &,
      gz::sim::EntityComponentManager &) override
  {
    ++this->resets;
    this->nextPublish = 0;
    this->commandTime = Unknown;
    this->samples = 0;
    for (auto &item : this->joints)
    {
      item.command = Unknown;
      item.maxCommand = item.maxVelocity = 0;
      item.saturatedSteps = 0;
    }
  }

  private: gz::sim::Model model{gz::sim::kNullEntity};
  private: gz::transport::Node node;
  private: gz::transport::Node::Publisher publisher;
  private: std::vector<ObservedJoint> joints;
  private: std::string hash;
  private: bool valid{false};
  private: double period{0.01}, nextPublish{0}, commandTime{Unknown};
  private: std::uint64_t samples{0}, resets{0}, commandIteration{0};
};
}

GZ_ADD_PLUGIN(uchuva::RobotTelemetrySystem, gz::sim::System,
    uchuva::RobotTelemetrySystem::ISystemConfigure,
    uchuva::RobotTelemetrySystem::ISystemConfigurePriority,
    uchuva::RobotTelemetrySystem::ISystemPreUpdate,
    uchuva::RobotTelemetrySystem::ISystemPostUpdate,
    uchuva::RobotTelemetrySystem::ISystemReset)
GZ_ADD_PLUGIN_ALIAS(uchuva::RobotTelemetrySystem, "uchuva::RobotTelemetrySystem")
