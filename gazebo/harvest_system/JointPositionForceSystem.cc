// Original project code, MIT. One force writer and a native, bounded reference.
#include "PositionForceController.hh"
#include "ObservationSchedule.hh"
#include <gz/common/Console.hh>
#include <gz/msgs/double.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Joint.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/components/JointType.hh>
#include <gz/transport/Node.hh>
#include <sdf/Element.hh>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <locale>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>

namespace uchuva
{
namespace
{
std::string JsonNumber(double _value)
{
  if (!std::isfinite(_value)) return "null";
  std::ostringstream out; out.imbue(std::locale::classic());
  out << std::setprecision(17) << _value; return out.str();
}
std::string JsonQuote(const std::string &_value)
{
  std::ostringstream out; out << '"';
  for (unsigned char c : _value)
  {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32) out << "\\u" << std::hex << std::setw(4)
        << std::setfill('0') << unsigned(c) << std::dec;
    else out << c;
  }
  out << '"'; return out.str();
}
constexpr double Unknown = std::numeric_limits<double>::quiet_NaN();
}

class JointPositionForceSystem final : public gz::sim::System,
    public gz::sim::ISystemConfigure,
    public gz::sim::ISystemConfigurePriority,
    public gz::sim::ISystemPreUpdate,
    public gz::sim::ISystemReset
{
  public: gz::sim::System::PriorityType ConfigurePriority() override { return 0; }
  public: void Configure(const gz::sim::Entity &_entity,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &_ecm, gz::sim::EventManager &) override
  {
    try
    {
      auto config = _sdf->Clone();
      for (const auto *field : {"joint_name", "topic", "state_topic", "robot_spec_sha256",
           "p_gain", "i_gain", "d_gain", "i_min", "i_max", "cmd_min", "cmd_max",
           "command_velocity", "lower_limit", "upper_limit", "initial_position"})
        if (!config->HasElement(field)) throw std::invalid_argument(std::string("Missing ")+field);
      this->name = config->Get<std::string>("joint_name");
      this->hash = config->Get<std::string>("robot_spec_sha256");
      const auto topic = config->Get<std::string>("topic");
      const auto stateTopic = config->Get<std::string>("state_topic");
      this->joint = gz::sim::Joint(gz::sim::Model(_entity).JointByName(_ecm, this->name));
      if (!this->joint.Valid(_ecm) || this->hash.size() != 64 || topic.empty() ||
          stateTopic.empty() || topic == stateTopic)
        throw std::invalid_argument("Invalid joint, hash or transport topics");
      const auto *type = _ecm.Component<gz::sim::components::JointType>(this->joint.Entity());
      if (!type || (type->Data() != sdf::JointType::PRISMATIC &&
                    type->Data() != sdf::JointType::REVOLUTE))
        throw std::invalid_argument("Force position control requires a one-axis revolute/prismatic joint");
      this->prismatic = type->Data() == sdf::JointType::PRISMATIC;
      this->speed = config->Get<double>("command_velocity");
      const double publishRate = config->Get<double>("publish_rate", 100).first;
      if (!std::isfinite(publishRate) || publishRate <= 0 || publishRate > 10000)
        throw std::invalid_argument("Invalid observation rate (0,10000] Hz");
      this->publishPeriod = 1/publishRate;
      this->controller = std::make_unique<PositionForceController>(PositionForceParameters{
          config->Get<double>("p_gain"), config->Get<double>("i_gain"), config->Get<double>("d_gain"),
          config->Get<double>("i_min"), config->Get<double>("i_max"),
          config->Get<double>("cmd_min"), config->Get<double>("cmd_max"), this->speed,
          config->Get<double>("lower_limit"), config->Get<double>("upper_limit"),
          config->Get<double>("initial_position")});
      this->joint.EnablePositionCheck(_ecm);
      this->joint.EnableVelocityCheck(_ecm);
      this->publisher = this->node.Advertise<gz::msgs::StringMsg>(stateTopic);
      if (!this->publisher || !this->node.Subscribe(topic, &JointPositionForceSystem::OnCommand, this))
        throw std::runtime_error("Cannot establish controller transport");
      this->valid = true;
    }
    catch (const std::exception &error)
    {
      gzerr << "JointPositionForceSystem: " << error.what() << '\n';
      this->valid = false;
    }
  }
  private: void OnCommand(const gz::msgs::Double &_message)
  {
    std::lock_guard<std::mutex> lock(this->mutex);
    ++this->commandSequence;
    if (!this->controller || !this->controller->SetTarget(_message.data()))
      ++this->rejectedCommands;
  }
  public: void PreUpdate(const gz::sim::UpdateInfo &_info,
      gz::sim::EntityComponentManager &_ecm) override
  {
    if (!this->valid || _info.paused) return;
    std::lock_guard<std::mutex> lock(this->mutex);
    // UpdateInfo labels the end of this step; the force is applied before it.
    // Match RobotTelemetry.commanded_before_step_time exactly.
    const double time = std::chrono::duration<double>(_info.simTime-_info.dt).count();
    const double responseTime = std::chrono::duration<double>(_info.simTime).count();
    const double dt = std::chrono::duration<double>(_info.dt).count();
    double q = Unknown, v = Unknown;
    PositionForceStep result{this->controller->Reference(), 0, 0, 0, false};
    std::string status = "waiting_for_native_state";
    const auto positions = this->joint.Position(_ecm), velocities = this->joint.Velocity(_ecm);
    if (positions && velocities && positions->size() == 1 && velocities->size() == 1)
    {
      q = positions->front(); v = velocities->front();
      try
      {
        result = this->controller->Step(q, v, dt);
        status = "active";
      }
      catch (const std::exception &error)
      {
        status = "invalid_native_state_or_step";
        gzerr << "JointPositionForceSystem [" << this->name << "]: " << error.what() << '\n';
        // Invalid state disables force; it never feeds fictitious coordinates
        // into the PID. The non-active state remains externally observable.
      }
    }
    this->joint.SetForce(_ecm, {result.force});
    ++this->windowSteps;
    if (std::isfinite(v)) this->maxVelocity = std::max(this->maxVelocity, std::abs(v));
    this->maxForce = std::max(this->maxForce, std::abs(result.force));
    this->maxRawForce = std::max(this->maxRawForce, std::abs(result.unsaturatedForce));
    this->maxReferenceRate = std::max(this->maxReferenceRate, std::abs(result.referenceRate));
    if (result.saturated) { ++this->saturatedSteps; ++this->totalSaturatedSteps; }
    if (status != "active") ++this->invalidStateSteps;
    if (responseTime+1e-12 < this->nextPublish) return;
    std::ostringstream out; out.imbue(std::locale::classic()); out << std::setprecision(17);
    out << "{\"schema_version\":\"joint-position-force/1.0\",\"robot_spec_sha256\":" << JsonQuote(this->hash)
        << ",\"joint_name\":" << JsonQuote(this->name) << ",\"sim_time\":" << JsonNumber(time)
        << ",\"update_info_sim_time\":" << JsonNumber(std::chrono::duration<double>(_info.simTime).count())
        << ",\"publication_grid\":\"update_info_sim_time/1.0\""
        << ",\"iteration\":" << _info.iterations
        << ",\"sample_phase\":\"pre_physics\",\"status\":" << JsonQuote(status)
        << ",\"joint_type\":" << JsonQuote(this->prismatic ? "prismatic" : "revolute")
        << ",\"position_unit\":" << JsonQuote(this->prismatic ? "m" : "rad")
        << ",\"velocity_unit\":" << JsonQuote(this->prismatic ? "m/s" : "rad/s")
        << ",\"force_unit\":" << JsonQuote(this->prismatic ? "N" : "Nm")
        << ",\"legacy_suffix_fields_are_SI_aliases\":true"
        << ",\"requested_target_position\":" << JsonNumber(this->controller->Target())
        << ",\"limited_reference\":" << JsonNumber(this->controller->Reference())
        << ",\"measured_position\":" << JsonNumber(q)
        << ",\"measured_velocity\":" << JsonNumber(v)
        << ",\"unsaturated_force\":" << JsonNumber(result.unsaturatedForce)
        << ",\"force_command\":" << JsonNumber(result.force)
        << ",\"command_velocity\":" << JsonNumber(this->speed)
        << ",\"requested_target_position_rad\":" << JsonNumber(this->controller->Target())
        << ",\"limited_reference_rad\":" << JsonNumber(this->controller->Reference())
        << ",\"measured_position_rad\":" << JsonNumber(q)
        << ",\"measured_velocity_rad_s\":" << JsonNumber(v)
        << ",\"unsaturated_force_nm\":" << JsonNumber(result.unsaturatedForce)
        << ",\"force_command_nm\":" << JsonNumber(result.force)
        << ",\"saturated\":" << (result.saturated ? "true" : "false")
        << ",\"command_velocity_rad_s\":" << JsonNumber(this->speed)
        << ",\"command_sequence\":" << this->commandSequence
        << ",\"rejected_commands\":" << this->rejectedCommands
        << ",\"max_abs_velocity_window\":" << JsonNumber(this->maxVelocity)
        << ",\"max_abs_force_command_window\":" << JsonNumber(this->maxForce)
        << ",\"max_abs_unsaturated_force_window\":" << JsonNumber(this->maxRawForce)
        << ",\"max_abs_reference_rate_window\":" << JsonNumber(this->maxReferenceRate)
        << ",\"saturated_steps_window\":" << this->saturatedSteps
        << ",\"saturated_steps_total\":" << this->totalSaturatedSteps
        << ",\"invalid_state_steps_window\":" << this->invalidStateSteps
        << ",\"window_steps\":" << this->windowSteps << "}";
    gz::msgs::StringMsg message; message.set_data(out.str()); this->publisher.Publish(message);
    this->nextPublish = NextObservationTime(responseTime, this->publishPeriod);
    this->ClearWindow();
  }
  public: void Reset(const gz::sim::UpdateInfo &, gz::sim::EntityComponentManager &_ecm) override
  {
    std::lock_guard<std::mutex> lock(this->mutex);
    if (this->controller) this->controller->Reset();
    if (this->joint.Valid(_ecm)) this->joint.SetForce(_ecm, {0});
    this->commandSequence = this->rejectedCommands = this->totalSaturatedSteps = 0;
    this->nextPublish = 0; this->ClearWindow();
  }
  private: void ClearWindow()
  {
    this->maxVelocity = this->maxForce = this->maxRawForce = this->maxReferenceRate = 0;
    this->saturatedSteps = this->windowSteps = this->invalidStateSteps = 0;
  }
  private: gz::sim::Joint joint;
  private: std::unique_ptr<PositionForceController> controller;
  private: gz::transport::Node node;
  private: gz::transport::Node::Publisher publisher;
  private: std::mutex mutex;
  private: std::string name, hash;
  private: bool valid{false};
  private: bool prismatic{false};
  private: double speed{0}, publishPeriod{.01}, nextPublish{0}, maxVelocity{0}, maxForce{0}, maxRawForce{0}, maxReferenceRate{0};
  private: std::uint64_t commandSequence{0}, rejectedCommands{0}, saturatedSteps{0}, totalSaturatedSteps{0}, windowSteps{0}, invalidStateSteps{0};
};
}
GZ_ADD_PLUGIN(uchuva::JointPositionForceSystem, gz::sim::System,
    uchuva::JointPositionForceSystem::ISystemConfigure,
    uchuva::JointPositionForceSystem::ISystemConfigurePriority,
    uchuva::JointPositionForceSystem::ISystemPreUpdate,
    uchuva::JointPositionForceSystem::ISystemReset)
GZ_ADD_PLUGIN_ALIAS(uchuva::JointPositionForceSystem, "uchuva::JointPositionForceSystem")
