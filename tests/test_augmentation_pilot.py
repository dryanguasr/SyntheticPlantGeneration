"""Campaign invariants independent of Blender and GPU execution."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from PIL import Image
from augmentation_pilot import image_geometry, gate, boxes
TEST_ROOT=Path(__file__).resolve().parents[1]/'outputs'


class GeometryTests(unittest.TestCase):
    def test_density_alone_does_not_block_admission(self):
        import copy
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as d:
            path=Path(d)/'image.png';Image.new('RGB',(960,960)).save(path)
            geometry=image_geometry(path,[[0,.5,.5,.06,.1]])
            dense=copy.deepcopy(geometry)
            dense['boxes']*=20;dense['count']=20
            result=gate([{'geometry':geometry}],[{'geometry':dense}])
            self.assertTrue(result['passed'])
            self.assertFalse(result['density_is_admission_criterion'])
            self.assertGreater(result['median_relative_errors']['density'],.2)
            small=copy.deepcopy(dense)
            for box in small['boxes']:box['min_side_960']=8
            self.assertFalse(gate([{'geometry':geometry}],[{'geometry':small}])['passed'])
    def test_stream_is_reproducible_and_covers_small_dataset(self):
        from train_augmentation_arm import schedule_indices
        a=schedule_indices(125,42,0)
        self.assertEqual(a,schedule_indices(125,42,0))
        self.assertEqual(len(a),1000)
        self.assertEqual(sorted(a[:125]),list(range(125)))
        self.assertNotEqual(a,schedule_indices(125,43,0))
        self.assertNotEqual(a,schedule_indices(125,42,1))

    def test_native_matching_does_not_double_count(self):
        from evaluate_augmentation_campaign import stats,ap_summary
        gt=[dict(class_id=0,bbox=[0.,0.,10.,10.])]
        pred=[dict(class_id=0,bbox=[0.,0.,10.,10.],confidence=.9),
              dict(class_id=0,bbox=[0.,0.,10.,10.],confidence=.8)]
        result=stats(gt,pred)
        self.assertEqual(sum(row[0] for row in result['tp']),1)
        self.assertGreater(ap_summary([dict(stats=result)])['map50_95'],.9)

    def test_scale_and_border(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as d:
            path=Path(d)/'image.png';Image.new('RGB',(1280,720)).save(path)
            g=image_geometry(path,[[0,.05,.5,.1,.2],[1,.5,.5,.1,.2]])
            self.assertEqual(g['count'],2)
            self.assertAlmostEqual(g['boxes'][0]['min_side_960'],96)
            self.assertTrue(g['boxes'][0]['touches_border'])
            self.assertFalse(g['boxes'][1]['touches_border'])
            self.assertEqual(g['boxes'][0]['max_box_iou'],0)
            rows=[{'geometry':g}]
            self.assertTrue(gate(rows,rows)['passed'])
            self.assertFalse(gate(rows,[])['passed'])

    def test_invalid_labels_are_not_negatives(self):
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as d:
            path=Path(d)/'label.txt';path.write_text('0 0.5 0.5 -0.2 0.1\n')
            with self.assertRaises(AssertionError):boxes(path)
            with self.assertRaises(FileNotFoundError):boxes(Path(d)/'missing.txt')


if __name__=='__main__':unittest.main()
