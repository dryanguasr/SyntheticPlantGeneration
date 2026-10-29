"""Blender integration: branch repulsion must replay exactly from the tree."""
from pathlib import Path
import sys
import unittest
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from mathutils import Vector
from test_nodal_repulsion import fixture
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import initialize_growth_poses,protected_anatomy
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions
from uchuva_lsystem.blender_nodal_branch_repair import repair_nodal_branches

def points():
    result={}
    for obj in bpy.context.scene.objects:
        if obj.get('uchuva_plant_id')!='growth' or obj.type not in {'MESH','CURVE'}:continue
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=evaluated.to_mesh()
        try:
            if mesh:result[str(obj.get('uchuva_organ_id'))]=[tuple(evaluated.matrix_world@v.co) for v in mesh.vertices]
        finally:evaluated.to_mesh_clear()
    return result

class NodalMeshIntegration(unittest.TestCase):
    def test_private_batch_cleanup_refuses_an_object_shared_with_another_scene(self):
        cleanup_scene(include_hidden=True)
        mesh=bpy.data.meshes.new('shared_fixture');obj=bpy.data.objects.new('shared_fixture',mesh)
        bpy.context.scene.collection.objects.link(obj)
        other=bpy.data.scenes.new('other_fixture');other.collection.objects.link(obj)
        try:
            with self.assertRaisesRegex(ValueError,'exclusive'):
                cleanup_scene(include_hidden=True)
            self.assertIn(obj.name,bpy.context.scene.objects)
            self.assertIn(obj.name,other.objects)
        finally:
            bpy.data.scenes.remove(other)
        cleanup_scene(include_hidden=True)
        self.assertNotIn('shared_fixture',bpy.data.objects)

    def test_three_axillary_units_can_be_coordinated_without_organ_loss(self):
        from uchuva_lsystem.blender_pose_repair_v2 import repair_size_preserving_poses
        from uchuva_lsystem.nodal_repulsion import revise_pedicel_mobility
        cleanup_scene(include_hidden=True);plant=fixture();plant.axes[0].child_axes=[]
        for index,node in enumerate(plant.axes[0].nodes):
            node.leaf=None;plant.axes[0].internodes[index].length_cm=20 if index==0 else 1
            node.reproductive_unit.calyx.length_cm=4;node.reproductive_unit.calyx.radius_cm=1.6
            node.reproductive_unit.pedicel.azimuth_deg=0
        initialize_growth_poses(plant);revise_pedicel_mobility(plant,150,reason='Three-unit fixture of explicitly expanded engineering search')
        before=protected_anatomy(plant);materials=create_project_materials(1)
        build_geometry_from_morphology(plant,materials,instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        result=repair_size_preserving_poses(plant,materials,instance_id='growth',max_passes=1,
            max_trials_per_organ=1,max_seconds=60,growth_joint_policy=True,repair_clearance=False,organ_kinds=('reproductive',))
        self.assertTrue(any(r['kind']=='cooperative_reproductive' for r in result['adjustments']))
        self.assertEqual(before,protected_anatomy(plant))
        cleanup_scene(include_hidden=True);materials=create_project_materials(1)
        build_geometry_from_morphology(Plant.from_dict(plant.to_dict()),materials,instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        report=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        self.assertEqual(report['physical_collision_count'],0)

    def test_two_blocking_capachos_can_move_together_and_replay(self):
        from uchuva_lsystem.blender_pose_repair_v2 import repair_size_preserving_poses
        cleanup_scene(include_hidden=True);plant=fixture()
        plant.axes[0].child_axes=[];plant.axes[0].nodes=plant.axes[0].nodes[:2];plant.axes[0].internodes=plant.axes[0].internodes[:2]
        for index,node in enumerate(plant.axes[0].nodes):
            node.leaf=None;plant.axes[0].internodes[index].length_cm=20 if index==0 else 1
            node.reproductive_unit.calyx.length_cm=4
            node.reproductive_unit.calyx.radius_cm=1.6
            node.reproductive_unit.pedicel.azimuth_deg=0
        initialize_growth_poses(plant);before=protected_anatomy(plant);materials=create_project_materials(1)
        build_geometry_from_morphology(plant,materials,instance_id='growth',add_ground=False)
        bpy.context.view_layer.update()
        initial=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        self.assertGreater(initial['physical_collision_count'],0)
        result=repair_size_preserving_poses(plant,materials,instance_id='growth',max_passes=1,
            max_trials_per_organ=1,max_seconds=30,growth_joint_policy=True,repair_clearance=False,organ_kinds=('reproductive',))
        self.assertTrue(any(r['kind']=='paired_reproductive' for r in result['adjustments']))
        self.assertEqual(before,protected_anatomy(plant));updated=points()
        cleanup_scene(include_hidden=True);materials=create_project_materials(1)
        build_geometry_from_morphology(Plant.from_dict(plant.to_dict()),materials,instance_id='growth',add_ground=False)
        bpy.context.view_layer.update();rebuilt=points()
        for organ,vertices in updated.items():
            for left,right in zip(vertices,rebuilt[organ]):self.assertLess((Vector(left)-Vector(right)).length,3e-5,organ)
        final=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        self.assertEqual(final['physical_collision_count'],0)

    def test_updated_scene_matches_independent_rebuild_without_organ_loss(self):
        cleanup_scene(include_hidden=True);plant=fixture()
        payload=plant.to_dict()
        duplicate=json.loads(json.dumps(payload['axes'][0]['child_axes'][0]).replace('axis_0_branch_0','axis_0_branch_1'))
        payload['axes'][0]['child_axes'].append(duplicate)
        plant=Plant.from_dict(payload);initialize_growth_poses(plant)
        before=protected_anatomy(plant);materials=create_project_materials(1)
        build_geometry_from_morphology(plant,materials,instance_id='growth',add_ground=False)
        bpy.context.view_layer.update()
        result=repair_nodal_branches(plant,passes=2,max_seconds=30)
        self.assertTrue(result['adjustments'],'Fixture must actually exercise accepted nodal branch movement')
        self.assertEqual(before,protected_anatomy(plant));updated=points()
        first=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        cleanup_scene(include_hidden=True)
        materials=create_project_materials(1)
        build_geometry_from_morphology(Plant.from_dict(plant.to_dict()),materials,instance_id='growth',add_ground=False)
        bpy.context.view_layer.update();rebuilt=points()
        self.assertEqual(set(updated),set(rebuilt))
        for organ,vertices in updated.items():
            self.assertEqual(len(vertices),len(rebuilt[organ]),organ)
            for left,right in zip(vertices,rebuilt[organ]):
                self.assertLess((Vector(left)-Vector(right)).length,3e-5,organ)
        second=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        self.assertEqual(first['physical_collision_count'],second['physical_collision_count'])

suite=unittest.defaultTestLoader.loadTestsFromTestCase(NodalMeshIntegration)
result=unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():raise SystemExit(1)
