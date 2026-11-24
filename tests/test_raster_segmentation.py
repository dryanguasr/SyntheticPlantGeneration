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
    def test_historical_area_predictor_matches_training_pixels(self):
        from types import SimpleNamespace
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        from raster_segmentation_inference import AreaRasterSegmentationPredictor
        predictor = object.__new__(AreaRasterSegmentationPredictor)
        predictor.imgsz = [256, 256]
        predictor.model = SimpleNamespace(stride=32)
        image = np.random.default_rng(178).integers(0, 256, (64, 128, 3), dtype=np.uint8)
        expected = np.full((256, 256, 3), 114, np.uint8)
        expected[64:192] = cv2.resize(image, (256, 128), interpolation=cv2.INTER_AREA)
        actual = predictor.pre_transform([image])[0]
        np.testing.assert_array_equal(actual, expected)
        self.assertFalse(np.array_equal(actual[64:192], cv2.resize(image, (256, 128), interpolation=cv2.INTER_LINEAR)))

    def test_rgb_matches_inference_letterbox(self):
        from ultralytics.data.augment import LetterBox
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rng = np.random.default_rng(178)
            image = rng.integers(0, 256, (64, 128, 3), dtype=np.uint8)
            mask = np.zeros((64, 128), np.uint16)
            mask[10:30, 20:50] = 1
            cv2.imwrite(str(root / 'image.png'), image)
            cv2.imwrite(str(root / 'mask.png'), mask)
            row = dict(split='train', image='image.png', mask='mask.png',
                       image_size=[128, 64], instances=[dict(mask_id=1,
                       class_id=2, bbox=[20, 10, 50, 30])])
            (root / 'raster_manifest.json').write_text(json.dumps({'images': [row]}))
            for size in (32, 256):
                sample = module.RasterDataset(root, 'train', size, False, 2)[0]
                expected = LetterBox((size, size), auto=False)(image=image)
                expected = expected[:, :, ::-1].transpose(2, 0, 1).copy()
                np.testing.assert_array_equal(sample['img'].numpy(), expected)

    def test_coverage_keeps_tiny_instances_separate(self):
        native=np.zeros((16,32),np.uint16)
        native[1,1]=1;native[1,2]=2
        items=[{'mask_id':1},{'mask_id':2}]
        masks=module.coverage_masks(native,items,16,4)
        self.assertEqual(masks.shape,(2,4,4))
        self.assertEqual(masks.sum(axis=(1,2)).tolist(),[1,1])
        self.assertTrue(np.any(masks[0]&masks[1]))
        flipped=module.coverage_masks(native,items,16,4,True)
        np.testing.assert_array_equal(flipped,masks[:,:,::-1])
        with self.assertRaises(ValueError):
            module.coverage_masks(native,[{'mask_id':3}],16,4)

    def test_coverage_identity_resolution_preserves_hole(self):
        native=np.zeros((16,16),np.uint16);native[2:14,2:14]=1;native[6:10,6:10]=0
        masks=module.coverage_masks(native,[{'mask_id':1}],16,1)
        np.testing.assert_array_equal(masks[0],native==1)

    def test_coverage_cannot_change_validation_targets(self):
        with self.assertRaises(ValueError):
            module.RasterDataset('.', 'val', 960, supervision_policy='any_coverage')

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
            coverage=module.RasterDataset(root,'train',128,False,4,'any_coverage')[0]
            self.assertTrue(bool(coverage['masks'].flatten(1).any(1).all()))
            second=coverage['masks'][1].numpy().astype(bool)
            self.assertTrue(np.all(coverage['sem_masks'].numpy()[second]==2))
            self.assertEqual(coverage['cls'].tolist(),sample['cls'].tolist())
            np.testing.assert_array_equal(coverage['bboxes'].numpy(),sample['bboxes'].numpy())

    def test_absent_split_is_an_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'raster_manifest.json').write_text('{"images":[]}')
            with self.assertRaises(ValueError):module.RasterDataset(root,'val',128)


if __name__=='__main__':unittest.main()
