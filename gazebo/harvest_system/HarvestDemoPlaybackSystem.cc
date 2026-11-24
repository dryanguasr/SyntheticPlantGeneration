// Original project code, MIT. Prescribed robot motion for native video.
#include <gz/common/Console.hh>
#include <gz/math/Pose3.hh>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Joint.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/AngularVelocityCmd.hh>
#include <gz/sim/components/JointType.hh>
#include <gz/sim/components/LinearVelocityCmd.hh>
#include <gz/transport/Node.hh>
#include <sdf/Element.hh>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iomanip>
#include <limits>
#include <locale>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

namespace uchuva
{
namespace
{
constexpr double PeakQuinticSlope = 1.875;

struct Frame
{
  double time;
  std::vector<double> values;
};

struct HarvestCommand
{
  double time;
  std::string action;
  std::string target;
};

std::ifstream Open(const std::string &_path)
{
  std::ifstream input(_path);
  input.imbue(std::locale::classic());
  if (!input) throw std::runtime_error("Cannot read " + _path);
  return input;
}

std::FILE *OpenExclusiveObservation(const std::string &_path)
{
  const int descriptor = ::open(_path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
  if (descriptor < 0)
    throw std::runtime_error("Cannot create native observations without replacing evidence: " +
        _path + ": " + std::strerror(errno));
  std::FILE *stream = ::fdopen(descriptor, "w");
  if (!stream)
  {
    const int error = errno;
    ::close(descriptor);
    throw std::runtime_error("Cannot stream native observations: " +
        _path + ": " + std::strerror(error));
  }
  return stream;
}

bool ReadRow(std::ifstream &_file, std::istringstream &_row)
{
  std::string line;
  while (std::getline(_file, line))
  {
    const auto start = line.find_first_not_of(" \t\r");
    if (start == std::string::npos || line[start] == '#') continue;
    _row.clear();
    _row.str(line);
    return true;
  }
  return false;
}
}

class HarvestDemoPlaybackSystem final : public gz::sim::System,
    public gz::sim::ISystemConfigure,
    public gz::sim::ISystemConfigurePriority,
    public gz::sim::ISystemPreUpdate,
    public gz::sim::ISystemPostUpdate
{
  public: gz::sim::System::PriorityType ConfigurePriority() override
  {
    return -10;
  }

  public: void Configure(const gz::sim::Entity &_entity,
      const std::shared_ptr<const sdf::Element> &_sdf,
      gz::sim::EntityComponentManager &_ecm, gz::sim::EventManager &) override
  {
    try
    {
      const auto config = _sdf->Clone();
      this->model = gz::sim::Model(_entity);
      if (!this->model.Valid(_ecm))
        throw std::invalid_argument("Attach playback to the articulated robot model");
      this->ReadJoints(config, _ecm);
      this->ReadTrajectory(config->Get<std::string>("trajectory_file"));
      if (config->HasElement("commands_file"))
      {
        this->ReadCommands(config->Get<std::string>("commands_file"));
        this->publisher = this->node.Advertise<gz::msgs::StringMsg>(
            config->Get<std::string>("harvest_command_topic", "/harvest/command").first);
        if (!this->publisher)
          throw std::runtime_error("Cannot advertise native harvest commands");
      }
      if (config->HasElement("observations_file"))
      {
        this->observations.reset(OpenExclusiveObservation(
            config->Get<std::string>("observations_file")));
        std::ostringstream header;
        header.imbue(std::locale::classic());
        header << "time x y z roll pitch yaw";
        for (const auto &name : this->jointNames)
          header << ' ' << name << "_position " << name << "_velocity";
        header << '\n';
        if (!this->WriteObservation(header.str()))
          throw std::runtime_error("Cannot write native playback observation header");
      }
      this->valid = true;
      gzmsg << "HarvestDemoPlaybackSystem: " << this->frames.size()
            << " prescribed frames and " << this->commands.size()
            << " native harvest commands\n";
    }
    catch (const std::exception &error)
    {
      gzerr << "HarvestDemoPlaybackSystem: " << error.what() << '\n';
    }
  }

  public: void PreUpdate(const gz::sim::UpdateInfo &_info,
      gz::sim::EntityComponentManager &_ecm) override
  {
    if (!this->valid || _info.paused) return;
    // UpdateInfo names the end of the step. Seed the state at the start and
    // let physics integrate to the observed timestamp and resolve contacts.
    const double time = std::chrono::duration<double>(_info.simTime - _info.dt).count();
    if (time < this->previousTime)
    {
      gzerr << "HarvestDemoPlaybackSystem: restart the world after a reset\n";
      this->valid = false;
      return;
    }
    this->previousTime = time;
    while (this->segment + 1 < this->frames.size() - 1 &&
        time >= this->frames[this->segment + 1].time)
      ++this->segment;
    const auto &a = this->frames[this->segment];
    const auto &b = this->frames[this->segment + 1];
    const double duration = b.time - a.time;
    const double u = std::clamp((time - a.time) / duration, 0., 1.);
    const double blend = u * u * u * (10. + u * (-15. + 6. * u));
    const double derivative = 30. * u * u * (1. - u) * (1. - u) / duration;
    const auto position = [&](size_t i)
    {
      return a.values[i] + blend * (b.values[i] - a.values[i]);
    };
    const auto velocity = [&](size_t i)
    {
      return derivative * (b.values[i] - a.values[i]);
    };

    this->model.SetWorldPoseCmd(_ecm, {position(0), position(1), position(2),
                                     0., 0., position(3)});
    // These model commands accept body-frame vectors. Rotate world motion
    // using the same observed model orientation that the Physics system uses.
    const auto rotation = gz::sim::worldPose(this->model.Entity(), _ecm).Rot();
    _ecm.SetComponentData<gz::sim::components::LinearVelocityCmd>(this->model.Entity(),
        rotation.RotateVectorReverse({velocity(0), velocity(1), velocity(2)}));
    _ecm.SetComponentData<gz::sim::components::AngularVelocityCmd>(this->model.Entity(),
        rotation.RotateVectorReverse({0., 0., velocity(3)}));
    for (size_t i = 0; i < this->joints.size(); ++i)
    {
      this->joints[i].ResetPosition(_ecm, {position(i + 4)});
      this->joints[i].ResetVelocity(_ecm, {velocity(i + 4)});
    }
    while (this->nextCommand < this->commands.size() &&
        this->commands[this->nextCommand].time <= time + 1e-10)
    {
      const auto &command = this->commands[this->nextCommand];
      gz::msgs::StringMsg message;
      message.set_data(command.action + " " + command.target);
      if (!this->publisher.Publish(message))
      {
        gzerr << "HarvestDemoPlaybackSystem: native command publish failed at "
              << time << " for " << command.target << '\n';
        this->valid = false;
        return;
      }
      ++this->nextCommand;
    }
  }

  public: void PostUpdate(const gz::sim::UpdateInfo &_info,
      const gz::sim::EntityComponentManager &_ecm) override
  {
    if (!this->valid || !this->observations || _info.paused) return;
    const double time = std::chrono::duration<double>(_info.simTime).count();
    if (time + 1e-10 < this->nextObservation) return;
    this->nextObservation = time + .05;
    const auto pose = gz::sim::worldPose(this->model.Entity(), _ecm);
    std::ostringstream row;
    row.imbue(std::locale::classic());
    row << std::setprecision(15) << time << ' ' << pose;
    for (const auto &joint : this->joints)
    {
      const auto q = joint.Position(_ecm);
      const auto v = joint.Velocity(_ecm);
      const auto nan = std::numeric_limits<double>::quiet_NaN();
      row << ' ' << (q && q->size() == 1 ? (*q)[0] : nan)
          << ' ' << (v && v->size() == 1 ? (*v)[0] : nan);
    }
    row << '\n';
    if (!this->WriteObservation(row.str()))
    {
      gzerr << "HarvestDemoPlaybackSystem: native observation write failed\n";
      this->valid = false;
    }
  }

  private: bool WriteObservation(const std::string &_row)
  {
    return std::fwrite(_row.data(), 1, _row.size(), this->observations.get()) == _row.size()
        && std::fflush(this->observations.get()) == 0;
  }

  private: void ReadJoints(const sdf::ElementPtr &_config,
      gz::sim::EntityComponentManager &_ecm)
  {
    std::set<std::string> seen;
    if (_config->HasElement("joint"))
    {
      for (auto entry = _config->GetElement("joint"); entry;
           entry = entry->GetNextElement("joint"))
      {
        const auto name = entry->Get<std::string>("name");
        const auto limit = entry->Get<double>("max_speed");
        const auto entity = this->model.JointByName(_ecm, name);
        const auto *type = _ecm.Component<gz::sim::components::JointType>(entity);
        if (!type || (type->Data() != sdf::JointType::PRISMATIC &&
                      type->Data() != sdf::JointType::REVOLUTE &&
                      type->Data() != sdf::JointType::CONTINUOUS) ||
            !seen.insert(name).second || !std::isfinite(limit) || limit <= 0.)
          throw std::invalid_argument("Invalid playback joint or rate: " + name);
        gz::sim::Joint joint(entity);
        joint.EnablePositionCheck(_ecm);
        joint.EnableVelocityCheck(_ecm);
        this->joints.push_back(joint);
        this->jointNames.push_back(name);
        this->maxSpeed.push_back(limit);
      }
    }
    if (this->joints.empty())
      throw std::invalid_argument("At least one playback joint is required");
  }

  private: void ReadTrajectory(const std::string &_path)
  {
    auto file = Open(_path);
    std::istringstream row;
    row.imbue(std::locale::classic());
    while (ReadRow(file, row))
    {
      Frame frame{0., std::vector<double>(4 + this->joints.size())};
      if (!(row >> frame.time) || !std::isfinite(frame.time) ||
          (this->frames.empty() ? frame.time != 0. : frame.time <= this->frames.back().time))
        throw std::invalid_argument("Playback times must start at zero and increase");
      for (auto &value : frame.values)
        if (!(row >> value) || !std::isfinite(value))
          throw std::invalid_argument("Invalid or missing playback coordinate");
      std::string extra;
      if (row >> extra)
        throw std::invalid_argument("Unexpected playback coordinate");
      if (!this->frames.empty())
      {
        const auto &prev = this->frames.back();
        const double duration = frame.time - prev.time;
        for (size_t i = 0; i < this->joints.size(); ++i)
        {
          const double speed = PeakQuinticSlope *
              std::abs(frame.values[i + 4] - prev.values[i + 4]) / duration;
          if (speed > this->maxSpeed[i] + 1e-9)
            throw std::invalid_argument("Playback rate exceeded at " +
                std::to_string(frame.time) + " by " + this->jointNames[i]);
        }
      }
      this->frames.push_back(std::move(frame));
    }
    if (this->frames.size() < 2)
      throw std::invalid_argument("At least two playback waypoints are required");
  }

  private: void ReadCommands(const std::string &_path)
  {
    auto file = Open(_path);
    std::istringstream row;
    row.imbue(std::locale::classic());
    double previous = 0.;
    while (ReadRow(file, row))
    {
      HarvestCommand command;
      std::string extra;
      if (!(row >> command.time >> command.action >> command.target) || row >> extra ||
          !std::isfinite(command.time) || command.time <= previous ||
          command.time > this->frames.back().time ||
          (command.action != "arm" && command.action != "cut" && command.action != "release"))
        throw std::invalid_argument("Invalid timed harvest command");
      previous = command.time;
      this->commands.push_back(std::move(command));
    }
  }

  private: gz::sim::Model model{gz::sim::kNullEntity};
  private: std::vector<gz::sim::Joint> joints;
  private: std::vector<std::string> jointNames;
  private: std::vector<double> maxSpeed;
  private: std::vector<Frame> frames;
  private: std::vector<HarvestCommand> commands;
  private: gz::transport::Node node;
  private: gz::transport::Node::Publisher publisher;
  private: std::unique_ptr<std::FILE, decltype(&std::fclose)> observations{nullptr, &std::fclose};
  private: size_t segment{0};
  private: size_t nextCommand{0};
  private: double previousTime{-1.};
  private: double nextObservation{0.};
  private: bool valid{false};
};
}

GZ_ADD_PLUGIN(uchuva::HarvestDemoPlaybackSystem, gz::sim::System,
    uchuva::HarvestDemoPlaybackSystem::ISystemConfigure,
    uchuva::HarvestDemoPlaybackSystem::ISystemConfigurePriority,
    uchuva::HarvestDemoPlaybackSystem::ISystemPreUpdate,
    uchuva::HarvestDemoPlaybackSystem::ISystemPostUpdate)
