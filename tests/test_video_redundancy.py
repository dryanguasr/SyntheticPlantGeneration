import sys
from pathlib import Path
import unittest
import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reduce_video_redundancy import similar


class VideoRedundancyTests(unittest.TestCase):
    def test_small_motion_matches_but_zoom_and_new_scene_remain(self):
        rng=np.random.default_rng(20260922)
        im=cv2.GaussianBlur(rng.integers(0,256,(360,480),dtype=np.uint8),(3,3),0)
        orb=cv2.ORB_create(nfeatures=1800,fastThreshold=10)
        def feature(image):
            kp,desc=orb.detectAndCompute(image,None)
            return dict(gray=image,points=np.float32([k.pt for k in kp]),desc=desc)
        baseline=feature(im)
        translated=cv2.warpAffine(im,np.float32([[1,0,12],[0,1,5]]),(480,360))
        self.assertIsNotNone(similar(feature(translated),baseline))
        zoom=cv2.warpAffine(im,cv2.getRotationMatrix2D((240,180),0,1.4),(480,360))
        self.assertIsNone(similar(feature(zoom),baseline))
        self.assertIsNone(similar(feature(255-im),baseline))


if __name__=='__main__':
    unittest.main()
