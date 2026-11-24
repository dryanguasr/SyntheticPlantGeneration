"""Contracts for a goal-limited completion campaign, independent of Blender.

Historical images/trees remain immutable references. Only closed, hash-checked
new scenes join the combined bank. No training entry point is provided.
"""
from pathlib import Path
import ctypes
import os
from .nodal_automation import read,write,sha,awake_seconds
from .spatial_dataset import committed_views,admitted_pool


def process_identity(pid=None,handle=None):
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    creation=ctypes.c_ulonglong();ended=ctypes.c_ulonglong();system=ctypes.c_ulonglong();user=ctypes.c_ulonglong()
    process=kernel.GetCurrentProcess() if handle is None else handle
    if not kernel.GetProcessTimes(wintypes.HANDLE(process),ctypes.byref(creation),ctypes.byref(ended),ctypes.byref(system),ctypes.byref(user)):
        raise ctypes.WinError(ctypes.get_last_error())
    return dict(pid=os.getpid() if pid is None else int(pid),creation_tick=str(creation.value))


def owner_alive(record):
    """Access denied is unknown, never evidence that a lock is obsolete."""
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    handle=kernel.OpenProcess(0x1000,False,int(record['pid']))
    if not handle:
        error=ctypes.get_last_error()
        if error in (87,1168):return False
        raise ctypes.WinError(error)
    try:
        code=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(wintypes.HANDLE(handle),ctypes.byref(code)):raise ctypes.WinError(ctypes.get_last_error())
        return code.value==259 and process_identity(record['pid'],handle)['creation_tick']==str(record['creation_tick'])
    finally:kernel.CloseHandle(wintypes.HANDLE(handle))


def verify_sources(root):
    lock=read(Path(root)/'source_lock.json')
    for name,expected in lock['files'].items():
        if sha(name)!=expected:raise ValueError('Frozen source/input changed: '+name)
    if sha(Path(root)/'source_lock.json')!=sha(Path(root)/'dataset/source_lock.json'):
        raise ValueError('Dataset source lock alias differs')
    return lock


def baseline_rows(root,verify=True):
    root=Path(root);lock=read(root/'baseline_lock.json');rows=[]
    for item in lock['views']:
        if verify:
            if sha(item['view_record'])!=item['view_record_sha256']:raise ValueError('Inherited view record changed')
            for key in ('image','mask','label'):
                if sha(item[key])!=item[key+'_sha256']:raise ValueError('Inherited pair changed')
        rows.append(read(item['view_record']))
    return rows


def new_rows(root,closed_only=True):
    root=Path(root);bank=root/'dataset';rows=committed_views(bank)
    result=[];scenes={}
    for row in rows:
        folder=bank/'scenes'/row['scene_id'];marker=folder/'capture_complete.json'
        if closed_only and not marker.exists():continue
        if marker.exists():
            # Reports can exceed 40 MB per scene. Validate once per call,
            # while still checking every view against that scene's closure.
            if row['scene_id'] not in scenes:
                closure=read(marker)
                if not closure.get('geometry_unchanged'):raise ValueError('Scene closure guard failed')
                accepted=read(folder/'accepted.json');mesh=read(folder/'mesh.json')
                if accepted['geometry_sha256']!=closure['geometry_sha256'] or mesh['physical_collision_count']:
                    raise ValueError('Scene admission or geometry differs')
                if read(folder/'ground.json')['status']!='valid' or read(folder/'orientation.json')['status']!='valid':
                    raise ValueError('Scene ground/orientation admission failed')
                scenes[row['scene_id']]=closure
            if row['geometry_sha256']!=scenes[row['scene_id']]['geometry_sha256']:
                raise ValueError('Scene/view geometry mismatch')
        result.append(row)
    return result


def verify_pool(source):
    source=Path(source);pool=read(source/'dataset/pool_lock.json')['plants']
    audited=admitted_pool(source,read(source/'results.json')['rows'])
    if len(pool)!=20 or {p['seed']:p['plant_sha256'] for p in pool}!={p['seed']:p['plant_sha256'] for p in audited}:
        raise ValueError('Twenty immutable, independently admitted plants required')
    for p in pool:
        if sha(p['plant'])!=p['plant_sha256'] or sha(p['admission'])!=p['admission_sha256']:
            raise ValueError('Frozen plant or admission changed')
    return pool


def select_next_scene(root):
    """Resume a real checkpoint first; an inventory is not an admission."""
    root=Path(root);bank=root/'dataset';config=read(bank/'config.json')
    folders=sorted((bank/'scenes').glob('scene_*'))
    for folder in folders:
        if (folder/'rejected.json').exists() or (folder/'capture_complete.json').exists():continue
        if all((folder/name).exists() for name in ('accepted.json','capture_plan.json','scene.blend')):
            return int(folder.name.split('_')[-1]),True
        raise ValueError('Incomplete scene construction requires preserved recovery: '+str(folder))
    index=max([int(p.name.split('_')[-1]) for p in folders],default=config['first_scene_index']-1)+1
    return index,False


def preserve_unbuilt(root,recovery):
    """Move only incomplete construction with no committed image; inside root."""
    root=Path(root).resolve();bank=root/'dataset'
    for scene in sorted((bank/'scenes').glob('scene_*')):
        if any((scene/n).exists() for n in ('rejected.json','capture_complete.json')):continue
        if all((scene/n).exists() for n in ('accepted.json','capture_plan.json','scene.blend')):continue
        views=list((bank/'views').glob(scene.name+'_view_*'))
        if any((v/'view.json').exists() for v in views):raise ValueError('Cannot relocate construction with committed views')
        for source in [scene]+views:
            target=Path(recovery)/source.parent.name/source.name
            if root not in source.resolve().parents or root not in target.resolve().parents:raise ValueError('Recovery path outside campaign')
            target.parent.mkdir(parents=True,exist_ok=True);source.rename(target)


def publish_index(root,rows):
    root=Path(root);baseline=read(root/'baseline_lock.json')
    target=read(root/'config.json')['target_total']
    count=len(baseline['views'])+len(rows)
    if count>target:raise ValueError('Target exceeded')
    entries=[dict(view_id=p['view_id'],view_record=p['view_record'],origin='inherited') for p in baseline['views']]
    entries += [dict(view_id=r['view_id'],view_record=str(root/'dataset/views'/r['view_id']/'view.json'),origin='optimized') for r in rows]
    write(root/'combined_index.json',dict(schema='uchuva.combined_capture_index/1',complete_images=count,
        inherited_images=len(baseline['views']),optimized_images=len(rows),target_images=target,
        entries=entries,training_started=False,human_sample_review='pending'))
    return count
