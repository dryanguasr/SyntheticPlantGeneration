"""Meaningful segmentation, blinding and source-preservation checks."""
from pathlib import Path
import copy,json,sys,tempfile,unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from uchuva_annotation_audit.masks import encode_mask,decode_mask,area,mask_bbox,mask_iou,polygons_mask
from uchuva_annotation_audit.store import AuditStore,SessionLock,atomic_json,read,sha,validate_objects,compare_objects


def shape(cid=2,offset=0):
    mask=Image.new('L',(40,30));d=ImageDraw.Draw(mask)
    d.polygon([(3+offset,3),(14+offset,3),(8+offset,15)],fill=255)
    return validate_objects([dict(id='object_a',class_id=cid,segmentation=encode_mask(mask),bbox=[0,0,40,30])],40,30)[0]


def fixture(root):
    samples=[]
    for i in range(2):
        ident=f'I{i+1:02}';path=root/'images'/f'{ident}.jpg';path.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(40,30),'#8a9b75').save(path)
        samples.append(dict(id=ident,image=f'images/{ident}.jpg',width=40,height=30))
        atomic_json(root/'private/proposals'/f'{ident}.json',dict(objects=[shape()],method='fixture_only'))
        atomic_json(root/'private/originals'/f'{ident}.json',dict(objects=[shape(0)],source_row=i))
    atomic_json(root/'samples.json',dict(samples=samples))
    atomic_json(root/'private/selection.json',dict(samples=[dict(id=s['id'],stratum='random' if i==0 else 'difficult') for i,s in enumerate(samples)]))
    files={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
    atomic_json(root/'sealed.json',dict(files=files))
    return root


class MaskTests(unittest.TestCase):
    def test_parts_and_holes_survive_exact_rle(self):
        mask=Image.new('L',(20,15));d=ImageDraw.Draw(mask);d.rectangle((2,2,8,9),fill=255);d.rectangle((4,4,5,6),fill=0);d.rectangle((15,10,16,12),fill=255)
        value=encode_mask(mask)
        self.assertEqual(mask.tobytes(),decode_mask(value).tobytes())
        self.assertEqual(mask_bbox(value),[2,2,17,13]);self.assertEqual(area(value),56)
    def test_box_is_derived_and_box_only_annotation_rejected(self):
        obj=shape();self.assertNotEqual(obj['bbox'],[0,0,40,30]);self.assertEqual(obj['bbox_source'],'native_mask_pixels')
        with self.assertRaises(ValueError):validate_objects([dict(class_id=2,bbox=[1,1,5,5])],40,30)
    def test_mask_comparison_not_box_overlap(self):
        a=Image.new('L',(10,10));b=Image.new('L',(10,10));d=ImageDraw.Draw(a);e=ImageDraw.Draw(b)
        d.line((0,0,9,9),fill=255);e.line((0,9,9,0),fill=255)
        aa,bb=encode_mask(a),encode_mask(b)
        self.assertEqual(mask_bbox(aa),mask_bbox(bb));self.assertEqual(mask_iou(aa,bb),0)
        objs=[validate_objects([dict(id='a',class_id=2,segmentation=s)],10,10)[0] for s in (aa,bb)]
        self.assertEqual(compare_objects([objs[0]],[objs[1]])['matches'],[])
    def test_polygon_hole_and_outside_vertex(self):
        mask=polygons_mask([dict(points=[[1,1],[12,1],[12,12],[1,12]]),dict(role='hole',points=[[4,4],[8,4],[8,8],[4,8]])],20,20)
        self.assertEqual(mask.getpixel((5,5)),0);self.assertEqual(mask.getpixel((2,2)),255)
        with self.assertRaises(ValueError):polygons_mask([dict(points=[[-1,0],[5,0],[5,5]])],20,20)
    def test_bad_rle_and_unknown_sidecar_class(self):
        obj=shape(None);self.assertIsNone(obj['class_id'])
        with self.assertRaises(ValueError):validate_objects([dict(class_id=3,segmentation=obj['segmentation'])],40,30)
        broken=copy.deepcopy(obj);broken['segmentation']['counts'][0]+=1
        with self.assertRaises(ValueError):validate_objects([broken],40,30)


class StoreTests(unittest.TestCase):
    def setUp(self):
        temporary_root=REPO/'outputs/annotation_audit_unit_tests'
        temporary_root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=temporary_root);self.root=fixture(Path(self.tmp.name));self.store=AuditStore(self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_manual_gate_even_after_draft(self):
        with self.assertRaises(PermissionError):self.store.comparison('I01')
        self.store.save_draft('I01',[shape()])
        with self.assertRaises(PermissionError):self.store.comparison('I01')
    def test_first_manual_immutable_originals_untouched(self):
        source=self.root/'private/originals/I01.json';original_sha=sha(source)
        self.store.commit_manual('I01',[shape(1)],'Auditor fixture')
        saved=sha(self.store.manual_path('I01'))
        with self.assertRaises(FileExistsError):self.store.commit_manual('I01',[shape(2)],'Other')
        self.store.save_final('I01',[shape(2)],'Auditor fixture')
        self.assertEqual(saved,sha(self.store.manual_path('I01')));self.assertEqual(original_sha,sha(source))
        result=self.store.comparison('I01')['comparison'];self.assertFalse(result['matches'][0]['class_agrees'])
    def test_empty_needs_confirmation_and_reviewer(self):
        with self.assertRaises(ValueError):self.store.commit_manual('I01',[],'A')
        with self.assertRaises(ValueError):self.store.commit_manual('I01',[],'',empty_confirmed=True)
        self.store.commit_manual('I01',[],'A',empty_confirmed=True)
        self.assertEqual(self.store.comparison('I01')['manual']['objects'],[])
    def test_export_hides_unreviewed_answers(self):
        self.store.commit_manual('I01',[shape()],'A');path=self.store.export()
        report=read(path.parent/'audit.json')
        self.assertEqual([r['sample_id'] for r in report['cases']],['I01']);self.assertFalse(report['human_audit_complete'])
        self.assertEqual(report['by_stratum']['difficult']['images'],0)
    def test_no_traversal_and_no_concurrent_session(self):
        with self.assertRaises(ValueError):AuditStore(self.root,'../other')
        with self.assertRaises(KeyError):self.store.sample('../../secrets')
        a=SessionLock(self.root/'lock')
        try:
            with self.assertRaises(RuntimeError):SessionLock(self.root/'lock')
        finally:a.close()
    def test_changed_proposals_rejected_on_open(self):
        atomic_json(self.root/'private/proposals/I01.json',dict(objects=[]))
        with self.assertRaises(ValueError):AuditStore(self.root)


class DesktopContractTests(unittest.TestCase):
    # UI mutations below use a disposable fixture only.
    setUp=StoreTests.setUp
    tearDown=StoreTests.tearDown
    def test_polygon_then_commit_reveals_masks_without_changing_original(self):
        import tkinter as tk
        from annotation_audit_app import AuditApp
        window=tk.Tk();window.withdraw();app=AuditApp(window,self.store)
        try:
            app.change_image('I01');self.assertEqual(app.phase,'manual');self.assertIsNone(app.comparison_data)
            self.assertEqual(app.left.objects,[])
            app.left.points=[(3,3),(15,3),(8,16)];app.left.finish_polygon()
            obj=app.left.payload()[0];self.assertLess(area(obj['segmentation']),12*14)
            app.reviewer.set('Fixture automated test')
            with patch('annotation_audit_app.messagebox.askyesno',return_value=True),patch('annotation_audit_app.messagebox.showerror',side_effect=AssertionError):app.commit()
            self.assertEqual(app.phase,'compare');self.assertIsNotNone(app.comparison_data)
            self.assertFalse(app.left.editable);self.assertFalse(app.right.editable)
            self.assertIn('segmentation',app.right.objects[0])
            self.assertEqual(self.store.progress()['manual'],1)
        finally:app.lock.close();window.destroy()


if __name__=='__main__':unittest.main()
