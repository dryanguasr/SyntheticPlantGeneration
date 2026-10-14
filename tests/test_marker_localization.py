import unittest
import numpy as np
import importlib.util
from pathlib import Path
from uchuva_gazebo.localization import canonical_pose,robust_triangulate,reconcile,PersistentTracker


class MarkerLocalizationTests(unittest.TestCase):
    def test_competing_crossing_detections_do_not_share_persistent_id(self):
        image=np.random.default_rng(19).integers(0,255,(100,100,3),dtype=np.uint8)
        tracker=PersistentTracker()
        original=dict(box_xyxy_px=[20,20,60,60],center_px=[40,40])
        tracker.update(image,[original],0)
        crossing=[dict(box_xyxy_px=[20,20,60,60],center_px=[40,40]) for _ in range(2)]
        tracker.update(image,crossing,200000000)
        self.assertEqual(len({d['track_id'] for d in crossing}),2)
        self.assertTrue(all(d['track_id']!=original['track_id'] for d in crossing))

    def test_small_pixel_noise_preserves_metric_triangulation(self):
        K=np.array([[700,0,640],[0,700,360],[0,0,1.]])
        point=np.array([.1,.3,2.]);rng=np.random.default_rng(71);observations=[]
        for i,x in enumerate(np.linspace(-.3,.3,9)):
            t=np.array([x,0,0]);pixel=K@(point+t)
            observations.append(dict(R=np.eye(3).tolist(),t=t.tolist(),
                point_px=(pixel[:2]/pixel[2]+rng.normal(0,.1,2)).tolist(),
                marker_id=0,observation_id=str(i)))
        result=robust_triangulate(observations,K)
        self.assertEqual(result['status'],'estimated')
        self.assertLess(np.linalg.norm(np.asarray(result['position_marker_m'])-point),.01)

    def test_brief_gap_recovers_id_but_expired_track_does_not(self):
        image=np.random.default_rng(73).integers(0,255,(100,100,3),dtype=np.uint8)
        tracker=PersistentTracker()
        def detection():return dict(box_xyxy_px=[20,20,60,60],center_px=[40,40])
        first=detection();tracker.update(image,[first],0)
        tracker.update(image,None,200000000)
        recovered=detection();tracker.update(image,[recovered],400000000)
        self.assertEqual(first['track_id'],recovered['track_id'])
        expired=detection();tracker.update(image,[expired],3000000000)
        self.assertNotEqual(first['track_id'],expired['track_id'])

    def test_confirmation_uses_inliers_and_requires_stability(self):
        path = Path(__file__).resolve().parents[1] / 'scripts/refine_localization_support.py'
        spec = importlib.util.spec_from_file_location('support_refinement', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        observations = [dict(observation_id=str(i)) for i in range(6)]
        fit = dict(inlier_observation_ids=['0','1','2','3','4'], uncertainty_m=.01)
        support, reasons = module.supported_candidate(fit, observations, 5)
        self.assertEqual(len(support), 5)
        self.assertNotIn(observations[5], support)
        self.assertEqual(reasons, [])
        fit['uncertainty_m'] = None
        self.assertIn('unstable_triangulation', module.supported_candidate(fit, observations, 5)[1])

    def test_back_marker_to_canonical(self):
        pose={'R':np.eye(3).tolist(),'t':[0,0,2]}
        rig={'R_marker_from_canonical':np.diag([-1,1,-1]).tolist(),'t_marker_from_canonical_m':[0,0,-.36]}
        result=canonical_pose(pose,rig)
        np.testing.assert_allclose(result['t'],[0,0,1.64])
        np.testing.assert_allclose(np.asarray(result['R'])@[.2,.4,-.3]+result['t'],[-.2,.4,1.94])

    def test_triangulation_rejects_outlier(self):
        K=np.array([[700,0,640],[0,700,360],[0,0,1.]])
        point=np.array([.1,.3,2.]);obs=[]
        for i,x in enumerate(np.linspace(-.3,.3,7)):
            t=np.array([x,0,0]);p=K@(point+t);uv=p[:2]/p[2]
            if i==2:uv+=60
            obs.append(dict(R=np.eye(3).tolist(),t=t.tolist(),point_px=uv.tolist(),marker_id=0,observation_id=str(i)))
        fit=robust_triangulate(obs,K)
        self.assertEqual(fit['status'],'estimated')
        np.testing.assert_allclose(fit['position_marker_m'],point,atol=1e-6)
        self.assertNotIn('2',fit['inlier_observation_ids'])

    def test_simultaneous_objects_are_not_merged(self):
        def candidate(tid):return dict(marker_id=0,observations=4,stamps=[1,2,3,4],appearance=[1.,0.],position_marker_m=[0,1,0],track_ids=[tid],observation_ids=[tid])
        self.assertEqual(len(reconcile([candidate('a'),candidate('b')])),2)


if __name__=='__main__':unittest.main()
