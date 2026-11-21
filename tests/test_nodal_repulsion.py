"""Pure growth-frame tests; admission still requires an evaluated mesh audit."""
import math
import unittest
from unittest.mock import patch
from copy import deepcopy
from uchuva_lsystem.morphology import Plant,Axis,Internode,Node,Leaf,Pedicel,ReproductiveUnit,Calyx,Fruit
from uchuva_lsystem.nodal_repulsion import (KEY,initialize_growth_poses,protected_anatomy,ProxyIndex,
    coarsen_stem_guides,branch_candidate,pitched,resolve_nodal_repulsion)
from uchuva_lsystem.collisions import build_scene_proxies
from uchuva_lsystem.reproductive_orientation import assign_reproductive_orientation,organ_direction
from uchuva_lsystem.parameters import get_morphology_parameters


def fixture():
    def branch(name,order,parent=None):
        axis=Axis(name,order,parent_node_id=parent,branch_angle_deg=35,azimuth_deg=50,
            provenance={'branch_frame_v140':True,'continuous_tangent_v140':True})
        for i in range(3):
            node=f'{name}_node_{i}'
            leaf=Leaf(node+'_leaf',node,7,4,2,insertion_angle_deg=65,azimuth_deg=20,
                provenance={'insertion_frame':'local_cone_v2'})
            axis.internodes.append(Internode(f'{name}_internode_{i}',order,10,.1,bend_angle_deg=2))
            unit=ReproductiveUnit(node+'_reproductive_unit',node,'mature_fruit_with_calyx',
                Pedicel(node+'_pedicel',node,2,35,120),calyx=Calyx(node+'_calyx',3,1),fruit=Fruit(node+'_fruit',.7,'ripe','hidden'))
            axis.nodes.append(Node(node,order,i,i,leaf=leaf,reproductive_unit=unit))
        return axis
    root=branch('axis_0',0);child=branch('axis_0_branch_0',1,root.nodes[1].id)
    child.child_axes.append(branch('axis_0_branch_0_branch_0',2,child.nodes[1].id));root.child_axes.append(child)
    plant=Plant('fixture','fixture',1,'fixture','fixture',axes=[root])
    assign_reproductive_orientation(plant,get_morphology_parameters('trained_trellis_pendulous_audit_v7'))
    return plant


