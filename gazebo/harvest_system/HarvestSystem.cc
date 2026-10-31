// Original project code, MIT license (see repository LICENSE).
// Runtime target: Gazebo Harmonic (gz-sim8), DART physics.
// API references inspected for this implementation:
// https://gazebosim.org/api/sim/8/createsystemplugins.html
// https://gazebosim.org/api/sim/8/detachablejoints.html
// https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/detachable_joint/DetachableJoint.cc
// https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/physics/Physics.cc
//
// This is an IDEALIZED cut-and-retain mechanism, not a fracture / grip-force
// model. Commands never change model poses, disable gravity, or teleport fruit.
// Each fruit has at most one parent constraint. Physics creates new joints
// before removing old ones, so transfer must span separate simulation steps.

#include <gz/common/Console.hh>
#include <gz/math/Pose3.hh>
#include <gz/math/Vector3.hh>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/DetachableJoint.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/components/ParentEntity.hh>
#include <gz/sim/components/Pose.hh>
#include <gz/sim/components/Static.hh>
#include <gz/sim/components/World.hh>
#include <gz/transport/Node.hh>
#include <sdf/Element.hh>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <deque>
#include <iomanip>
#include <limits>
#include <locale>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace uchuva
{
namespace
{
using Entity = gz::sim::Entity;
constexpr Entity kNull = gz::sim::kNullEntity;
constexpr double kUnknown = std::numeric_limits<double>::quiet_NaN();

double Seconds(const std::chrono::steady_clock::duration &_time)
{
  return std::chrono::duration<double>(_time).count();
}

std::string Quote(const std::string &_text)
{
  std::ostringstream out;
  out << '"';
  for (const unsigned char c : _text)
  {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 0x20)
      out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
          << static_cast<unsigned int>(c) << std::dec;
    else out << c;
  }
  out << '"';
  return out.str();
}

std::string Number(double _number)
{
  if (!std::isfinite(_number)) return "null";
  std::ostringstream out;
  out.imbue(std::locale::classic());
  out << std::setprecision(12) << _number;
  return out.str();
}

std::string Vector(const gz::math::Vector3d &_v)
{
  return "[" + Number(_v.X()) + "," + Number(_v.Y()) + "," +
         Number(_v.Z()) + "]";
}

bool Finite(const gz::math::Pose3d &_pose)
{
  const auto &p = _pose.Pos();
  const auto &q = _pose.Rot();
  return std::isfinite(p.X()) && std::isfinite(p.Y()) &&
      std::isfinite(p.Z()) && std::isfinite(q.X()) && std::isfinite(q.Y()) &&
      std::isfinite(q.Z()) && std::isfinite(q.W());
}

std::string Pose(const gz::math::Pose3d &_pose)
{
  const auto &p = _pose.Pos();
  const auto &q = _pose.Rot();
  return "[" + Number(p.X()) + "," + Number(p.Y()) + "," +
      Number(p.Z()) + "," + Number(q.X()) + "," + Number(q.Y()) + "," +
      Number(q.Z()) + "," + Number(q.W()) + "]";
}

enum class State
{
  ATTACHED, ARMED, CUT_PENDING, HELD, RELEASE_PENDING, RELEASED, ERROR
};

const char *Name(State _state)
{
  switch (_state)
  {
    case State::ATTACHED: return "ATTACHED";
    case State::ARMED: return "ARMED";
    case State::CUT_PENDING: return "CUT_PENDING";
    case State::HELD: return "HELD";
    case State::RELEASE_PENDING: return "RELEASE_PENDING";
    case State::RELEASED: return "RELEASED";
    case State::ERROR: return "ERROR";
  }
  return "ERROR";
}

struct Fruit
{
  std::string id;
  std::string model;
  std::string link;
  std::string parentModel;
  std::string parentLink;
  gz::math::Vector3d cutPoint;
  Entity modelEntity{kNull};
  Entity linkEntity{kNull};
  Entity plantLinkEntity{kNull};
  Entity joint{kNull};
  Entity removingJoint{kNull};
  Entity jointParent{kNull};
  State state{State::ATTACHED};
  gz::math::Pose3d relativeAttachment;
  gz::math::Pose3d observedPose;
  gz::math::Vector3d observedCut;
  gz::math::Vector3d previousRelativeCut;
  gz::math::Vector3d previousRelativeCenter;
  double previousObservation{kUnknown};
  double relativeSpeed{kUnknown};
  double stableSince{kUnknown};
  double constraintError{kUnknown};
  double pendingSince{kUnknown};
  std::uint64_t attachmentIteration{0};
  bool hasObservation{false};
};
}  // namespace

