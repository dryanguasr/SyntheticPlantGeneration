"""Record actual Gazebo camera messages, indexed by simulation timestamps.

No synthetic poses, interpolated renders or replacement footage are generated.
The existing encoder resamples native frames at the declared display rate;
raw frame timestamps and SHA-256 identify every received source image.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading

from run_neo_flight import Recorder


class NativeVideoRecorder:
    def __init__(self, output, observer):
        from gz.transport13 import Node
        from gz.msgs10.image_pb2 import Image
        if not shutil.which('ffmpeg'):
            raise RuntimeError('Native video requires the existing FFmpeg executable')
        self.output = Path(output)
        self.node = Node()
        self.topic = observer['topic']
        self.fps = observer['fps']
        self.lock = threading.Lock()
        self.closed = False
        self.error = None
        self.rows = []
        self.stream = (self.output/'video_frames.jsonl').open('x', encoding='utf-8')
        self.encoder = Recorder(self.output, 'native_mission', fps=observer['fps'], threads=2)
        if not self.node.subscribe(Image, self.topic, self.callback):
            self.close()
            raise RuntimeError('Native RGB subscription failed')

    def callback(self, message):
        with self.lock:
            if self.closed:
                return
            try:
                if message.pixel_format_type != 3:
                    raise ValueError('Expected native RGB_INT8 camera frames')
                stamp = message.header.stamp.sec+message.header.stamp.nsec*1e-9
                if self.rows and stamp <= self.rows[-1]['sim_time']:
                    raise ValueError('Native video timestamps must increase')
                row = {'sim_time': stamp, 'width': message.width, 'height': message.height,
                       'step': message.step, 'sha256': hashlib.sha256(message.data).hexdigest()}
                self.rows.append(row)
                self.stream.write(json.dumps(row)+'\n')
                self.encoder.callback(message)
            except Exception as error:
                self.error = repr(error)

    def close(self):
        with self.lock:
            self.closed = True
        self.node.unsubscribe(self.topic)
        try:
            self.encoder.close()
        except Exception as error:
            self.error = self.error or repr(error)
        self.stream.close()
        path = self.output/'native_mission.mp4'
        failure = self.error
        if not self.rows or not path.is_file():
            failure = failure or 'No native RGB video was received'
        elif not failure:
            result = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path),
                                     '-f', 'null', '-'], capture_output=True, text=True, timeout=120)
            if result.returncode:
                failure = result.stderr
        report = {'status': 'FAIL' if failure else 'RECORDED_NATIVE_RGB', 'error': failure,
            'topic': self.topic, 'source': 'Gazebo native RGB camera sensor',
            'received_frames': len(self.rows), 'encoded_frames': self.encoder.count,
            'first_sim_time': self.rows[0]['sim_time'] if self.rows else None,
            'last_sim_time': self.rows[-1]['sim_time'] if self.rows else None,
            'maximum_frame_gap_s': max((b['sim_time']-a['sim_time'] for a,b in zip(self.rows, self.rows[1:])), default=None),
            'display_fps': self.fps,
            'resampling': 'Repeats only existing native frames by simulation timestamp',
            'video_sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
            'scope': 'Visual evidence only; harvest acceptance is reported independently'}
        (self.output/'video_report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        if failure:
            raise RuntimeError(failure)
        return report
