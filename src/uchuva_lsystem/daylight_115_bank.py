"""Frozen weather slots and exact-mask cache gates for the bounded115 bank."""
from collections import Counter,defaultdict
import copy,random,hashlib,ctypes,os
from .capture_skies import sky_condition_for_view
from .daylight_balance import balance_for_condition

VERSION='daylight115-reviewed-bank/1'
WEATHER_COUNTS={'clear_blue':69,'hazy_clear':29,'overcast':17}


def weather_slots(rows,seed=20261112):
    if len(rows)!=115 or len({r['view_id'] for r in rows})!=115:
        raise ValueError('Exactly115 distinct frozen camera slots required')
    groups=defaultdict(list)
    for r in rows:groups[r['depth_stratum']].append(r['view_id'])
    rng=random.Random(f'{seed}:weather_only');result={};remaining=Counter(WEATHER_COUNTS)
    for depth,ids in sorted(groups.items()):
        ids=sorted(ids);rng.shuffle(ids)
        if len(ids)<3:raise ValueError('Each depth needs all three weather states')
        for sky,i in zip(WEATHER_COUNTS,ids[:3]):result[i]=sky;remaining[sky]-=1
    bag=[k for k,n in remaining.items() for _ in range(n)];rng.shuffle(bag)
    free=sorted(r['view_id'] for r in rows if r['view_id'] not in result)
    result.update(zip(free,bag))
    assert Counter(result.values())==Counter(WEATHER_COUNTS)
    return result


def capture_condition(row,sky,seed=20261112):
    sid,index=int(row['scene_id'][-3:]),int(row['view_id'][-3:])
    c=sky_condition_for_view(sid,index,seed)
    rng=random.Random(f'{seed}:solar_only:{row["view_id"]}')
    c.update(sky_type=sky,diagnostic_light={'clear_blue':'field','hazy_clear':'diffuse','overcast':'shade'}[sky],
        azimuth_offset_deg=rng.uniform(-115,45),elevation_offset_deg=rng.uniform(-12,20),
        exposure_offset_ev=rng.uniform(-.12,.12),sun_angle_deg={'clear_blue':3.,'hazy_clear':9.,'overcast':18.}[sky],
        aerosol_density={'clear_blue':.025,'hazy_clear':.8,'overcast':1.}[sky],
        sky_air_density={'clear_blue':.65,'hazy_clear':.9,'overcast':1.}[sky],
        sky_ozone_density={'clear_blue':1.5,'hazy_clear':1.1,'overcast':1.}[sky],
        analytic_sky_saturation={'clear_blue':1.25,'hazy_clear':1.05,'overcast':1.}[sky],
        analytic_sky_value=.9 if sky=='clear_blue' else 1.,
        fill_energy_w=60. if sky=='clear_blue' else 80. if sky=='hazy_clear' else 18.,
        sky_schedule_version=VERSION,
        sky_provenance='engineering_heuristic; frozen69clear/29hazy/17overcast; native analytic sky and corrected ambient chroma')
    return c


def exact_mask_cache_gate(original,actual_matrix,bulk_hash,visibility_hash,expected_visibility_hash,intrinsics,expected_intrinsics):
    if actual_matrix!=original['camera_matrix']:raise ValueError('Cached mask camera differs')
    if bulk_hash!=original['bulk_geometry_sha256']:raise ValueError('Cached mask geometry differs')
    if visibility_hash!=expected_visibility_hash:raise ValueError('Cached mask visibility differs')
    if intrinsics!=expected_intrinsics:raise ValueError('Cached mask intrinsics differ')
    if original['render_config']['width']!=960 or original['render_config']['height']!=720:
        raise ValueError('Cached mask resolution differs')
    return True


def visibility_fingerprint(scene):
    rows=[]
    for o in sorted(scene.objects,key=lambda o:o.name):
        if o.type not in {'MESH','CURVE','SURFACE'}:continue
        mods=[(m.name,m.type,bool(m.show_render),getattr(m,'render_levels',None)) for m in o.modifiers]
        rows.append((o.name,bool(o.hide_render),bool(o.get('uchuva_annotation_visible',False)),
                     o.get('uchuva_semantic_class'),o.get('uchuva_reproductive_instance_id'),mods))
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def camera_intrinsics(camera):
    d=camera.data
    return {k:getattr(d,k) for k in ('type','lens','sensor_width','sensor_height','sensor_fit','shift_x','shift_y','clip_start','clip_end','ortho_scale')}


def memory_snapshot():
    if os.name!='nt':return {}
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
            ('peak_working','working','paged_peak','paged','nonpaged_peak','nonpaged','pagefile','peak_pagefile','private')]
    c=Counters();c.cb=ctypes.sizeof(c)
    ok=ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1),ctypes.byref(c),c.cb)
    result=dict(working_bytes=int(c.working),private_bytes=int(c.private)) if ok else {}
    class GlobalMemory(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(n,ctypes.c_ulonglong) for n in
            ('physical','available','pagefile','available_pagefile','virtual','available_virtual','extended')]
    g=GlobalMemory();g.length=ctypes.sizeof(g)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(g)):
        result.update(available_bytes=int(g.available),system_load_percent=int(g.load))
    return result
