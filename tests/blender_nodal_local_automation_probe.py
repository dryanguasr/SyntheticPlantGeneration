"""Cached two-bone trials must equal an independent full interpretation."""
from pathlib import Path
import sys,json,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from mathutils import Vector
from test_nodal_repulsion import fixture
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import initialize_growth_poses,protected_anatomy
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions
from uchuva_lsystem.blender_nodal_local_repair import repair_local_nodal_contacts

def points():
    output={}
    for obj in bpy.context.scene.objects:
        if obj.get('uchuva_plant_id')!='growth' or obj.type not in {'MESH','CURVE'}:continue
        ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        try:
            if mesh:output[str(obj.get('uchuva_organ_id'))]=[tuple(ev.matrix_world@v.co) for v in mesh.vertices]
        finally:ev.to_mesh_clear()
    return output

class AutomaticLocalJoint(unittest.TestCase):
    def test_cached_commit_replays_all_organs_and_stems(self):
        cleanup_scene(include_hidden=True);payload=fixture().to_dict()
        duplicate=json.loads(json.dumps(payload['axes'][0]['child_axes'][0]).replace('axis_0_branch_0','axis_0_branch_1'))
        payload['axes'][0]['child_axes'].append(duplicate)
        plant=Plant.from_dict(payload);initialize_growth_poses(plant);before=protected_anatomy(plant)
        build_geometry_from_morphology(plant,create_project_materials(1),instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        mesh=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        self.assertGreater(mesh['physical_collision_count'],0)
        result=repair_local_nodal_contacts(plant,mesh,max_nodes=2,max_trials=40,max_seconds=45)
        self.assertTrue(result['adjustments'],'Fixture must exercise a real cached commit')
        self.assertEqual(before,protected_anatomy(plant));updated=points()
        first=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        cleanup_scene(include_hidden=True)
        build_geometry_from_morphology(Plant.from_dict(plant.to_dict()),create_project_materials(1),instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update();rebuilt=points()
        self.assertEqual(set(updated),set(rebuilt))
        for organ,vertices in updated.items():
            self.assertEqual(len(vertices),len(rebuilt[organ]))
            for x,y in zip(vertices,rebuilt[organ]):self.assertLess((Vector(x)-Vector(y)).length,3e-5,organ)
        second=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        self.assertEqual(first['physical_collision_count'],second['physical_collision_count'])

result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AutomaticLocalJoint))
if not result.wasSuccessful():raise SystemExit(1)
