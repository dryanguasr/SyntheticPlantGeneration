"""Reject unpaired controls and verify the native size-policy interpretation."""
from pathlib import Path
import copy,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
from appearance_campaign import schedule_indices
from reviewed_augmentation_pilot import configurations
from run_appearance_campaign import verify_sequences
from ultralytics.data.augment import RandomPerspective


class ReviewedPilotTests(unittest.TestCase):
    def test_six_runs_and_real_replacement_schedule(self):
        configs=configurations('frozen.yaml');self.assertEqual(len(configs),6)
        ids=[f'row_{i:04d}' for i in range(461)]+[f'view_{i:04d}' for i in range(115)]
        import random
        from collections import Counter
        for c in configs[:2]:
            rows=[];exposure=Counter()
            for epoch in range(8):
                indices=schedule_indices(len(ids),c['seed'],epoch);planned=[ids[i] for i in indices]
                if c['real_only']:
                    rng=random.Random(c['seed']+900000+epoch)
                    indices=[rng.choice(list(range(461))) if name.startswith('view_') else i for i,name in zip(indices,planned)]
                actual=[ids[i] for i in indices];exposure.update('real' if n.startswith('row_') else 'synthetic' for n in actual)
                rows.append(dict(epoch=epoch,indices=indices,planned_source_ids=planned,actual_source_ids=actual))
            verify_sequences(c,ids,rows,dict(exposure))
            broken=copy.deepcopy(rows);broken[0]['actual_source_ids'][0]='view_bad'
            with self.assertRaises(ValueError):verify_sequences(c,ids,broken,dict(exposure))
            if c['real_only']:self.assertEqual(exposure,{'real':8000})
            else:self.assertGreater(exposure['synthetic'],0)

    def test_native_threshold_is_strict_side_and_relative_area(self):
        old=np.array([[0,0,2,3],[0,0,3,3],[0,0,100,100]],float).T
        new=np.array([[0,0,2,3],[0,0,3,3],[0,0,20,20]],float).T
        self.assertEqual(RandomPerspective.box_candidates(old,new).tolist(),[False,True,False])
        self.assertEqual(RandomPerspective.box_candidates(old,new,area_thr=.01).tolist(),[False,True,True])


if __name__=='__main__':unittest.main()
