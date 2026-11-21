import unittest
from uchuva_lsystem.blender_geometry import _node_attaches_to_axis_object, _mesh_collision_exempt


class MeshAttachmentTopologyTest(unittest.TestCase):
    def test_annotation_writer_accepts_explicit_topology(self):
        from uchuva_lsystem.blender_annotations import tag_annotation_object
        obj = {}
        tag_annotation_object(obj, 'stem', node_start_id='a', node_end_id='b')
        self.assertEqual(obj['uchuva_node_start_id'], 'a')
        self.assertEqual(obj['uchuva_node_end_id'], 'b')

    def test_explicit_node_ids_override_naming(self):
        obj = dict(uchuva_node_start_id='basal-2', uchuva_node_end_id='fork-A',
                   uchuva_axis_id='legacy', uchuva_internode_index=0, uchuva_organ_kind='axis_segment')
        self.assertTrue(_node_attaches_to_axis_object('fork-A', obj))
        self.assertFalse(_node_attaches_to_axis_object('legacy_node_0', obj))
        self.assertFalse(_node_attaches_to_axis_object('', obj))

    def test_branch_joint_but_not_foreign_node_or_calyx(self):
        parent = dict(uchuva_plant_id='p', uchuva_semantic_class='stem',
                      uchuva_organ_kind='axis_segment', uchuva_axis_id='base',
                      uchuva_internode_index=2, uchuva_node_start_id='a', uchuva_node_end_id='fork')
        child = dict(uchuva_plant_id='p', uchuva_semantic_class='stem',
                     uchuva_organ_kind='axis_segment', uchuva_axis_id='child',
                     uchuva_internode_index=0, uchuva_axis_parent_node_id='fork')
        self.assertTrue(_mesh_collision_exempt(parent, child))
        child['uchuva_axis_parent_node_id'] = 'elsewhere'
        self.assertFalse(_mesh_collision_exempt(parent, child))
        child.update(uchuva_axis_parent_node_id='fork', uchuva_semantic_class='calyx', uchuva_organ_id='fruit_calyx')
        self.assertFalse(_mesh_collision_exempt(parent, child))

    def test_historical_fallback(self):
        self.assertTrue(_node_attaches_to_axis_object('axis_node_2',
            dict(uchuva_axis_id='axis', uchuva_internode_index=3, uchuva_organ_kind='axis_segment')))
