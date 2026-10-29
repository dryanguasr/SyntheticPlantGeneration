"""Pure phase-boundary contracts for an admitted-plant multidepth dataset."""
from pathlib import Path
from .nodal_automation import read,sha,unique_admissions
from .spatial_admission import validate_plan
from .nodal_repulsion import protected_anatomy
from .morphology import Plant


def admitted_pool(root,rows,target=20):
    """Inspect real audits, not an inventory or a claimed status counter."""
    valid=unique_admissions(rows)
    if len(valid)<target:return []
    accepted=[]
    for row in valid[:target]:
        f=Path(row['folder']);mesh=read(f/'final_independent_mesh.json')
        ground=read(f/'ground.json');orientation=read(f/'orientation.json');morph=read(f/'morphology.json')
        if mesh['physical_collision_count'] or mesh.get('truncated') or ground['status']!='valid' or orientation['status']!='valid' or morph['errors']:
            raise ValueError('A claimed admitted plant fails its independent audits')
        original=row['original_counts'];kept=row['counts']
        tree=Plant.from_dict(read(f/'plant.json'));raw=Plant.from_dict(read(f/'raw.json'))
        if protected_anatomy(tree)['counts']!=kept or protected_anatomy(raw)['counts']!=original:
            raise ValueError('Original or retained morphology counts differ')
        proof=validate_plan(tree)
        if proof.get('applied') and proof['original_counts']!=original:raise ValueError('Undo differs from original morphology')
        for name in ['fruits','leaves']:
            if not 0<=20*(original[name]-kept[name])<original[name]:raise ValueError('Strict original-count loss guard failed')
        if row['spatial_admission'].get('leaf_nominal_area_loss_fraction',0)>=.05:raise ValueError('Nominal foliage loss guard failed')
        accepted.append(dict(seed=row['seed'],plant=str((f/'plant.json').resolve()),plant_sha256=sha(f/'plant.json'),
                             admission=str((f/'admission.json').resolve()),admission_sha256=sha(f/'admission.json'),
                             counts=kept,original_counts=original,origin=row['origin']))
    return accepted


def depth_stratum(index):return ('near','middle','far')[index%3]


def select_scene_plants(pool,count,rng,capacity=4095):
    """Choose whole unchanged trees within the flower+calyx ID capacity."""
    for _ in range(200):
        selected=rng.sample(pool,count)
        if sum(p['counts']['calyces']+p['counts']['flowers'] for p in selected)<=capacity:
            return selected
    selected=sorted(pool,key=lambda p:p['counts']['calyces']+p['counts']['flowers'])[:count]
    if len(selected)!=count or sum(p['counts']['calyces']+p['counts']['flowers'] for p in selected)>capacity:
        raise ValueError('Whole scene plants exceed the exact reproductive-ID capacity')
    rng.shuffle(selected)
    return selected


def committed_views(folder):
    folder=Path(folder)
    exclusions=read(folder/'excluded_views.json').get('view_ids',[]) if (folder/'excluded_views.json').exists() else []
    rows=[];seen=set()
    for p in sorted(Path(folder).glob('views/*/view.json')):
        row=read(p)
        if row.get('view_id') in exclusions:continue
        if row.get('status')!='complete':continue
        for key in ['image','label','mask']:
            if sha(row[key])!=row[key+'_sha256']:raise ValueError('Changed committed view: '+str(p))
        signature=(row['scene_id'],row['camera_sha256'])
        if signature in seen:raise ValueError('Repeated camera in the same frozen scene')
        seen.add(signature);rows.append(row)
    return rows
