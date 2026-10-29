"""Small Blender CPU probe: exact mesh trials, anatomy and visibility preserved."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from uchuva_lsystem.morphology import Plant, Axis, Internode, Node, Pedicel, ReproductiveUnit, Calyx, Fruit, Leaf
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology, audit_scene_mesh_collisions
from uchuva_lsystem.blender_pose_repair_v2 import repair_size_preserving_poses, pose_invariant_manifest, _GroundPenalty
from uchuva_lsystem.blender_pose_repair import _remove_pose_objects


def obstacle(location, material):
    mesh=bpy.data.meshes.new("obstacle_mesh")
    mesh.from_pydata([(x*.40,y*.025,z*.40) for x in (-1,1) for y in (-1,1) for z in (-1,1)],[],
                    [(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)])
    mesh.update()
    obj=bpy.data.objects.new("obstacle",mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location=location
    obj["uchuva_plant_role"]="support"
    obj["uchuva_semantic_class"]="background"
    obj.data.materials.append(material)
    return obj


class PoseIntegration(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj,do_unlink=True)
        material=bpy.data.materials.get("fixture") or bpy.data.materials.new("fixture")
        self.materials={key:material for key in ("stem","stem_green","petiole","petiole_green","leaf","leaf_vein","fruit_ripe","fruit_unripe","calyx","flower")}

    def test_leaf_rebuild_preserves_dimensions_and_exact_audit(self):
        leaf=Leaf("leaf","node",8,5,2,insertion_angle_deg=60,azimuth_deg=0,
                  provenance={"insertion_frame":"local_cone_v2"})
        plant=Plant("fixture","fixture",1,"test","test",axes=[Axis("axis",0,internodes=[Internode("segment",0,30,.1)],nodes=[Node("node",0,0,0,leaf=leaf)])])
        invariant=pose_invariant_manifest(plant)
        build_geometry_from_morphology(plant,self.materials,instance_id="fixture",add_ground=False)
        bpy.context.view_layer.update()
        blade=next(o for o in bpy.context.scene.objects if o.get("uchuva_organ_id")=="leaf")
        points=[blade.matrix_world @ Vector(v) for v in blade.bound_box]
        center=sum(points,Vector())/len(points)
        obstacle(center,self.materials["stem"])
        bpy.context.view_layer.update()
        initial=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,near_contact_distance=0)
        self.assertGreater(initial["physical_collision_count"],0)
        report=repair_size_preserving_poses(plant,self.materials,instance_id="fixture",max_passes=1,max_trials_per_organ=56,max_seconds=60,organ_kinds=("leaf",))
        self.assertEqual(report['searched_organ_kinds'],['leaf'])
        self.assertTrue(report["adjustments"])
        self.assertEqual(invariant,pose_invariant_manifest(plant))
        after=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,near_contact_distance=0)
        self.assertLess(after["physical_collision_count"],initial["physical_collision_count"])
        self.assertEqual(len([o for o in bpy.context.scene.objects if o.get("uchuva_plant_id")=="fixture" and o.get("uchuva_organ_id")=="leaf"]),1)
        _remove_pose_objects([o for o in bpy.context.scene.objects if o.get("uchuva_plant_id")=="fixture"])
        build_geometry_from_morphology(Plant.from_dict(plant.to_dict()),self.materials,instance_id="fixture",add_ground=False)
        bpy.context.view_layer.update()
        rebuilt=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,near_contact_distance=0)
        self.assertEqual((after["physical_collision_count"],after["clearance_violation_count"]),
                         (rebuilt["physical_collision_count"],rebuilt["clearance_violation_count"]))

    def test_reproductive_templates_exact_with_instance_transform(self, pendulous=False):
        unit=ReproductiveUnit("unit","node","mature_fruit_with_calyx",Pedicel("unit_pedicel","node",2,35,0),
            calyx=Calyx("unit_calyx",3,1,openness=0,covers_fruit_fraction=1),fruit=Fruit("unit_fruit",.7,"ripe","hidden"))
        plant=Plant("fixture","fixture",1,"test","test",axes=[Axis("axis",0,internodes=[Internode("segment",0,30,.1)],nodes=[Node("node",0,0,0,reproductive_unit=unit)])])
        if pendulous:
            from uchuva_lsystem.reproductive_orientation import assign_reproductive_orientation
            from uchuva_lsystem.parameters import get_morphology_parameters
            assign_reproductive_orientation(plant, get_morphology_parameters('trained_trellis_pendulous_audit_v7'))
        before=pose_invariant_manifest(plant)
        transform=Matrix.Translation((2,3,4)) @ Matrix.Rotation(.4,4,"Z")
        build_geometry_from_morphology(plant,self.materials,instance_id="fixture",position=(2,3,4),rotation_deg=.4*180/3.141592653589793,add_ground=False)
        bpy.context.view_layer.update()
        calyx=next(o for o in bpy.context.scene.objects if o.get("uchuva_semantic_class")=="calyx")
        obstacle(calyx.matrix_world.translation,self.materials["stem"])
        bpy.context.view_layer.update()
        original=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,near_contact_distance=0)
        self.assertGreater(original["physical_collision_count"],0)
        # A leaf-only allocation must leave the reproductive fixture untouched.
        skip=repair_size_preserving_poses(plant,self.materials,instance_id="fixture",world_from_local=transform,max_passes=1,max_trials_per_organ=56,max_seconds=60,repair_clearance=False,organ_kinds=("leaf",))
        self.assertFalse(skip['adjustments'])
        self.assertEqual(before,pose_invariant_manifest(plant))
        report=repair_size_preserving_poses(plant,self.materials,instance_id="fixture",world_from_local=transform,max_passes=1,max_trials_per_organ=56,max_seconds=60,repair_clearance=False,organ_kinds=("reproductive",))
        self.assertEqual(report['searched_organ_kinds'],['reproductive'])
        self.assertFalse(report['repair_positive_interorgan_clearance'])
        self.assertTrue(report["adjustments"])
        self.assertEqual(before,pose_invariant_manifest(plant))
        fruits=[o for o in bpy.context.scene.objects if o.get("uchuva_organ_kind")=="fruit"]
        self.assertEqual(len(fruits),1)
        self.assertTrue(fruits[0].hide_render)
        current=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,near_contact_distance=0)
        self.assertLess(current["physical_collision_count"],original["physical_collision_count"])
        # Rebuilding from the serialized angles must reproduce the accepted audit.
        objects=[o for o in bpy.context.scene.objects if o.get("uchuva_plant_id")=="fixture"]
        _remove_pose_objects(objects)
        plant=Plant.from_dict(plant.to_dict())
        build_geometry_from_morphology(plant,self.materials,instance_id="fixture",position=(2,3,4),rotation_deg=.4*180/3.141592653589793,add_ground=False)
        bpy.context.view_layer.update()
        rebuilt=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,near_contact_distance=0)
        self.assertEqual((current["physical_collision_count"],current["clearance_violation_count"]),
                         (rebuilt["physical_collision_count"],rebuilt["clearance_violation_count"]))
        if pendulous:
            from uchuva_lsystem.blender_reproductive_orientation import audit_calyx_orientation
            from uchuva_lsystem.scene import CultivationScene, PlantInstance
            layout = CultivationScene('fixture', 'fixture', 1,
                plant_instances=[PlantInstance('fixture', 1, position=(2,3,4), rotation_deg=.4*180/3.141592653589793)])
            audit = audit_calyx_orientation([plant], layout, list(bpy.context.scene.objects))
            self.assertEqual(audit['checked_count'], 1)
            self.assertEqual(audit['status'], 'valid', audit)
            calyx=next(o for o in bpy.context.scene.objects if o.get('uchuva_semantic_class')=='calyx')
            calyx.rotation_euler.x += 1.
            bpy.context.view_layer.update()
            self.assertEqual(audit_calyx_orientation([plant], layout, list(bpy.context.scene.objects))['status'], 'invalid')

    def test_pendulous_reproductive_templates_and_post_repair_gravity_audit(self):
        self.test_reproductive_templates_exact_with_instance_transform(pendulous=True)

    def test_gravity_frame_near_vertical_regression_without_relaxing_audit(self):
        from uchuva_lsystem.blender_reproductive_orientation import gravity_axis_rotation, audit_calyx_orientation
        from uchuva_lsystem.reproductive_orientation import KEY, POLICY, organ_direction
        from uchuva_lsystem.scene import CultivationScene, PlantInstance
        nodes, segments = [], []
        for i, tilt in enumerate((0., .0001, .069596, .1, 25.)):
            for azimuth in (0., 81.221324, 179., 270.):
                for sign in (-1, 1):
                    import math
                    a, t = math.radians(azimuth), math.radians(tilt)
                    direction=Vector((math.sin(t)*math.cos(a),math.sin(t)*math.sin(a),sign*math.cos(t)))
                    matrix=gravity_axis_rotation(direction).to_euler().to_matrix()
                    self.assertLess((matrix@Vector((0,0,1))-direction).length,1e-6)
            name=f'near_vertical_{i}';node='node_'+name
            unit=ReproductiveUnit(name,node,'mature_fruit_with_calyx',Pedicel(name+'_pedicel',node,2,35,0),
                calyx=Calyx(name+'_calyx',3,1,openness=0),fruit=Fruit(name+'_fruit',.7,'ripe','hidden'),
                provenance={KEY:dict(policy=POLICY,frame='plant_gravity_down',inclination_from_down_deg=tilt,
                    azimuth_deg=81.221324,inclination_bounds_deg=[0.,25.])})
            nodes.append(Node(node,i,0,i,reproductive_unit=unit))
            segments.append(Internode('segment_'+name,0,30,.1))
        plant=Plant('fixture','fixture',1,'test','test',axes=[Axis('axis',0,internodes=segments,nodes=nodes)])
        build_geometry_from_morphology(plant,self.materials,instance_id='fixture',position=(-8,0,-.0548095703125),rotation_deg=324,add_ground=False)
        bpy.context.view_layer.update()
        layout=CultivationScene('fixture','fixture',1,plant_instances=[PlantInstance('fixture',1,position=(-8,0,-.0548095703125),rotation_deg=324)])
        audit=audit_calyx_orientation([plant],layout,list(bpy.context.scene.objects))
        self.assertEqual(audit['checked_count'],5)
        self.assertEqual(audit['status'],'valid',audit)

    def test_leaf_trial_exception_restores_tree_and_releases_temporary_scene_meshes(self):
        leaf=Leaf("leaf","node",8,5,2,insertion_angle_deg=60,azimuth_deg=0,
                  provenance={"insertion_frame":"local_cone_v2"})
        plant=Plant("fixture","fixture",1,"test","test",axes=[Axis("axis",0,internodes=[Internode("segment",0,30,.1)],nodes=[Node("node",0,0,0,leaf=leaf)])])
        build_geometry_from_morphology(plant,self.materials,instance_id="fixture",add_ground=False)
        bpy.context.view_layer.update()
        blade=next(o for o in bpy.context.scene.objects if o.get("uchuva_organ_id")=="leaf")
        points=[blade.matrix_world @ Vector(v) for v in blade.bound_box]
        obstacle(sum(points,Vector())/len(points),self.materials["stem"])
        bpy.context.view_layer.update()
        before=plant.to_dict()
        inventory=(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.scenes))
        from uchuva_lsystem.blender_geometry import _create_leaf_at_node
        def failing(*args,**kwargs):
            _create_leaf_at_node(*args,**kwargs)
            raise RuntimeError("injected after leaf allocation")
        with patch("uchuva_lsystem.blender_geometry._create_leaf_at_node",side_effect=failing):
            with self.assertRaisesRegex(RuntimeError,"injected"):
                repair_size_preserving_poses(plant,self.materials,instance_id="fixture",max_passes=1,max_seconds=60)
        self.assertEqual(plant.to_dict(),before)
        self.assertEqual(inventory,(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.scenes)))

    def ground_fixture(self,heights=(0,0,0,0),hole=False,location=(0,0,2),halfsize=.02):
        mesh=bpy.data.meshes.new("terrain_fixture")
        mesh.from_pydata([(-2,-2,heights[0]),(2,-2,heights[1]),(2,2,heights[2]),(-2,2,heights[3])],[],
                        [(0,1,2)] if hole else [(0,1,2),(0,2,3)])
        terrain=bpy.data.objects.new("uchuva_terrain_agricultural",mesh)
        bpy.context.scene.collection.objects.link(terrain)
        obj=obstacle(location,self.materials["stem"])
        obj.scale=(halfsize/.4,halfsize/.025,halfsize/.4)
        obj["uchuva_semantic_class"]="leaf"
        obj["uchuva_plant_role"]="foreground"
        obj["uchuva_plant_id"]="fixture"
        bpy.context.scene.unit_settings.scale_length=.125
        bpy.context.view_layer.update()
        ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh=ev.to_mesh()
        try:
            mesh.calc_loop_triangles()
            vertices=[ev.matrix_world @ v.co for v in mesh.vertices]
            triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
        finally:
            ev.to_mesh_clear()
        bounds=tuple(tuple(fn(v[i] for v in vertices) for i in range(3)) for fn in (min,max))
        return _GroundPenalty(terrain,.001),[{"obj":obj,"vertices":vertices,"triangles":triangles,"bounds":bounds}]

    def test_nonplanar_ground_fast_path_requires_complete_xy_coverage(self):
        ground,group=self.ground_fixture(heights=(0,.2,.6,.1))
        self.assertTrue(ground.rectangular_coverage)
        self.assertEqual(ground.score(group),(0,0,0))
        self.assertEqual(ground.fast_above_count,1)
        self.assertEqual(ground.ray_count,0)

    def test_fully_buried_organ_is_detected_without_surface_crossing(self):
        ground,group=self.ground_fixture(heights=(0,.2,.6,.1),location=(0,0,-.5))
        self.assertEqual(ground.score(group),(1,0,0))

    def test_missing_ground_coverage_is_blocking_even_far_above_surface(self):
        ground,group=self.ground_fixture(hole=True,location=(-1,1,2))
        self.assertFalse(ground.rectangular_coverage)
        self.assertEqual(ground.score(group),(0,0,1))

    def test_positive_clearance_uses_metres_not_blender_units(self):
        ground,group=self.ground_fixture(location=(0,0,.024))
        self.assertAlmostEqual(ground.required_bu,.008)
        self.assertEqual(ground.score(group),(0,1,0))

    def test_ground_aware_repair_resolves_buried_calyx_without_extending_pedicel(self):
        from uchuva_lsystem.blender_environment import audit_plant_ground_clearance
        unit=ReproductiveUnit("unit","node","mature_fruit_with_calyx",Pedicel("unit_pedicel","node",2,35,0),
            calyx=Calyx("unit_calyx",3,1,openness=0,covers_fruit_fraction=1),fruit=Fruit("unit_fruit",.7,"ripe","hidden"))
        plant=Plant("fixture","fixture",1,"test","test",axes=[Axis("axis",0,internodes=[Internode("segment",0,2,.1)],nodes=[Node("node",0,0,0,reproductive_unit=unit)])])
        invariant=pose_invariant_manifest(plant)
        build_geometry_from_morphology(plant,self.materials,instance_id="fixture",add_ground=False)
        mesh=bpy.data.meshes.new("terrain_fixture")
        mesh.from_pydata([(-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0)],[],[(0,1,2),(0,2,3)])
        terrain=bpy.data.objects.new("uchuva_terrain_agricultural",mesh)
        bpy.context.scene.collection.objects.link(terrain)
        bpy.context.scene.unit_settings.scale_length=.125
        bpy.context.view_layer.update()
        initial=audit_plant_ground_clearance(seed=0)
        self.assertGreater(initial["physical_collision_count"],0)
        report=repair_size_preserving_poses(plant,self.materials,instance_id="fixture",max_passes=1,max_seconds=60,ground_clearance_m=.001)
        self.assertTrue(report["adjustments"])
        self.assertEqual(invariant,pose_invariant_manifest(plant))
        final=audit_plant_ground_clearance(seed=0)
        self.assertEqual(final["physical_collision_count"],0)
        self.assertEqual(final["clearance_violation_count"],0)
        self.assertEqual(final["coverage_failure_count"],0)

    def test_fine_five_degree_pose_escapes_a_coarse_grid_plateau(self):
        unit=ReproductiveUnit("unit","node","mature_fruit_with_calyx",Pedicel("unit_pedicel","node",2,35,5),
            calyx=Calyx("unit_calyx",3,1,openness=0,covers_fruit_fraction=1),fruit=Fruit("unit_fruit",.7,"ripe","hidden"))
        plant=Plant("fixture","fixture",1,"test","test",axes=[Axis("axis",0,internodes=[Internode("segment",0,30,.1)],nodes=[Node("node",0,0,0,reproductive_unit=unit)])])
        build_geometry_from_morphology(plant,self.materials,instance_id="fixture",add_ground=False)
        bpy.context.view_layer.update()
        # A bounded synthetic corridor encloses exactly the evaluated five-degree
        # pose. Parallel surfaces outside it prevent jumping through a wall to an
        # untested external cavity; this is a mesh regression, not a crop scene.
        points=[]
        for obj in bpy.context.scene.objects:
            if obj.get("uchuva_reproductive_instance_id")=="fixture:unit" and obj.get("uchuva_semantic_class") in {"calyx","stem"}:
                ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
                points.extend(ev.matrix_world@v.co for v in mesh.vertices);ev.to_mesh_clear()
        bounds=[(min(v[d] for v in points),max(v[d] for v in points)) for d in range(3)]
        for axis in range(3):
            for side in (-1,1):
                edge=bounds[axis][0 if side<0 else 1]
                for i in range(50):
                    coordinate=edge+side*(.0201+i*.008)
                    other=[d for d in range(3) if d!=axis]
                    vertices=[]
                    for u,v in ((-4,-4),(4,-4),(4,4),(-4,4)):
                        point=[0.,0.,0.];point[axis]=coordinate;point[other[0]]=u;point[other[1]]=v
                        vertices.append(point)
                    mesh=bpy.data.meshes.new("corridor_plane")
                    mesh.from_pydata(vertices,[],[(0,1,2,3)])
                    obj=bpy.data.objects.new("corridor_plane",mesh)
                    bpy.context.scene.collection.objects.link(obj)
                    obj["uchuva_plant_role"]="support"
                    obj["uchuva_semantic_class"]="background"
        _remove_pose_objects([o for o in bpy.context.scene.objects if o.get("uchuva_plant_id")=="fixture"])
        unit.pedicel.azimuth_deg=0
        build_geometry_from_morphology(plant,self.materials,instance_id="fixture",add_ground=False)
        bpy.context.view_layer.update()
        initial=plant.to_dict()
        coarse=repair_size_preserving_poses(plant,self.materials,instance_id="fixture",max_passes=1,max_trials_per_organ=112,max_seconds=60)
        self.assertFalse(coarse["adjustments"],"Fixture must expose a genuine coarse plateau")
        fine=repair_size_preserving_poses(plant,self.materials,instance_id="fixture",max_passes=1,max_trials_per_organ=112,max_seconds=60,fine_angular_step_deg=5)
        self.assertTrue(fine["adjustments"])
        self.assertEqual(fine["adjustments"][-1]["search_phase"],"fine")
        self.assertEqual(fine["adjustments"][-1]["after_deg"],[5.,35.])
        self.assertEqual(fine["adjustments"][-1]["remaining_pairs"],[0,0])
        self.assertLessEqual(fine["candidate_count"],112)
        self.assertEqual(pose_invariant_manifest(Plant.from_dict(initial)),pose_invariant_manifest(plant))
        history=unit.pedicel.provenance["mesh_feedback_pose_history_v2"]
        self.assertEqual(history[-1],unit.pedicel.provenance["mesh_feedback_pose_v2"])
        # The optional absolute lattice must resolve the same real mesh corridor
        # without relying on the fine-search phase or changing anatomy.
        _remove_pose_objects([o for o in bpy.context.scene.objects if o.get("uchuva_plant_id")=="fixture"])
        plant=Plant.from_dict(initial)
        build_geometry_from_morphology(plant,self.materials,instance_id="fixture",add_ground=False)
        bpy.context.view_layer.update()
        dense=repair_size_preserving_poses(plant,self.materials,instance_id="fixture",max_passes=1,
            max_trials_per_organ=2048,max_seconds=60,dense_reproductive_step_deg=5,clearance_tiebreak=True)
        self.assertTrue(dense["adjustments"])
        self.assertEqual(dense["adjustments"][-1]["search_phase"],"dense")
        self.assertEqual(dense["adjustments"][-1]["remaining_pairs"],[0,0])
        self.assertLessEqual(dense["candidate_count"],2048)
        self.assertEqual(pose_invariant_manifest(Plant.from_dict(initial)),pose_invariant_manifest(plant))


if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PoseIntegration))
    if not result.wasSuccessful():
        raise RuntimeError("Pose repair probe failed")
