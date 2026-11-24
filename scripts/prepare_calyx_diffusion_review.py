"""Bake a new coherent vein/albedo/normal texture set for a small review."""
from pathlib import Path
import sys,copy,json,hashlib
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src')]
import numpy as np
from PIL import Image
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.calyx_diffusion_texture import VERSION,SNAPSHOTS,vein_graph,simulate
from uchuva_lsystem.texture_assets import _vein_mask,_normal_map,_relief_height,texture_preset


def prepare(out):
    prior=REPO/'outputs/calyx_approval_samples_20261031';plan=copy.deepcopy(read(prior/'plan.json'))
    source=Path(plan['source']);assert read(source/'pause_requested.json')['active']
    baseline=read(prior/'baseline.json')
    for p,item in baseline['locks'].items():
        assert sha(p)==item['sha256'],p
        if item.get('files'):
            for f,h in read(p)['files'].items():assert sha(f)==h,f
    out.mkdir(exist_ok=True,parents=True);assert not (out/'source_lock.json').exists()
    textures=out/'textures';textures.mkdir(exist_ok=False)
    n=512;seed=20261111;height,orders,graph=vein_graph(n,seed)
    vein=Image.frombytes('L',(n,n),_vein_mask(height));vein.save(textures/'veins.png')
    small=np.asarray(vein.resize((256,256),Image.Resampling.BILINEAR),dtype=float)/255
    snapshots=simulate(small)
    field_stats={str(step):dict(mean=float(field.mean()),proximal=float(field[-32:].mean()),distal=float(field[:32].mean()))
                 for step,field in snapshots.items()}
    write(out/'diffusion_stats.json',dict(version=VERSION,graph=graph,snapshots=field_stats))
    print('DIFFUSION_FIELDS_COMPLETE',field_stats,flush=True)
    v=np.asarray(vein,dtype=float)/255
    rng=np.random.default_rng(seed);tiny=rng.random((9,9),dtype=np.float32)
    tile=Image.fromarray(np.concatenate((tiny,tiny,tiny),axis=1)).resize((n*3,n),Image.Resampling.BICUBIC)
    coherent=np.clip(np.asarray(tile,dtype=float)[:,n:2*n],0,1)
    grain=rng.normal(0,.009,(n,n));variation=1+.10*(coherent-.5)+grain
    stages={'historical':0,'light':600,'intermediate':1400,'extensive':2600,'advanced_diffused':4200,
            'dry_bleached':2600,'control_with_optional_proximal_patch':600}
    presets={};names=read(source/'profiles.json')['materials']['candidate']['class_presets']
    for cid,preset in enumerate(names):
        base=np.array(((176,185,108),(193,190,117),(211,188,131))[cid],dtype=float)
        structure=np.clip(v**.55*(.65 if cid!=0 else .55),0,.8)
        veins_color=np.array((83,47,73),dtype=float)
        carrier=base[None,None,:]*(1-structure[:,:,None])+veins_color[None,None,:]*structure[:,:,None]
        carrier*=variation[:,:,None]
        normal_path=textures/f'{preset}_normal.png'
        relief=_relief_height(texture_preset(preset),height,orders)
        Image.frombytes('RGB',(n,n),_normal_map(relief,n,.6,'calyx')).save(normal_path)
        items={}
        for name,step in stages.items():
            p=np.asarray(Image.fromarray(snapshots[step].astype(np.float32)).resize((n,n),Image.Resampling.BILINEAR))
            strength=p*(.73+.18*coherent)
            target=np.stack((78+16*coherent,48+16*coherent,66+13*coherent),axis=2)
            rgb=carrier*(1-strength[:,:,None])+target*strength[:,:,None]
            if name=='dry_bleached':rgb=rgb*.65+np.array((193,179,147))*.35
            path=textures/f'{preset}_{name}_albedo.png'
            Image.fromarray(np.clip(rgb,0,255).astype('uint8')).save(path)
            rough=textures/f'{preset}_{name}_roughness.png'
            Image.fromarray(np.clip((.92+.035*p)*255,0,255).astype('uint8')).save(rough)
            items[name]=dict(albedo=str(path),albedo_sha256=sha(path),roughness=str(rough),roughness_sha256=sha(rough),step=step)
        presets[preset]=dict(stages=items,normal=str(normal_path),normal_sha256=sha(normal_path))
    manifest=textures/'manifest.json'
    write(manifest,dict(version=VERSION,resolution=n,solver_resolution=256,seed=seed,presets=presets,graph=graph,
        parameters=dict(dt=.12,dx='0.02+0.55*network',dy='0.03+1.25*network',activation='(0.005+0.32*network)*a*(1-a)',
            pigment='(0.005+0.032*network)*a*(1-p)',source='proximal collar only',uv='v0 proximal, PNG bottom'),
        color_status='engineering choices after visual comparison with real train; not measured intrinsic albedo',
        shared_graph='one frozen network for controlled stage comparison; not population variability'))
    plan.update(version=VERSION,vein_maps_manifest=str(manifest),previous_review=str(REPO/'outputs/calyx_vein_spread_review_20261111'),
        authorization='user requested self-comparison against real Madura/Sobremadura and rule-based diffusion texture generation',
        scope='four review renders only; generation/training pause retained')
    write(out/'plan.json',plan);write(out/'baseline.json',baseline)
    files=dict(read(prior/'source_lock.json')['files'])
    for name in ('src/uchuva_lsystem/calyx_diffusion_texture.py','src/uchuva_lsystem/blender_calyx_diffusion_texture.py',
        'src/uchuva_lsystem/calyx_mottling.py','scripts/prepare_calyx_diffusion_review.py',
        'scripts/render_calyx_diffusion_review.py','scripts/report_calyx_diffusion_review.py','tests/test_calyx_diffusion_texture.py'):
        p=REPO/name;files[str(p)]=sha(p)
    for p in list((REPO/'assets/textures/current').glob('*'))+list(textures.glob('*'))+[out/'plan.json']:
        if p.is_file():files[str(p)]=sha(p)
    write(out/'source_lock.json',dict(version=VERSION,files=files))
    print(out,flush=True)


if __name__=='__main__':prepare(Path(sys.argv[1]).resolve())
