import sys
from pathlib import Path
import unittest
import numpy as np
from uchuva_gazebo.mask_tracking import MaskTracker

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cache_continuous_predictions import suppress,native_tiles


def scene(positions,classes=None):
    image=np.zeros((80,120,3),np.uint8);masks=[];detections=[]
    for i,x in enumerate(positions):
        mask=np.zeros((80,120),bool);mask[25:45,x:x+15]=True
        image[mask]=[30,160,180]
        # Reproducible texture inside the silhouette supports optical flow.
        image[28:42:3,x+2:x+13:3]=[200,30,50]
        masks.append(mask);detections.append(dict(box_xyxy_px=[x,25,x+15,45],center_px=[x+7,35],class_id=(classes or [0]*len(positions))[i]))
    return image,detections,masks


class TrackingTests(unittest.TestCase):
    def test_native_tiling_has_true_twenty_percent_overlap_and_full_coverage(self):
        tiles=native_tiles(1280,720)
        self.assertEqual(tiles,[(0,0,960,720),(768,0,1280,720)])
        cover=np.zeros((720,1280),bool)
        for x,y,xx,yy in tiles:cover[y:yy,x:xx]=True
        self.assertTrue(cover.all())

    def test_reappearance_and_class_change_do_not_reset_identity(self):
        tracker=MaskTracker();image,detections,masks=scene([30])
        tracker.update(image,detections,0,masks);identifier=detections[0]['track_id']
        tracker.update(image,[],100000000,[])
        image,detections,masks=scene([30],[2]);tracker.update(image,detections,200000000,masks)
        self.assertEqual(detections[0]['track_id'],identifier)

    def test_two_coexisting_tracks_remain_distinct_when_order_reverses(self):
        tracker=MaskTracker();image,detections,masks=scene([15,70])
        tracker.update(image,detections,0,masks);ids=[d['track_id'] for d in detections]
        image,detections,masks=scene([70,15]);tracker.update(image,detections,33000000,masks)
        self.assertEqual([d['track_id'] for d in detections],ids[::-1])

    def test_duplicate_tiles_suppressed_without_deleting_adjacent_calyx(self):
        _,d,m=scene([15,70]);proposals=[dict(class_id=0,confidence=c,box_xyxy_px=b) for c,b in [(0.9,d[0]['box_xyxy_px']),(.8,d[0]['box_xyxy_px']),(.7,d[1]['box_xyxy_px'])]]
        kept=suppress(proposals,[m[0],m[0].copy(),m[1]])
        self.assertEqual(kept,[0,2]);self.assertEqual(proposals[1]['cross_tile_suppressed_by'],0)
        proposals[1]['class_id']=2
        self.assertEqual(suppress(proposals,[m[0],m[0].copy(),m[1]]),[0,2])


if __name__=='__main__':unittest.main()
