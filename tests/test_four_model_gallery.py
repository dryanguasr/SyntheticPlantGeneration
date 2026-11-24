"""Protect label absence and competing predictions in the cached review."""
from pathlib import Path
import sys,unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parents[1]/'src')]
from build_sobremadura_four_model_gallery import same_truth,presence_status,best_candidates,candidate_regions


class FourModelGalleryTests(unittest.TestCase):
    def test_no_label_is_not_the_same_as_no_prediction(self):
        truth=[dict(class_id=1,bbox=[0,0,10,10])]
        pred=[dict(class_id=2,bbox=[0,0,10,10],confidence=.8)]
        self.assertEqual(presence_status(truth,pred,.076),'prediction_without_class2_label')
        self.assertEqual(presence_status(truth,[],.076),'no_class2_label_or_prediction')
        truth[0]['class_id']=2
        self.assertEqual(presence_status(truth,[],.076),'labelled_without_prediction')

    def test_true_class_candidate_does_not_hide_higher_competing_class(self):
        truth=dict(class_id=2,bbox=[0,0,10,10])
        pred=[dict(class_id=0,bbox=[0,0,10,10],confidence=.478),
              dict(class_id=2,bbox=[0,0,10,10],confidence=.100),
              dict(class_id=2,bbox=[0,0,10,10],confidence=.059)]
        out=best_candidates(truth,pred,.076)
        self.assertEqual(set(out),{'0','2'})
        self.assertEqual(out['0']['confidence'],.478)
        self.assertEqual(out['2']['confidence'],.100)
        pred.pop(1);self.assertFalse(best_candidates(truth,pred,.076)['2']['above_threshold'])

    def test_changed_ground_truth_rejects_cached_comparison(self):
        truth=[dict(class_id=2,bbox=[0,0,10,10])]
        self.assertTrue(same_truth(truth,truth))
        self.assertFalse(same_truth(truth,[dict(class_id=1,bbox=[0,0,10,10])]))
        self.assertFalse(same_truth(truth,[dict(class_id=2,bbox=[0,0,10,11])]))
        self.assertFalse(same_truth(truth,[]))

    def test_candidate_does_not_invent_a_label_in_unannotated_region(self):
        truth=[dict(class_id=1,bbox=[0,0,10,10])]
        predictions=[dict(class_id=2,bbox=[0,0,10,10],confidence=.8),dict(class_id=2,bbox=[30,30,40,40],confidence=.9)]
        result=candidate_regions(truth,predictions,.076)
        self.assertEqual(result[0]['kind'],'overlaps_annotation')
        self.assertEqual(result[0]['nearest_truth_class'],1)
        self.assertEqual(result[1]['kind'],'no_nearby_annotation')
        self.assertEqual(truth,[dict(class_id=1,bbox=[0,0,10,10])])


if __name__=='__main__':unittest.main()
