"""Bake a controlled texture refinement; never edit frozen prior maps."""
from pathlib import Path
import sys,copy
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src')]
import numpy as np
from PIL import Image
from array import array
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.calyx_dry_refinement import VERSION,SNAPSHOTS,vein_graph,simulate,dry_fibres,color_surface
from uchuva_lsystem.texture_assets import _vein_mask,_normal_map,_relief_height,texture_preset


def prepare(out):
    prior=REPO/'outputs/calyx_diffusion_review_20261111/revisions/profile_interpretation_03'
    for p,h in read(prior/'source_lock.json')['files'].items():assert sha(p)==h,p
    plan=copy.deepcopy(read(prior/'plan.json'));source=Path(plan['source']);assert read(source/'pause_requested.json')['active']
    baseline=read(prior/'baseline.json')
    for p,item in baseline['locks'].items():
        assert sha(p)==item['sha256'],p
        if item.get('files'):
            for f,h in read(p)['files'].items():assert sha(f)==h,f
    out.mkdir(parents=True,exist_ok=False);textures=out/'textures';textures.mkdir()
    n=512;seed=20261111;height,orders,graph=vein_graph(n,seed)
    vein=Image.frombytes('L',(n,n),_vein_mask(height));vein.save(textures/'veins.png')
    v=np.asarray(vein,dtype=float)/255;order=np.frombuffer(orders,dtype=np.uint8).reshape((n,n))
    small=np.asarray(vein.resize((256,256),Image.Resampling.BILINEAR),dtype=float)/255
    snapshots=simulate(small)
    write(out/'diffusion_stats.json',dict(version=VERSION,snapshots={str(k):dict(mean=float(p.mean()),
        proximal=float(p[-32:].mean()),distal=float(p[:32].mean())) for k,p in snapshots.items()}))
    print('REFINED_FIELDS_COMPLETE',flush=True)
    rng=np.random.default_rng(seed);tiny=rng.random((9,9),dtype=np.float32)
    tile=Image.fromarray(np.concatenate((tiny,tiny,tiny),axis=1)).resize((n*3,n),Image.Resampling.BICUBIC)
    coherent=np.clip(np.asarray(tile,dtype=float)[:,n:2*n],0,1);grain=rng.normal(0,.009,(n,n))
    fibres=np.asarray(dry_fibres(n,seed+47),dtype=float).reshape((n,n));fibres=np.clip(fibres,0,1)
    Image.fromarray((fibres*255).astype('uint8')).save(textures/'dry_fibres.png')
    stages={'historical':(0,0),'light':(600,.18),'intermediate':(1400,.42),'extensive':(2600,.68),
        'advanced_diffused':(4200,.88),'dry_bleached':(2600,.90),'control_with_optional_proximal_patch':(600,0)}
    profiles=read(source/'profiles.json');names=profiles['materials']['candidate']['class_presets'];presets={};metrics=[]
    oldmanifest=read(read(prior/'plan.json')['vein_maps_manifest'])
    def lightness(rgb):
        c=np.clip(rgb/255,0,1);c=np.where(c<=.04045,c/12.92,((c+.055)/1.055)**2.4)
        y=c@np.array([.2126,.7152,.0722]);return 116*np.where(y>216/24389,np.cbrt(y),(24389/27*y+16)/116)-16
    for cid,preset in enumerate(names):
        items={};base_relief=np.asarray(_relief_height(texture_preset(preset),height,orders)).reshape((n,n))
        for name,(step,severity) in stages.items():
            pigment=np.asarray(Image.fromarray(snapshots[step].astype(np.float32)).resize((n,n),Image.Resampling.BILINEAR))
            rgb=color_surface(v,order,pigment,coherent,grain,cid,severity=severity,bleached=name=='dry_bleached')
            # Light dry fibres are an optical approximation, not added hair geometry.
            fibre_light=np.clip(fibres-.25,0,1)*severity*.09
            rgb=rgb*(1-fibre_light[:,:,None])+np.array((212,201,168))*fibre_light[:,:,None]
            albedo=textures/f'{preset}_{name}_albedo.png';Image.fromarray(np.clip(rgb,0,255).astype('uint8')).save(albedo)
            rough=textures/f'{preset}_{name}_roughness.png'
            roughness=np.clip(.90+.055*severity+.025*coherent+.015*fibres,.89,.985)
            Image.fromarray((roughness*255).astype('uint8')).save(rough)
            normal=textures/f'{preset}_{name}_normal.png'
            relief=base_relief*(1-.65*pigment*(cid==2))+.20*severity*fibres
            Image.frombytes('RGB',(n,n),_normal_map(array('f',relief.ravel()),n,.65+1.20*severity,'calyx')).save(normal)
            items[name]=dict(albedo=str(albedo),albedo_sha256=sha(albedo),roughness=str(rough),roughness_sha256=sha(rough),
                normal=str(normal),normal_sha256=sha(normal),step=step,severity=severity)
            if (cid==1 and name=='control_with_optional_proximal_patch') or (cid==2 and name=='advanced_diffused'):
                old=np.asarray(Image.open(oldmanifest['presets'][preset]['stages'][name]['albedo']).convert('RGB'),dtype=float)
                now=np.asarray(Image.open(albedo).convert('RGB'),dtype=float);a=lightness(old);b=lightness(now)
                for label,mask in [('primary_veins',(order==1)&(v>.6)),('secondary_veins',(order==3)&(v>.2)),('intervenal',order==0)]:
                    metrics.append(dict(class_id=cid,stage=name,region=label,pixels=int(mask.sum()),
                        previous_mean_Lstar=float(a[mask].mean()),new_mean_Lstar=float(b[mask].mean())))
        common=items['control_with_optional_proximal_patch'];presets[preset]=dict(stages=items,normal=common['normal'],normal_sha256=common['normal_sha256'])
    manifest=textures/'manifest.json';gains=profiles['materials']['candidate']['albedo_multiplier_linear']
    write(manifest,dict(version=VERSION,resolution=n,solver_resolution=256,seed=seed,presets=presets,graph=graph,
        class_albedo_multiplier_linear={str(i):g for i,g in enumerate(gains)},profile_sha256=sha(source/'profiles.json'),
        parameters=dict(dt=.12,dx='0.055+0.52*network',dy='0.06+1.20*network',pigment='(0.012+0.025*network)*a*(1-p)'),
        status='engineering heuristic; baked color/normal/roughness; no physiology or opacity calibration'))
    write(out/'paired_texture_metrics.json',dict(scope='raw sRGB texture lightness before frozen profile gains; no real-image lesion estimates',metrics=metrics))
    plan.update(version=VERSION,vein_maps_manifest=str(manifest),previous_review=str(prior),
        authorization='strengthen mature veins, soften overmature reticulum with intervenal pigment and drying texture; compare with real; keep pilot paused')
    write(out/'plan.json',plan);write(out/'baseline.json',baseline)
    files=dict(read(prior/'source_lock.json')['files'])
    for f in ('src/uchuva_lsystem/calyx_dry_refinement.py','src/uchuva_lsystem/blender_calyx_dry_refinement.py',
        'scripts/prepare_calyx_dry_refinement.py','scripts/render_calyx_dry_refinement.py','tests/test_calyx_dry_refinement.py'):
        p=REPO/f;files[str(p)]=sha(p)
    for p in list(textures.glob('*'))+[out/'plan.json',source/'profiles.json']:
        if p.is_file():files[str(p)]=sha(p)
    write(out/'source_lock.json',dict(version=VERSION,files=files));print(out,flush=True)


if __name__=='__main__':prepare(Path(sys.argv[1]).resolve())
