import math
import unittest
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from uchuva_gazebo.field import write_world
from uchuva_gazebo.neo import neo_model, mission_waypoints, MASS, FORCE_CONSTANT


class NeoTests(unittest.TestCase):
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
