"""Reproducible continuous camera distances; independent of plant/weather RNG."""
import math,random


def sample_capture_distance(span,scene_index,view_index,seed=20261030):
    if not math.isfinite(span) or span<=0:raise ValueError('Positive finite focus span required')
    references={name:max(2.,min(100.,span*960*50/(36*pixels)))
                for name,pixels in [('near',48.),('middle',24.),('far',10.)]}
    rng=random.Random(f'{seed}:continuous_distance:{scene_index}:{view_index}')
    segment='near_to_middle' if rng.random()<.7 else 'middle_to_far'
    low,high=(references['near'],references['middle']) if segment=='near_to_middle' else (references['middle'],references['far'])
    distance=rng.uniform(low,high)
    # Labels describe the realized distance after drawing it. They no longer
    # select three exact camera positions.
    depth='near' if distance<(references['near']+references['middle'])/2 else (
        'middle' if distance<(references['middle']+references['far'])/2 else 'far')
    return dict(version='continuous_distance/1',seed=seed,reference_distances_bu=references,
        segment=segment,segment_probabilities={'near_to_middle':.7,'middle_to_far':.3},
        distribution='uniform within selected segment',distance_bu=distance,
        distance_m=.1*distance,depth_stratum=depth,collapsed_segment=low==high,
        definition='distance from camera to selected calyx bounding-box center; image-framing reference anchors, not plant constraints')


def continuous_camera_pose(camera,targets,scene_index,view_index):
    from mathutils import Vector
    rng=random.Random(20261029+scene_index*1000+view_index);focus=rng.choice(targets)
    center=sum((focus.matrix_world@Vector(v) for v in focus.bound_box),Vector())/8
    span=min(float(d) for d in focus.dimensions if d>0)
    sample=sample_capture_distance(span,scene_index,view_index);distance=sample['distance_bu']
    az=rng.uniform(-math.pi*.56,-math.pi*.44);el=rng.uniform(.05,.28)
    camera.location=center+Vector((math.cos(az),math.sin(az),el)).normalized()*distance
    aim=center+Vector((rng.uniform(-.08,.08)*distance,0,rng.uniform(-.06,.06)*distance))
    camera.rotation_euler=(aim-camera.location).to_track_quat('-Z','Y').to_euler()
    sample.update(focus_object=focus.name,focus_center_bu=list(center),aim_bu=list(aim),
        actual_camera_to_focus_bu=(camera.location-center).length,
        actual_camera_to_aim_bu=(camera.location-aim).length)
    return aim,sample
