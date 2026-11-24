"""Paired diagnostic on an existing camera; never overwrites/counts a bank view."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import bpy
from mathutils import Matrix
import render_spatial_dataset as legacy
from render_spatial_dataset_optimized import camera_pose
from render_appearance_bank import labels_from_mask
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.blender_appearance import geometry_digest
from uchuva_lsystem.blender_capture_optimized import refresh_hidden_fruit_transforms
from uchuva_lsystem.blender_capture_dual_scene import DualSceneCaptureSession
from uchuva_lsystem.blender_capture_skies import CaptureSkyBackground


def run(root,view_id,assets,out):
    out.mkdir(parents=True,exist_ok=False);bank=root/'dataset';row=read(bank/'views'/view_id/'view.json')
    folder=bank/'scenes'/row['scene_id'];record=read(folder/'accepted.json');plan=read(folder/'capture_plan.json')
    if sha(folder/'scene.blend')!=plan['checkpoint_sha256']:raise ValueError('Checkpoint changed')
    bpy.ops.wm.open_mainfile(filepath=str(folder/'scene.blend'));legacy.configure()
    refresh_hidden_fruit_transforms(bpy.context.scene)
    if geometry_digest(bpy.context.scene)!=record['geometry_sha256']:raise ValueError('Geometry differs')
    camera=bpy.context.scene.camera;targets=[bpy.data.objects[n] for n in plan['camera_target_names']]
    aim,distance,depth=camera_pose(camera,targets,int(row['scene_id'].split('_')[-1]),int(view_id.split('_')[-1]))
    bpy.context.view_layer.update()
    error=max(abs(float(camera.matrix_world[i][j])-row['camera_matrix'][i][j]) for i in range(4) for j in range(4))
    if error>1e-5:raise ValueError('Reference camera cannot be reconstructed exactly')
    camera.matrix_world=Matrix(row['camera_matrix']);config=read(bank/'config.json')
    config['horizon_assets_manifest']=str(assets)
    with DualSceneCaptureSession(bpy.context.scene,read(root/'profiles.json'),config,
            int(row['scene_id'].split('_')[-1]),camera) as session:
        lighting=session.lighting(camera,tuple(aim),condition=row['lighting']['capture_condition'])
        lighting=CaptureSkyBackground(session).apply(row['lighting']['capture_condition'],lighting)
        session.verify_geometry();bpy.context.scene.render.filepath=str(out/'rgb.png');bpy.ops.render.render(write_still=True)
        annotation=session.mask(camera,out,width=960,height=720)
        labels,instances=labels_from_mask(annotation,record['assignments'],960,720)
        write(out/'annotations.json',annotation);(out/'labels.txt').write_text(labels,encoding='utf-8')
        session.verify_geometry()
        if geometry_digest(bpy.context.scene)!=record['geometry_sha256']:raise ValueError('Final geometry differs')
    if instances!=row['instances']:raise ValueError('Instance annotations changed on paired camera')
    if labels!=Path(row['label']).read_text(encoding='utf-8'):raise ValueError('Paired YOLO changed')
    write(out/'result.json',dict(reference_view=view_id,reference_image=row['image'],new_image=str(out/'rgb.png'),
        reference_mask=row['mask'],new_mask=annotation['path'],mask_file_sha_equal=sha(annotation['path'])==row['mask_sha256'],
        geometry_unchanged=True,camera_max_error=error,annotations_exact=True,lighting=lighting,
        diagnostic_not_counted_in_dataset=True))


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:];run(Path(args[0]).resolve(),args[1],Path(args[2]).resolve(),Path(args[3]).resolve())
