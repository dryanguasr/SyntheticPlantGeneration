from pathlib import Path
import sys, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from uchuva_lsystem.blue_sky_sample_review import sample_conditions, sparse_assignments


class BlueSkyReviewTests(unittest.TestCase):
    def test_majority_blue_with_actual_light_variation(self):
        rows=sample_conditions()
        self.assertEqual(sum(r['condition']['sky_type']=='clear_blue' for r in rows),3)
        self.assertEqual(len({r['condition']['azimuth_offset_deg'] for r in rows}),4)
        for r in rows:
            c=r['condition']
            self.assertEqual(c['diagnostic_light'],'field' if c['sky_type']=='clear_blue' else 'diffuse')

    def test_sparse_reproducible_complete_assignments(self):
        ids=[str(i) for i in range(1000)]
        views=[dict(view_id='v',instances=[dict(instance_id=i,visible_pixels=j+1) for j,i in enumerate(ids[:200])])]
        a=sparse_assignments(ids,views)
        self.assertEqual(a,sparse_assignments(reversed(ids),views))
        self.assertEqual(set(a),set(ids))
        self.assertEqual(sum(x['class_id']==2 for x in a.values()),30)
        self.assertLessEqual(sum(a[i]['class_id']==2 for i in ids[:200]),10)
        self.assertGreaterEqual(sum(a[i]['class_id']==2 for i in ids[:200]),3)


if __name__=='__main__':unittest.main()
