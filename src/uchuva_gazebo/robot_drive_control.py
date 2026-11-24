"""Bounded wheel references with optional ideal-native chassis yaw feedback.

This module issues references only. Native wheel controllers still apply
finite forces. Native model poses are privileged simulator observations, not
calibrated odometry. Historical profiles omit ``base_feedback``.
"""
from __future__ import annotations

from collections import deque
import math


def finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label+' must be a finite number')
    return float(value)


def bounded(value, limit):
    return max(-limit, min(limit, value))


class DriveReferenceController:
    """Single owner of reference ramps; caller serializes observe/step calls."""

    def __init__(self, drive):
        self.drive = drive
        self.feedback = drive.get('base_feedback', {})
        self.enabled = self.feedback.get('enabled', False)
        self.observations = deque()
        self.previous = (0., 0., 0.)

    def observe_pose(self, stamp, pose):
        if not self.enabled:
            return
        stamp = finite(stamp, 'Native pose time')
        if stamp < 0 or not isinstance(pose, (list, tuple)) or len(pose) != 7:
            raise ValueError('Native base observation requires nonnegative time and xyz+quaternion')
        values = tuple(finite(v, 'Native base pose') for v in pose)
        x, y, z, w = values[3:]
        if abs(x*x+y*y+z*z+w*w-1) > 1e-6:
            raise ValueError('Native base quaternion must be unit length')
        angle = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
        if self.observations:
            previous = self.observations[-1]
            if stamp < previous[0]:
                raise ValueError('Native base observation clock regressed')
            if stamp == previous[0]:
                if values != previous[3]:
                    raise ValueError('Conflicting native base poses at the same timestamp')
                return
            unwrapped = previous[2]+math.atan2(math.sin(angle-previous[1]), math.cos(angle-previous[1]))
        else:
            unwrapped = angle
        self.observations.append((stamp, angle, unwrapped, values))
        cutoff = stamp-self.feedback['window_s']
        while len(self.observations) > 2 and self.observations[1][0] < cutoff:
            self.observations.popleft()

    def _rate(self, stamp):
        if not self.observations:
            raise ValueError('Native yaw-rate observation is not available')
        latest = self.observations[-1]
        age = stamp-latest[0]
        if age < -1e-9:
            raise ValueError('Native yaw-rate observation is from the future')
        if age > self.feedback['max_observation_age_s']+1e-12:
            raise ValueError('Native yaw-rate observation is stale')
        beginning = latest[0]-self.feedback['window_s']
        if len(self.observations) < 2 or self.observations[0][0] > beginning+1e-12:
            raise ValueError('Native yaw-rate observation window is incomplete')
        before, after = self.observations[0], self.observations[1]
        for a, b in zip(self.observations, list(self.observations)[1:]):
            if a[0] <= beginning+1e-12:
                before, after = a, b
            if b[0] >= beginning-1e-12:
                break
        fraction = max(0., min(1., (beginning-before[0])/(after[0]-before[0])))
        initial = before[2]+fraction*(after[2]-before[2])
        rate = (latest[2]-initial)/self.feedback['window_s']
        return rate, latest[0], max(0., age), beginning

    def step(self, linear, angular, stamp):
        """Reject nonzero motion without valid feedback; zero twist always brakes.

        A rejected request does not mutate the ramp. Call ``step(0,0,stamp)``
        to apply the same bounded stop ramp when handling that rejection.
        """
        linear, angular, stamp = (finite(linear, 'Linear target'), finite(angular, 'Angular target'), finite(stamp, 'Command time'))
        if stamp < self.previous[0]:
            raise ValueError('Drive command clock regressed')
        drive = self.drive
        target_v = bounded(linear, drive['max_linear_velocity'])
        target_w = bounded(angular, drive['max_angular_velocity'])
        record = {'schema_version': 'native-base-drive-reference/1.0', 'sim_time': stamp,
            'requested_linear_m_s': linear, 'requested_angular_rad_s': angular,
            'target_linear_m_s': target_v, 'target_angular_rad_s': target_w,
            'feedback_enabled': self.enabled, 'observation_source': 'native_model_pose_ideal' if self.enabled else None,
            'observed_yaw_rate_rad_s': None, 'observation_time': None, 'observation_age_s': None,
            'observation_window_start': None, 'feedback_correction_rad_s': 0.,
            'feedback_status': 'disabled', 'zero_twist_feedback_bypass': False}
        corrected = target_w
        if self.enabled:
            if target_v == 0 and target_w == 0:
                record.update(feedback_status='zero_twist_braking', zero_twist_feedback_bypass=True)
            else:
                rate, when, age, beginning = self._rate(stamp)
                correction = self.feedback['p_gain']*(target_w-rate)
                corrected += correction
                record.update(feedback_status='active', observed_yaw_rate_rad_s=rate,
                    observation_time=when, observation_age_s=age, observation_window_start=beginning,
                    feedback_correction_rad_s=correction)
        desired_w = bounded(corrected, drive['max_angular_velocity'])
        dt = stamp-self.previous[0]
        v = self.previous[1]+bounded(target_v-self.previous[1], drive['max_linear_acceleration']*dt)
        w = self.previous[2]+bounded(desired_w-self.previous[2], drive['max_angular_acceleration']*dt)
        wheel_refs = {}
        for side, sign in (('left_joints', -1), ('right_joints', 1)):
            speed = (v+sign*w*drive['wheel_separation_m']/2)/drive['wheel_radius_m']
            for name in drive[side]:
                wheel_refs[name] = bounded(speed*drive['joint_signs'][name], drive['joints'][name]['command_velocity'])
        self.previous = (stamp, v, w)
        record.update(compensated_angular_before_limit_rad_s=corrected,
            compensated_angular_rad_s=desired_w, angular_feedback_clipped=desired_w != corrected,
            linear_m_s=v, angular_rad_s=w, ramp_dt_s=dt,
            wheel_velocity_references_rad_s=wheel_refs)
        return record
