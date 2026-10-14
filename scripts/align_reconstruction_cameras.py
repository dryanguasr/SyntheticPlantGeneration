"""Align a recovered extension using shared camera centers, retaining diagnostics."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pycolmap

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_reconstruction.geometry import read_colmap_points


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--target',type=Path,required=True)
    parser.add_argument('--crop',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-error',type=float,default=.1)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    source=pycolmap.Reconstruction(args.source)
    target=pycolmap.Reconstruction(args.target)
    sim3=pycolmap.align_reconstructions_via_proj_centers(source,target,args.max_error)
    if sim3 is None:raise ValueError('No robust alignment from common camera centers')
    source.transform(sim3)
    native=args.output/'sparse';native.mkdir()
    source.write(native);source.write_text(native)
    target_images={i.name:i for i in target.images.values() if i.has_pose}
    crop=read_colmap_points(args.crop)
    center=np.column_stack([crop[n] for n in ('x','y','z')]).mean(axis=0)
    reference=target_images[sorted(target_images)[0]].projection_center()-center
    reference/=np.linalg.norm(reference)
    residuals=[];poses=[];directions=[]
    for image_id in source.reg_image_ids():
        image=source.images[image_id]
        poses.append(dict(image_id=image_id,image=image.name,camera_id=image.camera_id,
            center=image.projection_center().tolist(),cam_from_world=image.cam_from_world().matrix().tolist()))
        if image.name in target_images:
            old=target_images[image.name]
            relative=image.cam_from_world().matrix()[:,:3]@old.cam_from_world().matrix()[:,:3].T
            residuals.append(dict(image=image.name,center_error=float(np.linalg.norm(image.projection_center()-old.projection_center())),
                rotation_error_degrees=float(np.degrees(np.arccos(np.clip((np.trace(relative)-1)/2,-1,1))))))
        else:
            direction=image.projection_center()-center
            angle=np.degrees(np.arccos(np.clip(np.dot(direction,reference)/np.linalg.norm(direction),-1,1)))
            directions.append(dict(image=image.name,angle_from_first_front_camera_degrees=float(angle)))
    metadata=dict(script_version='reconstruction-pilot/0.2',seed=20261001,parameter_preset='camera_center_alignment',units='arbitrary')
    (native/'poses.json').write_text(json.dumps(dict(**metadata,images=poses),indent=2))
    report=dict(**metadata,source=str(args.source),target=str(args.target),
        similarity_matrix=sim3.matrix().tolist(),ransac_max_error_arbitrary=args.max_error,
        common_cameras=residuals,new_camera_angles=directions,
        interpretation='Alignment evidence from shared cameras; angle about partial crop center is not proof of complete opposite-side geometry')
    (args.output/'alignment_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(common=len(residuals),new=len(directions),
        median_center_error=float(np.median([r['center_error'] for r in residuals])),
        max_center_error=max(r['center_error'] for r in residuals),
        median_rotation_error_degrees=float(np.median([r['rotation_error_degrees'] for r in residuals])),
        max_new_angle=max(r['angle_from_first_front_camera_degrees'] for r in directions))))


if __name__=='__main__':main()
