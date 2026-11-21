"""Pixel provenance, loupe geometry and blind-workflow preservation."""
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
from PIL import Image
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts'),str(REPO/'tests')]
from uchuva_annotation_audit.reference_loupe import REFERENCE,load_palette,disk_sample,magnified_patch,hex_color
from uchuva_annotation_audit.store import AuditStore
from test_blind_annotation_audit import fixture


class ReferencePixelTests(unittest.TestCase):
    @unittest.skipUnless(REFERENCE.is_file(), 'Requiere la lámina local de coordinación')
    def test_palette_reproduces_declared_source_pixels_and_historical_groups(self):
        palette,image=load_palette()
        self.assertEqual([r['grade'] for r in palette['grades']],list(range(7)))
        self.assertEqual([r['agreed_visual_group'] for r in palette['grades']],['Verde','Verde','Pintona','Pintona','Pintona','Madura','Sobremadura'])
        for grade in palette['grades']:
            for kind in ('calyx','fruit'):
                patch=grade[kind];rgb=disk_sample(image,patch['center'],patch['radius'])
                self.assertEqual(list(rgb),patch['rgb']);self.assertEqual(hex_color(rgb),patch['hex'])

    def test_zoom_at_edge_keeps_sample_and_actual_focus_without_black_pixels(self):
        image=Image.new('RGB',(8,6),(24,87,162));image.putpixel((0,0),(231,20,48))
        for zoom in (2,4,8,12):
            result=magnified_patch(image,(0,0),zoom,(60,40))
            self.assertEqual(result['pixel'],(231,20,48))
            self.assertEqual(result['image'].getpixel(result['crosshair']),(231,20,48))
            self.assertEqual(result['median'],(24,87,162))
            self.assertEqual(image.getpixel((0,0)),(231,20,48))
        with self.assertRaises(ValueError):magnified_patch(image,(-1,0))


@unittest.skipUnless(REFERENCE.is_file(), 'Requiere la lámina local de coordinación')
class ReferenceBlindWorkflowTests(unittest.TestCase):
    def test_loupe_and_palette_do_not_assign_classes_or_reveal_proposals(self):
        import tkinter as tk
        from annotation_audit_app import AuditApp
        base=REPO/'outputs/annotation_audit_unit_tests';base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory:
            store=AuditStore(fixture(Path(directory)));window=tk.Tk();window.withdraw();app=AuditApp(window,store)
            try:
                app.change_image('I01');current_class=app.class_var.get()
                self.assertEqual(float(app.reference_tool.place_info()['relx']),1)
                self.assertEqual(len(app.reference_tool.swatches),7)
                self.assertTrue(all(kind=='calyx' for _,_,kind in app.reference_tool.swatches))
                children=app.reference_tool.pack_slaves()
                self.assertEqual(children.index(app.reference_tool.palette_canvas),children.index(app.reference_tool.display)+1)
                for grade in app.reference_tool.palette['grades']:
                    items=app.reference_tool.palette_canvas.find_withtag(f'grade_{grade["grade"]}_calyx')
                    self.assertEqual([app.reference_tool.palette_canvas.type(item) for item in items],['rectangle','text','text'])
                    self.assertEqual(app.reference_tool.palette_canvas.itemcget(items[1],'text'),str(grade['grade']))
                    self.assertEqual(app.reference_tool.palette_canvas.itemcget(items[2],'text'),grade['agreed_visual_group'])
                    self.assertGreater(app.reference_tool.palette_canvas.coords(items[2])[1],app.reference_tool.palette_canvas.coords(items[1])[1])
                app.reference_tool.last=(app.left.image,(10,10));app.reference_tool.refresh_last()
                app.reference_tool.select_grade(6)
                self.assertEqual(app.class_var.get(),current_class)
                self.assertEqual(app.left.objects,[]);self.assertIsNone(app.comparison_data)
                with self.assertRaises(PermissionError):store.comparison('I01')
                app.reviewer.set('Fixture only');app.empty_var.set(True)
                with patch('annotation_audit_app.messagebox.askyesno',return_value=True),patch('annotation_audit_app.messagebox.showerror',side_effect=AssertionError):app.commit()
                context=store.manual('I01')['application_context']
                self.assertTrue(context['loupe_used_for_this_image'])
                self.assertEqual(context['palette_grades_consulted'],[6])
                app.change_image('I02')
                self.assertEqual(app.reference_tool.winfo_manager(),'place')
                self.assertIsNone(app.reference_tool.last)
                self.assertEqual(store.runtime_context['palette_grades_consulted'],[])
                self.assertEqual(store.progress()['manual'],1)
            finally:app.lock.close();window.destroy()


if __name__=='__main__':unittest.main()
