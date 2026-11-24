"""Disjoint error attribution and confidence-ordered matching sanity cases."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_sobremadura_pilot import error_type,inspect_row


class SobremaduraDiagnosisTests(unittest.TestCase):
    def test_confusion_localization_and_unannotated_are_separate(self):
        truth=[dict(class_id=2,bbox=[0,0,10,10]),dict(class_id=0,bbox=[20,0,30,10])]
        for box,expected in (([0,0,10,10],'duplicate_or_assignment'),([20,0,30,10],'other_annotated_class'),
                             ([25,0,35,10],'localization_IoU_0.1_to_0.5'),([40,40,50,50],'background_or_unannotated')):
            self.assertEqual(error_type(dict(bbox=box),truth),expected)

    def test_lower_scored_duplicate_does_not_create_another_true_positive(self):
        row=dict(truth=[dict(class_id=2,bbox=[0,0,10,10])],predictions=[
            dict(class_id=2,bbox=[0,0,10,10],confidence=.8),dict(class_id=2,bbox=[0,0,10,10],confidence=.2)])
        result=inspect_row(row,.1)
        self.assertEqual((result['tp'],result['fp'],result['fn']),(1,1,0))
        self.assertEqual(result['fp_types'],{'duplicate_or_assignment':1})
        self.assertEqual(result['outcomes'][0]['prediction_index'],0)

    def test_low_confidence_and_wrong_class_are_not_called_missing_geometry(self):
        row=dict(truth=[dict(class_id=2,bbox=[0,0,10,10])],predictions=[dict(class_id=2,bbox=[0,0,10,10],confidence=.04)])
        self.assertEqual(inspect_row(row,.1)['outcomes'][0]['status'],'correct_class_below_fixed_threshold')
        row['predictions'].append(dict(class_id=0,bbox=[0,0,10,10],confidence=.8))
        self.assertEqual(inspect_row(row,.1)['outcomes'][0]['status'],'confusion_to_Pintona')


if __name__=='__main__':unittest.main()
