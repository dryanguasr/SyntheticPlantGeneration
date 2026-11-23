"""Analytic inertia and synthetic occurrence-tree tests; no private CAD needed."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('cad_robot_builder',ROOT/'scripts/prepare_cad_robot.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def mass(value=1, center=(0,0,0), tensor=(.001,.001,.001,0,0,0)):
    return {'mass_kg':value,'center_of_mass_m':list(center),'xyz_moments_kg_m2':list(tensor),
            'tensor_principal_consistency':{'consistent':True,'scope':'analytic synthetic fixture'}}


def matrix(x=0,y=0,z=0):
    return [1,0,0,x,0,1,0,y,0,0,1,z,0,0,0,1]


class CadRobotInertiaTests(unittest.TestCase):
    def test_native_offdiagonal_order_rotation_and_com_translation(self):
        # A +90deg Z rotation maps (x,y,z) -> (-y,x,z). Native tensor order
        # is xx,yy,zz,xy,yz,xz; RobotSpec order ends xy,xz,yz.
        placement = builder.from_matrix([0,-1,0,10,1,0,0,-1,0,0,1,.5,0,0,0,1])
        result = builder.aggregate_inertia([(mass(2,(1,2,3),(4,5,6,.2,.3,.4)),placement)])
        for observed, expected in zip(result['com_m'],[8,0,3.5]):
            self.assertAlmostEqual(observed,expected,places=12)
        for observed, expected in zip(result['tensor_kg_m2'],[5,4,6,-.2,-.3,.4]):
            self.assertAlmostEqual(observed,expected,places=12)

    def test_parallel_axis_is_about_group_com_and_counted_once(self):
        parts = [(mass(2,tensor=(.8,.8,.8,0,0,0)),builder.pose()),
                 (mass(1,tensor=(.1,.1,.1,0,0,0)),builder.pose((3,6,0)))]
        result = builder.aggregate_inertia(parts)
        self.assertEqual(result['mass_kg'],3)
        self.assertEqual(result['com_m'],[1,2,0])
        for observed, expected in zip(result['tensor_kg_m2'],[24.9,6.9,30.9,-12,0,0]):
            self.assertAlmostEqual(observed,expected,places=12)
        self.assertEqual(result,builder.aggregate_inertia(list(reversed(parts))))

    def test_empty_or_nonpositive_mass_is_never_silently_zero(self):
        for parts in ([],[(mass(0),builder.pose())],[(mass(-1),builder.pose())],[(mass(float('nan')),builder.pose())]):
            with self.assertRaises(ValueError):
                builder.aggregate_inertia(parts)

    def test_cad_basis_is_a_proper_rotation_without_unit_rescaling(self):
        transformed = builder.transform_point(builder.CAD_ROTATION,[2,3,5])
        for observed,expected in zip(transformed,[-5,-2,3]):
            self.assertAlmostEqual(observed,expected,places=12)
        with self.assertRaisesRegex(ValueError,'Reflected'):
            builder.from_matrix([-1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1])


def synthetic_inputs(directory):
    """13 occurrences of one part, plus massive assemblies that must not count."""
    directory.mkdir()
    mesh = directory/'part.obj'
    mesh.write_text('v 0 0 0\nv .01 0 0\nv 0 .01 0\nf 1 2 3\n')
    mesh_hash = hashlib.sha256(mesh.read_bytes()).hexdigest()
    docs = [
        {'id':'a','source_path':'arm.iam','sha256':'a'*64},
        {'id':'b','source_path':'base.iam','sha256':'b'*64},
        {'id':'assembly','source_path':'subassembly.iam','sha256':'c'*64,'mass_properties':mass(999)},
        {'id':'part','source_path':'same_part.ipt','sha256':'d'*64,'mass_properties':mass(),
         'bounds_m':{'min':[-.01,-.01,-.01],'max':[.01,.01,.01]},
         'exports':{'obj':{'status':'exported','uri':'part.obj','sha256':mesh_hash}}},
    ]
    occurrences=[]
    def add(identifier,name,root,parent,document='part',xyz=(0,0,0),suppressed=False):
        occurrences.append({'id':identifier,'name':name,'root_document_id':root,'parent_id':parent,
                            'document_id':document,'status':'resolved','suppressed':suppressed,'visible':True,
                            'transform_root_m':matrix(*xyz)})
    groups = {'Mount':'base_mount','YawAssembly':'yaw','UpperAssembly':'upper_arm',
              'Forearm':'forearm','Wrist':'wrist_pitch','Tool':'wrist_roll'}
    for i,(name,group) in enumerate(groups.items()):
        identifier='a/'+str(i)
        if name.endswith('Assembly'):
            add(identifier,name,'a','a','assembly')
            add(identifier+'/body','Body','a',identifier,xyz=(.01*i,.02*i,.03*i))
            add(identifier+'/driven','Driven','a',identifier,xyz=(.02*i,.03*i,.04*i))
        else:add(identifier,name,'a','a',xyz=(.01*i,.02*i,.03*i))
    add('a/suppressed','Suppressed','a','a',suppressed=True)
    add('b/chassis','Chassis','b','b')
    wheels=[]
    for i,name in enumerate(('front_left','front_right','rear_left','rear_right')):
        center=[.2 if i<2 else -.2,.2 if name.endswith('left') else -.2,-.1]
        add('b/w'+str(i),name,'b','b',xyz=center)
        wheels.append({'name':name,'group':'wheel_'+name,'assembly_occurrence_id':'b/w'+str(i),
                       'center_base_m':center,'radius_m':.1,'width_m':.04})
    inv={'status':'exported_cad_not_hardware_validated','source_integrity':{'changed_files':[]},
         'documents':docs,'occurrences':occurrences,'issues':[]}
    source_arm=json.loads((ROOT/'configs/robots/cad_arm_mapping.json').read_text(encoding='utf-8'))
    arm={'source_document_path':'arm.iam','source_document_sha256':'a'*64,
         'top_level_occurrence_groups':groups,'joints':source_arm['joints'],'frames':source_arm['frames'],
         'nested_assignment_overrides':[{'occurrence_path':['YawAssembly','Driven'],'group':'base_mount'},
                                       {'occurrence_path':['UpperAssembly','Driven'],'group':'forearm'}]}
    base={'source':{'root_source_path':'base.iam','root_sha256':'b'*64},'wheels':wheels,
          'dimensions':{'wheel_separation_m':.4,'cad_pose_chassis_origin_height_for_tire_tangent_ground_m':.2}}
    assumptions=json.loads((ROOT/'configs/robots/cad_diagnostic_assumptions.json').read_text(encoding='utf-8'))
    paths=[]
    for name,value in [('inventory',inv),('arm',arm),('base',base),('assumptions',assumptions)]:
        path=directory/(name+'.json');path.write_text(json.dumps(value),encoding='utf-8');paths.append(path)
    return paths


class CadRobotGroupingTests(unittest.TestCase):
    def test_leaf_occurrences_count_once_and_nested_overrides_survive_mesh_dedup(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);inventory,arm,base,assumptions=synthetic_inputs(path/'inputs')
            output=path/'result'
            result=builder.prepare(inventory,output,arm,base,assumptions)
            report=json.loads((output/'cad_import_report.json').read_text(encoding='utf-8'))
            profile=json.loads((output/'cad_diagnostic_frozen.json').read_text(encoding='utf-8'))
            self.assertEqual(result['leaf_parts'],13)
            self.assertEqual(result['meshes'],1)
            self.assertEqual(result['total_cad_mass_kg'],13)
            self.assertEqual(len({r['occurrence_id'] for r in report['parts']}),13)
            assigned={tuple(r['occurrence_name_path']):r['link'] for r in report['parts']}
            self.assertEqual(assigned[('YawAssembly','Driven')],'arm_base_mount')
            self.assertEqual(assigned[('UpperAssembly','Driven')],'arm_forearm')
            self.assertNotIn(('YawAssembly',),assigned)
            self.assertNotIn(('Suppressed',),assigned)
            masses={link['name']:link['inertial']['mass_kg'] for link in profile['links']}
            self.assertEqual(masses['arm_base_mount'],2)
            self.assertEqual(masses['arm_forearm'],2)
            self.assertFalse(report['native_harvest_eligible'])
            self.assertEqual(report['native_validation'],'NO EJECUTADO')
            from uchuva_gazebo.robot_kinematics import forward_kinematics
            from uchuva_gazebo.robot_spec import resolve_robot
            poses=forward_kinematics(resolve_robot(profile))
            for record in report['parts']:
                native=next(o for o in json.loads(inventory.read_text())['occurrences'] if o['id']==record['occurrence_id'])
                # Independent permutation expresses document origin in base:
                # x=-CAD z, y=-CAD x, z=CAD y, plus mount for arm only.
                m=native['transform_root_m'];expected=[-m[11],-m[3],m[7]]
                if native['root_document_id']=='a':
                    mount=json.loads(assumptions.read_text())['arm_mount_xyz_m']
                    expected=[a+b for a,b in zip(expected,mount)]
                actual=builder.compose_poses(poses[record['link']],record['link_T_document'])['xyz_m']
                for observed,wanted in zip(actual,expected):self.assertAlmostEqual(observed,wanted,places=10)

    def test_changed_root_revision_and_unclassified_issue_fail_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);inventory,arm,base,assumptions=synthetic_inputs(root/'inputs')
            original=json.loads(inventory.read_text())
            for failure in ('revision','issue'):
                data=copy.deepcopy(original)
                if failure=='revision':data['documents'][0]['sha256']='e'*64
                else:data['issues']=[{'scope':'unresolved_or_ambiguous_reference','message':'missing_physical_shaft.ipt'}]
                inventory.write_text(json.dumps(data))
                output=root/failure
                with self.assertRaises(ValueError):builder.prepare(inventory,output,arm,base,assumptions)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
