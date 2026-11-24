import copy
import io
import json
import unittest
from uchuva_gazebo.public_pose_stream import load_public_pose_stream


class StreamPath:
    def __init__(self,rows):self.rows=rows
    def open(self):return io.StringIO(''.join(json.dumps(r)+'\n' for r in self.rows))


class PublicPoseTests(unittest.TestCase):
    def setUp(self):
        self.rig={8:{'canonical_id':8},9:{'canonical_id':8}}
        self.row={'stamp_ns':10,'marker_poses':{'8':{'R':[[1,0,0],[0,1,0],[0,0,1]],'t':[1,2,3],'source':'RGB_ArUco'}}}

    def test_canonical_pose_is_not_transformed_again(self):
        loaded=load_public_pose_stream(StreamPath([self.row]),self.rig)
        self.assertEqual(loaded[10][8]['t'],[1.,2.,3.])

    def test_reject_truth_fields_and_noncanonical_code(self):
        for location in ('frame','pose','code'):
            row=copy.deepcopy(self.row)
            if location=='frame':row['world_pose']=[0,0,0]
            elif location=='pose':row['marker_poses']['8']['truth_id']=123
            else:row['marker_poses']['9']=row['marker_poses'].pop('8')
            with self.assertRaises(ValueError):load_public_pose_stream(StreamPath([row]),self.rig)

    def test_reject_duplicate_timestamp_reflection_and_identity_mismatch(self):
        with self.assertRaises(ValueError):load_public_pose_stream(StreamPath([self.row,self.row]),self.rig)
        for key,value in [('R',[[-1,0,0],[0,1,0],[0,0,1]]),('marker_id',9),('stamp_ns',11)]:
            row=copy.deepcopy(self.row);row['marker_poses']['8'][key]=value
            with self.assertRaises(ValueError):load_public_pose_stream(StreamPath([row]),self.rig)

if __name__=='__main__':unittest.main()
