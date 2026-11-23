import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_cad_inspection import matrix_pose, prepare


class CadInspectionTests(unittest.TestCase):
    def test_si_translation_and_rotation_are_not_scaled_twice(self):
        pose = matrix_pose([0,-1,0,.25, 1,0,0,-.1, 0,0,1,.2, 0,0,0,1])
        self.assertEqual(pose[:3], [.25,-.1,.2])
        self.assertAlmostEqual(pose[5], 1.5707963267948966)
        with self.assertRaises(ValueError):
            matrix_pose([-1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1])

    def test_mesh_admission_and_partial_inspection_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); mesh=root/'piece.obj'
            mesh.write_text('v 0 0 0\nv .1 0 0\nv 0 .1 0\nf 1 2 3\n')
            data={'schema_version':'uchuva.inventor_cad_inventory/1','status':'partial_export',
                  'documents':[{'id':'root','source_path':'assembly.iam'}, {'id':'part','source_path':'piece.ipt',
                   'exports':{'obj':{'status':'exported','uri':'piece.obj','sha256':hashlib.sha256(mesh.read_bytes()).hexdigest()}}}],
                  'occurrences':[{'id':'root/1','root_document_id':'root','document_id':'part','status':'resolved',
                    'transform_root_m':[1,0,0,.25,0,1,0,0,0,0,1,0,0,0,0,1]},
                    {'id':'root/2','root_document_id':'root','status':'external_or_unavailable'}],
                  'issues':[{'scope':'missing_reference'}]}
            source=root/'inventory.json';source.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Partial CAD'):
                prepare(source,root/'rejected')
            self.assertFalse((root/'rejected').exists())
            report=prepare(source,root/'inspection',True)
            self.assertEqual(report['status'],'PARTIAL')
            self.assertEqual(report['missing_occurrences'],['root/2'])
            model=ET.parse(root/'inspection/inspection.sdf')
            self.assertEqual(model.findtext('.//visual/pose').split()[0],'0.25')
            self.assertEqual(model.findtext('.//model/static'),'true')
            self.assertEqual(model.findall('.//collision'),[])
            mesh.write_text('tampered')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                prepare(source,root/'tampered',True)


if __name__=='__main__': unittest.main()