class HarvestSystem : public gz::sim::System,
                      public gz::sim::ISystemConfigure,
                      public gz::sim::ISystemPreUpdate,
                      public gz::sim::ISystemPostUpdate,
                      public gz::sim::ISystemReset
{
  public: void Configure(const Entity &_entity,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &_ecm,
      gz::sim::EventManager &) override
  {
    this->world = _entity;
    auto config = _sdf->Clone();
    this->robotName = config->Get<std::string>("robot_model", "harvester").first;
    this->toolName = config->Get<std::string>("tool_link", "tool_link").first;
    const auto commandTopic = config->Get<std::string>(
        "command_topic", "/harvest/command").first;
    const auto stateTopic = config->Get<std::string>(
        "state_topic", "/harvest/state").first;
    const auto eventTopic = config->Get<std::string>(
        "event_topic", "/harvest/events").first;
    this->cutTolerance = config->Get<double>("cut_tolerance", 0.02).first;
    this->captureRadius = config->Get<double>("capture_radius", 0.12).first;
    this->maxRelativeSpeed = config->Get<double>("max_relative_speed", 0.12).first;
    this->stableTime = config->Get<double>("stable_time", 0.2).first;
    this->startupTimeout = config->Get<double>("startup_timeout", 5.0).first;
    this->attachmentTolerance = config->Get<double>(
        "attachment_tolerance", 0.01).first;

    this->statePub = this->node.Advertise<gz::msgs::StringMsg>(stateTopic);
    this->eventPub = this->node.Advertise<gz::msgs::StringMsg>(eventTopic);
    const bool subscribed = this->node.Subscribe(
        commandTopic, &HarvestSystem::OnCommand, this);
    if (!_ecm.Component<gz::sim::components::World>(this->world))
      this->Fail("plugin_must_be_attached_to_world");
    if (!this->statePub || !this->eventPub || !subscribed)
      this->Fail("invalid_transport_topics");
    for (const auto value : {this->cutTolerance, this->captureRadius,
          this->maxRelativeSpeed, this->stableTime, this->startupTimeout,
          this->attachmentTolerance})
    {
      if (!std::isfinite(value) || value <= 0)
        this->Fail("tolerances_and_timeouts_must_be_finite_positive");
    }
    if (!config->HasElement("fruit"))
    {
      this->Fail("no_fruits_configured");
      return;
    }
    for (auto entry = config->GetElement("fruit"); entry;
         entry = entry->GetNextElement("fruit"))
    {
      Fruit fruit;
      if (!entry->HasAttribute("id") || !entry->HasElement("model") ||
          !entry->HasElement("link") || !entry->HasElement("parent_model") ||
          !entry->HasElement("parent_link") || !entry->HasElement("cut_point"))
      {
        this->Fail("fruit_missing_required_configuration");
        return;
      }
      fruit.id = entry->GetAttribute("id")->GetAsString();
      fruit.model = entry->Get<std::string>("model");
      fruit.link = entry->Get<std::string>("link");
      fruit.parentModel = entry->Get<std::string>("parent_model");
      fruit.parentLink = entry->Get<std::string>("parent_link");
      fruit.cutPoint = entry->Get<gz::math::Vector3d>("cut_point");
      if (fruit.id.empty() || fruit.id.find_first_of(" \t\r\n") != std::string::npos ||
          fruit.model.empty() || fruit.link.empty() || fruit.parentModel.empty() ||
          fruit.parentLink.empty() || !std::isfinite(fruit.cutPoint.X()) ||
          !std::isfinite(fruit.cutPoint.Y()) || !std::isfinite(fruit.cutPoint.Z()))
      {
        this->Fail("invalid_fruit_configuration");
        return;
      }
      for (const auto &other : this->fruits)
      {
        if (fruit.id == other.id ||
            (fruit.model == other.model && fruit.link == other.link))
        {
          this->Fail("duplicate_fruit_id_or_body");
          return;
        }
      }
      this->fruits.push_back(std::move(fruit));
    }
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &_info,
      gz::sim::EntityComponentManager &_ecm) override
  {
    this->simTime = Seconds(_info.simTime);
    if (!this->error.empty())
    {
      this->RejectQueued("system_error:" + this->error);
      return;
    }
    if (!this->initialized)
    {
      if (!this->Initialize(_ecm, _info.iterations))
      {
        if (this->simTime > this->startupTimeout)
          this->Fail("startup_timeout:" + this->waitingFor);
        this->RejectQueued("not_ready:" + this->waitingFor);
        return;
      }
    }
    if (!this->EntitiesValid(_ecm))
    {
      this->Fail("configured_entity_removed_restart_required");
      this->RejectQueued(this->error);
      return;
    }
    if (_info.paused) return;

    for (auto &fruit : this->fruits)
    {
      if (fruit.state == State::CUT_PENDING)
      {
        // HasEntity false proves the ECM removal phase completed. Do not
        // replace this with immediate CreateComponent in the cut handler.
        if (!_ecm.HasEntity(fruit.removingJoint))
        {
          fruit.removingJoint = kNull;
          const auto reason = this->Guard(fruit, _ecm);
          if (reason.empty())
          {
            this->Attach(fruit, this->tool, _ecm, _info.iterations);
            fruit.state = State::HELD;
            this->Event(fruit.id, "cut", true, "retention_constraint_created",
                        "result");
          }
          else
          {
            fruit.state = State::RELEASED;
            this->Event(fruit.id, "cut", false,
                        "cut_completed_but_retention_failed:" + reason, "result");
          }
        }
        else if (this->simTime - fruit.pendingSince > 1.0)
          this->Fail("constraint_removal_timeout:" + fruit.id);
      }
      else if (fruit.state == State::RELEASE_PENDING)
      {
        if (!_ecm.HasEntity(fruit.removingJoint))
        {
          fruit.removingJoint = kNull;
          fruit.state = State::RELEASED;
          fruit.constraintError = kUnknown;
          this->Event(fruit.id, "release", true, "constraint_removed", "result");
        }
        else if (this->simTime - fruit.pendingSince > 1.0)
          this->Fail("constraint_removal_timeout:" + fruit.id);
      }
    }
    if (!this->error.empty())
    {
      this->RejectQueued(this->error);
      return;
    }

    const auto overflow = this->droppedCommands.exchange(0);
    if (overflow != 0)
      this->Event("", "queue", false,
          "oversized_or_queue_full_commands:" + std::to_string(overflow));
    for (const auto &command : this->TakeCommands())
      this->ProcessCommand(command, _ecm);
  }

  public: void PostUpdate(const gz::sim::UpdateInfo &_info,
      const gz::sim::EntityComponentManager &_ecm) override
  {
    this->simTime = Seconds(_info.simTime);
    if (this->initialized && this->error.empty() && this->EntitiesValid(_ecm))
    {
      this->toolPose = gz::sim::worldPose(this->tool, _ecm);
      this->robotPose = gz::sim::worldPose(this->robot, _ecm);
      if (!Finite(this->toolPose) || !Finite(this->robotPose))
        this->Fail("nonfinite_robot_pose");
      bool observedAll = true;
      for (auto &fruit : this->fruits)
      {
        fruit.observedPose = gz::sim::worldPose(fruit.linkEntity, _ecm);
        if (!Finite(fruit.observedPose))
        {
          this->Fail("nonfinite_fruit_pose:" + fruit.id);
          break;
        }
        fruit.observedCut = fruit.observedPose.Pos() +
            fruit.observedPose.Rot().RotateVector(fruit.cutPoint);
        // Relative points expressed in tool coordinates include rotational
        // movement of the tool. Both the cut point and capture center count.
        const auto inverseTool = this->toolPose.Inverse();
        const auto relativeCut = inverseTool.Pos() +
            inverseTool.Rot().RotateVector(fruit.observedCut);
        const auto relativeCenter = inverseTool.Pos() +
            inverseTool.Rot().RotateVector(fruit.observedPose.Pos());
        const double dt = this->simTime - fruit.previousObservation;
        if (!_info.paused && std::isfinite(dt) && dt > 0)
        {
          fruit.relativeSpeed = std::max(
              (relativeCut - fruit.previousRelativeCut).Length(),
              (relativeCenter - fruit.previousRelativeCenter).Length()) / dt;
        }
        else if (!fruit.hasObservation)
          fruit.relativeSpeed = kUnknown;
        if (!_info.paused || !fruit.hasObservation)
        {
          fruit.previousRelativeCut = relativeCut;
          fruit.previousRelativeCenter = relativeCenter;
          fruit.previousObservation = this->simTime;
        }
        fruit.hasObservation = true;
        if (fruit.state == State::ARMED && this->Guard(fruit, _ecm).empty())
        {
          if (!std::isfinite(fruit.stableSince))
            fruit.stableSince = this->simTime;
        }
        else fruit.stableSince = kUnknown;

        if (fruit.joint != kNull && _ecm.HasEntity(fruit.joint) &&
            _info.iterations > fruit.attachmentIteration)
        {
          const auto parentPose = gz::sim::worldPose(fruit.jointParent, _ecm);
          const auto expected = parentPose * fruit.relativeAttachment;
          fruit.constraintError =
              (expected.Pos() - fruit.observedPose.Pos()).Length();
          if (!std::isfinite(fruit.constraintError) ||
              fruit.constraintError > this->attachmentTolerance)
          {
            this->Event(fruit.id, "observe", false,
                "attachment_pose_residual_exceeded", "result");
            this->Fail("attachment_pose_residual_exceeded:" + fruit.id);
          }
        }
        else if (fruit.state == State::ATTACHED || fruit.state == State::ARMED ||
                 fruit.state == State::HELD)
          observedAll = false;
      }
      this->ready = this->error.empty() && observedAll &&
          this->simTime - this->initializedAt >= 0.05;
    }
    else this->ready = false;

    // Use simulation time for reproducible telemetry. Publish immediately on
    // state transitions even if the simulation is paused.
    if (this->dirty || this->simTime >= this->nextPublishTime)
    {
      this->PublishState(_ecm);
      this->nextPublishTime = this->simTime + 0.05;
      this->dirty = false;
    }
  }

  public: void Reset(const gz::sim::UpdateInfo &_info,
      gz::sim::EntityComponentManager &) override
  {
    this->simTime = Seconds(_info.simTime);
    this->nextPublishTime = -1.0;
    this->ready = false;
    this->Fail("reset_not_supported_restart_gazebo_process_required");
    this->RejectQueued(this->error);
    // Reconstructing constraints after ECM rollback needs a separate native
    // integration test. A reset therefore locks this pilot instead of
    // silently recreating attachments or claiming a successful fresh run.
  }

  private: Entity FindModel(const gz::sim::EntityComponentManager &_ecm,
      const std::string &_name) const
  {
    return _ecm.EntityByComponents(gz::sim::components::Model(),
        gz::sim::components::Name(_name),
        gz::sim::components::ParentEntity(this->world));
  }

  private: bool Initialize(gz::sim::EntityComponentManager &_ecm,
      std::uint64_t _iteration)
  {
    this->waitingFor = "robot_or_tool";
    this->robot = this->FindModel(_ecm, this->robotName);
    if (this->robot == kNull) return false;
    this->tool = gz::sim::Model(this->robot).LinkByName(_ecm, this->toolName);
    if (this->tool == kNull) return false;
    // Resolve ALL names before creating any constraint: partial configuration
    // must not be mistaken for a usable world.
    for (auto &fruit : this->fruits)
    {
      this->waitingFor = fruit.id;
      fruit.modelEntity = this->FindModel(_ecm, fruit.model);
      const Entity plant = this->FindModel(_ecm, fruit.parentModel);
      if (fruit.modelEntity == kNull || plant == kNull) return false;
      if (fruit.modelEntity == plant || fruit.modelEntity == this->robot)
      {
        this->Fail("fruit_must_be_separate_world_model:" + fruit.id);
        return false;
      }
      const auto *isStatic =
          _ecm.Component<gz::sim::components::Static>(fruit.modelEntity);
      if (!isStatic || isStatic->Data())
      {
        this->Fail("fruit_must_be_dynamic:" + fruit.id);
        return false;
      }
      fruit.linkEntity =
          gz::sim::Model(fruit.modelEntity).LinkByName(_ecm, fruit.link);
      fruit.plantLinkEntity =
          gz::sim::Model(plant).LinkByName(_ecm, fruit.parentLink);
      if (fruit.linkEntity == kNull || fruit.plantLinkEntity == kNull)
        return false;
    }
    for (auto &fruit : this->fruits)
      this->Attach(fruit, fruit.plantLinkEntity, _ecm, _iteration);
    this->initialized = true;
    this->initializedAt = this->simTime;
    this->waitingFor.clear();
    this->dirty = true;
    this->Event("", "initialize", true, "attachment_constraints_created", "result");
    return true;
  }

  private: bool EntitiesValid(const gz::sim::EntityComponentManager &_ecm) const
  {
    if (!_ecm.HasEntity(this->robot) || !_ecm.HasEntity(this->tool)) return false;
    for (const auto &fruit : this->fruits)
    {
      if (!_ecm.HasEntity(fruit.modelEntity) || !_ecm.HasEntity(fruit.linkEntity) ||
          !_ecm.HasEntity(fruit.plantLinkEntity)) return false;
    }
    return true;
  }

  private: void Attach(Fruit &_fruit, Entity _parent,
      gz::sim::EntityComponentManager &_ecm, std::uint64_t _iteration)
  {
    _fruit.relativeAttachment = gz::sim::worldPose(_parent, _ecm).Inverse() *
        gz::sim::worldPose(_fruit.linkEntity, _ecm);
    _fruit.joint = _ecm.CreateEntity();
    _ecm.CreateComponent(_fruit.joint,
        gz::sim::components::DetachableJoint({_parent, _fruit.linkEntity, "fixed"}));
    _fruit.jointParent = _parent;
    _fruit.attachmentIteration = _iteration;
    _fruit.constraintError = kUnknown;
    // A queued release must not remove a just-created constraint before its
    // first physics/observation step. PostUpdate restores ready afterwards.
    this->ready = false;
    this->dirty = true;
  }

  private: void RemoveAttachment(Fruit &_fruit,
      gz::sim::EntityComponentManager &_ecm)
  {
    _fruit.removingJoint = _fruit.joint;
    _ecm.RequestRemoveEntity(_fruit.joint);
    _fruit.joint = kNull;
    _fruit.jointParent = kNull;
    _fruit.pendingSince = this->simTime;
    this->dirty = true;
  }

  private: std::string Guard(const Fruit &_fruit,
      const gz::sim::EntityComponentManager &_ecm) const
  {
    const auto toolPoseNow = gz::sim::worldPose(this->tool, _ecm);
    const auto fruitPoseNow = gz::sim::worldPose(_fruit.linkEntity, _ecm);
    if (!Finite(toolPoseNow) || !Finite(fruitPoseNow)) return "nonfinite_pose";
    const auto cut = fruitPoseNow.Pos() +
        fruitPoseNow.Rot().RotateVector(_fruit.cutPoint);
    if ((cut - toolPoseNow.Pos()).Length() > this->cutTolerance)
      return "cut_point_out_of_range";
    if ((fruitPoseNow.Pos() - toolPoseNow.Pos()).Length() > this->captureRadius)
      return "fruit_outside_capture_radius";
    if (!std::isfinite(_fruit.relativeSpeed)) return "relative_speed_unknown";
    if (_fruit.relativeSpeed > this->maxRelativeSpeed) return "relative_speed_too_high";
    return "";
  }

  private: bool Busy(const std::string &_except = "") const
  {
    for (const auto &fruit : this->fruits)
    {
      if (fruit.id == _except) continue;
      if (fruit.state == State::ARMED || fruit.state == State::CUT_PENDING ||
          fruit.state == State::HELD || fruit.state == State::RELEASE_PENDING)
        return true;
    }
    return false;
  }

  private: void ProcessCommand(const std::string &_command,
      gz::sim::EntityComponentManager &_ecm)
  {
    std::istringstream input(_command);
    std::string action, id, extra;
    input >> action;
    input >> id;
    input >> extra;
    if (action.empty() || !extra.empty() ||
        (action == "disarm" && !id.empty()) ||
        (action != "disarm" && id.empty()))
    {
      this->Event(id, action, false, "invalid_command_syntax");
      return;
    }
    if (!this->ready || !this->error.empty())
    {
      this->Event(id, action, false, "not_ready:" + this->error);
      return;
    }
    if (action == "disarm")
    {
      bool changed = false;
      for (auto &fruit : this->fruits)
      {
        if (fruit.state == State::ARMED)
        {
          fruit.state = State::ATTACHED;
          fruit.stableSince = kUnknown;
          changed = true;
        }
      }
      this->Event("", action, changed, changed ? "disarmed" : "nothing_armed");
      return;
    }
    auto it = std::find_if(this->fruits.begin(), this->fruits.end(),
        [&id](const Fruit &_fruit) { return _fruit.id == id; });
    if (it == this->fruits.end())
    {
      this->Event(id, action, false, "unknown_fruit");
      return;
    }
    auto &fruit = *it;
    if (action == "arm")
    {
      if (fruit.state != State::ATTACHED)
        this->Event(id, action, false, "state_must_be_ATTACHED");
      else if (this->Busy(id))
        this->Event(id, action, false, "tool_busy");
      else
      {
        const auto reason = this->Guard(fruit, _ecm);
        if (!reason.empty()) this->Event(id, action, false, reason);
        else
        {
          fruit.state = State::ARMED;
          fruit.stableSince = this->simTime;
          this->Event(id, action, true, "armed_no_second_constraint_created");
        }
      }
    }
    else if (action == "cut")
    {
      if (fruit.state != State::ARMED)
        this->Event(id, action, false, "state_must_be_ARMED");
      else if (this->Busy(id))
        this->Event(id, action, false, "tool_busy");
      else if (fruit.joint == kNull || !_ecm.HasEntity(fruit.joint))
        this->Event(id, action, false, "plant_constraint_missing");
      else
      {
        const auto reason = this->Guard(fruit, _ecm);
        if (!reason.empty()) this->Event(id, action, false, reason);
        else if (!std::isfinite(fruit.stableSince) ||
            this->simTime - fruit.stableSince < this->stableTime)
          this->Event(id, action, false, "stable_time_not_reached");
        else
        {
          this->RemoveAttachment(fruit, _ecm);
          fruit.state = State::CUT_PENDING;
          this->Event(id, action, true, "plant_constraint_removal_requested");
        }
      }
    }
    else if (action == "release")
    {
      if (fruit.state != State::HELD)
        this->Event(id, action, false, "state_must_be_HELD");
      else if (fruit.joint == kNull || !_ecm.HasEntity(fruit.joint))
        this->Event(id, action, false, "tool_constraint_missing");
      else
      {
        this->RemoveAttachment(fruit, _ecm);
        fruit.state = State::RELEASE_PENDING;
        this->Event(id, action, true, "tool_constraint_removal_requested");
      }
    }
    else this->Event(id, action, false, "unknown_action");
  }

  private: void OnCommand(const gz::msgs::StringMsg &_message)
  {
    std::lock_guard<std::mutex> guard(this->queueMutex);
    if (_message.data().size() > 512 || this->commands.size() >= 64)
    {
      ++this->droppedCommands;
      return;
    }
    this->commands.push_back(_message.data());
  }

  private: std::deque<std::string> TakeCommands()
  {
    std::deque<std::string> pending;
    std::lock_guard<std::mutex> guard(this->queueMutex);
    pending.swap(this->commands);
    return pending;
  }

  private: void RejectQueued(const std::string &_reason)
  {
    for (const auto &command : this->TakeCommands())
    {
      std::istringstream input(command);
      std::string action, id;
      input >> action >> id;
      this->Event(id, action, false, _reason);
    }
  }

  private: void Event(const std::string &_id, const std::string &_action,
      bool _accepted, const std::string &_reason, const std::string &_phase = "ack")
  {
    ++this->eventSeq;
    gz::msgs::StringMsg message;
    message.set_data("{\"schema_version\":1,\"seq\":" + std::to_string(this->eventSeq) +
        ",\"sim_time\":" + Number(this->simTime) + ",\"id\":" + Quote(_id) +
        ",\"action\":" + Quote(_action) + ",\"phase\":" + Quote(_phase) +
        ",\"accepted\":" + (_accepted ? "true" : "false") +
        ",\"reason\":" + Quote(_reason) + "}");
    if (this->eventPub) this->eventPub.Publish(message);
    this->dirty = true;
  }

  private: void Fail(const std::string &_reason)
  {
    if (this->error.empty())
    {
      this->error = _reason;
      gzerr << "[UchuvaHarvestSystem] " << _reason << std::endl;
      this->Event("", "system", false, _reason, "result");
    }
    this->ready = false;
    for (auto &fruit : this->fruits) fruit.state = State::ERROR;
    this->dirty = true;
  }

  private: void PublishState(const gz::sim::EntityComponentManager &_ecm)
  {
    const bool available = this->initialized && this->EntitiesValid(_ecm);
    std::ostringstream out;
    out << "{\"schema_version\":1,\"sim_time\":" << Number(this->simTime)
        << ",\"ready\":" << (this->ready ? "true" : "false")
        << ",\"status\":" << Quote(!this->error.empty() ? "error" :
                                  this->ready ? "ready" : "initializing")
        << ",\"error\":" << Quote(this->error)
        << ",\"waiting_for\":" << Quote(this->waitingFor)
        << ",\"mechanism\":\"idealized_cut_and_fixed_retention\""
        << ",\"constraint_evidence\":\"ecm_and_pose_residual_not_force_validation\""
        << ",\"last_event_seq\":" << this->eventSeq
        << ",\"tool_pose\":" << (available ? Pose(this->toolPose) : "null")
        << ",\"robot_pose\":" << (available ? Pose(this->robotPose) : "null")
        << ",\"fruits\":[";
    bool first = true;
    for (const auto &fruit : this->fruits)
    {
      if (!first) out << ',';
      first = false;
      const bool observed = available && fruit.hasObservation;
      out << "{\"id\":" << Quote(fruit.id)
          << ",\"state\":" << Quote(Name(fruit.state))
          << ",\"position\":" << (observed ? Vector(fruit.observedPose.Pos()) : "null")
          << ",\"cut_position\":" << (observed ? Vector(fruit.observedCut) : "null")
          << ",\"relative_speed\":" << Number(fruit.relativeSpeed)
          << ",\"stable_seconds\":" << Number(std::isfinite(fruit.stableSince) ?
                                             this->simTime - fruit.stableSince : 0)
          << ",\"joint_present\":" <<
              (fruit.joint != kNull && _ecm.HasEntity(fruit.joint) ? "true" : "false")
          << ",\"joint_parent\":" << Quote(fruit.jointParent == this->tool ? "tool" :
              fruit.jointParent == fruit.plantLinkEntity && fruit.jointParent != kNull ?
              "plant" : "none")
          << ",\"removal_pending\":" <<
              (fruit.removingJoint != kNull && _ecm.HasEntity(fruit.removingJoint) ? "true" : "false")
          << ",\"constraint_error_m\":" << Number(fruit.constraintError) << '}';
    }
    out << "]}";
    gz::msgs::StringMsg message;
    message.set_data(out.str());
    if (this->statePub) this->statePub.Publish(message);
  }

  private: gz::transport::Node node;
  private: gz::transport::Node::Publisher statePub;
  private: gz::transport::Node::Publisher eventPub;
  private: std::mutex queueMutex;
  private: std::deque<std::string> commands;
  private: std::atomic<std::uint64_t> droppedCommands{0};
  private: std::vector<Fruit> fruits;
  private: std::string robotName;
  private: std::string toolName;
  private: std::string error;
  private: std::string waitingFor;
  private: Entity world{kNull};
  private: Entity robot{kNull};
  private: Entity tool{kNull};
  private: gz::math::Pose3d toolPose;
  private: gz::math::Pose3d robotPose;
  private: double cutTolerance{0.02};
  private: double captureRadius{0.12};
  private: double maxRelativeSpeed{0.12};
  private: double stableTime{0.2};
  private: double startupTimeout{5.0};
  private: double attachmentTolerance{0.01};
  private: double initializedAt{0};
  private: double simTime{0};
  private: double nextPublishTime{-1};
  private: std::uint64_t eventSeq{0};
  private: bool initialized{false};
  private: bool ready{false};
  private: bool dirty{true};
};
}  // namespace uchuva

GZ_ADD_PLUGIN(uchuva::HarvestSystem, gz::sim::System,
    uchuva::HarvestSystem::ISystemConfigure,
    uchuva::HarvestSystem::ISystemPreUpdate,
    uchuva::HarvestSystem::ISystemPostUpdate,
    uchuva::HarvestSystem::ISystemReset)
GZ_ADD_PLUGIN_ALIAS(uchuva::HarvestSystem, "uchuva::HarvestSystem")
