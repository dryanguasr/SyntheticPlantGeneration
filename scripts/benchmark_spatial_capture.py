"""Small paired capture benchmark, isolated from completed campaign outputs.

Run with Blender --background --python ... -- MODE CAMPAIGN BENCHMARK.
The prepare phase rebuilds and independently audits one existing scene recipe;
capture phases reopen the exact saved scene, cameras and lighting schedule.
"""
from pathlib import Path
import sys
import time
import random
import math
import ctypes
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
import bpy
from mathutils import Vector
import render_spatial_dataset as legacy
from uchuva_lsystem.nodal_automation import read, write, sha, awake_seconds
from uchuva_lsystem.appearance_profiles import resolved_profile
from uchuva_lsystem.blender_appearance import apply_profile, geometry_digest
from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations
from render_appearance_bank import labels_from_mask
from uchuva_lsystem.capture_plan import profiles_for_condition,CaptureJournal


class Timings:
    def __init__(self, path):
        self.path = path
        self.rows = []

    def call(self, stage, function, *args, **kwargs):
        start = awake_seconds()
        result = function(*args, **kwargs)
        self.rows.append(dict(stage=stage, active_seconds=awake_seconds()-start))
        write(self.path, dict(stages=self.rows))
        print('TIMING', self.rows[-1], flush=True)
        return result


