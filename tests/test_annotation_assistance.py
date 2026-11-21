"""Prompt semantics, exact-mask contour edits and assisted blind-workflow checks."""
from pathlib import Path
import copy,sys,tempfile,unittest,time
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageDraw
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts'),str(REPO/'tests')]
from uchuva_annotation_audit.assistance import checked_prompts,mask_contours,apply_contour_edit,SamAssistant,validate_assistance
from uchuva_annotation_audit.store import AuditStore
from uchuva_annotation_audit.masks import encode_mask,decode_mask
from test_blind_annotation_audit import fixture


def metadata(size):
    return dict(version='human-prompted-sam/1',model_name='mobile_sam.pt',model_sha256='a'*64,
        ultralytics_version='fixture',device='cpu',points=[[8,8],[30,20]],labels=[1,0],
        native_size=list(size),class_source='human',boundary_edited=False)


class ContourTests(unittest.TestCase):
    def test_only_edited_boundary_delta_changes_native_mask_parts_and_hole(self):
        mask=Image.new('L',(80,70));draw=ImageDraw.Draw(mask)
        draw.rectangle((5,5,35,35),fill=255);draw.rectangle((12,12,18,18),fill=0);draw.rectangle((55,45,65,55),fill=255)
        baseline=mask.tobytes();rings=mask_contours(mask)
        self.assertEqual(mask.tobytes(),baseline)
        ring=next(r for r in rings if r['role']=='outer' and min(p[0] for p in r['points'])==5)
        self.assertEqual(apply_contour_edit(mask,ring,ring['points']).tobytes(),baseline)
        moved=copy.deepcopy(ring['points']);moved[0][0]=2
        edited=apply_contour_edit(mask,ring,moved)
        self.assertEqual(edited.crop((12,12,19,19)).tobytes(),mask.crop((12,12,19,19)).tobytes())
        self.assertEqual(edited.crop((50,40,79,69)).tobytes(),mask.crop((50,40,79,69)).tobytes())
        self.assertNotEqual(edited.tobytes(),baseline)
        hole=next(r for r in rings if r['role']=='hole')
        self.assertEqual(apply_contour_edit(mask,hole,hole['points']).tobytes(),baseline)
        with self.assertRaises(ValueError):apply_contour_edit(mask,ring,[[2,2],[35,35],[2,35],[35,2]])
        with self.assertRaises(ValueError):apply_contour_edit(mask,ring,[[-1,1],[2,1],[3,3]])

    def test_prompts_require_foreground_and_native_coordinates(self):
        with self.assertRaises(ValueError):checked_prompts([[3,3]],[0],(40,30))
        with self.assertRaises(ValueError):checked_prompts([[40,3]],[1],(40,30))
        self.assertEqual(checked_prompts([[3,3],[4,4]],[1,0],(40,30))[1],[1,0])
        self.assertEqual(validate_assistance(metadata((40,30)),(40,30))['class_source'],'human')

    def test_sam_groups_all_clicks_into_one_object_and_reuses_encoder(self):
        import numpy as np
        class Tensor:
            def __init__(self,array):self.array=array
            def detach(self):return self
            def cpu(self):return self
            def numpy(self):return self.array
        class Predictor:
            def __init__(self):self.images=[];self.calls=[]
            def reset_image(self):pass
            def set_image(self,image):self.images.append(image)
            def __call__(self,**kwargs):
                self.calls.append(kwargs);pixels=np.zeros((30,40),dtype=np.uint8);pixels[5:12,5:12]=1
                return [SimpleNamespace(masks=SimpleNamespace(data=[Tensor(pixels)]))]
        assistant=SamAssistant.__new__(SamAssistant);assistant.predictor=Predictor();assistant.image_key=None
        assistant.path=Path('mobile_sam.pt');assistant.sha='a'*64;assistant.version='fixture';assistant.device='cpu'
        image=Image.new('RGB',(40,30),(11,22,33))
        mask,meta=assistant.predict(image,[[8,8],[30,20]],[1,0]);assistant.predict(image,[[8,8]],[1])
        self.assertEqual(len(assistant.predictor.images),1)
        self.assertEqual(assistant.predictor.images[0][0,0].tolist(),[33,22,11])
        self.assertEqual(assistant.predictor.calls[0]['points'],[[[8.,8.],[30.,20.]]])
        self.assertEqual(assistant.predictor.calls[0]['labels'],[[1,0]])
        self.assertEqual(mask.size,image.size);self.assertEqual(meta['class_source'],'human')
        with self.assertRaises(FileNotFoundError):SamAssistant(REPO/'outputs/no_such_sam/mobile_sam.pt')


class AssistedDesktopTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from annotation_audit_app import AuditApp
        base=REPO/'outputs/annotation_audit_unit_tests';base.mkdir(exist_ok=True,parents=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.store=AuditStore(fixture(Path(self.tmp.name)))
        self.window=tk.Tk();self.window.withdraw();self.app=AuditApp(self.window,self.store);self.app.change_image('I01')
    def tearDown(self):
        self.app.assist_closed=True
        if self.app.assist_executor:self.app.assist_executor.shutdown(wait=True,cancel_futures=True)
        self.app.lock.close();self.window.destroy();self.tmp.cleanup()

    def test_accept_nodes_undo_and_assistance_provenance_without_gt_leak(self):
        app=self.app;view=app.left;app.tool_var.set('sam');app.set_tool()
        mask=Image.new('L',(40,30));ImageDraw.Draw(mask).rectangle((4,4,16,16),fill=255)
        view.assist_points=[(8,8)];view.assist_labels=[1];view.assist_preview=mask;view.assist_metadata=metadata(mask.size)
        self.assertFalse(app.save_draft(quiet=True))
        self.assertEqual(view.payload(),[])
        with self.assertRaises(PermissionError):self.store.comparison('I01')
        app.class_var.set('2');app.accept_sam();self.assertEqual(app.tool_var.get(),'nodes')
        self.assertEqual(view.objects[0]['class_id'],2);self.assertIsNone(app.comparison_data)
        old=view.mask(view.objects[0]).tobytes();node=view.node_rings[0]['points'][0]
        event=SimpleNamespace(x=node[0]*view.scale+view.ox,y=node[1]*view.scale+view.oy,state=0)
        view.press(event);event.x-=2*view.scale;view.motion(event);view.release(event)
        self.assertNotEqual(view.mask(view.objects[0]).tobytes(),old)
        self.assertTrue(view.objects[0]['assistance']['boundary_edited'])
        view.undo();self.assertEqual(view.mask(view.objects[0]).convert('L').tobytes(),old)
        self.assertTrue(app.save_draft(quiet=True));draft=self.store.draft('I01')
        self.assertEqual(draft['objects'][0]['assistance']['model_sha256'],'a'*64)
        self.store.commit_manual('I01',view.payload(),'Fixture only')
        saved=self.store.manual('I01')
        self.assertEqual(saved['annotation_method'],'human_prompted_model_assisted')
        self.assertFalse(saved['proposal_seen_before_commit'])
        app.current=None;app.change_image('I02');self.assertEqual(app.left.objects,[]);self.assertFalse(app.left.assist_points)

    def test_stale_async_mask_cannot_enter_another_image_or_readonly_view(self):
        from concurrent.futures import Future
        app=self.app;view=app.left;app.tool_var.set('sam');app.set_tool()
        future=Future();future.set_result((Image.new('L',(40,30),255),metadata((40,30))))
        app.assist_future=future;app.assist_job=(view,view.assist_serial,'I01')
        app.change_image('I02');app.poll_assistance()
        self.assertIsNone(view.assist_preview);self.assertEqual(view.objects,[])
        view.editable=False;view.assist_preview=Image.new('L',(40,30),255);view.assist_metadata=metadata((40,30))
        self.assertIsNone(view.accept_assistance());self.assertEqual(view.objects,[])

    def test_insert_move_delete_nodes_survive_save_reload_and_undo(self):
        app=self.app;view=app.left
        mask=Image.new('L',(40,30));draw=ImageDraw.Draw(mask)
        draw.rectangle((4,4,20,20),fill=255);draw.rectangle((8,8,10,10),fill=0);draw.rectangle((30,23,34,27),fill=255)
        obj=view.new_object(mask);app.tool_var.set('nodes');app.set_tool();view.choose(obj['id'])
        outer=next(i for i,r in enumerate(view.node_rings) if r['role']=='outer' and r['points'][0][0]==4)
        old=view.mask(obj).convert('L').tobytes();initial=len(view.node_rings[outer]['points'])
        a,b=view.node_rings[outer]['points'][:2];p=[(a[0]+b[0])/2,(a[1]+b[1])/2]
        event=SimpleNamespace(x=p[0]*view.scale+view.ox,y=p[1]*view.scale+view.oy,state=1)
        view.press(event);view.release(event)
        self.assertEqual(len(view.node_rings[outer]['points']),initial+1)
        self.assertEqual(view.mask(obj).convert('L').tobytes(),old)
        self.assertTrue(app.save_draft(quiet=True));draft=self.store.draft('I01')
        self.assertEqual(len(draft['objects'][0]['boundary_nodes']['rings'][outer]['points']),initial+1)
        view.load(view.image,draft['objects'],True);view.choose(obj['id']);obj=view.objects[0]
        self.assertEqual(len(view.node_rings[outer]['points']),initial+1)
        # Drag the inserted handle; it must not disappear during re-extraction.
        event.state=0;view.press(event);self.assertIsNotNone(view.node_drag)
        event.x-=2*view.scale;view.motion(event);view.release(event)
        self.assertNotEqual(view.mask(obj).convert('L').tobytes(),old)
        self.assertEqual(view.mask(obj).getpixel((9,9)),0)
        self.assertEqual(view.mask(obj).getpixel((32,25)),255)
        view.undo();obj=view.objects[0]
        self.assertEqual(view.mask(obj).convert('L').tobytes(),old)
        self.assertEqual(len(view.node_rings[outer]['points']),initial+1)
        event.x=p[0]*view.scale+view.ox;event.state=4;view.press(event);view.release(event)
        self.assertEqual(len(view.node_rings[outer]['points']),initial)
        view.undo();self.assertEqual(len(view.node_rings[outer]['points']),initial+1)
        view.editable=False;before=copy.deepcopy(view.payload());view.press(event)
        self.assertEqual(view.payload(),before)

    def test_node_deletion_preserves_minimum_and_rejects_crossings(self):
        app=self.app;view=app.left;errors=[];view.error_callback=errors.append
        mask=Image.new('L',(40,30));ImageDraw.Draw(mask).polygon([(5,5),(20,5),(10,20)],fill=255)
        obj=view.new_object(mask);app.node_action.set('delete');app.set_node_action();view.choose(obj['id'])
        self.assertEqual(view.node_action,'delete')
        ring=next(r for r in view.node_rings if r['role']=='outer')
        self.assertEqual(len(ring['points']),3);before=view.payload()
        x,y=ring['points'][0];view.press(SimpleNamespace(x=x*view.scale+view.ox,y=y*view.scale+view.oy,state=0))
        self.assertIn('tres nodos',errors[-1]);self.assertEqual(view.payload(),before)
        self.assertFalse(view.undo_stack)


if __name__=='__main__':unittest.main()
