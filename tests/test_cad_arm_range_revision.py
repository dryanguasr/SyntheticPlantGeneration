import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_cad_arm_range_revision import arm_range_revision,resolve_robot_profile


class ArmRangeRevisionTests(unittest.TestCase):
    def fixture(self):
        robot=resolve_robot_profile('proxy_v1')
        revision={'base_robot_spec_sha256':robot.sha256,'joint_names':list(robot.joint_names),
            'status':'user_reported_approximate','centering_status':'engineering_heuristic_unconfirmed',
            'candidate_limits_rad':[-math.pi/2,math.pi/2],'total_travel_rad':math.pi,
            'original_total_travel':180,'original_unit':'degree','interpretation':'180 degrees total',
            'centering_assumption':'Unconfirmed symmetric interval around CAD zero'}
        return robot,revision
    def test_changes_only_bound_values_with_audited_resolver_history(self):
        robot,revision=self.fixture();before=robot.to_dict()
        _,candidate,changes=arm_range_revision(robot,revision,'user-register','a'*64)
        self.assertEqual(robot.to_dict(),before)
        self.assertEqual(len(changes),10)
        self.assertNotEqual(robot.sha256,candidate.sha256)
        self.assertEqual(len(candidate.to_dict()['override_history']),len(before['override_history'])+10)
        for key in ('links','frames','control','physics'):self.assertEqual(before.get(key),candidate.to_dict().get(key))
    def test_total_travel_and_source_identity_cannot_be_reinterpreted(self):
        robot,revision=self.fixture()
        for changes in ({'base_robot_spec_sha256':'b'*64},{'candidate_limits_rad':[-math.pi,math.pi]},
                        {'centering_status':'measured'},{'joint_names':list(robot.joint_names)[:-1]}):
            with self.assertRaises(ValueError):arm_range_revision(robot,{**revision,**changes},'user-register','a'*64)


if __name__=='__main__':unittest.main()