def prepare(campaign, output):
    output.mkdir(parents=True, exist_ok=False)
    bank = output/'dataset'; bank.mkdir()
    for name in ('config.json', 'pool_lock.json', 'source_lock.json'):
        write(bank/name, read(campaign/'dataset'/name))
    config = read(bank/'config.json')
    config['benchmark_only'] = True
    write(bank/'config.json', config)
    profiles = read(campaign/'profiles.json')
    pool = read(bank/'pool_lock.json')['plants']
    lock = read(bank/'source_lock.json')
    for path, expected in lock['files'].items():
        if sha(path) != expected:
            raise ValueError('Historical source/input differs: '+path)
    timer = Timings(output/'prepare_timings.json')
    result = timer.call('build_and_audit_scene', legacy.build_scene,
                        campaign, bank, 13, pool, profiles)
    if result is None:
        raise ValueError('Benchmark scene failed physical admission')
    record, camera, objects = result
    config = read(bank/'config.json')
    front = {p['seed'] for j,p in enumerate(record['plants'])
             if j % config['columns'] == config['columns']//2 and j//config['columns'] < 2}
    targets = [o for o in objects if o.get('uchuva_semantic_class') == 'calyx'
               and o.get('uchuva_plant_id') in {'plant_'+str(seed) for seed in front}]
    schedule = []
    for index, light in enumerate(('field', 'diffuse', 'shade')):
        rng = random.Random(20261029+13000+index)
        focus = rng.choice(targets)
        center = sum((focus.matrix_world@Vector(v) for v in focus.bound_box), Vector())/8
        depth = ('near', 'middle', 'far')[index]
        span = min(float(d) for d in focus.dimensions if d > 0)
        distance = max(2., min(100., span*960*50/(36*{'near':48.,'middle':24.,'far':10.}[depth])))
        az = rng.uniform(-math.pi*.56, -math.pi*.44); el = rng.uniform(.05,.28)
        camera.location = center+Vector((math.cos(az),math.sin(az),el)).normalized()*distance
        aim = center+Vector((rng.uniform(-.08,.08)*distance,0,rng.uniform(-.06,.06)*distance))
        camera.rotation_euler = (aim-camera.location).to_track_quat('-Z','Y').to_euler()
        bpy.context.view_layer.update()
        schedule.append(dict(index=index,depth=depth,diagnostic_light=light,
            location=list(camera.location),rotation=list(camera.rotation_euler),aim=list(aim),
            lighting=resolved_profile(profiles,'LT',light)))
    write(output/'schedule.json', schedule)
    write(output/'scene_record.json', record)
    write(output/'profiles.json', profiles)
    timer.call('save_audited_scene', bpy.ops.wm.save_as_mainfile, filepath=str(output/'audited_scene.blend'))
    write(output/'preparation_complete.json',dict(plants_unchanged=True,physical_admission=True,
          source_campaign=str(campaign),scene_index=13,scene_sha256=sha(output/'audited_scene.blend'),
          pool_lock_sha256=sha(campaign/'dataset/pool_lock.json'),
          schedule_sha256=sha(output/'schedule.json'),quality=dict(width=960,height=720,samples=12,denoise=True)))


def capture(campaign, output, mode):
    for path,expected in read(output/'benchmark_source_lock.json')['files'].items():
        if sha(path)!=expected:raise ValueError('Benchmark source/input changed: '+path)
    folder = output/mode; folder.mkdir(exist_ok=False)
    timer = Timings(folder/'timings.json')
    started = awake_seconds()
    timer.call('load_audited_scene', bpy.ops.wm.open_mainfile, filepath=str(output/'audited_scene.blend'))
    legacy.configure()
    bpy.context.view_layer.update()
    from uchuva_lsystem.blender_capture_optimized import refresh_hidden_fruit_transforms
    timer.call('refresh_hidden_fruit_transforms',refresh_hidden_fruit_transforms,bpy.context.scene)
    scene = bpy.context.scene; camera = scene.camera
    record = read(output/'scene_record.json'); profiles = read(output/'profiles.json')
    schedule = read(output/'schedule.json'); config = read(output/'dataset/config.json')
    expected = record['geometry_sha256']
    if timer.call('initial_full_geometry_guard',geometry_digest,scene) != expected:
        raise ValueError('Saved geometry differs')
    session = None
    # Include the actual old growing-manifest write cost at the current bank size.
    # Copies live only in the benchmark, never in the completed dataset.
    history=read(campaign/'dataset/manifest.json')['views']
    journal_bank=folder/'journal';journal=CaptureJournal(journal_bank)
    journal.paths=[str((campaign/'dataset/views'/r['view_id']/'view.json').resolve()) for r in history]
    journal.identities={r['view_id'] for r in history}
    if mode == 'optimized':
        from uchuva_lsystem.blender_capture_optimized import CaptureSession
        session = timer.call('prepare_capture_session',CaptureSession,scene,profiles,config,13,camera)
    rows=[]
    try:
        for view in schedule:
            out = folder/f"view_{view['index']:03d}"; out.mkdir()
            start = awake_seconds()
            camera.location = view['location']; camera.rotation_euler = view['rotation']
            condition=view.get('condition')
            if session:
                lighting = timer.call('lighting',session.lighting,camera,view['aim'],view['diagnostic_light'],condition)
                timer.call('geometry_guard_before',session.verify_geometry)
            else:
                vp,light=profiles_for_condition(profiles,condition) if condition else (profiles,view['diagnostic_light'])
                lighting = timer.call('lighting',apply_profile,vp,'LT',camera,view['aim'],light)
                lighting['camera_background']=legacy.camera_background(config,13)
                if condition:lighting['capture_condition']=condition
                bpy.context.view_layer.update()
                if timer.call('geometry_guard_before',geometry_digest,scene) != expected:raise ValueError('Geometry changed')
            scene.render.filepath=str(out/'rgb.png')
            timer.call('rgb_render',bpy.ops.render.render,write_still=True)
            annotation=timer.call('mask_and_stats',session.mask if session else render_crisp_calyx_annotations,
                                  camera,out,width=960,height=720)
            labels,instances=timer.call('labels',labels_from_mask,annotation,record['assignments'],960,720)
            (out/'labels.txt').write_text(labels,encoding='utf-8')
            timer.call('annotation_write',write,out/'annotations.json',annotation)
            if session:timer.call('geometry_guard_after',session.verify_geometry)
            elif timer.call('geometry_guard_after',geometry_digest,scene) != expected:raise ValueError('Annotation changed geometry')
            row=dict(index=view['index'],depth=view['depth'],diagnostic_light=view['diagnostic_light'],
                active_seconds=awake_seconds()-start,instances=instances,lighting=lighting,
                camera_matrix=[list(r) for r in camera.matrix_world],geometry_sha256=expected)
            timer.call('view_record_write',write,out/'view.json',row)
            if mode=='baseline':
                history.append(row)
                timer.call('growing_manifest_write',write,folder/'manifest.json',dict(views=history,complete_images=len(history)))
            else:
                # The journal writes per-view commits + a small count/path index.
                commit_folder=journal_bank/'views'/f"view_{view['index']:03d}"
                commit_row=dict(row,status='complete',view_id=commit_folder.name,
                    image=str(out/'rgb.png'),mask=annotation['path'],label=str(out/'labels.txt'))
                for k in ('image','mask','label'):commit_row[k+'_sha256']=sha(commit_row[k])
                timer.call('incremental_manifest_write',journal.commit,commit_folder,commit_row)
            row['active_seconds']=awake_seconds()-start
            rows.append(row)
            write(folder/'progress.json',dict(completed=len(rows),views=rows))
        if timer.call('final_full_geometry_guard',geometry_digest,scene) != expected:
            raise ValueError('Final geometry differs')
        if session:timer.call('consolidate_manifest_once',journal.consolidate)
    finally:
        if session:session.close()
    write(folder/'complete.json',dict(mode=mode,total_active_seconds=awake_seconds()-started,
          views=rows,quality=dict(width=960,height=720,samples=12,denoise=True),scene_sha256=sha(output/'audited_scene.blend')))


if __name__ == '__main__':
    mode, campaign, output = sys.argv[sys.argv.index('--')+1:]
    campaign, output = Path(campaign).resolve(), Path(output).resolve()
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        if mode == 'prepare':prepare(campaign, output)
        else:capture(campaign, output, mode)
    except Exception:
        output.mkdir(parents=True,exist_ok=True)
        write(output/(mode+'_failure.json'),dict(traceback=traceback.format_exc()));raise
    finally:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
