"""Public relative-motion contract; no simulator/world pose is accepted.

Translation is the new camera origin expressed in the previous camera.
Rotation vector maps new camera coordinates into the previous camera.
Covariance order is translation (metres), then rotation (radians).
"""
from dataclasses import dataclass
import numpy as np

VERSION='relative-motion/1.0'


@dataclass(frozen=True)
class RelativeMotion:
    start_stamp_ns: int
    end_stamp_ns: int
    translation_previous_camera_m: tuple
    rotation_vector_previous_camera_rad: tuple
    covariance_6x6: tuple
    source: str = 'simulated_noisy_odometry'
    frame: str = 'previous_camera'

    def validate(self):
        if self.end_stamp_ns<=self.start_stamp_ns or self.frame!='previous_camera':
            raise ValueError('Nonmonotonic stamps or unsupported frame')
        t=np.asarray(self.translation_previous_camera_m);r=np.asarray(self.rotation_vector_previous_camera_rad)
        cov=np.asarray(self.covariance_6x6,dtype=float)
        if t.shape!=(3,) or r.shape!=(3,) or cov.shape!=(6,6):raise ValueError('Invalid dimensions')
        if not all(np.isfinite(v).all() for v in (t,r,cov)):raise ValueError('Nonfinite measurement')
        if not np.allclose(cov,cov.T) or np.linalg.eigvalsh(cov).min()<-1e-12:raise ValueError('Invalid covariance')
        return self

    def to_dict(self):
        self.validate()
        return dict(version=VERSION,start_stamp_ns=self.start_stamp_ns,end_stamp_ns=self.end_stamp_ns,
            translation_previous_camera_m=list(self.translation_previous_camera_m),
            rotation_vector_previous_camera_rad=list(self.rotation_vector_previous_camera_rad),
            covariance_6x6=[list(row) for row in self.covariance_6x6],source=self.source,frame=self.frame)

    @classmethod
    def from_dict(cls,payload):
        allowed={'version','start_stamp_ns','end_stamp_ns','translation_previous_camera_m',
            'rotation_vector_previous_camera_rad','covariance_6x6','source','frame'}
        if set(payload)!=allowed or payload['version']!=VERSION:
            raise ValueError('Unexpected fields/version; simulator pose is not a public measurement')
        return cls(**{k:v for k,v in payload.items() if k!='version'}).validate()
