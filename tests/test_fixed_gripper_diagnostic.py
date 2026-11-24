"""The fixed-gripper diagnostic cannot discard mass or alter the arm/drive."""
import copy
import itertools
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import forward_kinematics
from uchuva_gazebo.robot_sdf import resolved_robot_model
from prepare_cad_fixed_gripper_diagnostic import derive_fixed_gripper, xml_value


class FixedGripperTests(unittest.TestCase):
    def source(self):
        data = resolve_robot_profile(ROOT/'configs/robots/proxy_v1.json').to_dict()
        inertia = {'mass_kg':.01,'com_m':[0,0,0], 'tensor_kg_m2':[1e-5,1e-5,1e-5,0,0,0]}
        identity = {'xyz_m':[0,0,0], 'quaternion_xyzw':[0,0,0,1]}
        for name in ('gripper_driver_body','gripper_follower_body','gripper_closure_aux'):
            data['links'].append({'name':name,'inertial':copy.deepcopy(inertia),'visuals':[],'collisions':[]})
        for name,child,group in (
            ('gripper_driver','gripper_driver_body','gripper'),
            ('gripper_follower','gripper_follower_body','passive'),
            ('gripper_closure_pin','gripper_closure_aux','passive')):
            data['joints'].append({'name':name,'type':'revolute','group':group,'parent':'tool_link','child':child,
                'origin':copy.deepcopy(identity),'child_pose':copy.deepcopy(identity),'axis':[0,1,0],'zero_offset':0,
                'limits':{'lower':-.4,'upper':.4,'effort':.02,'velocity':1}})
        original = copy.deepcopy(inertia)
        original['mass_kg'] *= 2
        original['tensor_kg_m2'] = [v*2 for v in original['tensor_kg_m2']]
        data['closures'] = [{'name':'gripper_weld','moving_joint':'gripper_closure_pin',
            'body':'gripper_driver_body','auxiliary':'gripper_closure_aux','mass_fraction':.5,'original_inertial':original}]
        data['gear_couplings'] = [{'name':'gear','driver':'gripper_driver','follower':'gripper_follower',
            'ratio':-1,'offset':0,'stiffness_nm_rad':100,'damping_nms_rad':.012,'maximum_step_s':.0001}]
        data['control']['gripper'] = {'gripper_driver':{'p_gain':.2,'i_gain':0,'d_gain':.01,
            'i_min':0,'i_max':0,'cmd_min':-.02,'cmd_max':.02,'command_velocity':.2,'reference_mode':'ramped_position'}}
        data['actuators'].append({'name':'gripper_motor','joint':'gripper_driver','continuous_effort':.02,
            'peak_effort':.02,'effort_reference':'joint_output','transmission_ratio':1,'efficiency':1,'status':'estimado'})
        data['collision_policy']['excluded_pairs'] = [{'links':list(pair),'reason':'Synthetic fixture source policy'}
            for pair in itertools.combinations([l['name'] for l in data['links']],2)]
        return resolve_robot_profile(data)

    def test_fixed_derivative_preserves_every_physical_link_and_other_controls(self):
        source = self.source()
        old = source.to_dict()
        robot, report = derive_fixed_gripper(source,old['provenance'])
        new = robot.to_dict()
        self.assertEqual(new['links'],old['links'])
        self.assertEqual(new['control']['arm'],old['control']['arm'])
        self.assertEqual(new['control']['drive'],old['control']['drive'])
        self.assertEqual(new['collision_policy'],old['collision_policy'])
        self.assertEqual(len(report['fixed_joint_names']),3)
        self.assertEqual(new['closures'],[])
        self.assertEqual(new['gear_couplings'],[])
        self.assertNotIn('gripper',new['control'])
        self.assertFalse(any(a['joint'].startswith('gripper_') for a in new['actuators']))
        self.assertNotIn('native_harvest',new['capabilities'])
        a,b = resolved_robot_model(source),resolved_robot_model(robot)
        self.assertEqual([xml_value(l) for l in a.findall('link')],[xml_value(l) for l in b.findall('link')])
        self.assertEqual(source.to_dict(),old)

    def test_link_poses_follow_the_same_arm_motion_with_gripper_fixed(self):
        source = self.source()
        robot,_ = derive_fixed_gripper(source,source.to_dict()['provenance'])
        for angle in (-.08,0,.08):
            oldq = {j['name']:0 for j in source.to_dict()['joints'] if j['type']!='fixed'}
            newq = {j['name']:0 for j in robot.to_dict()['joints'] if j['type']!='fixed'}
            oldq['shoulder_joint'] = newq['shoulder_joint'] = angle
            self.assertEqual(forward_kinematics(source,oldq),forward_kinematics(robot,newq))

    def test_nonzero_reference_offset_is_not_silently_ignored(self):
        data = self.source().to_dict()
        next(j for j in data['joints'] if j['name']=='gripper_follower')['zero_offset'] = .1
        source = resolve_robot_profile(data)
        with self.assertRaisesRegex(ValueError,'zero CAD offsets'):
            derive_fixed_gripper(source,data['provenance'])


if __name__ == '__main__': unittest.main()
