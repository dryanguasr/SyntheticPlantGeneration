"""Runtime command ownership, finite observations, fixed settling and rate caps."""
import copy
from pathlib import Path
import sys
import threading
import types
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from harvest_gripper_control import GripperPositionControl,move_gripper,prepare_gripper,ramp_reference


def description():
    joints=[]
    for name,parent,child,group in (('arm','base','housing','arm'),('driver','housing','left','gripper'),
        ('follower','housing','right','passive'),('jaw','left','jaw_link','passive'),('wheel','base','wheel_link','drive')):
        joints.append({'name':name,'parent':parent,'child':child,'type':'revolute','group':group,
                       'limits':{'lower':-.4,'upper':.4,'velocity':1}})
    gains={'p_gain':.2,'i_gain':0,'d_gain':.01,'cmd_min':-.02,'cmd_max':.02,'command_velocity':.2}
    return {'namespace':'/test','joints':joints,'control':{'gripper':{'driver':gains},'arm':{'arm':{}},
        'drive':{'joints':{'wheel':{}}}},'gear_couplings':[{'driver':'driver','follower':'follower','ratio':-1}]}


class FakePilot:
    def __init__(self,data=None,forced_velocity=None):
        self.data=data or description();self.resolved_robot=types.SimpleNamespace(sha256='fixture',to_dict=lambda:copy.deepcopy(self.data))
        self.Double=lambda:types.SimpleNamespace(data=0);self.reference=0;self.sent=[];self.advertisements=[]
        def advertise(topic,_type):
            self.advertisements.append(topic)
            def publish(msg):self.reference=msg.data;self.sent.append(msg.data);return True
            return types.SimpleNamespace(publish=publish)
        self.node=types.SimpleNamespace(advertise=advertise);self.condition=threading.Condition()
        self.manifest={'robot_task':{'gripper_open_positions':{'driver':.1}}};self.phase='initial';self.logs=[]
        self.all_joints={j['name']:0 for j in self.data['joints']};self.forced_velocity=forced_velocity
        self.state={'sim_time':0};self.joint_time=0;self._update(0)
    def _update(self,t):
        old=self.all_joints['driver'];dt=t-self.state['sim_time'];self.state={'sim_time':t};self.joint_time=t
        self.all_joints.update(driver=self.reference,follower=-self.reference,jaw=self.reference/2)
        velocity=(self.reference-old)/dt if dt else 0
        self.robot_observation={'robot_spec_sha256':'fixture','sim_time':t,'joints':[
            {'name':name,'position':value,'velocity':self.forced_velocity if self.forced_velocity is not None else
                velocity if name=='driver' else -velocity if name=='follower' else velocity/2 if name=='jaw' else 0,
             'position_available':True,'velocity_available':True} for name,value in self.all_joints.items()]}
    def set_phase(self,phase):self.phase=phase
    def snapshot(self):return self.state
    def _line(self,name,row):self.logs.append((name,row))
    def wait(self,predicate,*,simulation_timeout,wall_timeout,action):
        self.deadlines=(simulation_timeout,wall_timeout);start=self.state['sim_time']
        while self.state['sim_time']-start<=simulation_timeout:
            action(self.state)
            if predicate(self.state):return self.state
            self._update(round(self.state['sim_time']+.02,10))
        raise TimeoutError('Frozen simulation timeout')


class GripperControlTests(unittest.TestCase):
    def test_ramp_never_exceeds_declared_velocity_or_overshoots(self):
        self.assertAlmostEqual(ramp_reference(0,.1,.2,.1),.02)
        self.assertAlmostEqual(ramp_reference(.099,.1,.2,.1),.1)
        self.assertAlmostEqual(ramp_reference(.1,-.1,.2,.1),.08)
        self.assertEqual(ramp_reference(.1,0,.2,0),.1)
        for args in ((0,0,0,.1),(0,0,.1,-.1),(0,float('nan'),.1,.1)):
            with self.assertRaises(ValueError):ramp_reference(*args)

    def test_one_pid_publisher_cached_and_settled_from_native_velocities(self):
        pilot=FakePilot();result=move_gripper(pilot)
        self.assertEqual(pilot.advertisements,['/test/gripper/driver/cmd_pos'])
        self.assertIs(prepare_gripper(pilot),prepare_gripper(pilot))
        self.assertEqual(pilot.deadlines,(12.,300))
        self.assertGreaterEqual(result['settled_seconds'],.2-1e-12)
        self.assertEqual(set(result['observed_positions_rad']),{'driver','follower','jaw'})
        self.assertTrue(all(b-a<=.2*.02+1e-12 for a,b in zip(pilot.sent,pilot.sent[1:])))
        self.assertTrue(all(row['kind']=='gripper_position' and row['phase']=='gripper_open'
            and not row['passive_joints_commanded'] for _,row in pilot.logs))

    def test_position_alone_never_passes_velocity_settling(self):
        pilot=FakePilot(forced_velocity=.02)
        with self.assertRaises(TimeoutError):move_gripper(pilot)
        self.assertEqual(pilot.deadlines[0],12.)

    def test_invalid_targets_never_publish(self):
        for targets in ({'driver':float('nan')},{'driver':.5},{'wheel':0},{'driver':0,'wheel':0}):
            pilot=FakePilot()
            with self.assertRaises(ValueError):move_gripper(pilot,targets)
            self.assertEqual(pilot.sent,[])

    def test_follower_pid_and_ambiguous_driver_are_rejected(self):
        for mutate in (lambda d:d['control']['gripper'].update(follower=copy.deepcopy(d['control']['gripper']['driver'])),
                       lambda d:d['control']['arm'].update(driver={}),
                       lambda d:d['control']['arm'].update(jaw={}),
                       lambda d:d['control']['gripper']['driver'].update(command_velocity=2)):
            data=description();mutate(data)
            with self.assertRaises(ValueError):GripperPositionControl(FakePilot(data))

    def test_missing_stale_nonfinite_and_outside_limits_fail_closed(self):
        mutations=(lambda p:p.all_joints.pop('jaw'),lambda p:setattr(p,'joint_time',-.2),
            lambda p:p.robot_observation.update(sim_time=-.2),
            lambda p:p.robot_observation['joints'][0].update(velocity_available=False),
            lambda p:p.robot_observation['joints'][0].update(velocity=float('inf')),
            lambda p:p.robot_observation['joints'][0].update(velocity=1.1),
            lambda p:p.all_joints.update(jaw=.6))
        for mutate in mutations:
            pilot=FakePilot();controller=GripperPositionControl(pilot);mutate(pilot)
            with self.assertRaises((ValueError,RuntimeError)):controller.move()
            self.assertEqual(pilot.sent,[])


if __name__=='__main__':unittest.main()
