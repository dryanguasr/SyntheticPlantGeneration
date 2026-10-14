"""Explicit image-frustum crop; not a full-plant instance segmentation."""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_reconstruction.geometry import read_colmap_points, write_colmap_points


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cloud",type=Path,required=True)
    parser.add_argument("--poses",type=Path,required=True)
    parser.add_argument("--sfm-report",type=Path,required=True)
    parser.add_argument("--image",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--rect",type=float,nargs=4,required=True,metavar=("X0","Y0","X1","Y1"))
    parser.add_argument("--depth",type=float,nargs=2,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    poses=json.loads(args.poses.read_text())["images"]
    pose=next(p for p in poses if p["image"]==args.image.name)
    report=json.loads(args.sfm_report.read_text())
    component=next(c for c in report["components"] if args.image.name in c["registered_names"] and c["registered_images"]>10)
    camera=next(c for c in component["cameras"] if c["camera_id"]==pose["camera_id"])
    if camera["model"]!="SIMPLE_RADIAL": raise ValueError("Crop projection supports SIMPLE_RADIAL only")
    f,cx,cy,k=camera["params"]
    values=read_colmap_points(args.cloud)
    xyz=np.column_stack([values[n] for n in ("x","y","z")])
    extrinsic=np.asarray(pose["cam_from_world"])
    camera_xyz=xyz@extrinsic[:,:3].T+extrinsic[:,3]
    xy=camera_xyz[:,:2]/camera_xyz[:,2,None]
    uv=xy*(1+k*(xy**2).sum(axis=1,keepdims=True))*f+[cx,cy]
    x0,y0,x1,y1=args.rect;near,far=args.depth
    keep=(uv[:,0]>=x0)&(uv[:,0]<=x1)&(uv[:,1]>=y0)&(uv[:,1]<=y1)&(camera_xyz[:,2]>=near)&(camera_xyz[:,2]<=far)
    if keep.sum()<100:raise ValueError("Too few foreground points")
    write_colmap_points(args.output/"analytical_crop.ply",values[keep])
    image=cv2.imdecode(np.fromfile(args.image,dtype=np.uint8),cv2.IMREAD_COLOR)
    cv2.rectangle(image,(round(x0),round(y0)),(round(x1),round(y1)),(0,200,255),3)
    for u,v in uv[keep][::max(1,int(keep.sum()/1500))]:
        cv2.circle(image,(round(u),round(v)),1,(0,255,255),-1)
    cv2.putText(image,f'Foreground crop; depth {near:g}-{far:g} arbitrary units',(20,35),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,0),4)
    cv2.putText(image,f'Foreground crop; depth {near:g}-{far:g} arbitrary units',(20,35),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,255,255),1)
    ok,encoded=cv2.imencode('.jpg',image);(args.output/'crop_evidence.jpg').write_bytes(encoded.tobytes())
    # Camera-aligned right / forward / up. This is NOT an estimated gravity frame.
    rotation=np.array([[1,0,0],[0,0,1],[0,-1,0]])@extrinsic[:,:3]
    rotated=xyz[keep]@rotation.T
    low,high=rotated.min(axis=0),rotated.max(axis=0)
    translation=-np.array([(low[0]+high[0])/2,(low[1]+high[1])/2,low[2]-.2])
    value=dict(script_version="reconstruction-pilot/0.1",seed=20261001,parameter_preset="pilot_2h",
        source_cloud=str(args.cloud),source_points=len(values),retained_points=int(keep.sum()),
        reference_image=args.image.name,rectangle_pixels=args.rect,depth_interval_arbitrary=args.depth,
        crop_method="manual_image_frustum_and_depth_separation",plant_instance_segmentation=False,
        scale_status="uncalibrated",post_pair=None,physical_measurements=None,
        transform=dict(rotation=rotation.tolist(),translation=translation.tolist(),uniform_scale=1.0,
            formula="gazebo_xyz = rotation @ reconstruction_xyz + translation",
            axes="reference camera right, forward, up; gravity not estimated",
            scale_meaning="one arbitrary reconstruction unit mapped to one SDF metre for import diagnostics only; not physical scale"),
        descriptors=dict(extents_arbitrary=(high-low).tolist(),
            aspect_relative_width=((high-low)/(high[0]-low[0])).tolist(),
            definition="Axis-aligned bounding box of the partial frustum crop, in the reference camera frame; not plant height or volume"))
    (args.output/'crop_manifest.json').write_text(json.dumps(value,indent=2)); print(json.dumps(value))


if __name__=="__main__":main()
