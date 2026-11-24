"""Guard against faster capture silently weakening geometry/commit contracts."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.blender_capture_optimized import binary_geometry_digest,reads_object_color,refresh_hidden_fruit_transforms
from uchuva_lsystem.capture_plan import CaptureJournal, condition_for_view,profiles_for_condition
from uchuva_lsystem.appearance_profiles import initial_profiles
from uchuva_lsystem.nodal_automation import read,sha
from uchuva_lsystem.mask_arrays import quantize_stats
from uchuva_lsystem.capture_conditions import balanced_condition_for_view
from uchuva_lsystem import blender_annotations as annotations


class Values:
    def __init__(self,values):self.values=values
    def __len__(self):return len(self.values)
    def foreach_get(self,key,out):
        flat=[]
        for value in self.values:
            item=value[key];flat.extend(item if isinstance(item,tuple) else [item])
        for i,value in enumerate(flat):out[i]=value


def fake_scene():
    mesh=SimpleNamespace(vertices=Values([dict(co=(0.,0.,0.)),dict(co=(1.,0.,0.)),dict(co=(0.,1.,0.))]),
        loops=Values([dict(vertex_index=i) for i in (0,1,2)]),
        polygons=Values([dict(loop_start=0,loop_total=3)]))
    obj=SimpleNamespace(name='leaf',type='MESH',data=mesh,
        matrix_world=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]])
    return SimpleNamespace(objects=[obj])


class CaptureTests(unittest.TestCase):
    def test_each_depth_receives_all_lights_in_one_scene(self):
        from collections import Counter
        rows=[balanced_condition_for_view(13,i) for i in range(24)]
        self.assertEqual(Counter(r['diagnostic_light'] for r in rows),{'field':8,'diffuse':8,'shade':8})
        for depth in range(3):
            counts=Counter(rows[i]['diagnostic_light'] for i in range(depth,24,3))
            self.assertEqual(set(counts),{'field','diffuse','shade'})
            self.assertLessEqual(max(counts.values())-min(counts.values()),1)
        self.assertEqual(rows,[balanced_condition_for_view(13,i) for i in range(24)])

    def test_hidden_fruit_transform_warmup_restores_flags(self):
        class Fruit(dict):
            def __init__(self):
                super().__init__(uchuva_organ_kind='fruit');self.hide_viewport=True;self.local=True;self.hide_render=True
            def hide_get(self):return self.local
            def hide_set(self,value):self.local=value
        fruit=Fruit();states=[]
        def update():states.append((fruit.hide_viewport,fruit.local,fruit.hide_render))
        fake=SimpleNamespace(context=SimpleNamespace(view_layer=SimpleNamespace(update=update)))
        with patch.dict(sys.modules,{'bpy':fake}):
            row=refresh_hidden_fruit_transforms(SimpleNamespace(objects=[fruit]))
        self.assertEqual(states,[(False,False,True),(True,True,True)])
        self.assertTrue(row['render_flags_unchanged'])

    def test_bulk_guard_detects_in_place_vertex_edit(self):
        scene=fake_scene();before=binary_geometry_digest(scene)
        scene.objects[0].data.vertices.values[1]['co']=(1.0001,0.,0.)
        self.assertNotEqual(before,binary_geometry_digest(scene))

    def test_bulk_guard_detects_topology_and_transform(self):
        scene=fake_scene();before=binary_geometry_digest(scene)
        scene.objects[0].data.loops.values[0]['vertex_index']=2
        self.assertNotEqual(before,binary_geometry_digest(scene))
        scene=fake_scene();scene.objects[0].matrix_world[0][3]=.001
        self.assertNotEqual(before,binary_geometry_digest(scene))

    def test_camera_and_light_do_not_change_geometry_fingerprint(self):
        scene=fake_scene();before=binary_geometry_digest(scene)
        scene.objects.append(SimpleNamespace(type='CAMERA'))
        scene.objects.append(SimpleNamespace(type='LIGHT'))
        self.assertEqual(before,binary_geometry_digest(scene))

    def test_lighting_stream_reproducible_and_diverse(self):
        rows=[condition_for_view(13,i) for i in range(12)]
        self.assertEqual(rows,[condition_for_view(13,i) for i in range(12)])
        self.assertEqual({r['diagnostic_light'] for r in rows},{'field','diffuse','shade'})
        self.assertGreater(len({r['exposure_offset_ev'] for r in rows}),1)

    def test_variability_preserves_source_profiles_and_materials(self):
        profiles=initial_profiles();before=initial_profiles()
        varied,key=profiles_for_condition(profiles,condition_for_view(13,0))
        self.assertEqual(profiles,before)
        self.assertEqual(varied['materials'],before['materials'])
        self.assertIn(key,varied['diagnostic_lights'])

    def test_nested_object_color_material_is_rejected(self):
        inner=SimpleNamespace(nodes=[SimpleNamespace(type='OBJECT_INFO',outputs={'Color':SimpleNamespace(is_linked=True)})])
        outer=SimpleNamespace(nodes=[SimpleNamespace(type='GROUP',node_tree=inner)])
        self.assertTrue(reads_object_color(outer))

    def test_array_mask_keeps_single_pixel_and_transparency(self):
        palette={0:(0,0,0),1:(17,34,51),2:(255,255,255)}
        pixels=[0.,0.,0.,1., 17/255,34/255,51/255,1.,
                1.,1.,1.,.49, 1.,1.,1.,.5]
        snapped,stats=quantize_stats(pixels,palette,2,2)
        self.assertEqual(stats[1]['visible_pixels'],1)
        self.assertEqual(stats[1]['bbox_xywh'],[1,1,1,1])
        self.assertEqual(stats[2]['bbox_xywh'],[1,0,1,1])
        self.assertEqual(stats[0]['visible_pixels'],2)
        self.assertEqual(len(snapped),16)

    def test_array_mask_matches_legacy_rounding_and_nearest_rule(self):
        import numpy as np
        rng=np.random.default_rng(42)
        pixels=rng.random((100,4),dtype=np.float32)
        palette={0:(0,0,0),3:(17,34,51),9:(34,34,51),17:(255,255,255)}
        pixels[:5]=[[17/255,34/255,51/255,1],[34/255,34/255,51/255,1],
                    [.5/255,0,0,1],[17/255,34/255,51/255,.5],[1,1,1,1]]
        snapped,stats=quantize_stats(pixels,palette,10,10)
        ids=[]
        for pixel in pixels:
            rgb=tuple(annotations._normalized_channel_to_byte(float(x)) for x in pixel[:3])
            if pixel[3]<.5:rgb=(0,0,0)
            ids.append(annotations._nearest_palette_identifier(rgb,list(palette.items())))
        expected=[annotations._normalized_rgba(palette[i]) for i in ids]
        np.testing.assert_array_equal(snapped,np.asarray(expected,dtype=np.float32).reshape(-1))
        for identifier in palette:
            positions=[(i%10,9-i//10) for i,value in enumerate(ids) if value==identifier]
            self.assertEqual(stats[identifier]['visible_pixels'],len(positions))
            if positions:
                xs,ys=zip(*positions)
                self.assertEqual(stats[identifier]['bbox_xywh'],[min(xs),min(ys),max(xs)-min(xs)+1,max(ys)-min(ys)+1])

    def test_journal_rejects_partial_duplicate_and_outside_commit(self):
        test_root=Path(__file__).resolve().parents[1]/'outputs'/'capture_test_tmp'
        test_root.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=test_root) as temporary:
            bank=Path(temporary)/'bank';folder=bank/'views'/'v0';folder.mkdir(parents=True)
            row=dict(status='complete',view_id='v0')
            for k in ('image','mask','label'):
                p=folder/k;p.write_text(k);row[k]=str(p);row[k+'_sha256']=sha(p)
            journal=CaptureJournal(bank);journal.commit(folder,row)
            self.assertEqual(read(bank/'capture_index.json')['complete_images'],1)
            with self.assertRaises(ValueError):journal.commit(folder,row)
            with self.assertRaises(ValueError):journal.commit(bank/'outside',dict(row,view_id='v1'))
            self.assertEqual(journal.consolidate(),[row])
            self.assertEqual(CaptureJournal(bank).paths,journal.paths)


if __name__=='__main__':unittest.main()
