"""Preserve the frozen profile interpretation when using newly baked textures."""
from pathlib import Path
import sys
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts')]
from prepare_calyx_diffusion_review import prepare
from uchuva_lsystem.nodal_automation import read,write,sha


def run(out):
    prepare(out)
    plan=read(out/'plan.json');profile=Path(plan['source'])/'profiles.json'
    manifest=Path(plan['vein_maps_manifest']);data=read(manifest)
    gains=read(profile)['materials']['candidate']['albedo_multiplier_linear']
    data['class_albedo_multiplier_linear']={str(i):g for i,g in enumerate(gains)}
    data['profile_sha256']=sha(profile);write(manifest,data)
    plan['interpreter_revision']='baked texture with unchanged frozen profile gains'
    write(out/'plan.json',plan);lock=read(out/'source_lock.json')
    for path in (manifest,out/'plan.json',profile,Path(__file__).resolve(),
        REPO/'src/uchuva_lsystem/blender_calyx_diffusion_profile.py',REPO/'scripts/render_calyx_diffusion_profile_review.py'):
        lock['files'][str(path)]=sha(path)
    write(out/'source_lock.json',lock)


if __name__=='__main__':run(Path(sys.argv[1]).resolve())
