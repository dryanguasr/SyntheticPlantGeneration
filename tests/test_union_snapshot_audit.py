"""Small fixtures for the real-data audit's geometry and leakage checks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
from scripts.audit_union_snapshot import proper_crossings


class UnionAuditTests(unittest.TestCase):
    def test_simple_and_crossed_polygons(self):
        self.assertEqual(proper_crossings([(0, 0), (1, 0), (1, 1), (0, 1)]), 0)
        self.assertEqual(proper_crossings([(0, 0), (1, 1), (0, 1), (1, 0)]), 1)
        self.assertEqual(proper_crossings([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]), 0)

    def test_cross_split_duplicate_and_invalid_polygon(self):
        temp_root = Path('outputs/test_union_audit').resolve()
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            root = Path(tmp)
            rows = [{'type': 'dataset', 'version': 'fixture', 'class_names': {'0': 'Pintona'}}]
            downloads = []
            for index, split in enumerate(('train', 'test'), 2):
                image = root / f'{split}.png'
                Image.new('RGB', (20, 10), 'green').save(image)
                rows.append({'type': 'image', 'file': 'same.png', 'split': split, 'width': 20, 'height': 10,
                             'annotations': {'segments': [[0, 0, 0, 1, 1, 0, 1, 1, 0]]}})
                downloads.append({'source_row': index, 'path': image.name,
                                  'sha256': hashlib.sha256(image.read_bytes()).hexdigest()})
            source = root / 'source.ndjson'
            source.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
            (root / 'download_manifest.json').write_text(json.dumps({
                'source_file': source.name, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'images': downloads}), encoding='utf-8')
            subprocess.run([sys.executable, 'scripts/audit_union_snapshot.py', str(root)], check=True, capture_output=True)
            result = json.loads((root / 'audit/audit_report.json').read_text())
            self.assertEqual(result['cross_split_byte_duplicate_groups'], 1)
            self.assertEqual(result['cross_split_pixel_duplicate_groups'], 1)
            self.assertEqual(result['issue_counts']['proper_self_intersection'], 2)
            self.assertEqual(result['issue_counts']['degenerate_polygon'], 2)
            self.assertEqual(source.read_text(), '\n'.join(json.dumps(r) for r in rows))


if __name__ == '__main__':
    unittest.main()
