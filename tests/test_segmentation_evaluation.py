import unittest
import numpy as np
from uchuva_gazebo.segmentation_evaluation import decode_panoptic_rgb,mask_matches,mask_confusion,whole_plant_in_frame


class SegmentationEvaluationTests(unittest.TestCase):
    def test_whole_bush_framing_uses_pose_and_rejects_cropped_or_behind(self):
        bounds=[[-.5,3.,0],[.5,3.4,1.4]]
        quaternion=[0,0,2**-.5,2**-.5]
        self.assertTrue(whole_plant_in_frame(bounds,[],[0,0,.7],quaternion))
        self.assertFalse(whole_plant_in_frame(bounds,[],[3,0,.7],quaternion))
        self.assertFalse(whole_plant_in_frame(bounds,[],[0,5,.7],quaternion))

    def test_native_channels_class_plant_and_zero_instance(self):
        rgb=np.array([[[0,0,1],[5,1,6],[9,0,108],[0,0,255],[0,0,0]]],np.uint8)
        code=decode_panoptic_rgb(rgb)
        self.assertEqual(code.tolist(),[[65536,6*65536+261,108*65536+9,0,0]])
        labels=code[0,:3]//65536
        self.assertEqual(((labels-1)//3).tolist(),[0,1,35])
        self.assertEqual(((labels-1)%3).tolist(),[0,2,2])

    def test_duplicate_predictions_cannot_multiply_true_positives(self):
        ious=np.array([[.8,.1],[.9,0],[0,.95]])
        matched,_=mask_matches(ious,[0,0,2],[0,1],[.5,.9])
        self.assertEqual(matched.tolist(),[[True,False],[False,True],[False,False]])
        collapsed,_=mask_matches(ious,[0,0,2],[0,1],[.5],collapse=True)
        self.assertEqual(int(collapsed.sum()),2)
        confusion=mask_confusion(ious,[0,0,2],[0,1])
        self.assertEqual(confusion[0,0],1);self.assertEqual(confusion[3,0],1)
        self.assertEqual(confusion[1,2],1)

    def test_no_predictions_or_ground_truth(self):
        self.assertEqual(mask_confusion(np.zeros((0,1)),[],[2])[2,3],1)
        self.assertEqual(mask_confusion(np.zeros((1,0)),[1],[])[3,1],1)


if __name__=='__main__':unittest.main()
