"""Four-bone cached commits must replay all evaluated geometry exactly."""
from pathlib import Path
import sys,json,unittest,importlib.util
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from mathutils import Vector
from test_nodal_repulsion import fixture
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import initialize_growth_poses,protected_anatomy
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions

if '--' in sys.argv:
    path=Path(sys.argv[sys.argv.index('--')+1]).resolve()
    spec=importlib.util.spec_from_file_location('uchuva_lsystem._four_node_test_candidate',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    repair=module.repair_local_nodal_contacts
else:
    from uchuva_lsystem.blender_nodal_local_repair import repair_local_nodal_contacts as repair


def points():
    result={}
    for obj in bpy.context.scene.objects:
        if obj.get('uchuva_plant_id')!='growth' or obj.type not in {'MESH','CURVE'}:continue
        ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
        try:
            if mesh:result[str(obj.get('uchuva_organ_id'))]=[tuple(ev.matrix_world@v.co) for v in mesh.vertices]
        finally:ev.to_mesh_clear()
    return result


class FourNodeReplay(unittest.TestCase):
    def test_real_four_node_commit_preserves_anatomy_and_matches_rebuild(self):
        self.exercise(False)

    def test_contact_window_starts_upstream_of_the_only_reported_collision(self):
        self.exercise(True)

    def exercise(self,upstream_only):
        cleanup_scene(include_hidden=True);payload=fixture().to_dict()
        def extend(axis):
            for i in (3,4):
                old_node=axis['nodes'][2]['id'];new_node=old_node.rsplit('_',1)[0]+'_'+str(i)
                node=json.loads(json.dumps(axis['nodes'][2]).replace(old_node,new_node));node['position_index']=i;node['age']=i
                bone=json.loads(json.dumps(axis['internodes'][2]));bone['id']=bone['id'].rsplit('_',1)[0]+'_'+str(i)
                axis['nodes'].append(node);axis['internodes'].append(bone)
            for child in axis['child_axes']:extend(child)
        extend(payload['axes'][0])
        duplicate=json.loads(json.dumps(payload['axes'][0]['child_axes'][0]).replace('axis_0_branch_0','axis_0_branch_1'))
        payload['axes'][0]['child_axes'].append(duplicate)
        plant=Plant.from_dict(payload);initialize_growth_poses(plant);before=protected_anatomy(plant)
        build_geometry_from_morphology(plant,create_project_materials(1),instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        mesh=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        self.assertGreater(mesh['physical_collision_count'],0)
        if upstream_only:
            names={'uchuva_'+axis.nodes[1].reproductive_unit.calyx.id for axis in plant.axes[0].child_axes}
            rows=[r for r in mesh['physical_collisions'] if {r['object_a'],r['object_b']}==names]
            self.assertTrue(rows,'Must isolate the internal joint collision')
            mesh={**mesh,'physical_collisions':rows,'physical_collision_count':len(rows)}
        result=repair(plant,mesh,max_nodes=2,max_trials=40,max_seconds=45,candidate_modes=('four_nodes',))
        self.assertTrue(result['adjustments'],'Must commit a genuine four-node proposal')
        self.assertTrue(all(len(r['proposal']['directions'])==4 for r in result['adjustments']))
        if upstream_only:self.assertTrue(any(r['node'].endswith('_node_0') for r in result['adjustments']))
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


result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FourNodeReplay))
if not result.wasSuccessful():raise SystemExit(1)
