"""Native pixel mapping and coverage checks without GPU or simulator truth."""
import json
import unittest
from unittest.mock import patch
import numpy as np
import torch
from ultralytics.engine.results import Results
from uchuva_gazebo.roi_tiling import bush_rois, tile_boxes, predict_roi


class RoiTilingTests(unittest.TestCase):
    def test_safe_roi_keeps_pixels_outside_heuristic_proposal(self):
        coverage=np.zeros((120,180),bool)
        image=np.ones((120,180,3),np.uint8)
        image[:,:,0]=np.arange(180)[None,:]
        image[:,:,1]=np.arange(120)[:,None]
        class Model:
            names={0:'pintona'}
            def predict(self,canvas,**kwargs):
                valid=canvas[:,:,2]==1
                pixels=canvas[valid]
                coverage[pixels[:,1],pixels[:,0]]=True
                result=Results(canvas,'',self.names,boxes=torch.zeros((0,6)))
                result.speed={'inference':0.};return [result]
        with patch('uchuva_gazebo.roi_tiling.bush_rois',return_value=[(50,30,90,80)]):
            predict_roi(Model(),image,mode='safe_tiles',tile_size=64)
        self.assertTrue(coverage.all())

    def test_tiles_cover_odd_roi_including_edges(self):
        roi=(17,23,1193,699);coverage=np.zeros((720,1280),bool)
        for x,y,xx,yy in tile_boxes(roi,640,.2):coverage[y:yy,x:xx]=True
        self.assertTrue(coverage[23:699,17:1193].all())
        self.assertFalse(coverage[:23].any())

    def test_rgb_roi_serializes_and_empty_does_not_invent_bush(self):
        rgb=np.zeros((720,1280,3),np.uint8)
        self.assertEqual(bush_rois(rgb),[])
        rgb[40:640,200:600]=(30,120,40)
        self.assertTrue(bush_rois(rgb))
        json.dumps(bush_rois(rgb))

    def test_native_crop_mask_returns_to_original_coordinates(self):
        class Model:
            names={0:'pintona'}
            def predict(self,image,**kwargs):
                assert image.shape==(640,640,3)
                mask=torch.zeros((1,640,640));mask[0,5:15,7:17]=1
                result=Results(image,'',self.names,boxes=torch.tensor([[7,5,17,15,.9,0]]),masks=mask)
                result.speed={'inference':1.};return [result]
        image=np.zeros((200,300,3),np.uint8)
        with patch('uchuva_gazebo.roi_tiling.bush_rois',return_value=[(20,30,100,110)]):
            result=predict_roi(Model(),image)
        mask=result.masks.data.numpy()[0]
        self.assertEqual(mask.shape,(200,300))
        self.assertEqual(mask.sum(),100)
        self.assertTrue(mask[35:45,27:37].all())
        self.assertEqual(result.boxes.xyxy.tolist(),[[27.,35.,37.,45.]])


if __name__=='__main__':unittest.main()
