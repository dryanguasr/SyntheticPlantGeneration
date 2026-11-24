"""Derive a camera-only renderer from the frozen morphology interpreter."""
import copy
import random
from augmentation_pilot import ROOT, REPO, read, write, sha


def prepare():
    previous=REPO/'outputs/multiscale_dataset_20261020'
    out=ROOT/'renders';out.mkdir(exist_ok=False)
    (out/'source_snapshot').mkdir()
    source=previous/'source_snapshot/v142_materials.py'
    (out/'source_snapshot/v142_materials.py').write_bytes(source.read_bytes())
    scenes=[];rng=random.Random(20261022)
    real=read(ROOT/'geometry/real_train.json')['rows']
    for original in read(previous/'protocol.json')['scenes']:
        if original['split']!='train':continue
        s=copy.deepcopy(original);samples=[]
        for index in range(240):
            g=real[rng.randrange(len(real))]['geometry']
            aspect=g['width']/g['height']
            width=1280 if aspect>=1 else max(320,round(1280*aspect/32)*32)
            height=1280 if aspect<1 else max(320,round(1280/aspect/32)*32)
            samples.append(dict(target_plant=s['plants'][index%len(s['plants'])]['instance_id'],
                target_index=index//2, distance_m=[.6,1.0,1.5][index%3], lens_mm=70,
                yaw_deg=[-100,-50,0,50,100,160][index%6]+rng.uniform(-10,10),
                elevation_deg=rng.uniform(-10,20), target_height_bu=5,
                width=width,height=height))
        s.update(views=240,camera_samples=samples);scenes.append(s)
    write(out/'protocol.json',dict(version='geometry-matched-cameras/1',scenes=scenes,
        max_views=480,calibration_views=12,geometry_or_material_changes=False,
        source_renderer_sha256=sha(previous/'render_multiscale.py')))
    code=(previous/'render_multiscale.py').read_text()
    code=code.replace("target=Vector(entry['position'])+Vector((0,0,sample['target_height_bu']))", """candidates=sorted([o for o in plant_meshes if o.get('uchuva_semantic_class')=='calyx' and str(o.get('uchuva_reproductive_instance_id','')).startswith(entry['instance_id']+':')],key=lambda o:o.name)
  assert candidates,'No target calyces'
  obj=candidates[sample['target_index']%len(candidates)]
  target=sum((obj.matrix_world@Vector(c) for c in obj.bound_box),Vector())/8
  camera.data.lens=sample['lens_mm']
  scene.render.resolution_x=sample['width'];scene.render.resolution_y=sample['height']""")
    code=code.replace("width=1280,height=720", "width=sample['width'],height=sample['height']")
    code=code.replace("camera_metadata(camera,1280,720)", "camera_metadata(camera,sample['width'],sample['height'])")
    code=code.replace("else:raise RuntimeError('No clear camera pose; preserve scene and review camera recipe')", """else:
   write(folder/'rejected_pose.json',dict(reason='No clear pose',sample=sample))
   completed+=1
   if a.limit and completed>=a.limit:break
   continue""")
    code=code.replace("if (folder/'capture.json').exists():continue", "if (folder/'capture.json').exists() or (folder/'rejected_pose.json').exists():continue")
    # Budget checked between frames; the controller also enforces a process timeout.
    code=code.replace("for view in range(config['views']):", "for view in range(config['views']):\n  if time.time() >= protocol['deadline']:break")
    protocol=read(out/'protocol.json');protocol['deadline']=read(ROOT/'budget.json')['render_deadline'];write(out/'protocol.json',protocol)
    (out/'render.py').write_text(code,encoding='utf-8')
    write(out/'source_manifest.json',dict(files={str(previous/'render_multiscale.py'):sha(previous/'render_multiscale.py'),str(source):sha(source)},
        morphology={p['path']:p['sha256'] for s in scenes for p in s['plants']},
        frozen_interpreter=str(REPO/'outputs/frozen_field_pilot_20261019/frozen')))


if __name__=='__main__':prepare()
