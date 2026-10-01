"""Pure frame conversion and bounded mission commands (engineering heuristics)."""
import math


def world_to_body(vector, quaternion_xyzw):
    """R(q).T @ v; Gazebo's Lee controller rotates this back into world space."""
    x,y,z,w=quaternion_xyzw
    norm=math.sqrt(x*x+y*y+z*z+w*w)
    if not math.isfinite(norm) or norm<1e-9:
        raise ValueError('Invalid attitude quaternion')
    x,y,z,w=(v/norm for v in (x,y,z,w))
    vx,vy,vz=vector
    return ((1-2*(y*y+z*z))*vx+2*(x*y+w*z)*vy+2*(x*z-w*y)*vz,
            2*(x*y-w*z)*vx+(1-2*(x*x+z*z))*vy+2*(y*z+w*x)*vz,
            2*(x*z+w*y)*vx+2*(y*z-w*x)*vy+(1-2*(x*x+y*y))*vz)


def bounded_command(delta, yaw_error, previous, dt):
    """World velocity + body yaw rate; cap vector acceleration at 0.5 m/s²."""
    desired=[max(-.85,min(.85,1.3*v)) for v in delta]
    horizontal=math.hypot(*desired[:2])
    if horizontal>.85:
        desired[:2]=[v*.85/horizontal for v in desired[:2]]
    desired[2]=max(-.5,min(.6,desired[2]))
    change=[v-p for v,p in zip(desired,previous[:3])]
    length=math.sqrt(sum(v*v for v in change))
    limit=.5*max(0,min(dt,.1))
    factor=min(1,limit/length) if length else 1
    velocity=[p+factor*d for p,d in zip(previous[:3],change)]
    yaw_rate=max(-.5,min(.5,1.5*yaw_error))
    yaw_step=.6*max(0,min(dt,.1))
    return (*velocity,previous[3]+max(-yaw_step,min(yaw_step,yaw_rate-previous[3])))


def angular_rate_from_poses(previous, current, dt):
    """Interval body angular velocity, invariant under q -> -q representation.

    Kept separate from the raw odometry twist, which exhibited sign-flip spikes
    in the installed Gazebo runtime. This is a sampled estimate, not an IMU.
    """
    if dt<=0:raise ValueError('Positive sample interval required')
    normalized=[]
    for q in (previous,current):
        norm=math.sqrt(sum(v*v for v in q))
        if not math.isfinite(norm) or norm<1e-9:raise ValueError('Invalid quaternion')
        normalized.append(tuple(v/norm for v in q))
    x,y,z,w=normalized[1];px,py,pz,pw=normalized[0]
    delta=(w*-px+x*pw-y*pz+z*py,
           w*-py+x*pz+y*pw-z*px,
           w*-pz-x*py+y*px+z*pw,
           w*pw+x*px+y*py+z*pz)
    if delta[3]<0:delta=tuple(-v for v in delta)
    sine=math.sqrt(sum(v*v for v in delta[:3]))
    if sine<1e-12:return (0,0,0)
    factor=2*math.atan2(sine,delta[3])/(sine*dt)
    return world_to_body(tuple(v*factor for v in delta[:3]),normalized[1])


def flight_metrics(samples, tail_seconds=5):
    if not samples:
        return {'samples':0,'hover_settled':False}
    tail=[s for s in samples if s['t']>=samples[-1]['t']-tail_seconds]
    def rms(values):return math.sqrt(sum(v*v for v in values)/len(values))
    result={'samples':len(samples),'tail_seconds':tail_seconds,
        'max_tilt_deg':max(math.degrees(math.acos(max(-1,min(1,
            math.cos(s['roll'])*math.cos(s['pitch']))))) for s in samples),
        'tail_roll_rms_deg':math.degrees(rms([s['roll'] for s in tail])),
        'tail_pitch_rms_deg':math.degrees(rms([s['pitch'] for s in tail])),
        'tail_max_position_error_m':max(s['position_error_m'] for s in tail),
        'max_roll_pitch_rate_rad_s':max(math.hypot(*s['angular_velocity'][:2]) for s in samples)}
    result['hover_settled']=(samples[-1]['t']-samples[0]['t']>=10 and
        result['tail_roll_rms_deg']<1 and result['tail_pitch_rms_deg']<1 and
        result['tail_max_position_error_m']<.05)
    result['attitude_envelope_pass']=result['max_tilt_deg']<15
    return result
