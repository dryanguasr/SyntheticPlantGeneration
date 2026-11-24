"""Exercise gates between annotation, sealed phases, and real updates."""
from collections import Counter
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]

from annotate_private_mask_ladder import make_annotation
from run_private_mask_ladder import prepare_phase
from uchuva_annotation_audit.masks import encode_mask
from uchuva_annotation_audit.private_training import pair_supervision
from uchuva_annotation_audit.store import atomic_json, read, sha


class LadderGateTests(unittest.TestCase):
    def test_visual_gate_and_sealed_phase(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root/'image.png'
            Image.new('RGB',(12,10)).save(image)
            row = dict(id='row_test', image=str(image), image_sha256=sha(image),
                       width=12, height=10, group_id='train_group')
            inputs = dict(train=[row], val=[])
            self.assertEqual(prepare_phase(root, inputs, 1), (None, ['row_test']))
            mask = Image.new('L',(12,10))
            ImageDraw.Draw(mask).rectangle((2,3,5,8),fill=255)
            draft = dict(id=row['id'], image_sha256=row['image_sha256'], size=[12,10],
                         candidates=[dict(id='a', suggested_class=0, segmentation=encode_mask(mask),
                                          prompt_box=[1,2,7,9], source='test')], source_assets={})
            with self.assertRaisesRegex(ValueError, 'Visual review'):
                make_annotation(row, draft, dict(objects={}, scanned_rgb_and_overlay=True))
            decision = dict(objects={'a':dict(status='accept',class_id=1)},scanned_rgb_and_overlay=True)
            ann = make_annotation(row,draft,decision)
            self.assertEqual(ann['objects'][0]['bbox'],[2,3,6,9])
            destination = root/'annotations/row_test.json'
            atomic_json(destination,ann)
            phase, missing = prepare_phase(root, inputs, 1)
            self.assertFalse(missing)
            self.assertEqual(read(phase/'manifest.json')['coverage']['madura'],1)
            ann['objects'][0]['class_id'] = 2
            atomic_json(destination,ann)
            with self.assertRaisesRegex(ValueError,'Incompatible existing artifact'):
                prepare_phase(root,inputs,1)

    def test_exact_exposures_without_empty_optimizer_updates(self):
        order = [0,1,2,3,0,2,3,1]
        repaired = pair_supervision(order,{0,1})
        self.assertEqual(Counter(repaired),Counter(order))
        for start in range(0,len(order),2):
            self.assertFalse(set(repaired[start:start+2]) <= {0,1})
        with self.assertRaisesRegex(ValueError,'Too many'):
            pair_supervision([0,1,2,0],{0,1})
