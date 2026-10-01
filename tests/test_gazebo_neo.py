import math
import unittest
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from uchuva_gazebo.field import write_world
from uchuva_gazebo.neo import neo_model, mission_waypoints, MASS, FORCE_CONSTANT
from uchuva_gazebo.flight_control import world_to_body, bounded_command, angular_rate_from_poses, flight_metrics


class NeoTests(unittest.TestCase):
    def test_velocity_gain_has_mass_scaled_time_constant(self):
        control=neo_model().find("plugin[@name='gz::sim::systems::MulticopterVelocityControl']")
        self.assertEqual([float(v)/MASS for v in control.findtext('velocityGain').split()],[2,2,4])

    def test_world_velocity_transform_includes_roll_and_pitch(self):
        c=math.sqrt(.5)
        for q,vector,expected in [((0,0,c,c),(1,0,0),(0,-1,0)),
                                 ((c,0,0,c),(0,0,1),(0,1,0)),
                                 ((0,c,0,c),(0,0,1),(-1,0,0))]:
            for actual,wanted in zip(world_to_body(vector,q),expected):
                self.assertAlmostEqual(actual,wanted)
            self.assertEqual(world_to_body(vector,q),world_to_body(vector,tuple(-v for v in q)))

    def test_shortest_quaternion_rate_rejects_representation_spikes(self):
        q=(.1,.2,.3,math.sqrt(.86))
        self.assertEqual(angular_rate_from_poses(q,tuple(-v for v in q),.034),(0,0,0))
        rates=angular_rate_from_poses((0,0,0,1),(0,0,math.sin(.01),math.cos(.01)),.04)
        self.assertAlmostEqual(rates[2],.5)
        self.assertAlmostEqual(rates[0],0)

    def test_mission_commands_do_not_jump_on_waypoint_reversal(self):
        previous=(.85,0,0,.5)
        following=bounded_command((-8,3,2),-math.pi,previous,.034)
        self.assertLessEqual(math.dist(previous[:3],following[:3]),.5*.034+1e-12)
        self.assertLessEqual(abs(previous[3]-following[3]),.6*.034+1e-12)

    def test_hover_rejects_lateral_or_attitude_oscillation(self):
        samples=[{'t':i,'roll':.2*(-1)**i,'pitch':0,'position_error_m':.1,
                  'angular_velocity':[0,0,0]} for i in range(26)]
        self.assertFalse(flight_metrics(samples)['hover_settled'])
        for sample in samples:sample.update(roll=0,position_error_m=.001)
        self.assertTrue(flight_metrics(samples)['hover_settled'])

    def test_visual_mesh_does_not_change_dynamics(self):
        original=neo_model()
        adapted=neo_model(visual_assets=[{'uri':'body.obj','color':[1,1,1,1]},
            {'uri':'rotor.obj','color':[0,0,0,1],'link':'rotor_0'}])
        import xml.etree.ElementTree as ET
        for model in (original,adapted):
            for link in model.findall('link'):
                for visual in list(link.findall('visual')):link.remove(visual)
        self.assertEqual(ET.tostring(original),ET.tostring(adapted))

    def test_batch_preserves_positions_and_reindexes_faces(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'source';source.mkdir();(source/'meshes').mkdir()
            meshes=[]
            for i in range(2):
                uri=f'meshes/p{i}.obj'
                (source/uri).write_text(f'v {i*2} 0 0\nv {i*2+1} 0 0\nv {i*2} 1 0\nvn 0 0 1\nf 1//1 2//1 3//1\n')
                meshes.append({'uri':uri,'color':[.1,.3,.02,1],'triangles':1})
            (source/'manifest.json').write_text(json.dumps({'meshes':meshes,'colliders':[]}))
            write_world(source/'field.sdf',meshes,[],{},[])
            output=Path(temporary)/'batch'
            result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/batch_gazebo_field.py'),
                                   '--source',str(source),'--output',str(output)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            obj=(output/'meshes/batch_0.obj').read_text()
            self.assertIn('v 2 0 0',obj)
            self.assertIn('f 4//2 5//2 6//2',obj)
            self.assertEqual(sum(s.startswith('v ') for s in obj.splitlines()),6)

    def test_rotor_mass_thrust_and_controller_agree(self):
        model=neo_model()
        mass=sum(float(n.text) for n in model.findall('.//inertial/mass'))
        self.assertAlmostEqual(mass,MASS)
        motors=model.findall("plugin[@name='gz::sim::systems::MulticopterMotorModel']")
        self.assertEqual(len(motors),4)
        hover=math.sqrt(mass*9.81/(4*FORCE_CONSTANT))
        self.assertLess(hover,min(float(m.findtext('maxRotVelocity')) for m in motors))
        joints={j.attrib['name'] for j in model.findall('joint')}
        for motor in motors:self.assertIn(motor.findtext('jointName'),joints)
        self.assertEqual(sum(1 if m.findtext('turningDirection')=='ccw' else -1 for m in motors),0)

    def test_mission_covers_every_row_above_trellis(self):
        points=mission_waypoints()
        for row in range(6):
            entry=next(p for p in points if p['phase']==f'row_{row}_entry')
            exit_=next(p for p in points if p['phase']==f'row_{row}_exit')
            self.assertLess(min(entry['position'][0],exit_['position'][0]),-3.5)
            self.assertGreater(max(entry['position'][0],exit_['position'][0]),3.5)
            for p in (entry,exit_):
                self.assertAlmostEqual(p['position'][1],(row-2.5)*1.8)
                self.assertGreater(p['position'][2]-.0485/2,2.5+.5)
        self.assertEqual(points[-1]['position'][:2],[-5.2,-5.6])


if __name__=='__main__':unittest.main()
