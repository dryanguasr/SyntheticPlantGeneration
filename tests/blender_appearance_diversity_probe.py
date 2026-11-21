"""CPU verification of foliage shaders and translated ground vegetation."""
from pathlib import Path
import random
import sys
import unittest
import bpy

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src'))
from uchuva_lsystem.appearance_diversity import plant_appearance
from uchuva_lsystem.blender_appearance import apply_materials,geometry_digest
from uchuva_lsystem.blender_environment import _scatter_grasses,_terrain_height_at


class DiversityBlenderTests(unittest.TestCase):
    def setUp(self):
        for o in list(bpy.data.objects):bpy.data.objects.remove(o,do_unlink=True)

    def test_foliage_switches_keep_geometry_labels_and_emission_off(self):
        def material(name):
            m=bpy.data.materials.new(name);m.use_nodes=True
            return m
        sets={mode:{'leaf':material(mode+'_green'),'leaf_senescent':material(mode+'_yellow')} for mode in ('previous','candidate')}
        for mode in ('previous','candidate'):sets['class_'+mode]=[material(mode+str(c)) for c in range(3)]
        objects=[]; assignments={};profiles={}
        for i in range(3):
            plant=f'p{i}';profiles[plant]=plant_appearance(26,plant,0,i,[8,1,1])
            for kind in ('leaf','calyx'):
                bpy.ops.mesh.primitive_cube_add(size=.1,location=(i,0,0 if kind=='leaf' else .3))
                o=bpy.context.object;o['uchuva_semantic_class']=kind;o['uchuva_plant_id']=plant
                o['uchuva_organ_id']=plant+'leaf';o['uchuva_reproductive_instance_id']=plant+':unit'
                o.data.materials.append(sets['previous']['leaf']);objects.append(o)
                assignments[plant+':unit']={'class_id':i}
        bpy.context.view_layer.update();before=geometry_digest(bpy.context.scene)
        decisions=[]
        for mode in ('previous','candidate','previous'):
            apply_materials(objects,sets,mode,assignments,foliage_profiles=profiles,seed=26)
            self.assertEqual(geometry_digest(bpy.context.scene),before)
            decisions.append([o.get('appearance_leaf_material') for o in objects if o['uchuva_semantic_class']=='leaf'])
            for o in objects:
                mat=o.data.materials[0]
                if o['uchuva_semantic_class']=='calyx':
                    self.assertIs(mat,sets['class_'+mode][assignments[o['uchuva_reproductive_instance_id']]['class_id']])
                else:
                    self.assertEqual(mat.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value,0)
        self.assertEqual(decisions[0],decisions[1]);self.assertEqual(decisions[0],decisions[2])

    def test_weed_patch_centres_translate_only_context_and_follow_terrain(self):
        material=bpy.data.materials.new('grass');collection=bpy.data.collections.new('grass')
        bpy.context.scene.collection.children.link(collection)
        kwargs=dict(count=10,name='lolium',height_range=(.2,.4),width_range=(.01,.02))
        _scatter_grasses(random.Random(7),24,material,collection,**kwargs)
        first=list(collection.objects)[0];a=[tuple(v.co) for v in first.data.vertices]
        _scatter_grasses(random.Random(7),24,material,collection,centre=(8.,2.),terrain_seed=9,**kwargs)
        second=next(o for o in collection.objects if o is not first);b=[tuple(v.co) for v in second.data.vertices]
        self.assertEqual(len(a),len(b))
        for before,after in zip(a,b):
            self.assertAlmostEqual(after[0]-before[0],8.,places=5)
            self.assertAlmostEqual(after[1]-before[1],2.,places=5)
            self.assertAlmostEqual(after[2]-before[2],_terrain_height_at(after[0],after[1],9),places=5)


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DiversityBlenderTests))
    if not result.wasSuccessful():raise RuntimeError('Appearance diversity probe failed')
