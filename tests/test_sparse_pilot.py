"""Contracts that prevent silent geometry/label corruption in the 36-plant pilot."""
import importlib.util
from pathlib import Path
import unittest

from uchuva_lsystem.sparse_pilot import (SparseConfig, create_sparse_scene, marker_specs,
    class_for_grade, encode_rle, decode_rle, prepare_plant, attach_strings,
    sparse_morphology_parameters, walk_axes)
from uchuva_lsystem.scene import CultivationScene, create_cultivation_scene
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.blender_annotations import _instance_color


class SparsePilotTests(unittest.TestCase):
    def test_cached_calyx_uvs_keep_seam_and_cap_centers(self):
        from uchuva_lsystem.blender_geometry import _calyx_uv_coordinates
        polygons=((3,0,4,7),(12,0,3),(13,11,8))
        values=_calyx_uv_coordinates(2,4,12,13,polygons)
        self.assertEqual(values,(.75,0,1,0,1,.5,.75,.5,
                                 .875,0,1,0,.75,0,
                                 .875,1,.75,1,1,1))
        self.assertEqual(values,_calyx_uv_coordinates(2,4,12,13,polygons))

    def test_dense_crowns_increase_foliage_without_changing_field_spacing(self):
        counts = []
        for seed in (23092600,23092602,23092702,23092832,23092932):
            old = generate_morphology_tree(seed,get_morphology_parameters("trained_trellis"))
            dense = generate_morphology_tree(seed,sparse_morphology_parameters())
            counts.append((old.node_count(),dense.node_count()))
            self.assertGreater(dense.node_count(),3*old.node_count())
            self.assertEqual(dense.to_dict(),generate_morphology_tree(seed,sparse_morphology_parameters()).to_dict())
            prepare_plant(dense)
            self.assertTrue(all(110 <= n.leaf.insertion_angle_deg <= 155
                                for a in walk_axes(dense.axes) for n in a.nodes if n.leaf))
        self.assertGreater(sum(b for a,b in counts)/sum(a for a,b in counts),4)
        scene = create_sparse_scene(230926)
        self.assertEqual(len(scene.plant_instances),36)
        self.assertEqual(SparseConfig().plant_spacing_m,1.4)
        for marker in marker_specs(scene):
            self.assertEqual(marker["printed_faces"],"outward_only")
            self.assertEqual(marker["reverse_appearance"],"plain_opaque")
            self.assertGreater(marker["backing_thickness_m"],0)

    def test_bounded_collision_preview_preserves_organs_and_reports_skipped_search(self):
        from uchuva_lsystem.collisions import resolve_global_collisions
        scene = create_sparse_scene(1)
        scene.plant_instances = scene.plant_instances[:1]
        scene.support_system = None
        plant = prepare_plant(generate_morphology_tree(100,get_morphology_parameters("trained_trellis")))
        count = plant.node_count()
        result = resolve_global_collisions(scene,{"plant_00":plant},iterations=0,optimize_poses=False)
        self.assertEqual(plant.node_count(),count)
        self.assertEqual(result["pose_optimization"],"not_run_iterative_preview")
        self.assertEqual(result["leaf_calyx_micro_lift"]["status"],"not_run_iterative_preview")

    def test_grid_units_markers_and_roundtrip(self):
        scene = create_sparse_scene(5)
        self.assertEqual(scene.to_dict(), create_cultivation_scene(5, "sparse_overhead_strings_v1").to_dict())
        self.assertEqual(len(scene.plant_instances),36)
        self.assertEqual(len(set(p.position[0] for p in scene.plant_instances)),6)
        self.assertEqual(len(set(p.position[1] for p in scene.plant_instances)),6)
        self.assertEqual(scene.to_dict(), CultivationScene.from_dict(scene.to_dict()).to_dict())
        markers = marker_specs(scene)
        self.assertEqual([m["id"] for m in markers], list(range(72)))
        for front, back in zip(markers[::2],markers[1::2]):
            self.assertEqual(front["plant_id"],back["plant_id"])
            self.assertEqual(front["normal_world"],[0,-1,0])
            self.assertEqual(back["normal_world"],[0,1,0])
            self.assertAlmostEqual(back["center_world_m"][1]-front["center_world_m"][1],.36)
            self.assertAlmostEqual(front["center_world_m"][2]-.05-.02,.05)

    def test_grades_preserved_and_strings_attach_to_nodes(self):
        scene = create_sparse_scene(1)
        scene.plant_instances = scene.plant_instances[:1]
        plant = prepare_plant(generate_morphology_tree(100,get_morphology_parameters("trained_trellis")))
        self.assertEqual(Plant.from_dict(plant.to_dict()).to_dict(),plant.to_dict())
        attach_strings(scene,{"plant_00":plant})
        from uchuva_lsystem.growth import _node_frames
        frames = _node_frames(plant,scene.plant_instances[0])
        self.assertEqual(len(scene.support_system.ties),3)
        for tie, contact in zip(scene.support_system.ties,scene.support_system.contacts):
            self.assertEqual(tie.start,frames[contact.organ_id][0])
            self.assertEqual(tie.end[2],scene.support_system.lines[0].start[2])
        self.assertEqual([class_for_grade(i) for i in range(7)],[0,0,1,1,1,2,3])
        for bad in (-1,7,None,True):
            with self.assertRaises(ValueError): class_for_grade(bad)

    def test_lossless_rle_holes_components_and_edges(self):
        masks = [[[False]*6 for _ in range(5)], [[True]*6 for _ in range(5)],
                 [[True,True,False,False],[True,False,False,True],[True,True,False,True]]]
        spec = importlib.util.spec_from_file_location("export_sparse",Path(__file__).resolve().parents[1]/"scripts/export_sparse_pilot.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import numpy as np
        for mask in masks:
            self.assertEqual(mask,decode_rle(encode_rle(mask)))
            self.assertEqual(mask,decode_rle(module.numpy_rle(np.array(mask))))

    def test_palette_does_not_alias_after_200_instances(self):
        colors = [_instance_color(i) for i in range(4096)]
        self.assertEqual(len(set(colors)),4096)
        with self.assertRaises(ValueError): _instance_color(4096)

    def test_only_declared_nodal_string_contact_is_intentional(self):
        from uchuva_lsystem.blender_geometry import _declared_string_attachment
        support = {"uchuva_support_attachment_node_id":"axis_0_node_2","uchuva_plant_id":"p"}
        organ = {"uchuva_semantic_class":"stem","uchuva_plant_id":"p",
                 "uchuva_axis_id":"axis_0","uchuva_internode_index":2,"uchuva_organ_kind":"axis_segment"}
        self.assertTrue(_declared_string_attachment(support,organ))
        self.assertFalse(_declared_string_attachment(support,{**organ,"uchuva_plant_id":"other"}))
        self.assertFalse(_declared_string_attachment(support,{**organ,"uchuva_semantic_class":"calyx"}))
        self.assertFalse(_declared_string_attachment(support,{**organ,"uchuva_internode_index":0}))

    def test_invalid_dimensions(self):
        with self.assertRaises(ValueError): SparseConfig(row_spacing_m=float("nan"))
        with self.assertRaises(ValueError): SparseConfig(rows=2)

    def test_marker_pose_uses_metric_camera_frame(self):
        import cv2
        import numpy as np
        spec = importlib.util.spec_from_file_location("export_sparse",Path(__file__).resolve().parents[1]/"scripts/export_sparse_pilot.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        image = np.full((480,640,3),255,np.uint8)
        pattern = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100),71,100)
        image[190:290,270:370] = pattern[:,:,None]
        transform = np.diag([1.,-1.,-1.,1.])
        transform[2,3] = .8
        metadata = {"K":[[800,0,320],[0,800,240],[0,0,1]], "markers":[
            {"id":71,"side_m":.1,"T_camera_marker_m":transform.tolist(),"face":"back",
             "plant_id":"plant_35","in_frame":True,"front_facing":True}]}
        record = module.evaluate_aruco(image,metadata)["markers"][0]
        self.assertTrue(record["detected"])
        self.assertLess(record["selected"]["translation_error_m"],.01)
        self.assertLess(record["selected"]["rotation_error_deg"],2)


if __name__ == "__main__": unittest.main()
