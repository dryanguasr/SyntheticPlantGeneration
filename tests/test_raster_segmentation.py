"""Exact raster/YOLO batch contract regression tests; no GPU training required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('raster_training',ROOT/'scripts/train_raster_segmentation.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class RasterSegmentationTests(unittest.TestCase):
    def test_fragmented_instance_and_hole_survive_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            image=np.zeros((64,128,3),np.uint8)
            mask=np.zeros((64,128),np.uint16)
            mask[5:25,5:35]=1;mask[10:20,10:20]=0;mask[30:40,60:70]=1
            mask[40:55,90:110]=2
            cv2.imwrite(str(root/'image.png'),image);cv2.imwrite(str(root/'mask.png'),mask)
            row={'split':'train','image':'image.png','mask':'mask.png','image_size':[128,64],
                 'instances':[{'mask_id':1,'class_id':0,'bbox':[5,5,70,40]},
                              {'mask_id':2,'class_id':2,'bbox':[90,40,110,55]}]}
            (root/'raster_manifest.json').write_text(json.dumps({'images':[row]}))
            dataset=module.RasterDataset(root,'train',128,False,1)
            sample=dataset[0]
            expected=np.pad(mask,((32,32),(0,0)))
            self.assertTrue(np.array_equal(sample['masks'][0].numpy(),expected==1))
            self.assertTrue(np.array_equal(sample['masks'][1].numpy(),expected==2))
            self.assertTrue(np.all(sample['sem_masks'].numpy()[expected==2]==2))
            self.assertEqual(tuple(sample['img'].shape),(3,128,128))
            self.assertEqual(sample['ratio_pad'],((1.,1.),(0,32)))
            batch=dataset.collate_fn([dataset[0],dataset[0]])
            self.assertEqual(batch['batch_idx'].tolist(),[0,0,1,1])
            self.assertEqual(tuple(batch['sem_masks'].shape),(2,128,128))
            self.assertEqual(tuple(batch['masks'].shape),(4,128,128))

    def test_absent_split_is_an_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'raster_manifest.json').write_text('{"images":[]}')
            with self.assertRaises(ValueError):module.RasterDataset(root,'val',128)


if __name__=='__main__':unittest.main()
