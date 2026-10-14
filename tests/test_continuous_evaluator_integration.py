"""Small end-to-end evaluator fixture, without Blender, GPU or model weights."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


class EvaluatorIntegrationTests(unittest.TestCase):
    def test_background_intrusion_remains_false_positive_in_target_map(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('flight/paired','truth','cache','estimates'):(root/name).mkdir(parents=True)
            target=65537;missed=65538;background=262145
            objects={str(target):dict(role='target',class_id=0,ever_visible=True,canonical_marker_id=0,position_marker_m=[0,0,1],reproductive_id='target_a'),
                str(missed):dict(role='target',class_id=0,ever_visible=True,canonical_marker_id=0,position_marker_m=[.5,0,1],reproductive_id='target_b'),
                str(background):dict(role='background',class_id=0,ever_visible=True,canonical_marker_id=2,position_marker_m=[0,0,1],reproductive_id='context_a')}
            pairs=[];frames=[];observations=[]
            for stamp in (1,2,3):
                codes=np.zeros((20,30),np.uint32);codes[1:6,1:6]=target;codes[1:6,15:20]=background;codes[18,28]=missed
                rgb=np.stack((codes%256,(codes//256)%256,codes//65536),axis=-1).astype(np.uint8)
                cv2.imwrite(str(root/f'flight/paired/{stamp}.png'),rgb[:,:,::-1]);pairs.append(dict(stamp_ns=stamp,mask=f'{stamp}.png'))
                instances=[]
                for code in (target,missed,background):
                    ys,xs=np.nonzero(codes==code);instances.append(dict(code=code,pixels=len(xs),bbox=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]))
                frames.append(dict(stamp_ns=stamp,instances=instances));proposals=[]
                for i,(code,box,center) in enumerate([(target,[1,1,6,6],[3,3]),(background,[15,1,20,6],[17,3])]):
                    proposals.append(dict(observation_id=f'{stamp}:{i}',class_id=0,confidence=.9,accepted=True,cross_tile_suppressed_by=None,
                        box_xyxy_px=box,center_px=center,track_id=f'track{i}'))
                (root/f'cache/{stamp}.json').write_text(json.dumps(dict(proposals=proposals)))
                masks=np.stack([codes==target,codes==background]);np.savez_compressed(root/f'cache/{stamp}.npz',packed_masks=np.packbits(masks.reshape(2,-1),axis=1),shape=[20,30])
                observations.append(dict(stamp_ns=stamp,detections=proposals))
            (root/'flight/paired/pairs.json').write_text(json.dumps(dict(pairs=pairs)))
            (root/'truth/truth.json').write_text(json.dumps(dict(objects=objects,frames=frames)))
            (root/'truth/mapping_audit.json').write_text(json.dumps(dict(passed=True)))
            (root/'estimates/observations.jsonl').write_text('\n'.join(map(json.dumps,observations)))
            maps=[dict(map_id=f'calyx{i}',state='confirmed',marker_id=0,position_marker_m=[0,0,1],observation_ids=[f'{stamp}:{i}' for stamp in (1,2,3)]) for i in range(2)]
            (root/'estimates/map.json').write_text(json.dumps(dict(objects=maps,rejected=[])))
            subprocess.run([sys.executable,str(ROOT/'scripts/evaluate_continuous_study.py'),'--flight',str(root/'flight'),'--truth',str(root/'truth/truth.json'),
                '--cache',str(root/'cache'),'--estimates',str(root/'estimates'),'--output',str(root/'metrics')],check=True,capture_output=True,text=True)
            metrics=json.loads((root/'metrics/metrics.json').read_text())
            self.assertEqual(metrics['target_visible_unique'],2)
            self.assertEqual(metrics['background_intrusions'],1)
            self.assertEqual(metrics['precision_3d'],.5)
            self.assertEqual(metrics['recall_3d'],.5)
            self.assertEqual(metrics['totals']['target_observations'],6)
            self.assertEqual(metrics['precision_2d'],1)
            self.assertEqual(metrics['recall_2d'],.5)


if __name__=='__main__':unittest.main()
