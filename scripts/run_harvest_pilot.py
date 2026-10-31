#!/usr/bin/env python3
"""Run and audit a fresh Gazebo Harmonic harvest world (Linux / WSL).

No Gazebo imports occur until native execution starts. Inputs are frozen by
checksums; each run has isolated transport, an exclusive lock and separate raw
evidence. The fixture intentionally uses simulation truth for mechanics.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from uchuva_gazebo.harvester_robot import HarvesterConfig, inverse_kinematics
from uchuva_gazebo.harvest_pilot import load_verified_package, sha256_file
from uchuva_gazebo.harvest_validation import (angle_error, deposited_interval, distance,
    fruit_map, local_point, rotate_vector, world_point, yaw_of)
from audit_harvest_pilot import (NATIVE_SOURCE_FILES, audit, json_safe,
    strict_json_loads, valid_digest)


def write_json(path, data):
    Path(path).write_text(json.dumps(json_safe(data), indent=2, allow_nan=False) + '\n', encoding='utf-8')


def verified_plugin_build(manifest, directory):
    """Verify every required source and the shared library before Gazebo loads it."""
    directory = Path(directory).resolve()
    library = directory / 'libUchuvaHarvestSystem.so'
    provenance_path = directory / 'build_provenance.json'
    provenance = strict_json_loads(provenance_path.read_text(encoding='utf-8'))
    if not library.is_file() or not valid_digest(provenance.get('library_sha256')) or provenance['library_sha256'] != sha256_file(library):
        raise RuntimeError('Missing or changed native plugin; run build_harvest_plugin.sh')
    sources = provenance.get('source_sha256', {})
    if set(sources) != set(NATIVE_SOURCE_FILES):
        raise RuntimeError('Incomplete native plugin source provenance; rebuild the plugin')
    for name, digest in sources.items():
        expected = manifest.get('source', {}).get('files_sha256', {}).get('gazebo/harvest_system/' + name)
        if not valid_digest(digest) or expected != digest:
            raise RuntimeError('Plugin and prepared scene come from different source revisions; prepare a fresh package')
    return {**provenance, 'provenance_sha256': sha256_file(provenance_path), 'library_path': str(library)}


class NativePilot:
    def __init__(self, manifest, output, server, streams, wall_timeout):
        from gz.transport13 import Node
        from gz.msgs10.double_pb2 import Double
        from gz.msgs10.model_pb2 import Model
        from gz.msgs10.stringmsg_pb2 import StringMsg
        from gz.msgs10.twist_pb2 import Twist
        self.Double, self.StringMsg, self.Twist = Double, StringMsg, Twist
        self.manifest, self.output, self.server, self.streams = manifest, output, server, streams
        self.config = HarvesterConfig(**manifest['robot_config'])
        self.node = Node()
        self.condition = threading.Condition()
        self._closing = False
        self._subscriptions = []
        self.phase = 'startup'
        self.active_target = None
        self.state = None
        self.events = []
        self.samples = []
        self.joints = {}
        self.joint_time = None
        self.callback_error = None
        self.recording = False
        self.last_state_wall = time.monotonic()
        self.started_wall = time.monotonic()
        self.wall_timeout = wall_timeout
        self.interaction = manifest['interaction']
        topics = manifest['robot']['topics']
        self.base_publisher = self.node.advertise(topics['cmd_vel'], Twist)
        self.arm_publishers = {name: self.node.advertise(topic, Double)
                               for name, topic in topics['joint_commands'].items()}
        self.command_publisher = self.node.advertise(self.interaction['command_topic'], StringMsg)
        try:
            for msg_type, topic, callback in (
                (StringMsg, self.interaction['state_topic'], self._state_callback),
                (StringMsg, self.interaction['event_topic'], self._event_callback),
                (Model, topics['joint_states'], self._joint_callback),
            ):
                if not self.node.subscribe(msg_type, topic, callback):
                    raise RuntimeError(f'Could not subscribe to {topic}')
                self._subscriptions.append(topic)
        except Exception:
            self.close()
            raise

    def close(self):
        """Quiesce callbacks before their evidence streams can be closed."""
        with self.condition:
            self._closing = True
            topics, self._subscriptions = self._subscriptions, []
        # Do not hold the callback lock while a binding waits for unsubscribe.
        for topic in topics:
            try:
                self.node.unsubscribe(topic)
            except Exception as error:
                with self.condition:
                    self.callback_error = f'Unsubscribe failed for {topic}: {error}'

    def _line(self, name, value):
        self.streams[name].write(json.dumps(value, allow_nan=False) + '\n')
        self.streams[name].flush()

    def _state_callback(self, message):
        with self.condition:
            if self._closing:
                return
            try:
                state = strict_json_loads(message.data)
                if not isinstance(state, dict) or type(state.get('sim_time')) not in (int, float) or not math.isfinite(state['sim_time']):
                    raise ValueError('State must contain a finite simulation timestamp')
                if self.state is not None and state['sim_time'] < self.state['sim_time']:
                    raise ValueError('Simulation time regressed; a fresh process is required after reset')
                state['phase'] = self.phase
                state['active_target'] = self.active_target
                state['arm_joints_rad'] = dict(self.joints)
                state['joint_state_sim_time'] = self.joint_time
                self.state = state
                self.last_state_wall = time.monotonic()
                if state.get('ready'):
                    self.recording = True
                if self.recording:
                    self.samples.append(state)
                    self._line('telemetry', state)
            except (ValueError, TypeError, OSError) as error:
                self.callback_error = str(error)
            self.condition.notify_all()

    def _event_callback(self, message):
        with self.condition:
            if self._closing:
                return
            try:
                event = strict_json_loads(message.data)
                if not isinstance(event, dict) or type(event.get('seq')) is not int or event['seq'] <= 0:
                    raise ValueError('Event must contain a positive integer sequence number')
                if type(event.get('sim_time')) not in (int, float) or not math.isfinite(event['sim_time']):
                    raise ValueError('Event must contain a finite simulation timestamp')
                if type(event.get('accepted')) is not bool or event.get('phase') not in ('ack', 'result'):
                    raise ValueError('Event has invalid acknowledgement fields')
                if self.events and event['seq'] <= self.events[-1]['seq']:
                    raise ValueError('Duplicate or out-of-order harvest event')
                event['client_phase'] = self.phase
                self.events.append(event)
                self._line('events', event)
            except (ValueError, TypeError, OSError) as error:
                self.callback_error = str(error)
            self.condition.notify_all()

    def _joint_callback(self, message):
        with self.condition:
            if self._closing:
                return
            try:
                expected = set(self.manifest['robot']['arm_joint_names'])
                pairs = [(j.name, j.axis1.position) for j in message.joint if j.name in expected]
                joints = dict(pairs)
                stamp = message.header.stamp.sec + 1e-9 * message.header.stamp.nsec
                if len(pairs) != len(joints) or not all(math.isfinite(v) for v in joints.values()) or not math.isfinite(stamp):
                    raise ValueError('Missing, duplicate or non-finite joint state')
                if set(joints) != expected:
                    if self.joint_time is None:
                        # Component publication may start before every joint
                        # is observed. move_joints still requires a complete,
                        # fresh message and times out if it never arrives.
                        return
                    raise ValueError('Missing joint in an established joint-state stream')
                if self.joint_time is not None and stamp < self.joint_time:
                    raise ValueError('Joint-state clock regressed')
                self.joints, self.joint_time = joints, stamp
            except (AttributeError, TypeError, ValueError) as error:
                self.callback_error = f'Invalid joint-state message: {error}'
            self.condition.notify_all()

    def set_phase(self, phase, identifier=None):
        with self.condition:
            self.phase = phase
            self.active_target = identifier
        print(f'{phase}' + (f': {identifier}' if identifier else ''), flush=True)

    def snapshot(self):
        with self.condition:
            return self.state

    def _health(self):
        if self.server.poll() is not None:
            raise RuntimeError(f'Gazebo exited with status {self.server.returncode}')
        if self.callback_error:
            raise RuntimeError(f'Telemetry callback failed: {self.callback_error}')
        if time.monotonic() - self.started_wall > self.wall_timeout:
            raise TimeoutError('Global wall-clock timeout')
        state = self.snapshot()
        if state:
            if state.get('status') == 'error':
                raise RuntimeError('Harvest system: ' + state.get('error', 'unknown error'))
            if time.monotonic() - self.last_state_wall > 15:
                raise TimeoutError('No new simulator telemetry for 15 wall-clock seconds')
            pose = state.get('robot_pose', [])
            # The native system publishes null poses while resolving entities.
            # They are expected before ready and are not evidence samples.
            if state.get('ready') and (not isinstance(pose, list) or len(pose) != 7):
                raise RuntimeError('Ready state is missing the observed robot pose')
            if isinstance(pose, list) and len(pose) == 7 and rotate_vector(pose[3:], [0, 0, 1])[2] < math.cos(.30):
                raise RuntimeError('Robot tilt exceeded 0.30 rad')
        return state

    def wait(self, predicate, *, simulation_timeout=30, wall_timeout=180, action=None):
        started = time.monotonic()
        start_sim = None
        last_action = None
        while time.monotonic() - started < wall_timeout:
            state = self._health()
            if state is not None:
                now = state['sim_time']
                if start_sim is None:
                    start_sim = now
                if now - start_sim > simulation_timeout:
                    raise TimeoutError(f'Simulation timeout in {self.phase}')
                if action is not None and now != last_action:
                    action(state)
                    last_action = now
                if predicate(state):
                    return state
            with self.condition:
                self.condition.wait(timeout=.02)
        raise TimeoutError(f'Wall-clock timeout in {self.phase}')

    def hold(self, seconds):
        start = self.snapshot()['sim_time']
        return self.wait(lambda s: s['sim_time'] - start >= seconds,
                         simulation_timeout=seconds + 2, action=lambda _: self.send_base(0, 0))

    def send_base(self, linear, angular):
        msg = self.Twist()
        msg.linear.x, msg.angular.z = float(linear), float(angular)
        self.base_publisher.publish(msg)
        with self.condition:
            self._line('commands', {'kind': 'base_velocity', 'phase': self.phase,
                                   'sim_time': self.state['sim_time'] if self.state else None,
                                   'linear_m_s': linear, 'angular_rad_s': angular})

    def send_joints(self, values):
        for name, value in zip(self.manifest['robot']['arm_joint_names'], values):
            msg = self.Double()
            msg.data = float(value)
            self.arm_publishers[name].publish(msg)
        with self.condition:
            self._line('commands', {'kind': 'arm_position', 'phase': self.phase,
                                   'sim_time': self.state['sim_time'] if self.state else None,
                                   'positions_rad': list(values)})

    def command(self, action, identifier, expected=True, reason=None):
        self.wait(lambda state: state.get('ready') is True, simulation_timeout=3)
        with self.condition:
            last_seq = max((ev['seq'] for ev in self.events), default=0)
        msg = self.StringMsg()
        msg.data = action + (f' {identifier}' if identifier else '')
        self._line('commands', {'kind': 'interaction', 'command': msg.data, 'phase': self.phase,
                               'sim_time': self.snapshot()['sim_time']})
        if not self.command_publisher.publish(msg):
            raise RuntimeError(f'Unable to publish {msg.data}')

        def acknowledged(_state):
            with self.condition:
                return any(ev['seq'] > last_seq and ev.get('phase') == 'ack'
                           and ev.get('action') == action and ev.get('id') == identifier for ev in self.events)

        self.wait(acknowledged, simulation_timeout=3, wall_timeout=20)
        with self.condition:
            event = next(ev for ev in self.events if ev['seq'] > last_seq and ev.get('phase') == 'ack'
                         and ev.get('action') == action and ev.get('id') == identifier)
        if event.get('accepted') is not expected or (reason is not None and event.get('reason') != reason):
            raise RuntimeError(f'Unexpected acknowledgement: {event}')
        return event

    def move_joints(self, target, expected_tool=None):
        names = self.manifest['robot']['arm_joint_names']
        state = self.wait(lambda s: all(name in self.joints for name in names)
                          and self.joint_time is not None and abs(s['sim_time'] - self.joint_time) < .3,
                          simulation_timeout=3)
        start_joints = [self.joints[name] for name in names]
        started = state['sim_time']
        # Cubic interpolation's peak derivative is 1.5; cap nominal joint speed.
        duration = max(.8, 1.5 * max(abs(a - b) for a, b in zip(start_joints, target)) / .35)
        stable_since = None

        def advance(current):
            u = max(0.0, min(1.0, (current['sim_time'] - started) / duration))
            blend = u * u * (3 - 2 * u)
            self.send_joints([a + blend * (b - a) for a, b in zip(start_joints, target)])
            self.send_base(0, 0)

        def converged(current):
            nonlocal stable_since
            t = current['sim_time']
            valid = t >= started + duration and self.joint_time is not None and abs(t - self.joint_time) < .3
            valid = valid and all(abs(self.joints.get(name, math.inf) - q) <= .035 for name, q in zip(names, target))
            if expected_tool is not None:
                valid = valid and distance(current['tool_pose'][:3], expected_tool) <= .006
            stable_since = (t if stable_since is None else stable_since) if valid else None
            return stable_since is not None and t - stable_since >= .4

        self.wait(converged, simulation_timeout=duration + 15, wall_timeout=240, action=advance)

    def move_tool(self, world_target):
        target_in_base = local_point(world_target, self.snapshot()['robot_pose'])
        self.move_joints(inverse_kinematics(target_in_base, config=self.config), expected_tool=world_target)

    def carry(self):
        target = self.manifest['mission']['carry_tcp_base_m']
        self.move_joints(inverse_kinematics(target, config=self.config))

    def drive_to(self, x, y, yaw=0):
        stable_since = None

        def control(state):
            nonlocal stable_since
            pose = state['robot_pose']
            dx, dy = x - pose[0], y - pose[1]
            remaining = math.hypot(dx, dy)
            if remaining > .003:
                heading_error = angle_error(math.atan2(dy, dx), yaw_of(pose))
                linear = min(.16, .7 * remaining) if abs(heading_error) < .22 else 0.0
                angular = max(-.45, min(.45, 1.5 * heading_error))
                stable_since = None
            else:
                heading_error = angle_error(yaw, yaw_of(pose))
                linear = 0.0
                angular = max(-.35, min(.35, 1.4 * heading_error)) if abs(heading_error) > .008 else 0.0
                if angular == 0:
                    stable_since = state['sim_time'] if stable_since is None else stable_since
                else:
                    stable_since = None
            self.send_base(linear, angular)

        self.wait(lambda s: stable_since is not None and s['sim_time'] - stable_since >= .5,
                  simulation_timeout=150, wall_timeout=600, action=control)
        self.send_base(0, 0)

    def leave_bin_to_aisle(self):
        mission = self.manifest['mission']
        pose = self.snapshot()['robot_pose']
        aisle, via_y = mission['aisle_x_m'], mission['deposit_via_y_m']
        # The direct line from the aisle to the docking pose crosses the bin.
        # Route behind its lower edge, preserving a chassis-width clearance.
        if pose[0] < aisle - .2:
            self.drive_to(pose[0], via_y, -math.pi / 2)
            self.drive_to(aisle, via_y, 0)
        else:
            self.drive_to(aisle, pose[1], 0)

    def pickup_route(self, target):
        self.leave_bin_to_aisle()
        x, y, yaw = target['pickup_base_xyyaw']
        self.drive_to(self.manifest['mission']['aisle_x_m'], y, 0)
        self.drive_to(x, y, yaw)

    def deposit_route(self):
        mission = self.manifest['mission']
        pose = self.snapshot()['robot_pose']
        aisle, via_y = mission['aisle_x_m'], mission['deposit_via_y_m']
        x, y, yaw = mission['deposit_base_xyyaw']
        self.drive_to(aisle, pose[1], 0)
        self.drive_to(aisle, via_y, -math.pi / 2)
        self.drive_to(x, via_y, math.pi)
        self.drive_to(x, y, yaw)

    def run(self, target_ids, mode):
        self.wait(lambda s: s.get('ready') is True, simulation_timeout=8, wall_timeout=120)
        self.set_phase('stow')
        self.carry()
        self.set_phase('baseline')
        self.hold(2.5)
        self.set_phase('negative_unknown')
        self.command('arm', 'unknown_fruit', False, 'unknown_fruit')
        self.set_phase('negative_far')
        self.command('arm', target_ids[0], False, 'cut_point_out_of_range')
        self.command('cut', target_ids[0], False, 'state_must_be_ARMED')
        if mode == 'smoke':
            self.set_phase('finished')
            self.hold(.5)
            return
        plans = {p['id']: p for p in self.manifest['mission']['targets']}
        specs = {p['id']: p for p in self.manifest['fruits']}
        for identifier in target_ids:
            plan = plans[identifier]
            self.set_phase('drive_pickup', identifier)
            self.pickup_route(plan)
            self.set_phase('preapproach', identifier)
            self.move_tool(plan['tool_waypoints_world_m']['preapproach'])
            self.set_phase('approach_cut', identifier)
            cut = fruit_map(self.snapshot())[identifier]['cut_position']
            self.move_tool(cut)
            self.command('arm', identifier)
            # Exercise the actual geometric guard after arming, not just the
            # easier rejection of a cut in ATTACHED state.
            self.set_phase('negative_armed_far', identifier)
            self.move_tool(plan['tool_waypoints_world_m']['preapproach'])
            self.command('cut', identifier, False, 'cut_point_out_of_range')
            self.set_phase('cut', identifier)
            self.move_tool(fruit_map(self.snapshot())[identifier]['cut_position'])
            self.wait(lambda s: fruit_map(s)[identifier].get('stable_seconds', 0) >= .22,
                      simulation_timeout=4, action=lambda _: self.send_base(0, 0))
            self.command('cut', identifier)
            self.wait(lambda s: s.get('ready') and fruit_map(s)[identifier]['state'] == 'HELD', simulation_timeout=4)
            self.set_phase('negative_repeat', identifier)
            self.command('cut', identifier, False, 'state_must_be_ARMED')
            self.set_phase('retract', identifier)
            for waypoint in plan['withdrawal_sequence']:
                self.move_tool(plan['tool_waypoints_world_m'][waypoint])
            self.set_phase('carry', identifier)
            self.carry()
            self.set_phase('drive_deposit', identifier)
            self.deposit_route()
            self.set_phase('deposit_position', identifier)
            # Preserve the measured latch offset: align the FRUIT centre with
            # the tray, not merely the TCP. Orientation at this goal is near
            # horizontal; recompute once using the observed tool quaternion.
            goal = self.manifest['mission']['deposit_tool_world_m']
            self.move_tool(goal)
            current = self.snapshot()
            offset = [a - b for a, b in zip(fruit_map(current)[identifier]['position'], current['tool_pose'][:3])]
            corrected = [goal[0] - offset[0], goal[1] - offset[1], goal[2]]
            self.move_tool(corrected)
            self.set_phase('release', identifier)
            self.command('release', identifier)
            self.wait(lambda s: fruit_map(s)[identifier]['state'] == 'RELEASED', simulation_timeout=3)
            self.set_phase('settle_in_bin', identifier)

            def settled(_state):
                with self.condition:
                    recent = self.samples[-100:]
                return deposited_interval(recent, identifier, specs[identifier]['radius_m'], self.manifest['bin'])['passed']

            self.wait(settled, simulation_timeout=8, wall_timeout=120, action=lambda _: self.send_base(0, 0))
            self.set_phase('stow_after_deposit', identifier)
            self.carry()
        self.set_phase('finished')
        self.hold(.5)


def parser_for_run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--plugin-dir', type=Path, default=REPO / 'outputs/harvest_plugin_build')
    parser.add_argument('--mode', choices=('smoke', 'harvest'), default='smoke')
    parser.add_argument('--max-targets', type=int, default=1)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--wall-timeout', type=float, default=3600)
    parser.add_argument('--gui', action='store_true', help='Also open a GUI on this isolated transport partition')
    return parser


def main(argv=None):
    parser = parser_for_run()
    args = parser.parse_args(argv)
    package = args.package.resolve()
    manifest = load_verified_package(package)
    if not 1 <= args.max_targets <= len(manifest['mission']['targets']) or not math.isfinite(args.wall_timeout) or args.wall_timeout <= 0:
        parser.error('Invalid target count or wall timeout')
    output = args.output or package / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + f'-{os.getpid()}')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    target_ids = [p['id'] for p in manifest['mission']['targets'][:args.max_targets]]
    partition = f'uchuva_harvest_{os.getpid()}_{time.time_ns()}'
    os.environ['GZ_PARTITION'] = partition
    os.environ['GZ_SIM_RESOURCE_PATH'] = str(package) + os.pathsep + os.environ.get('GZ_SIM_RESOURCE_PATH', '')
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(args.plugin_dir.resolve()) + os.pathsep + os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH', '')
    metadata = {'mode': args.mode, 'target_ids': target_ids, 'manifest_sha256': sha256_file(package / 'manifest.json'),
                'partition': partition, 'python': sys.executable, 'runner_sha256': sha256_file(Path(__file__)),
                'gui_requested': args.gui, 'target_source': 'simulation_truth', 'status': 'native_execution_attempt',
                'native_executed': False, 'forced_gazebo_major': 8}
    write_json(output / 'run.json', metadata)
    failure = None
    server = gui = pilot = None
    start = time.monotonic()
    with ExitStack() as stack:
        lock = stack.enter_context((package / '.harvest_run.lock').open('a+'))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            failure = 'Another harvest run owns this package; use a separate prepared package'
        streams = {name: stack.enter_context((output / (name + '.jsonl')).open('w', encoding='utf-8'))
                   for name in ('telemetry', 'events', 'commands')}
        log = stack.enter_context((output / 'server.log').open('w', encoding='utf-8'))
        try:
            if failure:
                raise RuntimeError(failure)
            if not shutil.which('gz'):
                raise RuntimeError('Gazebo Harmonic executable gz is not available')
            provenance = verified_plugin_build(manifest, args.plugin_dir)
            metadata['plugin_sha256'] = provenance['library_sha256']
            metadata['plugin_build'] = provenance
            result = subprocess.run(['gz', 'sim', '--versions'], capture_output=True, text=True, timeout=15)
            metadata['gazebo_versions'] = result.stdout.strip()
            if result.returncode or not re.search(r'(?m)^\s*8\.\d+\.\d+\s*$', result.stdout):
                raise RuntimeError('Gazebo Sim 8 / Harmonic is not listed by gz sim --versions')
            write_json(output / 'run.json', metadata)
            checked = subprocess.run(['gz', 'sdf', '-k', str(package / manifest['world_file'])],
                                     capture_output=True, text=True, timeout=30)
            (output / 'sdf_check.log').write_text(checked.stdout + checked.stderr)
            if checked.returncode:
                raise RuntimeError('Native SDF validation failed; inspect sdf_check.log')
            # Fail before starting a simulator if Python bindings are absent.
            from gz.transport13 import Node  # noqa: F401
            from gz.msgs10.stringmsg_pb2 import StringMsg  # noqa: F401
            # gz sim otherwise chooses the newest installed major version.
            # https://gazebosim.org/docs/harmonic/gui/
            command = ['gz', 'sim', '--force-version', '8', '-s', '-r', '-v', '3']
            if manifest['robot_config']['camera'] and not args.gui:
                command.append('--headless-rendering')
            command.append(str(package / manifest['world_file']))
            server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=package)
            metadata.update(native_executed=True, status='native_server_started', server_command=command)
            write_json(output / 'run.json', metadata)
            if args.gui:
                gui_log = stack.enter_context((output / 'gui.log').open('w'))
                gui = subprocess.Popen(['gz', 'sim', '--force-version', '8', '-g', '-v', '2'], stdout=gui_log, stderr=subprocess.STDOUT, cwd=package)
            pilot = NativePilot(manifest, output, server, streams, args.wall_timeout)
            pilot.run(target_ids, args.mode)
        except KeyboardInterrupt:
            failure = 'operator_interrupted'
        except Exception as error:
            failure = f'{type(error).__name__}: {error}'
        finally:
            if pilot is not None:
                try:
                    pilot.send_base(0, 0)
                except Exception:
                    pass
                pilot.close()
            for process in (gui, server):
                if process is not None and process.poll() is None:
                    try:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                    except (OSError, subprocess.SubprocessError) as error:
                        if failure is None:
                            failure = f'Native process cleanup failed: {error}'
            # close() quiesced callback writers while evidence streams remained open.
            if pilot is not None:
                if pilot.callback_error and failure is None:
                    failure = pilot.callback_error
    metadata['status'] = 'native_run_failed' if failure else 'native_run_finished'
    write_json(output / 'run.json', metadata)
    write_json(output / 'outcome.json', {'error': failure, 'wall_seconds': time.monotonic() - start})
    try:
        report = audit(package, output)
    except Exception as error:
        report = {'passed': False, 'error': f'Audit failed: {error}', 'physical_validation': 'failed_or_unobserved'}
    write_json(output / 'summary.json', report)
    failed = [c['name'] for c in report.get('checks', []) if not c['passed']]
    print(json.dumps({'output': str(output), 'passed': report['passed'], 'failure': failure,
                      'failed_checks': failed}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