class NodalGrowthRepulsion(unittest.TestCase):
    def test_initialization_preserves_full_anatomy_and_serializes(self):
        plant=fixture();before=protected_anatomy(plant);initialize_growth_poses(plant)
        self.assertEqual(before,protected_anatomy(plant))
        self.assertEqual(plant.to_dict(),Plant.from_dict(plant.to_dict()).to_dict())

    def test_branch_bone_moves_entire_distal_module_and_matches_full_replay(self):
        plant=fixture();scene=initialize_growth_poses(plant);frames={};bones={}
        proxies=coarsen_stem_guides(build_scene_proxies(scene,{'growth':plant},frame_output=frames,bone_output=bones))
        index=ProxyIndex(proxies);axis=plant.axes[0].child_axes[0];part=axis.internodes[0]
        before=protected_anatomy(plant);part.provenance[KEY]['direction']=list(pitched(part.provenance[KEY]['direction'],-8))
        trial,rigid,delta,nodes,parts,reframe=branch_candidate(axis,0,part.provenance[KEY]['direction'],frames['growth'],bones['growth'],index)
        self.assertLess(delta[2],0);self.assertEqual(len(nodes),6)
        expected={p.proxy_id:p for p in coarsen_stem_guides(build_scene_proxies(scene,{'growth':plant}))}
        actual={p.proxy_id:p for p in proxies};actual.update({p.proxy_id:p for p in trial})
        self.assertEqual(set(expected),set(actual))
        for identity,p in expected.items():
            other=actual[identity]
            for field in ('center','start','end','half_extents'):
                if getattr(p,field) is not None:
                    for a,b in zip(getattr(p,field),getattr(other,field)):self.assertAlmostEqual(a,b,places=10,msg=(identity,field))
            self.assertAlmostEqual(p.radius,other.radius,places=10,msg=identity)
        self.assertEqual(before,protected_anatomy(plant))

    def test_pedicel_motion_does_not_rotate_calyx_gravity_axis(self):
        plant=fixture();initialize_growth_poses(plant);u=plant.axes[0].nodes[0].reproductive_unit
        before=organ_direction(u);u.pedicel.provenance[KEY]['direction']=[0,.9,.4358898943540673]
        self.assertEqual(before,organ_direction(u))

    def test_tiny_search_retains_organs_and_does_not_claim_physical_validity(self):
        plant=fixture();before=protected_anatomy(plant)
        result=resolve_nodal_repulsion(plant,sweeps=1,max_seconds=.1)
        self.assertEqual(before,protected_anatomy(plant))
        self.assertEqual(result['physical_validity'],'not established')
        self.assertEqual(result['direction_priority'],['lower','raise','lateral'])

    def test_failed_checkpoint_rolls_back_the_whole_tree(self):
        plant=fixture();before=deepcopy(plant.to_dict())
        with self.assertRaisesRegex(RuntimeError,'fixture failure'):
            resolve_nodal_repulsion(plant,sweeps=1,max_seconds=10,
                checkpoint=lambda *args:(_ for _ in ()).throw(RuntimeError('fixture failure')))
        self.assertEqual(plant.to_dict(),before)

    def test_new_preset_keeps_original_architecture_and_calls_growth_before_capture(self):
        from uchuva_lsystem.grammar import generate_morphology_tree
        legacy=generate_morphology_tree(2026102600,preset_name='trained_trellis_pendulous_audit_v7',phenology_model='literature_cohort_v1')
        with patch('uchuva_lsystem.nodal_repulsion.resolve_nodal_repulsion') as solve:
            current=generate_morphology_tree(2026102600,preset_name='trained_trellis_nodal_repulsion_v8',phenology_model='literature_cohort_v1')
            solve.assert_called_once()
        self.assertEqual(protected_anatomy(legacy),protected_anatomy(current))
        pending=generate_morphology_tree(2026102600,preset_name='trained_trellis_nodal_repulsion_v8',phenology_model='literature_cohort_v1',resolve_growth=False)
        self.assertEqual(protected_anatomy(pending),protected_anatomy(legacy))
        self.assertTrue(pending.metadata['nodal_repulsion_pending'])

    def test_validator_rejects_nonfinite_or_unbounded_recorded_pose(self):
        from uchuva_lsystem.validation import validate_morphology_tree
        plant=fixture();initialize_growth_poses(plant)
        plant.axes[0].nodes[0].leaf.provenance[KEY]['direction']=[float('nan'),0,1]
        report=validate_morphology_tree(plant,stage='adapted')
        self.assertTrue(any(e['category']=='nodal_growth_pose' for e in report['errors']))

    def test_leaf_candidates_lower_before_raising(self):
        from uchuva_lsystem.nodal_repulsion import joint_candidates,joint_direction
        candidates=joint_candidates((0,20),joint_direction(0,20),kind='leaf',limit=300)
        rising=False
        for yaw,elevation in candidates:
            if elevation>20:rising=True
            if rising:self.assertGreaterEqual(elevation,20)

    def test_historical_growth_cannot_prune_new_nodal_trees(self):
        from uchuva_lsystem.growth import coordinate_synchronous_growth
        from uchuva_lsystem.cultivation import adapt_cultivation_morphologies
        plant=fixture();scene=initialize_growth_poses(plant)
        for operation in (coordinate_synchronous_growth,adapt_cultivation_morphologies):
            with self.assertRaisesRegex(ValueError,'historical pose contract'):
                operation(scene,{'growth':plant})

    def test_expanded_pedicel_search_is_explicit_hashed_and_preserves_anatomy(self):
        from uchuva_lsystem.nodal_repulsion import revise_pedicel_mobility,joint_direction,joint_angles
        from uchuva_lsystem.validation import validate_morphology_tree
        plant=fixture();initialize_growth_poses(plant);before=protected_anatomy(plant)
        u=plant.axes[0].nodes[0].reproductive_unit;gravity=organ_direction(u)
        revise_pedicel_mobility(plant,150,reason='Fixture of an explicit unmeasured search revision')
        azimuth,elevation=joint_angles(u.pedicel.provenance[KEY]['input_direction'])
        u.pedicel.provenance[KEY]['direction']=list(joint_direction(azimuth,elevation+100))
        self.assertEqual(before,protected_anatomy(plant));self.assertEqual(gravity,organ_direction(u))
        report=validate_morphology_tree(plant,stage='adapted')
        self.assertFalse(any(e['category']=='nodal_growth_pose' for e in report['errors']))
        plant.metadata['nodal_mobility_revisions'][-1]['policy']['reason']='Changed without updating hash'
        report=validate_morphology_tree(plant,stage='adapted')
        self.assertTrue(any(e['category']=='nodal_growth_pose' for e in report['errors']))

    def test_local_two_bone_joint_preserves_lengths_and_distal_anchor(self):
        from uchuva_lsystem.nodal_repulsion import local_joint_candidates
        plant=fixture();scene=initialize_growth_poses(plant);bones={};frames={}
        build_scene_proxies(scene,{'growth':plant},bone_output=bones,frame_output=frames)
        axis=plant.axes[0].child_axes[0];before=protected_anatomy(plant)
        candidates=local_joint_candidates(axis,1,bones['growth'])
        self.assertTrue(candidates)
        proposal=candidates[0]
        axis.internodes[1].provenance[KEY]['direction']=list(proposal['first_direction'])
        axis.internodes[2].provenance[KEY]['direction']=list(proposal['second_direction'])
        updated={};build_scene_proxies(scene,{'growth':plant},bone_output=updated)
        for left,right in zip(updated['growth'][axis.internodes[2].id]['end'],bones['growth'][axis.internodes[2].id]['end']):
            self.assertAlmostEqual(left,right,places=10)
        for part in axis.internodes[1:3]:
            state=updated['growth'][part.id]
            self.assertAlmostEqual(sum((a-b)**2 for a,b in zip(state['end'],state['start']))**.5,part.length_cm*.08,places=10)
        self.assertEqual(before,protected_anatomy(plant))

    def test_counterbend_preserves_both_lengths_and_has_no_distal_sideways_drift(self):
        from uchuva_lsystem.nodal_repulsion import counterbend_candidates,sub,unit,cross,dot
        plant=fixture();scene=initialize_growth_poses(plant);bones={}
        build_scene_proxies(scene,{'growth':plant},bone_output=bones)
        axis=plant.axes[0].child_axes[0];before=protected_anatomy(plant)
        proposals=counterbend_candidates(axis,0,bones['growth'],bearing=(0,0,-1))
        self.assertTrue(proposals)
        a=bones['growth'][axis.internodes[0].id]['start'];old_end=bones['growth'][axis.internodes[1].id]['end']
        growth=unit(sub(old_end,a));proposal=proposals[0]
        for part,direction in zip(axis.internodes, (proposal['first_direction'],proposal['second_direction'])):
            part.provenance[KEY]['direction']=list(direction)
        updated={};build_scene_proxies(scene,{'growth':plant},bone_output=updated)
        end=updated['growth'][axis.internodes[1].id]['end']
        sideways=cross(sub(end,old_end),growth)
        self.assertLess(dot(sideways,sideways),1e-18)
        self.assertAlmostEqual(dot(sub(old_end,end),growth),proposal['axial_shortening_bu'],places=10)
        for part in axis.internodes[:2]:
            state=updated['growth'][part.id]
            self.assertAlmostEqual(sum((a-b)**2 for a,b in zip(state['end'],state['start']))**.5,part.length_cm*.08,places=10)
        self.assertEqual(before,protected_anatomy(plant))

    def test_gravity_restoration_is_more_downward_only_and_preserves_anatomy(self):
        from uchuva_lsystem.nodal_repulsion import restore_calyx_toward_gravity
        from uchuva_lsystem.reproductive_orientation import pedicel_direction
        plant=fixture();initialize_growth_poses(plant);before=protected_anatomy(plant)
        u=plant.axes[0].nodes[0].reproductive_unit;original_pose=deepcopy(u.provenance['reproductive_orientation'])
        initial=organ_direction(u);pd=pedicel_direction(u)
        restore_calyx_toward_gravity(plant,[u.id],fraction=.5)
        self.assertLess(organ_direction(u)[2],initial[2])
        self.assertEqual(pd,pedicel_direction(u));self.assertEqual(before,protected_anatomy(plant))
        restore_calyx_toward_gravity(plant,[u.id],fraction=1)
        self.assertEqual(organ_direction(u),(0,0,-1));self.assertEqual(original_pose,u.provenance['reproductive_orientation'])
        u.provenance[KEY]['calyx_direction']=[1,0,0]
        with self.assertRaises(ValueError):organ_direction(u)

    def test_unknown_gravity_unit_rejected_before_any_tree_change(self):
        from uchuva_lsystem.nodal_repulsion import restore_calyx_toward_gravity
        plant=fixture();before=deepcopy(plant.to_dict())
        identity=plant.axes[0].nodes[0].reproductive_unit.id
        with self.assertRaisesRegex(ValueError,'Unknown'):
            restore_calyx_toward_gravity(plant,[identity,'missing'])
        self.assertEqual(before,plant.to_dict())


if __name__=='__main__':unittest.main()
