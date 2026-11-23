"""Single-driver gripper references with native passive-joint observation.

This helper never commands followers or passive coordinates. Its fixed 12 s
simulation deadline and .01 rad / .01 rad/s / .2 s settling contract match the
mechanism acceptance thresholds; a blocked jaw is a timeout, not a reason to
increase gains, teleport a joint, or loosen the tolerances.
"""
from __future__ import annotations
from collections.abc import Mapping
import math

POSITION_TOLERANCE_RAD = .01
VELOCITY_TOLERANCE_RAD_S = .01
SETTLE_SECONDS = .2
SIMULATION_TIMEOUT_SECONDS = 12.
MAX_STATE_AGE_SECONDS = .1


def _finite(value, label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(label+' must be a finite number')
    return float(value)


def ramp_reference(previous, target, velocity_limit, dt):
    previous,target,velocity_limit,dt=(_finite(x,name) for x,name in
        ((previous,'previous reference'),(target,'target'),(velocity_limit,'command velocity'),(dt,'simulation dt')))
    if velocity_limit<=0 or dt<0:raise ValueError('Positive velocity and nonnegative elapsed time required')
    return previous+max(-velocity_limit*dt,min(velocity_limit*dt,target-previous))


class GripperPositionControl:
    """Own only the one gripper PID topic; observe the entire native mechanism."""
    def __init__(self,pilot):
        if getattr(pilot,'resolved_robot',None) is None:
            raise ValueError('A resolved CAD robot is required for gripper control')
        self.pilot=pilot;self.data=pilot.resolved_robot.to_dict()
        controllers=self.data['control'].get('gripper',{})
        if len(controllers)!=1:raise ValueError('Exactly one gripper PID driver is required')
        self.driver,self.gains=next(iter(controllers.items()))
        self.by_name={j['name']:j for j in self.data['joints']}
        if self.driver not in self.by_name or self.by_name[self.driver]['group']!='gripper' or self.by_name[self.driver]['type']!='revolute':
            raise ValueError('Gripper PID must command the declared revolute driver')
        other=set(self.data['control'].get('arm',{}))|set(self.data['control'].get('drive',{}).get('joints',{}))
        if self.driver in other:raise ValueError('Multiple controllers address the gripper driver')
        couplings=[row for row in self.data.get('gear_couplings',[]) if row['driver']==self.driver]
        if len(couplings)!=1:raise ValueError('One explicit passive gear coupling is required')
        self.follower=couplings[0]['follower']
        if self.follower not in self.by_name or self.by_name[self.follower]['group']!='passive' or self.follower in controllers or self.follower in other:
            raise ValueError('The gear follower must remain passive without a PID')
        self.rate=_finite(self.gains.get('command_velocity'),'command velocity')
        if self.rate<=0 or self.rate>self.by_name[self.driver]['limits']['velocity']:
            raise ValueError('Gripper command velocity exceeds its declared limit')
        for name in ('p_gain','i_gain','d_gain','cmd_min','cmd_max'):_finite(self.gains.get(name),name)
        if self.gains['p_gain']<=0 or not self.gains['cmd_min']<0<self.gains['cmd_max']:
            raise ValueError('A finite force PID with both torque signs is required')
        # Sibling passive branches at the same gripper housing belong to this
        # mechanism, including both closure auxiliaries. Do not confuse the
        # upstream wrist/arm or suspension coordinates with gripper joints.
        reachable={self.by_name[self.driver]['parent']};self.mechanism=set()
        changed=True
        while changed:
            changed=False
            for joint in self.data['joints']:
                if joint['parent'] in reachable and joint['child'] not in reachable:
                    reachable.add(joint['child']);changed=True
                    if joint['type']!='fixed':self.mechanism.add(joint['name'])
        if self.follower not in self.mechanism or any(self.by_name[n]['group'] not in ('gripper','passive') for n in self.mechanism):
            raise ValueError('Ambiguous gripper mechanism boundary')
        if (self.mechanism-{self.driver}) & (other|set(controllers)):
            raise ValueError('Passive gripper coordinates cannot have actuator controllers')
        self.expected={j['name'] for j in self.data['joints'] if j['type']!='fixed'}
        self.topic=self.data['namespace']+'/gripper/'+self.driver+'/cmd_pos'
        # Cache the helper on NativePilot through prepare_gripper; no competing
        # publisher is created for a second open/close action.
        self.publisher=pilot.node.advertise(self.topic,pilot.Double)
        if not self.publisher:raise RuntimeError('Cannot advertise gripper driver topic')
        self.last_observation_time=None

    def _targets(self,targets):
        if targets is None:targets=self.pilot.manifest.get('robot_task',{}).get('gripper_open_positions')
        if not isinstance(targets,Mapping) or self.driver not in targets or set(targets)-self.mechanism:
            raise ValueError('Targets must name the gripper driver and only its observed mechanism')
        result={name:_finite(value,'gripper target '+name) for name,value in targets.items()}
        for name,value in result.items():
            limits=self.by_name[name]['limits']
            if not limits['lower']<=value<=limits['upper']:raise ValueError('Gripper target outside limits: '+name)
        return result

    def _observe(self,state):
        now=_finite(state.get('sim_time'),'simulation time')
        with self.pilot.condition:
            positions=dict(self.pilot.all_joints)
            joint_time=self.pilot.joint_time
            row=getattr(self.pilot,'robot_observation',None)
        if set(positions)!=self.expected:raise RuntimeError('Incomplete all_joints observation')
        for name,value in positions.items():
            value=_finite(value,'observed '+name);limits=self.by_name[name]['limits']
            if value<limits['lower']-1e-9 or value>limits['upper']+1e-9:
                raise RuntimeError('Observed joint outside declared limits: '+name)
        if joint_time is None or abs(now-_finite(joint_time,'joint timestamp'))>MAX_STATE_AGE_SECONDS:
            raise RuntimeError('Stale or future joint-state observation')
        if not isinstance(row,Mapping) or row.get('robot_spec_sha256')!=self.pilot.resolved_robot.sha256:
            raise RuntimeError('Missing native gripper observation or wrong robot hash')
        stamp=_finite(row.get('sim_time'),'native observation timestamp')
        if abs(now-stamp)>MAX_STATE_AGE_SECONDS:
            raise RuntimeError('Stale or future native gripper velocity observation')
        if self.last_observation_time is not None and stamp<self.last_observation_time:
            raise RuntimeError('Native gripper observation clock regressed')
        joints=row.get('joints')
        if not isinstance(joints,list) or len(joints)!=len(self.expected) or {j.get('name') for j in joints}!=self.expected:
            raise RuntimeError('Incomplete or duplicate native joint observations')
        observed={}
        for joint in joints:
            if not joint.get('position_available') or not joint.get('velocity_available'):
                raise RuntimeError('Native joint position/velocity unavailable: '+joint['name'])
            position=_finite(joint.get('position'),'native position');velocity=_finite(joint.get('velocity'),'native velocity')
            limits=self.by_name[joint['name']]['limits']
            if position<limits['lower']-1e-9 or position>limits['upper']+1e-9:
                raise RuntimeError('Native joint position outside limits: '+joint['name'])
            if abs(velocity)>limits['velocity']+1e-9:
                raise RuntimeError('Native joint velocity outside limits: '+joint['name'])
            observed[joint['name']]={'position':position,'velocity':velocity}
        self.last_observation_time=stamp
        return stamp,observed

    def move(self,targets=None,*,phase='gripper_open'):
        targets=self._targets(targets);pilot=self.pilot
        pilot.set_phase(phase)
        initial=pilot.snapshot()
        if initial is None:raise RuntimeError('No native state for gripper command')
        _,observed=self._observe(initial)
        reference=observed[self.driver]['position'];last_time=initial['sim_time']
        stable_since=None;last_settle_stamp=None

        def advance(state):
            nonlocal reference,last_time
            self._observe(state)
            now=state['sim_time']
            reference=ramp_reference(reference,targets[self.driver],self.rate,now-last_time);last_time=now
            message=pilot.Double();message.data=reference
            if not self.publisher.publish(message):raise RuntimeError('Gripper reference publication failed')
            with pilot.condition:
                pilot._line('commands',{'kind':'gripper_position','phase':pilot.phase,'sim_time':now,
                    'joint':self.driver,'position_rad':reference,'target_position_rad':targets[self.driver],
                    'command_velocity_rad_s':self.rate,'passive_joints_commanded':False})

        def settled(state):
            nonlocal stable_since,last_settle_stamp
            stamp,current=self._observe(state)
            if last_settle_stamp is not None and stamp<=last_settle_stamp:return False
            last_settle_stamp=stamp
            valid=(abs(reference-targets[self.driver])<=1e-12 and
                all(abs(current[name]['position']-target)<=POSITION_TOLERANCE_RAD for name,target in targets.items()) and
                all(abs(current[name]['velocity'])<=VELOCITY_TOLERANCE_RAD_S for name in self.mechanism))
            stable_since=(stamp if stable_since is None else stable_since) if valid else None
            return stable_since is not None and stamp-stable_since>=SETTLE_SECONDS-1e-12

        result=pilot.wait(settled,simulation_timeout=SIMULATION_TIMEOUT_SECONDS,wall_timeout=300,action=advance)
        stamp,current=self._observe(result)
        return {'sim_time':stamp,'driver':self.driver,'target_positions_rad':targets,
                'observed_positions_rad':{n:current[n]['position'] for n in sorted(self.mechanism)},
                'observed_velocities_rad_s':{n:current[n]['velocity'] for n in sorted(self.mechanism)},
                'settled_seconds':stamp-stable_since,'position_tolerance_rad':POSITION_TOLERANCE_RAD,
                'velocity_tolerance_rad_s':VELOCITY_TOLERANCE_RAD_S}


def prepare_gripper(pilot):
    controller=getattr(pilot,'gripper_position_control',None)
    if controller is None:
        controller=GripperPositionControl(pilot);pilot.gripper_position_control=controller
    return controller


def move_gripper(pilot,targets=None,*,phase='gripper_open'):
    return prepare_gripper(pilot).move(targets,phase=phase)
