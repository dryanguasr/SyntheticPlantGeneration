import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from summarize_integral_sequence import detection_digest


class Record:
    def __init__(self,track,pose):self.track=track;self.pose=pose
    def open(self):return io.StringIO(json.dumps(dict(stamp_ns=1,detections=[dict(observation_id='a',track_id=self.track)],marker_poses=self.pose))+'\n')


class ComparisonTests(unittest.TestCase):
    def test_pose_change_allowed_identity_change_detected(self):
        original=detection_digest(Record('t1',{}))
        self.assertEqual(original,detection_digest(Record('t1',{'8':{'t':[1,2,3]}})))
        self.assertNotEqual(original,detection_digest(Record('t2',{})))

if __name__=='__main__':unittest.main()
