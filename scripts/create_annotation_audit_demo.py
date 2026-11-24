"""Disposable GUI demonstration, disjoint from the final50-image audit."""
from pathlib import Path
import sys,shutil
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src')]
from uchuva_annotation_audit.store import read,sha,atomic_json
from PIL import Image


def main():
    source=REPO/'outputs/blind_annotation_50_20261113'
    root=REPO/'outputs/annotation_audit_demo_20261113'
    root.mkdir(exist_ok=True)
    samples=[]
    for ident,previous in [('I01','I05'),('I02','I08')]:
        image=root/'images'/f'{ident}.jpg';image.parent.mkdir(exist_ok=True)
        if not image.exists():shutil.copy2(source/'images'/f'{previous}.jpg',image)
        with Image.open(image) as im:w,h=im.size
        samples.append(dict(id=ident,image=f'images/{ident}.jpg',width=w,height=h))
        for folder in ('proposals','originals'):
            value=read(source/'private'/folder/f'{previous}.json')
            atomic_json(root/'private'/folder/f'{ident}.json',value)
    atomic_json(root/'samples.json',dict(samples=samples,demonstration=True,not_for_human_pilot_metrics=True))
    atomic_json(root/'private/selection.json',dict(samples=[dict(id=s['id'],stratum='random') for s in samples]))
    paths=[root/'samples.json',*(root/'images').glob('*'),*(root/'private/proposals').glob('*'),*(root/'private/originals').glob('*'),root/'private/selection.json']
    atomic_json(root/'sealed.json',dict(files={str(p.relative_to(root)):sha(p) for p in paths},demonstration=True))
    print(root)


if __name__=='__main__':main()
