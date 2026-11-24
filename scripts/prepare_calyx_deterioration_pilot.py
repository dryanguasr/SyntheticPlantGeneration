"""Freeze a tiny organ-comparison pilot, preserving the admitted plant bank."""
from pathlib import Path
import sys,copy
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from appearance_campaign import read,write,sha
from uchuva_lsystem.dataset_completion import verify_sources,owner_alive


def prepare(out):
    source=REPO/'outputs/spatial_dataset_completion_20261030'
    assert read(source/'pause_requested.json')['active']
    assert not any(owner_alive(read(source/name)) for name in ('controller_identity.json','worker_identity.json'))
    lock=verify_sources(source);pool=read(source/'dataset/pool_lock.json')
    out.mkdir(parents=True,exist_ok=False);specimens=[]
    for index,p in enumerate(pool['plants'][:2]):
        assert sha(p['plant'])==p['plant_sha256']
        plant=read(p['plant']);axes=list(plant['axes']);units=[]
        while axes:
            a=axes.pop();axes.extend(a['child_axes'])
            for n in a['nodes']:
                unit=n.get('reproductive_unit');c=unit.get('calyx') if unit else None
                if c and 2.1<=c['length_cm']/c['radius_cm']<=3.1:units.append(unit)
        unit=sorted(units,key=lambda u:u['id'])[0]
        specimens.append(dict(source_plant=p['plant'],source_plant_sha256=p['plant_sha256'],source_unit_id=unit['id'],
            original_reproductive_unit=copy.deepcopy(unit),calyx=copy.deepcopy(unit['calyx']),
            pedicel_length_cm=unit['pedicel']['length_cm'],mesh_seed=202610310+index,texture_seed=202610318+index,
            phenotype='dark_proximal' if index==0 else 'bleached_dry'))
    stages=[dict(key='mature_control',label='Madura',class_id=1,severity=0),
        dict(key='overmature_existing',label='Sobre · pajiza actual',class_id=2,severity=0),
        dict(key='overmature_early',label='Sobre · deterioro leve',class_id=2,severity=.28),
        dict(key='overmature_middle',label='Sobre · intermedio',class_id=2,severity=.58),
        dict(key='overmature_late',label='Sobre · avanzado',class_id=2,severity=.90)]
    write(out/'plan.json',dict(version='calyx-deterioration-visual-pilot/1',seed=20261031,
        source_campaign=str(source),profiles=str(source/'profiles.json'),stages=stages,specimens=specimens,
        images=4,scope='isolated calyx surface fixtures, not new admitted whole plants',
        same_base_geometry_per_specimen=True,same_camera_and_scale_across_stages=True,
        user_authorization='Contrast mature and overmature calyces, multiple observed deterioration degrees; preserve existing valid examples',
        original_examples_remain_valid=True,new_classes=False,physiological_resorption='not verified or modeled',
        interior_fruit='not instantiated in isolated calyx diagnostic; full-plant containment requires new validation before bank use',
        parameter_status='user_observation plus engineering_heuristic_pending_review'))
    paths=[REPO/'src/uchuva_lsystem/calyx_deterioration.py',REPO/'src/uchuva_lsystem/blender_calyx_deterioration.py',
        REPO/'scripts/render_calyx_deterioration_pilot.py',Path(__file__),REPO/'tests/test_calyx_deterioration.py',out/'plan.json']
    # Archive existing frozen sources by reference and verify, without editing their lock.
    files=dict(lock['files']);files.update({str(p):sha(p) for p in paths})
    write(out/'source_lock.json',dict(files=files,original_source_lock_sha256=sha(source/'source_lock.json')))
    write(out/'preservation.json',dict(generation_budget_sha256=sha(source/'budget.json'),pool_lock_sha256=sha(source/'dataset/pool_lock.json'),
        plants={p['plant']:p['plant_sha256'] for p in pool['plants']},source_lock_sha256=sha(source/'source_lock.json'),generation_remains_paused=True))
    print('Prepared two morphology-derived specimens, five states, two light conditions; no bank edits')


if __name__=='__main__':prepare(Path(sys.argv[1]).resolve())
