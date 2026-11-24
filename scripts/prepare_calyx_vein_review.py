"""Freeze a small vein-origin review and generate registered UV arrival maps."""
from pathlib import Path
import sys,copy,math
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src')]
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.calyx_vein_spread import VERSION,arrival_field
from PIL import Image


def prepare(out):
    previous=REPO/'outputs/calyx_approval_samples_20261031'
    plan=copy.deepcopy(read(previous/'plan.json'));source=Path(plan['source'])
    assert read(source/'pause_requested.json')['active']
    baseline=read(previous/'baseline.json')
    for p,record in baseline['locks'].items():
        assert sha(p)==record['sha256'],p
        if record.get('files'):
            for f,h in read(p)['files'].items():assert sha(f)==h,f
    out.mkdir(parents=True,exist_ok=False);maps=out/'vein_maps';maps.mkdir()
    resolution=512;scale=1.4;presets={}
    profiles=read(source/'profiles.json')
    for preset in profiles['materials']['candidate']['class_presets']:
        path=REPO/'assets/textures/current'/f'{preset}_vein_mask.png'
        image=Image.open(path).convert('L').resize((resolution,resolution),Image.Resampling.BILINEAR)
        signal=[v/255 for v in image.getdata()]
        field=arrival_field(signal,resolution,resolution)
        pixels=bytearray()
        for i,(time,vein) in enumerate(zip(field,signal)):
            y,x=divmod(i,resolution);u=(x+.5)/resolution;v=1-(y+.5)/resolution
            window=.5+.25*math.sin(math.tau*(4*u+1.7*v))+.25*math.sin(math.tau*(9*u-3.1*v)+.7)
            pixels.extend((round(255*min(1,time/scale)),round(255*vein),round(255*window)))
        dest=maps/f'{preset}_arrival_rgb.png'
        Image.frombytes('RGB',(resolution,resolution),bytes(pixels)).save(dest)
        near=[t for i,t in enumerate(field) if signal[i]>=.2 and i//resolution>resolution*.8]
        far=[t for i,t in enumerate(field) if signal[i]>=.2 and i//resolution<resolution*.2]
        presets[preset]=dict(source_mask=str(path),source_mask_sha256=sha(path),map=str(dest),map_sha256=sha(dest),
            mean_proximal_seed_time=sum(near)/len(near),mean_distal_seed_time=sum(far)/len(far),
            max_arrival=max(field),vein_seed_fraction=sum(v>=.2 for v in signal)/len(signal))
        print('VEIN_MAP_COMPLETE',preset,flush=True)
    manifest=maps/'manifest.json'
    write(manifest,dict(version=VERSION,resolution=resolution,arrival_scale=scale,presets=presets,
        uv_convention='v0 proximal, v1 distal; PNG top row corresponds to v1',
        channels=dict(R='vein-origin arrival divided by arrival_scale',G='original registered vein mask',B='continuous intensity modulation; not an independent seed')))
    plan.update(version='vein-origin-visual-review/1',material_revision=VERSION,vein_maps_manifest=str(manifest),
        authorization='user observation: pigmentation starts on veins and near pedicel, then expands to neighboring tissue and distally',
        same_organ_progression='same surface network across stages, drying/compression parameters retained',
        source_observation_status='user_field_observation; numerical rates engineering heuristics; physiology unverified')
    write(out/'plan.json',plan);write(out/'baseline.json',baseline)
    files=dict(read(previous/'source_lock.json')['files'])
    for f in ('src/uchuva_lsystem/calyx_vein_spread.py','src/uchuva_lsystem/blender_calyx_vein_spread.py',
        'src/uchuva_lsystem/calyx_mottling.py','scripts/prepare_calyx_vein_review.py',
        'scripts/render_calyx_vein_review.py','scripts/report_calyx_vein_review.py','tests/test_calyx_vein_spread.py'):
        p=REPO/f;files[str(p)]=sha(p)
    for p in list((REPO/'assets/textures/current').glob('*'))+list(maps.glob('*'))+[out/'plan.json']:
        if p.is_file():files[str(p)]=sha(p)
    write(out/'source_lock.json',dict(version=VERSION,files=files,previous_review=str(previous)))
    print(out,flush=True)


if __name__=='__main__':prepare(Path(sys.argv[1]).resolve())
