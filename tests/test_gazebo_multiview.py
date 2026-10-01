import unittest
import numpy as np
import cv2
from uchuva_gazebo.multiview import (triangulate, marker_pose, unambiguous_assignment,
                                     mask_boxes, match_detections, Tracker)
from uchuva_gazebo.evaluation import visible_boxes
from uchuva_gazebo.low_flight_control import desired_velocity


class MultiviewTests(unittest.TestCase):
    K=np.array([[640,0,640],[0,640,360],[0,0,1]],float)

    def test_long_waypoint_does_not_dilute_lateral_feedback(self):
        far=desired_velocity((9,-.05,.02));near=desired_velocity((1,-.05,.02))
        np.testing.assert_allclose(far,near)
        self.assertLess(far[1],-.05)
        self.assertLess(np.linalg.norm(desired_velocity((100,100,100))),.20)

    def observations(self, point=(.03,.02,1.2), baseline=.1):
        result=[]
        for x in (-baseline,0,baseline):
            t=np.array([-x,0,0]); p=self.K@(np.array(point)+t)
            result.append({'marker_id':7,'R':np.eye(3).tolist(),'t':t.tolist(),'point_px':(p[:2]/p[2]).tolist()})
        return result

    def test_metric_triangulation_known_position(self):
        r=triangulate(self.observations(),self.K)
        self.assertEqual(r['status'],'estimated')
        np.testing.assert_allclose(r['position_marker_m'],[.03,.02,1.2],atol=1e-10)

    def test_no_parallax(self):
        self.assertEqual(triangulate(self.observations(baseline=0),self.K)['reason'],'insufficient_parallax')

    def test_missing_marker_observations(self):
        self.assertEqual(triangulate([],self.K)['status'],'unavailable')

    def test_cannot_join_marker_frames(self):
        obs=self.observations();obs[1]['marker_id']=9
        with self.assertRaises(ValueError):triangulate(obs,self.K)

    def test_reprojection_rejects_bad_correspondence(self):
        obs=self.observations();obs[1]['point_px'][1]+=30
        self.assertEqual(triangulate(obs,self.K)['reason'],'triangulation_reprojection')

    def test_ippe_scale_and_marker_axes(self):
        obj=np.array([[-.05,.05,0],[.05,.05,0],[.05,-.05,0],[-.05,-.05,0]])
        r=np.array([2.7,.15,.02]);t=np.array([.02,.1,.8])
        corners=cv2.projectPoints(obj,r,t,self.K,None)[0].reshape(4,2)
        pose=marker_pose(corners,self.K)
        self.assertEqual(pose['status'],'estimated')
        np.testing.assert_allclose(pose['t'],t,atol=1e-7)
        np.testing.assert_allclose(pose['R'],cv2.Rodrigues(r)[0],atol=1e-7)

    def test_ambiguous_assignment_and_competition(self):
        self.assertEqual(unambiguous_assignment([[.8,.79]])[0],{})
        self.assertEqual(unambiguous_assignment([[.8],[.9]])[0],{})
        self.assertEqual(unambiguous_assignment([[.8,0],[0,.9]])[0],{0:0,1:1})

    def test_occluded_mask_and_small_fragment(self):
        labels=np.zeros((20,20),int);labels[2:6,3:7]=1;labels[12,12]=2
        boxes=mask_boxes(labels)
        self.assertEqual(boxes[0],{'instance':1,'pixels':16,'box':[3,2,7,6]})
        self.assertEqual(sum(b['pixels']>=16 for b in boxes),1)
        self.assertNotIn(3,[b['instance'] for b in boxes])

    def test_vectorized_visible_boxes_equal_reference(self):
        labels=np.random.default_rng(92).integers(0,8,size=(40,60))
        self.assertEqual(visible_boxes(labels),mask_boxes(labels))
        self.assertEqual(visible_boxes(np.zeros((2,2),int)),[])

    def test_count_without_duplicates(self):
        matches,duplicates=match_detections([[0,0,10,10],[0,0,10,10]],[[0,0,10,10]])
        self.assertEqual(len(matches),1);self.assertEqual(len(duplicates),1)

    def test_estimator_has_no_truth_input(self):
        tracker=Tracker(); detections=[{'box_xyxy_px':[0,0,10,10]}]
        tracker.update(np.zeros((32,32,3),np.uint8),detections,0)
        self.assertEqual(detections[0]['track_id'],'track_000000')
        # Numeric triangulation accepts only image points, observed marker poses and K.
        self.assertEqual(triangulate(self.observations(),self.K)['status'],'estimated')


if __name__=='__main__':unittest.main()
