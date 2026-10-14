"""Changing evaluator masks must not change the RGB passed to the predictor."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import cv2
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('flight_evaluator',ROOT/'scripts/evaluate_segmentation_flight.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class PredictorIsolationTests(unittest.TestCase):
    def test_ground_truth_class_changes_metrics_not_predictor_input(self):
        received=[]
        class Predictor:
            def predict(self,image,**kwargs):
                received.append(image.copy())
                boxes=SimpleNamespace(xyxy=torch.zeros((0,4)),cls=torch.zeros(0),conf=torch.zeros(0))
                return [SimpleNamespace(masks=None,boxes=boxes,speed={'inference':0.0})]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);package=root/'package';flight=package/'flight'
            (flight/'paired/rgb').mkdir(parents=True);(flight/'paired/mask').mkdir()
            rgb=np.full((256,256,3),73,np.uint8)
            cv2.imwrite(str(flight/'paired/rgb/1000000000.png'),rgb)
            (flight/'paired/pairs.json').write_text(json.dumps({'error':None,'pairs':[
                {'stamp_ns':1000000000,'rgb':'rgb/1000000000.png','mask':'mask/1000000000.png'}]}))
            (flight/'segmentation_validation.json').write_text('{"passed":true}')
            (flight/'telemetry.json').write_text(json.dumps({'samples':[{'t':1,'phase':'station','position':[0,-3.5,.7]}]}))
            (package/'mission.json').write_text(json.dumps({'waypoints':[{'phase':'station','target_plant_id':'plant_00','position':[0,-3.5,.7]}]}))
            weights=root/'weights.pt';weights.write_bytes(b'unit-test-model-identity')
            reports=[]
            for label in (1,2):
                mask=np.zeros_like(rgb);mask[50:60,50:60]=[label,0,1]  # BGR storage of native RGB [1,0,label]
                cv2.imwrite(str(flight/'paired/mask/1000000000.png'),mask)
                output=root/f'evaluation_{label}'
                argv=['evaluate','--root',str(root),'--flight',str(flight),'--model',str(weights),
                      '--output',str(output),'--confidence','.25','--scope','technical']
                with patch.object(sys,'argv',argv),patch.object(module,'check_deadline',lambda _:None),\
                     patch.object(module,'YOLO',lambda _:Predictor()),patch.object(module.torch.cuda,'synchronize',lambda:None):
                    module.main()
                reports.append(json.loads((output/'metrics.json').read_text()))
            self.assertTrue(np.array_equal(received[0],received[1]))
            self.assertTrue(np.array_equal(received[0],rgb))
            self.assertEqual(reports[0]['per_class'][0]['class_id'],0)
            self.assertEqual(reports[1]['per_class'][0]['class_id'],1)


if __name__=='__main__':unittest.main()
