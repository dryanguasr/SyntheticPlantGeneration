"""Independent, small fixtures for the explicit CAD demo derivation."""
import copy
import hashlib
import itertools
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
from prepare_cad_v8_demo_robot import DEFAULTS, basket_parts, box_inertia, derive, pose
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import forward_kinematics, inverse_pose, compose_poses, transform_point


class DemoRobotTests(unittest.TestCase):
    def fixture(self, folder):
        data = resolve_robot_profile(ROOT/'configs/robots/proxy_v1.json').to_dict()
        for link in data['links']:
            if link['name'] == 'tool_link': link['name'] = 'arm_wrist_roll'
        for joint in data['joints']:
            for key in ('parent', 'child'):
                if joint[key] == 'tool_link': joint[key] = 'arm_wrist_roll'
        for frame in data['frames']:
            if frame['parent'] == 'tool_link': frame['parent'] = 'arm_wrist_roll'
        data['physics'] = {'backend':'DART', 'solver_type':'pgs', 'maximum_step_s':.0001}
        data['capabilities'].append('collision_meshes')
        data.pop('legacy_proxy_config', None)
        # Freeze this already-resolved small source as the CAD source is frozen;
        # legacy proxy mass recipes must not overwrite newly aggregated masses.
        data['derived_values']=[]
        data['parameter_metadata']={k:v for k,v in data['parameter_metadata'].items() if not k.startswith('/legacy_proxy_config/')}
        data['capabilities'].remove('legacy_proxy')
        data['parameters']['synthetic_mesh_revision']=1
        data['parameter_metadata']['/parameters/synthetic_mesh_revision']={**data['provenance'],'update_class':'cad_reexport'}
        names = ('gripper_left_jaw','gripper_right_jaw','gripper_left_short','gripper_right_short',
                 'gripper_left_gear','gripper_right_gear','gripper_left_aux','gripper_right_aux')
        for index, name in enumerate(names):
            shapes = []
            if name.endswith('_jaw'):
                bounds = (-.01,-.00025) if name == 'gripper_left_jaw' else (.00025,.01)
                vertices = list(itertools.product(bounds,(-.001,.001),(-.002,.002)))
                content = ''.join('v '+ ' '.join(str(v) for v in p)+'\n' for p in vertices)
                path = folder/(name+'.obj');path.write_text(content)
                geometry = {'type':'mesh','uri':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                            'bound_parameters':{'/parameters/synthetic_mesh_revision':1},'scale':[1,1,1]}
                shapes = [{'name':name+'_surface','pose':pose(),'geometry':geometry}]
            visuals=copy.deepcopy(shapes)
            for v in visuals:v['name']+='_visual'
            data['links'].append({'name':name,'inertial':box_inertia(.01+index*.001,[.01,.02,.03]),
                                  'visuals':visuals,'collisions':shapes})
            data['joints'].append({'name':name+'_pivot','type':'fixed','group':'fixed',
                'parent':'arm_wrist_roll','child':name,'origin':pose(),'child_pose':pose(),'zero_offset':0,
                'axis':[0,0,1],'limits':{'lower':0,'upper':0,'effort':0,'velocity':0}})
        # Fixture policy is explicit; the production source supplies its own pair list.
        data['collision_policy']['mode']='explicit_pairs'
        data['collision_policy']['excluded_pairs'] = [{'links':[j['parent'],j['child']],'reason':'Joint adjacency fixture'}
            for j in data['joints']]
        return resolve_robot_profile(data)

    def test_mass_surfaces_and_motion_preserved_except_declared_slider(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source=self.fixture(folder);old=source.to_dict()
            robot,report=derive(source,folder,copy.deepcopy(DEFAULTS),old['provenance'])
            new=robot.to_dict()
            self.assertAlmostEqual(report['added_mass_kg'],2.7,places=12)
            self.assertEqual(len(new['links']),len(old['links'])-6)
            self.assertEqual(new['control']['drive'],old['control']['drive'])
            self.assertEqual(new['physics'],old['physics'])
            self.assertNotIn('native_harvest',new['capabilities'])
            self.assertLess(report['maximum_original_shape_q0_position_error_m'],1e-12)
            changed=copy.deepcopy(old['control']['arm'])
            changed['wrist_pitch_joint']['command_velocity']=.25
            self.assertEqual(new['control']['arm'],changed)
            self.assertEqual(new['joints'][:9],old['joints'][:9])
            for link in new['links']:
                names=[s['name'] for kind in ('visuals','collisions') for s in link[kind]]
                self.assertEqual(len(names),len(set(names)))
            for q in (0,report['gripper']['open_position_m']/2,report['gripper']['open_position_m']):
                positions={j['name']:0 for j in new['joints'] if j['type']!='fixed'}
                positions.update({report['gripper']['joint']:q,'shoulder_joint':.08})
                fk=forward_kinematics(robot,positions)
                jaw=compose_poses(inverse_pose(fk['grasp_center']),fk['gripper_left_jaw'])
                self.assertAlmostEqual(transform_point(jaw,[0,0,0])[0],-q,places=12)
                self.assertAlmostEqual(transform_point(jaw,[0,0,0])[1],0,places=12)
            self.assertAlmostEqual(report['gripper']['closed_gap_m'],.0005,places=12)
            self.assertAlmostEqual(report['gripper']['open_gap_m'],.006,places=12)

    def test_basket_is_open_and_five_disjoint_positive_solids(self):
        parts=basket_parts(DEFAULTS['basket'])
        self.assertEqual(len(parts),5)
        self.assertAlmostEqual(sum(p['mass_kg'] for p in parts),.35,places=12)
        for a,b in itertools.combinations(parts,2):
            overlaps=[min(a['center_m'][i]+a['size_m'][i]/2,b['center_m'][i]+b['size_m'][i]/2)-
                      max(a['center_m'][i]-a['size_m'][i]/2,b['center_m'][i]-b['size_m'][i]/2) for i in range(3)]
            self.assertLessEqual(min(overlaps),1e-14)
        lo,hi=DEFAULTS['basket']['inner_min_m'],DEFAULTS['basket']['inner_max_m']
        for p in parts:
            self.assertLessEqual(p['center_m'][2]+p['size_m'][2]/2,hi[2]+1e-14)
        self.assertTrue(all(p['name']!='basket_lid' for p in parts))
        self.assertTrue(all(v>0 for v in box_inertia(1,[.1,.2,.3])['tensor_kg_m2'][:3]))

    def test_wrong_mesh_and_invalid_stroke_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source=self.fixture(folder);settings=copy.deepcopy(DEFAULTS)
            settings['gripper']['open_gap_m']=.0001
            with self.assertRaisesRegex(ValueError,'jaw travel'):derive(source,folder,settings,source.to_dict()['provenance'])
            (folder/'gripper_left_jaw.obj').write_text('v 0 0 0\n')
            with self.assertRaisesRegex(ValueError,'mesh identity'):derive(source,folder,copy.deepcopy(DEFAULTS),source.to_dict()['provenance'])

    def test_electronics_is_internal_and_clear_of_other_payload_boxes(self):
        box=DEFAULTS['electronics']
        # Measured inner faces of the CAD upper/lower chassis crossbars.
        z_low=box['center_m'][2]-box['size_m'][2]/2
        z_high=box['center_m'][2]+box['size_m'][2]/2
        self.assertGreaterEqual(z_low-(-.076725),.004)
        self.assertGreaterEqual(.076725-z_high,.004)
        self.assertEqual(box['mass_kg'],.35)
        for other in DEFAULTS['batteries']+basket_parts(DEFAULTS['basket']):
            gap2=sum(max(0,abs(a-b)-(x+y)/2)**2 for a,b,x,y in
                     zip(box['center_m'],other['center_m'],box['size_m'],other['size_m']))
            self.assertGreaterEqual(gap2,.004**2)


if __name__=='__main__':unittest.main()
