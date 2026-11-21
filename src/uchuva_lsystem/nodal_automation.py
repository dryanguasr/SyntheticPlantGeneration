"""Pure contracts for the bounded nodal review campaign (no training)."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import time
from .execution_budget import awake_seconds


def read(path):
    for attempt in range(10):
        try:return json.loads(Path(path).read_text(encoding='utf-8'))
        except (PermissionError,json.JSONDecodeError):
            if attempt==9:raise
            time.sleep(.05)


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.writing')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    for attempt in range(10):
        try:temporary.replace(path);return
        except PermissionError:
            if attempt==9:raise
            time.sleep(.05)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def active_elapsed(budget,now=None):
    now=awake_seconds() if now is None else now
    if now<budget['awake_started_seconds']-1:raise RuntimeError('Awake clock reset; explicit cumulative-budget recovery required')
    intervals=sorted((max(budget['awake_started_seconds'],r['start']),min(now,r['end'])) for r in budget.get('excluded_intervals',[]))
    merged=[]
    for start,end in intervals:
        if end<=start:continue
        if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(merged[-1][1],end))
        else:merged.append((start,end))
    excluded=sum(end-start for start,end in merged)
    return max(0.,now-budget['awake_started_seconds']-excluded)


def remaining(budget,now=None):return max(0.,budget['limit_active_seconds']-active_elapsed(budget,now))


def stop_reason(budget,count,now=None):
    if count>=budget['target_new_valid_plants']:return 'target_valid_plants_reached'
    if remaining(budget,now)<=0:return 'active_time_limit_reached'
    return None


def mesh_objective(mesh):
    """Comparable complete mesh states; proximity remains a warning."""
    return (int(mesh['physical_collision_count']),int(mesh['clearance_violation_count']))


def physically_admitted(mesh,ground,orientation,morphology,anatomy_before,anatomy_after):
    return (mesh['physical_collision_count']==0 and ground['status']=='valid'
            and orientation['status']=='valid' and not morphology['errors']
            and anatomy_before==anatomy_after)


def unique_admissions(rows):
    identities=set();seeds=set();accepted=[]
    for row in rows:
        if row.get('status')!='admitted':continue
        if row['anatomy_sha256'] in identities or row['seed'] in seeds:continue
        identities.add(row['anatomy_sha256']);seeds.add(row['seed']);accepted.append(row)
    return accepted


def candidate_seeds(preferred=()):
    seen=set()
    for seed in (2026102602,*preferred):
        if isinstance(seed,bool) or not isinstance(seed,int):raise ValueError('Seed queue requires integer seeds')
        if seed not in seen:yield seed;seen.add(seed)
    seed=2026102700
    while True:
        if seed not in seen:yield seed
        seed+=1
