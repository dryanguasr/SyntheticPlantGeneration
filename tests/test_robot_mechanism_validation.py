import copy
import math
import unittest

from uchuva_gazebo.robot_mechanism_validation import audit_mechanism_sample, audit_passive_gear_commands


class Fixture:
    sha256 = 'fixture'
    def to_dict(self):
        return {'closures':[{'name':'shock','body':'carrier_left','auxiliary':'carrier_aux'},
                            {'name':'gripper','body':'gripper_short','auxiliary':'gripper_aux'}],
                'gear_couplings':[{'name':'gears','driver':'driver','follower':'follower','ratio':-1,'offset':0}]}


class NativeMechanismAuditTests(unittest.TestCase):
    def setUp(self):
        self.robot=Fixture()
        self.poses={name:{'xyz_m':[.1,.2,.3],'quaternion_xyzw':[0,0,0,1]}
                    for name in ('carrier_left','carrier_aux','gripper_short','gripper_aux')}
        self.q={'driver':.12,'follower':-.12}

    def test_observed_constraint_failures_cannot_hide_behind_consistent_tree_fk(self):
        self.assertTrue(audit_mechanism_sample(self.robot,self.q,self.poses)['passed'])
        self.poses['gripper_aux']['xyz_m'][0] += .0006
        result=audit_mechanism_sample(self.robot,self.q,self.poses)
        self.assertFalse(result['passed'])
        self.assertFalse(result['closures'][1]['passed'])
        self.poses['gripper_aux']['xyz_m'][0] -= .0006
        self.q['follower'] += .0011
        self.assertFalse(audit_mechanism_sample(self.robot,self.q,self.poses)['passed'])

    def test_rotation_and_missing_observations_fail_closed(self):
        self.poses['carrier_aux']['quaternion_xyzw']=[0,0,math.sin(.001),math.cos(.001)]
        self.assertFalse(audit_mechanism_sample(self.robot,self.q,self.poses)['passed'])
        del self.poses['carrier_aux']
        self.assertFalse(audit_mechanism_sample(self.robot,self.q,self.poses)['passed'])

    def test_passive_follower_zero_command_is_distinct_from_transmitted_wrench(self):
        sample={'robot_spec_sha256':'fixture','joints':[{'name':'follower','force_command_available':False,
            'force_command':None,'max_abs_force_command_window':0,'transmitted_wrench':{'torque':[100,20,10]}}]}
        self.assertTrue(audit_passive_gear_commands(self.robot,sample)['passed'])
        sample['joints'][0]['max_abs_force_command_window']=.001
        self.assertFalse(audit_passive_gear_commands(self.robot,sample)['passed'])
        sample['robot_spec_sha256']='wrong'
        with self.assertRaises(ValueError):audit_passive_gear_commands(self.robot,sample)


if __name__=='__main__':unittest.main()
