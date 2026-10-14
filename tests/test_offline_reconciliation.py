import unittest
import numpy as np
from uchuva_gazebo.offline_reconciliation import representative_views,fit_sequence,reconcile_offline


K=[[1000,0,640],[0,1000,360],[0,0,1]]


def observations(start=0,point=(.1,.2,3),noise=0):
    rng=np.random.default_rng(10)
    rows=[]
    for i in range(20):
        t=np.array([-.6+i*.06,0,0]);camera=np.array(point)+t;pixel=np.asarray(K)@camera
        rows.append(dict(R=np.eye(3).tolist(),t=t.tolist(),point_px=(pixel[:2]/pixel[2]+rng.normal(0,noise,2)).tolist(),
            marker_id=0,stamp_ns=round((start+i*.21)*1e9),observation_id=f'{start}:{i}'))
    return rows


class OfflineTests(unittest.TestCase):
    def test_noisy_geometry_and_all_view_verification(self):
        rows=observations(noise=.2);fit=fit_sequence(rows,K)
        self.assertEqual(fit['status'],'estimated')
        self.assertLess(np.linalg.norm(np.array(fit['position_marker_m'])-[.1,.2,3]),.01)
        rows[8]['point_px']=[0,0]
        fit=fit_sequence(rows,K)
        self.assertEqual(fit['status'],'estimated')
        self.assertIn(rows[8]['observation_id'],fit['rejected_observation_ids'])

    def test_same_timestamp_cannot_fake_eight_views(self):
        rows=observations()
        for r in rows:r['stamp_ns']=1
        self.assertEqual(fit_sequence(rows,K)['reason'],'insufficient_temporally_separated_support')

    def test_low_parallax_rejected(self):
        rows=observations()
        for row in rows:
            row['t']=[0,0,0];row['point_px']=[640,360]
        self.assertNotEqual(fit_sequence(rows,K)['status'],'estimated')

    def test_joint_refit_and_simultaneous_distinct_objects_never_merge(self):
        def candidate(rows,tid):
            fit=fit_sequence(rows,K)
            return dict(**fit,marker_id=0,source_observations=rows,track_ids=[tid],
                appearance=[1,0],all_stamps=[o['stamp_ns'] for o in rows])
        first=candidate(observations(),'a');second=candidate(observations(10),'b')
        maps,log=reconcile_offline([first,second],K)
        self.assertEqual(len(maps),1);self.assertEqual(len(maps[0]['source_observations']),40)
        self.assertEqual(log[0]['action'],'merge_joint_geometry_refit')
        second=candidate(observations(point=(.11,.2,3)),'b')
        maps,_=reconcile_offline([first,second],K)
        self.assertEqual(len(maps),2)


if __name__=='__main__':unittest.main()
