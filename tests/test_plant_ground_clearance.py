"""Pure tests for precise basal-contact geometry; integration also runs in Blender."""
import unittest

from uchuva_lsystem.blender_environment import (
    _ground_basal_contact_properties,
    _ground_point_in_basal_zone,
    _ground_triangle_contact_points,
)


class PlantGroundContactTests(unittest.TestCase):
    def test_only_initial_main_axis_has_declared_basal_contact(self):
        properties = dict(uchuva_semantic_class="stem", uchuva_organ_kind="axis_segment",
                          uchuva_axis_order=0, uchuva_internode_index=0,
                          uchuva_axis_parent_node_id="", uchuva_node_start_id="")
        self.assertTrue(_ground_basal_contact_properties(properties))
        for name,value in (("uchuva_semantic_class","leaf"), ("uchuva_organ_kind","pedicel"),
                           ("uchuva_axis_order",1), ("uchuva_internode_index",1),
                           ("uchuva_axis_parent_node_id","node1"), ("uchuva_node_start_id","node1")):
            with self.subTest(name=name):
                self.assertFalse(_ground_basal_contact_properties({**properties,name:value}))

    def test_contact_zone_is_local_not_entire_stem_or_ground_plane(self):
        self.assertTrue(_ground_point_in_basal_zone((.01,0,0),(0,0,0),.02))
        self.assertFalse(_ground_point_in_basal_zone((.03,0,0),(0,0,0),.02))
        self.assertFalse(_ground_point_in_basal_zone((0,0,.03),(0,0,0),.02))
        self.assertFalse(_ground_point_in_basal_zone((0,0,0),None,.02))

    def test_localizes_actual_triangle_crossing(self):
        ground=[(-1,-1,0),(1,-1,0),(0,1,0)]
        stem=[(0,0,-.1),(.01,0,.1),(-.01,0,.1)]
        points=_ground_triangle_contact_points(stem,ground)
        self.assertGreaterEqual(len(points),2)
        self.assertTrue(all(abs(p[2])<1e-8 for p in points))
        self.assertTrue(all(_ground_point_in_basal_zone(p,(0,0,0),.02) for p in points))

    def test_contact_beyond_anchor_is_not_exempt(self):
        ground=[(-1,-1,0),(1,-1,0),(0,1,0)]
        stem=[(.2,0,-.1),(.21,0,.1),(.19,0,.1)]
        points=_ground_triangle_contact_points(stem,ground)
        self.assertTrue(points)
        self.assertTrue(all(not _ground_point_in_basal_zone(p,(0,0,0),.02) for p in points))

    def test_coplanar_or_separate_triangles_have_no_localization_exemption(self):
        ground=[(-1,-1,0),(1,-1,0),(0,1,0)]
        self.assertEqual(_ground_triangle_contact_points(ground,ground),[])
        self.assertEqual(_ground_triangle_contact_points([(0,0,1),(.1,0,1),(0,.1,1)],ground),[])


if __name__ == "__main__":
    unittest.main()
