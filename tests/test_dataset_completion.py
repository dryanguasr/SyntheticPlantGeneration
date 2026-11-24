"""No counting unclosed prefixes, no duplicate owners, no unsafe recovery."""
import sys,unittest,subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.nodal_automation import write,read,sha
from uchuva_lsystem.dataset_completion import new_rows,select_next_scene,preserve_unbuilt,process_identity,owner_alive,publish_index
from report_dataset_completion import audit_pixels


class CompletionTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'outputs/completion_test_tmp';parent.mkdir(parents=True,exist_ok=True)
        self.tmp=TemporaryDirectory(dir=parent);self.root=Path(self.tmp.name)
        write(self.root/'dataset/config.json',dict(first_scene_index=15))
        write(self.root/'config.json',dict(target_total=1000))
        write(self.root/'baseline_lock.json',dict(views=[dict(view_id='old',view_record='old.json')]*144))
    def tearDown(self):self.tmp.cleanup()

    def test_start_after_historical_scenes_and_resume_checkpoint(self):
        self.assertEqual(select_next_scene(self.root),(15,False))
        folder=self.root/'dataset/scenes/scene_015'
        for n in ('accepted.json','capture_plan.json'):write(folder/n,{})
        (folder/'scene.blend').write_bytes(b'checkpoint')
        self.assertEqual(select_next_scene(self.root),(15,True))

    def test_recovery_preserves_unbuilt_but_rejects_committed_view(self):
        f=self.root/'dataset/scenes/scene_015';f.mkdir(parents=True)
        (f/'partial').write_text('preserve')
        preserve_unbuilt(self.root,self.root/'recovery')
        self.assertEqual((self.root/'recovery/scenes/scene_015/partial').read_text(),'preserve')
        f.mkdir();write(self.root/'dataset/views/scene_015_view_000/view.json',dict(status='complete'))
        with self.assertRaises(ValueError):preserve_unbuilt(self.root,self.root/'recovery2')

    def test_only_closed_physically_admitted_views_count(self):
        folder=self.root/'dataset/views/scene_015_view_000';folder.mkdir(parents=True)
        row=dict(status='complete',view_id=folder.name,scene_id='scene_015',geometry_sha256='geometry',camera_sha256='camera')
        for key in ('image','mask','label'):
            p=folder/key;p.write_text(key);row[key]=str(p);row[key+'_sha256']=sha(p)
        write(folder/'view.json',row)
        self.assertEqual(new_rows(self.root),[])
        self.assertEqual(new_rows(self.root,closed_only=False),[row])
        scene=self.root/'dataset/scenes/scene_015'
        write(scene/'capture_complete.json',dict(geometry_unchanged=True,geometry_sha256='geometry'))
        write(scene/'accepted.json',dict(geometry_sha256='geometry'))
        write(scene/'mesh.json',dict(physical_collision_count=0))
        for n in ('ground','orientation'):write(scene/(n+'.json'),dict(status='valid'))
        self.assertEqual(new_rows(self.root),[row])
        write(scene/'mesh.json',dict(physical_collision_count=1))
        with self.assertRaises(ValueError):new_rows(self.root)

    def test_combined_target_cannot_be_exceeded(self):
        self.assertEqual(publish_index(self.root,[]),144)
        with self.assertRaises(ValueError):publish_index(self.root,[dict(view_id=str(i)) for i in range(857)])

    @unittest.skipUnless(sys.platform=='win32','native Windows identity contract')
    def test_native_identity_and_exited_child(self):
        own=process_identity();self.assertTrue(owner_alive(own))
        self.assertFalse(owner_alive(dict(own,creation_tick=str(int(own['creation_tick'])+1))))
        child=subprocess.Popen([sys.executable,'-c','pass'])
        record=process_identity(child.pid,child._handle);child.wait()
        self.assertFalse(owner_alive(record))

    def test_real_reference_pixel_contract(self):
        source=ROOT/'outputs/spatial_plant_pool_20261028/dataset'
        if not source.exists():self.skipTest('local reference not present')
        row=read(source/'views/scene_013_view_000/view.json')
        record=read(source/'scenes/scene_013/accepted.json')
        result=audit_pixels(row,record['assignments'])
        self.assertEqual(result['instances'],219)
        self.assertLess(result['max_yolo_error'],1e-9)


if __name__=='__main__':unittest.main()
