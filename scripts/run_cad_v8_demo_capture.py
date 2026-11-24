#!/usr/bin/env python3
"""Capture a continuous native Gazebo take of the prescribed CAD demonstration."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))

from audit_harvest_pilot import strict_json_loads
from uchuva_gazebo.harvest_basket import load_fruit_vertices
from uchuva_gazebo.harvest_pilot import _video_observer, sha256_file
from uchuva_gazebo.harvest_validation import deposited_interval

CAMERA_LIBRARY = 'libUchuvaHarvestDemoCameraSystem.so'
CAMERA_SYSTEM = 'uchuva::HarvestDemoCameraSystem'


def prepare_camera(world, robot_name='harvester', *, eye_offset=(-1.58, -.90, 1.42),
                   look_offset=(.23, .04, .23), fps=15, horizontal_fov=1.23):
    """Replace the fixed observer by a crop-side tracking observer in the new SDF."""
    robot = next(model for model in world.findall('model') if model.get('name') == robot_name)
    position = tuple(map(float, robot.findtext('pose', '0 0 0 0 0 0').split()[:3]))
    if any(len(values) != 3 for values in (position, eye_offset, look_offset)):
        raise ValueError('Camera offsets and robot position require three coordinates')
    dx, dy, dz = (b - a for a, b in zip(eye_offset, look_offset))
    if math.hypot(dx, dy) < .1:
        raise ValueError('Camera needs at least 0.1 m horizontal separation from its target')
    pose = [a + b for a, b in zip(position, eye_offset)]
    pose.extend((0, math.atan2(-dz, math.hypot(dx, dy)), math.atan2(dy, dx)))
    settings = {'pose': pose, 'width': 1280, 'height': 720, 'fps': fps,
                'horizontal_fov_rad': horizontal_fov, 'topic': '/harvest/video_observer/image'}
    for observer in world.findall("model[@name='harvest_video_observer']"):
        world.remove(observer)
    _video_observer(world, settings)
    observer = world.find("model[@name='harvest_video_observer']")
    plugin = ET.SubElement(observer, 'plugin', filename=CAMERA_LIBRARY, name=CAMERA_SYSTEM)
    ET.SubElement(plugin, 'robot_name').text = robot_name
    ET.SubElement(plugin, 'eye_offset').text = ' '.join(map(str, eye_offset))
    ET.SubElement(plugin, 'look_offset').text = ' '.join(map(str, look_offset))
    return settings


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                    encoding='utf-8')


def read_json(path):
    return strict_json_loads(path.read_text(encoding='utf-8'))


def read_rows(path):
    with path.open(encoding='utf-8') as stream:
        return [strict_json_loads(line) for line in stream if line.strip()]


class HarvestSignals:
    """Keep native events and state unchanged in separate evidence streams."""

    def __init__(self, output, interaction, stack):
        from gz.msgs10.stringmsg_pb2 import StringMsg
        from gz.transport13 import Node

        self.node = Node()
        self.lock = threading.Lock()
        self.sim_time = None
        self.error = None
        self.closed = False
        self.topics = []
        streams = {name: stack.enter_context((output / (name + '.jsonl')).open('x', encoding='utf-8'))
                   for name in ('telemetry', 'events')}
        stack.callback(self.close)
        for name, kind in (('telemetry', 'state'), ('events', 'event')):
            topic = interaction[kind + '_topic']
            if not self.node.subscribe(StringMsg, topic, self.callback(streams[name], kind)):
                raise RuntimeError(f'No transport subscription for {topic}')
            self.topics.append(topic)

    def callback(self, stream, kind):
        def receive(message):
            with self.lock:
                if self.closed:
                    return
                try:
                    data = strict_json_loads(message.data)
                    stamp = data['sim_time']
                    if not isinstance(stamp, (float, int)) or not math.isfinite(stamp):
                        raise ValueError('Native evidence is missing simulation time')
                    stream.write(json.dumps(data, ensure_ascii=False, allow_nan=False) + '\n')
                    stream.flush()
                    if kind == 'state':
                        if self.sim_time is not None and stamp < self.sim_time:
                            raise ValueError('Native state time regressed')
                        self.sim_time = stamp
                        if data.get('status') == 'error':
                            raise RuntimeError(data.get('error', 'Native HarvestSystem failed'))
                except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
                    self.error = str(error)
        return receive

    def close(self):
        with self.lock:
            self.closed = True
            topics, self.topics = self.topics, []
        for topic in topics:
            self.node.unsubscribe(topic)


def stop_server(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def capture(package, source_package, plugin_dirs, output, wall_timeout, *, record_video):
    from harvest_native_video import NativeVideoRecorder

    manifest_file = package / 'demo_manifest.json'
    manifest = read_json(manifest_file)
    source_file = source_package / 'manifest.json'
    source = read_json(source_file)
    world = (package / manifest['world_file']).resolve(strict=True)
    if not world.is_relative_to(package):
        raise ValueError('Demo world path escapes its package')
    if manifest['source_manifest_sha256'] != sha256_file(source_file):
        raise ValueError('The original fruit and basket manifest differs from this demo package')
    for name, expected in manifest['files_sha256'].items():
        artifact = (package / name).resolve(strict=True)
        if not artifact.is_relative_to(package) or sha256_file(artifact) != expected:
            raise ValueError(f'Mismatched demonstration artifact {name}')
    check = subprocess.run(['gz', 'sdf', '-k', str(world)], capture_output=True, text=True, timeout=60)
    if check.returncode:
        raise RuntimeError(f'Gazebo rejected the demonstration SDF: {check.stdout}{check.stderr}')
    video_settings = manifest['video_observer'] if record_video else None
    duration = manifest['duration_s']
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Demo duration must be positive and finite')
    interaction = manifest.get('interaction', source['interaction'])
    output.mkdir(parents=True, exist_ok=False)
    (output / 'sdf_check.log').write_text(check.stdout + check.stderr, encoding='utf-8')
    partition = f'uchuva_v8_take_{os.getpid()}_{time.time_ns()}'
    os.environ['GZ_PARTITION'] = partition
    os.environ['GZ_SIM_RESOURCE_PATH'] = os.pathsep.join(map(str, (package, source_package)))
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = os.pathsep.join(map(str, plugin_dirs))
    command = ['gz', 'sim', '--force-version', '8', '-s', '-r', '-v', '3']
    if record_video:
        command.append('--headless-rendering')
    command.append(str(world))
    provenance = {'status': 'CAPTURING', 'scope': 'Prescribed robot motion, native Gazebo RGB and fruit lifecycle',
                  'partition': partition, 'server_command': command, 'maximum_wall_seconds': wall_timeout,
                  'expected_simulation_seconds': duration, 'demo_manifest_sha256': sha256_file(manifest_file),
                  'source_manifest_sha256': sha256_file(source_file), 'world_sha256': sha256_file(world),
                  'target_ids': manifest['target_ids'], 'record_requested': record_video,
                  'plugin_sha256': {str(library): sha256_file(library) for directory in plugin_dirs
                                    for library in sorted(directory.glob('libUchuva*.so'))}}
    write_json(output / 'run.json', provenance)
    server = video = None
    failure = None
    started = time.monotonic()
    with ExitStack() as stack:
        log = stack.enter_context((output / 'server.log').open('x', encoding='utf-8'))
        try:
            signals = HarvestSignals(output, interaction, stack)
            if record_video:
                video = NativeVideoRecorder(output, video_settings)
            server = subprocess.Popen(command, cwd=package, stdout=log, stderr=subprocess.STDOUT,
                                      start_new_session=True)
            next_progress = 0
            while True:
                if server.poll() is not None:
                    raise RuntimeError(f'Gazebo exited early with code {server.returncode}')
                with signals.lock:
                    last_state, error = signals.sim_time, signals.error
                last_frame = video_error = None
                if video is not None:
                    with video.lock:
                        last_frame = video.rows[-1]['sim_time'] if video.rows else None
                        video_error = video.error or video.encoder.error
                if error or video_error:
                    raise RuntimeError(error or video_error)
                if last_state is not None and last_state >= next_progress:
                    print(f'Gazebo {last_state:.2f}/{duration:.2f} s', flush=True)
                    next_progress = last_state + 5
                if last_state is not None and last_state >= duration:
                    if video is None or (last_frame is not None and
                                         last_frame >= duration - 1 / video_settings['fps']):
                        break
                if time.monotonic() >= started + wall_timeout:
                    raise TimeoutError(f'Capture timed out at native state {last_state}, RGB {last_frame}')
                time.sleep(.05)
        except (KeyboardInterrupt, OSError, RuntimeError, TimeoutError) as error:
            failure = f'{type(error).__name__}: {error}'
        finally:
            if server is not None:
                stop_server(server)
                provenance['server_exit_code'] = server.returncode
            if video is not None:
                try:
                    provenance['native_video'] = video.close()
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    failure = failure or str(error)
    provenance.update(status='FAILED' if failure else 'CAPTURED', error=failure,
                      wall_seconds=time.monotonic() - started)
    write_json(output / 'run.json', provenance)
    return failure


def deposit_evidence(source_package, output):
    source_file = source_package / 'manifest.json'
    source_digest = sha256_file(source_file)
    source = read_json(source_file)
    run = read_json(output / 'run.json')
    recorded_source = run.get('source_manifest_sha256') or run.get('manifest_sha256')
    if recorded_source != source_digest:
        raise ValueError('The native run belongs to a different source manifest')
    samples = [row for row in read_rows(output / 'telemetry.jsonl') if row.get('ready')]
    events = read_rows(output / 'events.jsonl')
    native_results = {(row['id'], row['action']): row['sim_time'] for row in events
                      if row.get('phase') == 'result' and row.get('accepted') is True}
    vertices = load_fruit_vertices(source, source_package)
    results = []
    targets = set(run['target_ids'])
    for fruit in source['fruits']:
        identifier = fruit['id']
        if identifier not in targets:
            continue
        cut = native_results.get((identifier, 'cut'))
        release = native_results.get((identifier, 'release'))
        if cut is None or release is None or not 0 <= cut < release:
            continue
        after_release = [row for row in samples if row['sim_time'] >= release]
        result = deposited_interval(after_release, identifier, fruit['radius_m'], source['bin'],
                                    mesh_vertices=vertices.get(identifier))
        verified = result['first_confirmed_deposit_sim_s'] if result['passed'] else None
        results.append({'id': identifier, 'plant_id': fruit['plant_id'], 'cut_sim_s': cut,
                        'release_sim_s': release, 'verified_deposit_sim_s': verified, **result})
    audit = {'scope': 'Accepted native cut and release results and geometric final basket containment',
             'telemetry_sha256': sha256_file(output / 'telemetry.jsonl'),
             'events_sha256': sha256_file(output / 'events.jsonl'),
             'source_manifest_sha256': source_digest,
             'observed_final_sim_s': samples[-1]['sim_time'] if samples else None,
             'planned_fruit_ids': run['target_ids'],
             'native_results': results,
             'deposited_fruit_ids': [row['id'] for row in results if row['passed']]}
    write_json(output / 'deposit_audit.json', audit)
    return audit


def caption_time(seconds):
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, fraction = divmod(remainder, 100)
    return f'{hours}:{minutes:02d}:{seconds:02d}.{fraction:02d}'


def export_hud(output, audit):
    report = read_json(output / 'video_report.json')
    first_frame = report['first_sim_time']
    duration = report['encoded_frames'] / report['display_fps']
    if report['status'] != 'RECORDED_NATIVE_RGB' or first_frame is None:
        raise RuntimeError('Native video must be verified before adding the deposit count')
    counts = Counter()
    intervals = []
    start = 0.
    for row in sorted((row for row in audit['native_results'] if row['passed']),
                      key=lambda row: row['verified_deposit_sim_s']):
        end = min(duration, max(0., row['verified_deposit_sim_s'] - first_frame))
        if end > start:
            intervals.append((start, end, counts.copy()))
        counts[row['plant_id']] += 1
        start = end
    if duration > start:
        intervals.append((start, duration, counts))
    subtitle = output / 'deposit_hud.ass'
    header = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\nWrapStyle: 2\n\n'
              '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, '
              'OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, '
              'Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
              'Style: Counter,DejaVu Sans,23,&H00F4F4F4,&H00F4F4F4,&H500A1821,&H500A1821,-1,0,0,0,100,100,0,0,3,6,0,2,36,36,29,1\n\n'
              '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    with subtitle.open('w', encoding='utf-8') as stream:
        stream.write(header)
        for start, end, counts in intervals:
            by_plant = '  /  '.join(f'{counts[f"plant_{index:03d}"]}/3' for index in range(3))
            text = f'Canasta  {sum(counts.values())}/9     ·     Arbustos  {by_plant}'
            stream.write(f'Dialogue: 0,{caption_time(start)},{caption_time(end)},Counter,,0,0,0,,{text}\n')
    video = output / 'cosecha_v8.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', 'native_mission.mp4',
                    '-vf', 'ass=deposit_hud.ass', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
                    '-crf', '19', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', video.name],
                   cwd=output, check=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(video),
                    '-f', 'null', '-'], check=True)
    write_json(output / 'final_video.json', {'result': video.name, 'sha256': sha256_file(video),
                                            'duration_s': duration,
                                            'native_video_sha256': report['video_sha256'],
                                            'audit_sha256': sha256_file(output / 'deposit_audit.json')})


def export_compact(package, output, audit):
    """Retimestamp the uninterrupted native take while leaving cut and drop at 1×."""
    manifest_file = package / 'demo_manifest.json'
    manifest = read_json(manifest_file)
    run = read_json(output / 'run.json')
    if run['demo_manifest_sha256'] != sha256_file(manifest_file):
        raise ValueError('Phase schedule differs from the recorded native run')
    report = read_json(output / 'video_report.json')
    first = report['first_sim_time']
    duration = report['encoded_frames'] / report['display_fps']
    releases = {row['id']: row['release_sim_s'] for row in audit['native_results']}
    phases = manifest['phases']
    intervals = []
    for index, phase in enumerate(phases):
        start = phase['sim_time']
        end = phases[index + 1]['sim_time'] if index + 1 < len(phases) else first + duration
        name = phase['phase']
        # Keep the final approach, cut, separation and fruit settling unaccelerated.
        if name == 'acercamiento_pinza':
            end -= 2.
        elif name == 'deposito' and phase['id'] in releases:
            end = min(end, releases[phase['id']] - 1.5)
        elif name != 'acercamiento_carro':
            continue
        begin, finish = max(0., start - first), min(duration, end - first)
        if finish > begin:
            intervals.append({'start_source_s': begin, 'end_source_s': finish,
                              'speed': 3, 'phase': name, 'id': phase['id']})
    if not intervals:
        raise ValueError('The native take has no staging or transfer intervals to speed up')
    # A continuous integral of the changed rate maps each native frame to a
    # new PTS. VFR preserves every frame, including transitions at the phase edges.
    durations = [row['end_source_s'] - row['start_source_s'] for row in intervals]
    terms = [f"min(max(T-{row['start_source_s']:.9f},0),{length:.9f})"
             for row, length in zip(intervals, durations)]
    timestamps = "settb=1/1200,setpts='(T-2/3*(" + '+'.join(terms) + "))/TB'"
    video = output / 'cosecha_v8_compacta.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', 'native_mission.mp4',
                    '-vf', 'ass=deposit_hud.ass,' + timestamps, '-fps_mode', 'passthrough',
                    '-enc_time_base', '1:1200', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
                    '-crf', '19', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', video.name],
                   cwd=output, check=True)
    metadata = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                               'stream=nb_frames:format=duration', '-of', 'json', str(video)],
                              capture_output=True, text=True, check=True)
    probe = strict_json_loads(metadata.stdout)
    if int(probe['streams'][0]['nb_frames']) != report['encoded_frames']:
        raise RuntimeError('Compact edition frame count differs from the native take')
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(video),
                    '-f', 'null', '-'], check=True)
    write_json(output / 'compact_video.json', {'result': video.name, 'sha256': sha256_file(video),
                                              'duration_s': float(probe['format']['duration']),
                                              'native_video_sha256': report['video_sha256'],
                                              'original_frames_preserved': report['encoded_frames'],
                                              'accelerated_intervals': intervals})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--source-package', type=Path, required=True)
    parser.add_argument('--plugin-dir', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wall-timeout', type=float, default=1800.)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--hud-only', action='store_true', help='Audit and caption a completed native capture')
    mode.add_argument('--no-video', action='store_true', help='Observe state/events without a video subscriber')
    parser.add_argument('--compact', action='store_true', help='Also export a retimed continuous edition')
    args = parser.parse_args(argv)
    output, source = args.output.resolve(), args.source_package.resolve(strict=True)
    if not args.no_video and not shutil.which('ffmpeg'):
        parser.error('FFmpeg is required')
    failure = None
    if not args.hud_only:
        if not math.isfinite(args.wall_timeout) or args.wall_timeout <= 0:
            parser.error('--wall-timeout must be positive and finite')
        directories = [directory.resolve(strict=True) for directory in args.plugin_dir]
        if not directories:
            parser.error('Provide the native plugin directories')
        failure = capture(args.package.resolve(strict=True), source, directories, output, args.wall_timeout,
                          record_video=not args.no_video)
    audit = deposit_evidence(source, output)
    if (output / 'video_report.json').is_file():
        if read_json(output / 'video_report.json')['status'] == 'RECORDED_NATIVE_RGB':
            export_hud(output, audit)
            if args.compact:
                export_compact(args.package.resolve(strict=True), output, audit)
    print(json.dumps({'capture_error': failure, 'verified_deposits': audit['deposited_fruit_ids'],
                      'output': str(output)}, ensure_ascii=False), flush=True)
    return int(failure is not None)


if __name__ == '__main__':
    raise SystemExit(main())
