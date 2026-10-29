"""Pure nodal axis repair: topology/size preservation and mandatory mesh review."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from uchuva_lsystem.axis_pose_repair import (
    axis_angular_candidates, axis_pose_invariant_manifest, confirmed_axis_relations,
    local_pose_distance_deg, repair_axis_poses, _with_apex_proxies,
    confirmed_organ_axis_constraints,
)
from uchuva_lsystem.collisions import build_scene_proxies
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.morphology import Axis,Internode,Node,Plant,ReproductiveUnit,Pedicel,Calyx
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.provenance import parameter_snapshot_sha256
from uchuva_lsystem.scene import PlantInstance,CultivationScene
from uchuva_lsystem.validation import _validate_registered_axis_pose


def fixture():
    params=get_morphology_parameters("trained_trellis_lower_crown_audit_v6")
    params["branching"]["branch_angle_deg_by_order"]["1"].update(min=20.,max=85.)
    root=Axis("axis_0",0)
    for i in range(6):
        root.internodes.append(Internode(f"axis_0_internode_{i}",0,3.,.1))
        root.nodes.append(Node(f"axis_0_node_{i}",0,i,i))
    for i,(position,angle) in enumerate(((2,30.),(3,80.))):
        axis=Axis(f"axis_0_branch_{i}",1,parent_node_id=root.nodes[position].id,
                  branch_angle_deg=angle,azimuth_deg=0.,
                  provenance={"branch_frame_v140":True,"branch_direction_frame":"local_cone_v1"})
        for n in range(4):
            axis.internodes.append(Internode(f"{axis.id}_internode_{n}",1,2.,.06))
            axis.nodes.append(Node(f"{axis.id}_node_{n}",1,n,n))
        root.child_axes.append(axis)
    plant=Plant("test","test",1,"fixture","fixture",axes=[root],metadata={
        "model_stage":"generated","effective_parameters":params,
        "effective_parameters_sha256":parameter_snapshot_sha256(params)})
    objects={f"segment_{i}":{"properties":{"uchuva_organ_kind":"axis_segment",
             "uchuva_axis_id":axis.id,"uchuva_plant_id":"fixture","uchuva_internode_index":1}}
             for i,axis in enumerate(root.child_axes)}
    pairs=[{"object_a":"segment_0","object_b":"segment_1","classification":"physical_collision"}]
    return plant,objects,pairs


def run(plant,objects,pairs,**kwargs):
    return repair_axis_poses(plant,instance=PlantInstance("fixture",1),
                             intersection_pairs=pairs,object_inventory=objects,**kwargs)


class BoundedAxisRepair(unittest.TestCase):
    def test_measured_flower_pedicel_has_proxy_without_inventing_calyx(self):
        from uchuva_lsystem.reproductive_orientation import KEY, POLICY
        plant,objects,_=fixture()
        node=plant.axes[0].child_axes[0].nodes[0]
        node.reproductive_unit=ReproductiveUnit('flower',node.id,'flower',Pedicel('flower_ped',node.id,2,35,0),
            provenance={KEY:dict(policy=POLICY,frame='plant_gravity_down',inclination_from_down_deg=8,
                azimuth_deg=90,inclination_bounds_deg=[0.,25.])})
        objects['flower_ped']={'properties':dict(uchuva_plant_id='fixture',uchuva_semantic_class='stem',
            uchuva_organ_kind='pedicel',uchuva_reproductive_instance_id='fixture:flower')}
        pairs=[dict(object_a='flower_ped',object_b='segment_1',classification='physical_collision')]
        before=axis_pose_invariant_manifest(plant)
        proxies=build_scene_proxies(CultivationScene('fixture','fixture',1,plant_instances=[PlantInstance('fixture',1)]),{'fixture':plant})
        self.assertEqual([p.kind for p in proxies if p.group_id=='fixture:flower'],['pedicel'])
        report=run(plant,objects,pairs,include_organ_axis_constraints=True,max_passes=1,max_trials_per_axis=4)
        self.assertEqual(report['physical_validity'],'not_established')
        self.assertEqual(before,axis_pose_invariant_manifest(plant))
        self.assertIsNone(node.reproductive_unit.calyx)
        node.reproductive_unit.provenance.pop(KEY)
        proxies=build_scene_proxies(CultivationScene('fixture','fixture',1,plant_instances=[PlantInstance('fixture',1)]),{'fixture':plant})
        self.assertFalse([p for p in proxies if p.group_id=='fixture:flower'])

    def test_measured_calyx_with_empty_kind_uses_semantic_and_true_owner(self):
        plant,objects,_=fixture()
        node=plant.axes[0].child_axes[0].nodes[0]
        node.reproductive_unit=ReproductiveUnit('unit',node.id,'mature_fruit_with_calyx',
            Pedicel('ped',node.id,2,35,0),calyx=Calyx('cal',3,1))
        objects['calyx']={'properties':{'uchuva_plant_id':'fixture','uchuva_semantic_class':'calyx',
            'uchuva_organ_kind':'','uchuva_reproductive_instance_id':'fixture:unit'}}
        evidence=[{'object_a':'calyx','object_b':'segment_1','required_clearance':.022,'clearance':.01}]
        before=deepcopy(plant.to_dict())
        found=confirmed_organ_axis_constraints(plant,evidence,objects,'fixture')
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['owner_axis'],plant.axes[0].child_axes[0].id)
        self.assertEqual(found[0]['kind'],'calyx')
        self.assertEqual(found[0]['required'],.022)
        self.assertEqual(plant.to_dict(),before)

    def test_same_axis_calyx_pair_retains_two_unit_identities(self):
        plant,objects,_=fixture()
        axis=plant.axes[0].child_axes[0]
        for i in range(2):
            node=axis.nodes[i]
            node.reproductive_unit=ReproductiveUnit(f'unit{i}',node.id,'mature_fruit_with_calyx',
                Pedicel(f'ped{i}',node.id,2,35,0),calyx=Calyx(f'cal{i}',3,1))
            objects[f'cal{i}']={'properties':{'uchuva_plant_id':'fixture','uchuva_semantic_class':'calyx',
                'uchuva_reproductive_instance_id':f'fixture:unit{i}'}}
        found=confirmed_organ_axis_constraints(plant,[{'object_a':'cal0','object_b':'cal1'}],objects,'fixture')
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['unit'],'fixture:unit0')
        self.assertEqual(found[0]['other_unit'],'fixture:unit1')
        self.assertEqual(found[0]['owner_axis'],found[0]['axis'])

    def test_candidates_stay_in_range_and_cumulative_limit(self):
        original=(359.,52.)
        values=axis_angular_candidates((2.,49.),original,(20.,55.),12.,limit=64)
        self.assertTrue(values)
        self.assertEqual(values,axis_angular_candidates((2.,49.),original,(20.,55.),12.,limit=64))
        self.assertEqual(len(values),len(set(values)))
        for pose in values:
            self.assertTrue(20<=pose[1]<=55)
            self.assertLessEqual(local_pose_distance_deg(original,pose),12.000001)
            self.assertLessEqual(abs((pose[0]-original[0]+180)%360-180),12.000001)

    def test_fine_axis_grid_preserves_original_cumulative_bound(self):
        original=(359.,52.)
        for step in (1.,.25):
            values=axis_angular_candidates((2.,49.),original,(20.,55.),12.,limit=48,step_deg=step)
            self.assertTrue(any(abs(p[1]-49.)==step for p in values))
            for pose in values:
                self.assertTrue(20<=pose[1]<=55)
                self.assertLessEqual(local_pose_distance_deg(original,pose),12.000001)
                self.assertLessEqual(abs((pose[0]-original[0]+180)%360-180),12.000001)
        with self.assertRaises(ValueError):
            axis_angular_candidates(original,original,(20.,55.),12.,step_deg=0.)

    def test_only_evaluated_axis_pairs_create_targets(self):
        plant,objects,pairs=fixture()
        objects["segment_1"]["properties"]["uchuva_organ_kind"]="pedicel"
        self.assertEqual(confirmed_axis_relations(pairs,objects,plant_id="fixture")[0],[])
        before=deepcopy(plant.to_dict()["axes"])
        result=run(plant,objects,pairs)
        self.assertEqual(result["changes"],[])
        self.assertEqual(plant.to_dict()["axes"],before)

    def test_improvement_preserves_anatomy_and_requires_full_rebuild(self):
        plant,objects,pairs=fixture()
        before=axis_pose_invariant_manifest(plant)
        report=run(plant,objects,pairs,max_trials_per_axis=24)
        self.assertTrue(report["changes"])
        self.assertLess(report["final_axis_proxy_score"],report["initial_axis_proxy_score"])
        self.assertEqual(before,axis_pose_invariant_manifest(plant))
        self.assertEqual(report["physical_validity"],"not_established")
        self.assertTrue(report["requires_full_mesh_rebuild"])
        self.assertEqual(plant.metadata["model_stage"],"adapted")
        self.assertEqual(Plant.from_dict(plant.to_dict()).to_dict(),plant.to_dict())

    def test_repeated_repairs_cannot_reset_the_original_pose_or_bound(self):
        plant,objects,pairs=fixture()
        run(plant,objects,pairs)
        originals={a.id:deepcopy(a.provenance["axis_pose_repair_v1"]["generated_pose"])
                   for a in plant.axes[0].child_axes if "axis_pose_repair_v1" in a.provenance}
        run(plant,objects,pairs)
        for a in plant.axes[0].child_axes:
            if a.id in originals:
                self.assertEqual(a.provenance["axis_pose_repair_v1"]["generated_pose"],originals[a.id])
                self.assertLessEqual(local_pose_distance_deg(originals[a.id],(a.azimuth_deg,a.branch_angle_deg)),12.000001)

    def test_registered_pose_is_valid_only_in_adapted_stage_and_with_effective_bounds(self):
        plant,objects,pairs=fixture()
        run(plant,objects,pairs)
        axis=next(a for a in plant.axes[0].child_axes if "axis_pose_repair_v1" in a.provenance)
        params=plant.metadata["effective_parameters"]
        errors=[]
        _validate_registered_axis_pose(axis,params,"adapted",errors)
        self.assertFalse(errors)
        _validate_registered_axis_pose(axis,params,"generated",errors)
        self.assertTrue(errors)
        axis.provenance["axis_pose_repair_v1"]["max_correction_deg"]=180
        errors=[]
        _validate_registered_axis_pose(axis,params,"adapted",errors)
        self.assertTrue(errors)

    def test_changed_dimensions_are_detected_by_the_invariant(self):
        plant,_,_=fixture()
        before=axis_pose_invariant_manifest(plant)
        plant.axes[0].child_axes[0].internodes[0].length_cm+=.1
        self.assertNotEqual(before,axis_pose_invariant_manifest(plant))

    def test_missing_inventory_or_incompatible_snapshot_fails(self):
        plant,objects,pairs=fixture()
        with self.assertRaisesRegex(ValueError,"absent"):
            run(plant,{},pairs)
        plant.metadata["effective_parameters_sha256"]="bad"
        with self.assertRaisesRegex(ValueError,"snapshot"):
            run(plant,objects,pairs)

    def test_same_axis_collision_is_recorded_without_unsupported_bend_edit(self):
        plant,objects,pairs=fixture()
        objects["segment_1"]["properties"]["uchuva_axis_id"]=objects["segment_0"]["properties"]["uchuva_axis_id"]
        before=deepcopy(plant.to_dict()["axes"])
        report=run(plant,objects,pairs)
        self.assertTrue(report["same_axis_self_intersections_not_repaired"])
        self.assertFalse(report["changes"])
        self.assertEqual(before,plant.to_dict()["axes"])

    def test_generated_v6_anatomy_invariant_covers_fruits_and_leaves(self):
        plant=generate_morphology_tree(2026102600,preset_name="trained_trellis_lower_crown_audit_v6",phenology_model="literature_cohort_v1")
        before=axis_pose_invariant_manifest(plant)
        self.assertGreater(before["counts"]["fruits"],10)
        plant.axes[0].nodes[0].leaf.length_cm+=.01
        self.assertNotEqual(before,axis_pose_invariant_manifest(plant))

    def test_failure_rolls_back_anatomy_and_metadata_atomically(self):
        plant,objects,pairs=fixture()
        before=deepcopy(plant.to_dict())
        def fail(*args,**kwargs):
            plant.axes[0].internodes[0].length_cm=999
            plant.metadata["incomplete_attempt"]=True
            raise RuntimeError("fixture failure")
        with patch("uchuva_lsystem.axis_pose_repair.build_scene_proxies",side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,"fixture failure"):
                run(plant,objects,pairs)
        self.assertEqual(before,plant.to_dict())

    def test_awake_deadline_stops_without_truncating_a_pose(self):
        plant,objects,pairs=fixture()
        before=deepcopy(plant.to_dict()["axes"])
        with patch("uchuva_lsystem.axis_pose_repair.awake_seconds",side_effect=[0,2,2]):
            report=run(plant,objects,pairs,max_seconds=1)
        self.assertTrue(report["exhausted"])
        self.assertEqual(report["trials"],0)
        self.assertEqual(before,plant.to_dict()["axes"])

    def test_confirmed_clearance_only_can_move_an_axis_without_new_intersection(self):
        plant,objects,_=fixture()
        plant.axes[0].child_axes[0].azimuth_deg=6.
        clearance=[{"object_a":"segment_0","object_b":"segment_1",
                    "clearance":.001,"required_clearance":.024}]
        invariant=axis_pose_invariant_manifest(plant)
        report=run(plant,objects,[],clearance_pairs=clearance)
        self.assertEqual(report["initial_axis_proxy_score"][0],0)
        self.assertEqual(report["final_axis_proxy_score"][0],0)
        self.assertTrue(report["changes"])
        self.assertLess(report["final_axis_clearance_score"],report["initial_axis_clearance_score"])
        self.assertEqual(report["required_clearance_scene_units"],.024)
        self.assertEqual(invariant,axis_pose_invariant_manifest(plant))

    def test_apex_clearance_metadata_is_explicit_and_preserves_evidence_order(self):
        _,objects,_=fixture()
        objects["segment_0"]["properties"].update(uchuva_organ_kind="axis_apex",uchuva_internode_index=4)
        rows=[{"object_a":"segment_1","object_b":"segment_0","clearance":.01,"required_clearance":.024}]
        relations,detail,_=confirmed_axis_relations(rows,objects,plant_id="fixture",clearance=True)
        self.assertTrue(relations)
        self.assertEqual(detail[0]["objects"],["segment_1","segment_0"])
        self.assertEqual(detail[0]["kinds"],["axis_segment","axis_apex"])
        self.assertEqual(detail[0]["internode_indices"],[1,4])
        self.assertEqual(detail[0]["axis_ids"],["axis_0_branch_1","axis_0_branch_0"])

    def test_apex_proxies_use_final_replayed_endpoint_and_rendered_radius(self):
        plant,_,_=fixture()
        instance=PlantInstance("fixture",1,scale=2)
        scene=CultivationScene("test","test",1,plant_instances=[instance])
        proxies=build_scene_proxies(scene,{"fixture":plant})
        complete=_with_apex_proxies(proxies,plant,instance)
        apex=next(p for p in complete if p.proxy_id.endswith("axis_0_branch_0:apex"))
        last=[p for p in proxies if p.axis_id=="axis_0_branch_0"][-1]
        self.assertEqual(apex.start,last.end)
        self.assertEqual(apex.end,last.end)
        self.assertAlmostEqual(apex.radius,max(.018*(1-.18),.008)*2)
        self.assertEqual(apex.internode_index,4)

    def test_unconfirmed_clearance_hint_does_not_activate_search(self):
        plant,objects,_=fixture()
        plant.axes[0].child_axes[0].azimuth_deg=6.
        before=deepcopy(plant.to_dict()["axes"])
        report=run(plant,objects,[])
        self.assertEqual(report["changes"],[])
        self.assertEqual(before,plant.to_dict()["axes"])


if __name__=="__main__":
    unittest.main()
