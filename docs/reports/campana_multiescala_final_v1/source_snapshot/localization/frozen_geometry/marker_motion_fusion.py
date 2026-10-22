"""Marker-anchored first-order pose filter using public relative odometry only.

State maps camera coordinates to the canonical marker. Increment rotation maps
the new camera to the previous camera; translation is the new camera origin in
the previous camera. Covariance order is translation then rotation (metres, rad).
Noise settings and marker covariance require calibration; this is a pilot EKF.
"""
import cv2
import numpy as np
from .motion_observations import RelativeMotion


def skew(v):
    x,y,z=v
    return np.array([[0,-z,y],[z,0,-x],[-y,x,0]],float)


def exp(v):return cv2.Rodrigues(np.asarray(v,dtype=float))[0]


def covariance(value):
    p=np.asarray(value,float)
    if p.shape!=(6,6) or not np.isfinite(p).all() or not np.allclose(p,p.T) or np.linalg.eigvalsh(p).min()<-1e-12:
        raise ValueError('Invalid pose covariance')
    return p


def marker_projection_covariance(R_camera_from_marker, t_camera_from_marker,
                                 K, side_m, corner_sigma_px=.5):
    """Local covariance in the filter's marker-frame tangent coordinates.

    Assumes independent isotropic corner noise, not hardware calibration.
    Preserves translation/rotation coupling. This linearization describes one
    selected planar-pose mode; it cannot resolve IPPE ambiguity. Call only after
    pose selection. Degenerate geometry fails instead of fabricating certainty.
    """
    Rc=np.asarray(R_camera_from_marker,dtype=float)
    tc=np.asarray(t_camera_from_marker,dtype=float)
    K=np.asarray(K,dtype=float)
    if (Rc.shape!=(3,3) or tc.shape!=(3,) or K.shape!=(3,3)
            or not all(np.isfinite(x).all() for x in (Rc,tc,K))
            or not np.isfinite(side_m) or side_m<=0
            or not np.isfinite(corner_sigma_px) or corner_sigma_px<=0):
        raise ValueError('Invalid marker projection inputs')
    if (not np.allclose(Rc.T@Rc,np.eye(3),atol=1e-6)
            or not np.isclose(np.linalg.det(Rc),1.,atol=1e-6)
            or K[0,0]<=0 or K[1,1]<=0
            or not np.allclose(K[2],[0,0,1])):
        raise ValueError('Invalid rotation or camera intrinsics')
    h=side_m/2
    points=np.array([[-h,h,0],[h,h,0],[h,-h,0],[-h,-h,0]])
    if ((Rc@points.T).T+tc)[:,2].min()<=0:
        raise ValueError('Marker must have positive depth')
    R=Rc.T;center=-R@tc
    def project(delta):
        rotation=exp(delta[3:])@R
        camera_rotation=rotation.T
        camera_translation=-camera_rotation@(center+delta[:3])
        return cv2.projectPoints(points,cv2.Rodrigues(camera_rotation)[0],
                                 camera_translation,K,None)[0].reshape(-1)
    step=1e-6
    J=np.column_stack([(project(d*step)-project(-d*step))/(2*step)
                       for d in np.eye(6)])
    _,singular,vt=np.linalg.svd(J,full_matrices=False)
    if singular[-1]<=singular[0]*1e-10:
        raise ValueError('Degenerate marker projection')
    Q=(vt.T*((corner_sigma_px/singular)**2))@vt
    return covariance((Q+Q.T)/2)


def canonical_visual_measurements(poses, decoded_to_canonical):
    """Historical records already hold canonical poses under decoded-ID keys.

    Relabel only: applying the rigid-board transform again would corrupt them.
    Unknown decoded IDs fail closed instead of creating a new coordinate frame.
    """
    return [(decoded_to_canonical[str(decoded)], pose) for decoded, pose in poses.items()]


class MarkerMotionFusion:
    """One explicitly identified canonical marker component, never world poses."""
    def __init__(self,canonical_marker_id,gate=16.8):
        self.marker_id=canonical_marker_id;self.gate=gate;self.stamp=None
        self.R=None;self.t=None;self.P=None;self.rejections=[]

    def predict(self,measurement):
        m=RelativeMotion.from_dict(measurement)
        if self.stamp is None:raise ValueError('A decoded visual marker must initialize the component')
        if m.start_stamp_ns!=self.stamp:raise ValueError('Motion chain has a gap or out-of-order increment')
        delta=self.R@np.asarray(m.translation_previous_camera_m)
        F=np.eye(6);F[:3,3:]=-skew(delta)
        G=np.zeros((6,6));G[:3,:3]=self.R;G[3:,3:]=self.R
        self.P=F@self.P@F.T+G@covariance(m.covariance_6x6)@G.T
        self.t=self.t+delta
        self.R=self.R@exp(m.rotation_vector_previous_camera_rad)
        self.stamp=m.end_stamp_ns

    def correct(self,stamp_ns,marker_id,R_camera_from_marker,t_camera_from_marker,pose_covariance):
        if marker_id!=self.marker_id:raise ValueError('Marker relation must be publicly calibrated before fusion')
        Rc=np.asarray(R_camera_from_marker,float);tc=np.asarray(t_camera_from_marker,float)
        if Rc.shape!=(3,3) or tc.shape!=(3,) or not np.isfinite(Rc).all() or not np.isfinite(tc).all():raise ValueError('Invalid marker pose')
        if not np.allclose(Rc.T@Rc,np.eye(3),atol=1e-5) or np.linalg.det(Rc)<.999:raise ValueError('Improper rotation')
        R=Rc.T;t=-R@tc;Q=covariance(pose_covariance)
        # Covariance is explicitly in canonical-marker tangent coordinates.
        if self.stamp is None:
            self.R=R;self.t=t;self.P=Q.copy();self.stamp=stamp_ns;return True
        if stamp_ns!=self.stamp:raise ValueError('Visual and predicted timestamps must agree')
        residual=np.r_[t-self.t,cv2.Rodrigues(R@self.R.T)[0].ravel()]
        S=self.P+Q;distance=float(residual@np.linalg.pinv(S)@residual)
        if distance>self.gate:
            self.rejections.append(dict(stamp_ns=stamp_ns,reason='marker_innovation_gate',mahalanobis_squared=distance));return False
        K=self.P@np.linalg.pinv(S);correction=K@residual
        self.t+=correction[:3];self.R=exp(correction[3:])@self.R
        A=np.eye(6)-K;self.P=A@self.P@A.T+K@Q@K.T
        self.P=(self.P+self.P.T)/2
        return True

    def camera_from_marker(self):
        if self.stamp is None:return None
        return dict(stamp_ns=self.stamp,marker_id=self.marker_id,R=self.R.T.tolist(),
            t=(-self.R.T@self.t).tolist(),canonical_pose_covariance=self.P.tolist(),
            source='RGB_ArUco_plus_relative_motion',version='marker-motion-fusion/1.0',
            uncertainty_status='first_order_pilot_not_calibrated')
