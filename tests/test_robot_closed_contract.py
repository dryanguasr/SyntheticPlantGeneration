import copy
import itertools
import unittest

from uchuva_gazebo.robot_spec import resolve_robot
from uchuva_gazebo.robot_kinematics import forward_kinematics, inverse_pose, pose_identity
from uchuva_gazebo.robot_sdf import resolved_robot_model
from uchuva_gazebo.robot_collision_filters import collision_masks


class ClosedContractTests(unittest.TestCase):
    def example(self):
        robot=resolve_robot('proxy_v1')
        data=robot.to_dict()
        data['derived_values']=[r for r in data['derived_values'] if not r['path'].startswith('/links/0/inertial')]
        original=copy.deepcopy(data['links'][0]['inertial'])
        half=copy.deepcopy(original)
        half['mass_kg']/=2
        half['tensor_kg_m2']=[v/2 for v in half['tensor_kg_m2']]
        data['links'][0]['inertial']=copy.deepcopy(half)
        data['links'].append({'name':'closure_aux','inertial':half,'collisions':[],'visuals':[]})
        parent=data['joints'][-1]['child']
        data['joints'].append({'name':'closure_joint','parent':parent,'child':'closure_aux',
            'type':'revolute','group':'passive','axis':[0,1,0],'zero_offset':0,
            'origin':inverse_pose(forward_kinematics(robot,{j['name']:0 for j in robot.joints})[parent]),'child_pose':pose_identity(),
            'limits':{'lower':-1,'upper':1,'effort':1,'velocity':1},'spring_reference':0,'spring_stiffness':10})
        data['closures']=[{'name':'closure','body':'base_link','auxiliary':'closure_aux',
            'moving_joint':'closure_joint','mass_fraction':.5,'original_inertial':original}]
        data['collision_policy']={'mode':'explicit_pairs','excluded_pairs':[
            {'links':[j['parent'],j['child']],'reason':'connected'} for j in data['joints']]}
        return data

    def test_conserved_native_closure_and_spring_export(self):
        data=self.example()
        model=resolved_robot_model(resolve_robot(data))
        closure=model.find("plugin[@name='uchuva::ClosedLoopSystem']/closure")
        self.assertEqual(closure.findtext('body'),'base_link')
        self.assertEqual(model.findtext("joint[@name='closure_joint']/axis/dynamics/spring_stiffness"),'10')

    def test_duplicate_mass_and_unclosed_reference_rejected(self):
        data=self.example()
        data['links'][-1]['inertial']['mass_kg']*=2
        with self.assertRaisesRegex(ValueError,'conserve'):
            resolve_robot(data)
        data=self.example()
        data['joints'][-1]['origin']['xyz_m'][0]+=.01
        with self.assertRaisesRegex(ValueError,'coincide'):
            resolve_robot(data)

    def test_masks_preserve_all_unexcluded_pairs(self):
        names=[f'link_{i}' for i in range(20)]
        extra={tuple(sorted((names[i],names[i+1]))) for i in range(0,14,2)}
        data={'links':[{'name':n,'collisions':[{}]} for n in names], 'joints':[],
              'collision_policy':{'excluded_pairs':[{'links':list(p)} for p in extra]}}
        masks=collision_masks(data)
        self.assertTrue(all(0<v<=65535 for v in masks.values()))
        for a,b in itertools.combinations(names,2):
            self.assertEqual(bool(masks[a]&masks[b]),tuple(sorted((a,b))) not in extra)


if __name__=='__main__':
    unittest.main()
