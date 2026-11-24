"""Auditar la tanda limitada y producir muestras; no lanzar entrenamiento."""
from pathlib import Path
from collections import Counter
import argparse, sys, html

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'src'), str(REPO / 'scripts')]
from uchuva_lsystem.nodal_automation import read, write, sha
from run_daylight_115_bank import checked_rows


def report(root, final=False):
    bank = root / 'bank'
    rows = checked_rows(bank)
    plan = read(bank / 'plan.json')
    if final:
        assert len(rows) == 115 and read(bank / 'sealed.json')['rendering_stopped']
        for path, digest in read(bank / 'source_lock.json')['files'].items():
            assert sha(path) == digest, path
        for path, item in read(bank / 'baseline.json')['locks'].items():
            assert sha(path) == item['sha256'], path
            for original, digest in read(path).get('files', {}).items():
                assert sha(original) == digest, original
    classes = Counter(str(i['class_id']) for r in rows for i in r['instances'])
    weather = Counter(r['lighting']['capture_condition']['sky_type'] for r in rows)
    depth = Counter(r['depth_stratum'] for r in rows)
    visible = {i['instance_id'].split(':')[0] for r in rows for i in r['instances']}
    proportions = [sum(i['class_id'] == 2 for i in r['instances']) / len(r['instances']) for r in rows]
    assert not proportions or max(proportions) <= .05
    groups = {}
    for row in rows:
        groups.setdefault((row['lighting']['capture_condition']['sky_type'], row['depth_stratum']), []).append(row)
    samples = [group[len(group)//2] for _, group in sorted(groups.items())]
    summary = dict(complete_images=len(rows), target=115, final=final,
        weather=dict(weather), depth=dict(depth), class_instance_exposure=dict(classes),
        class_names={'0':'Pintona', '1':'Madura', '2':'Sobremadura'},
        overmature_instance_exposure_fraction=classes['2']/sum(classes.values()) if classes else 0,
        max_visible_overmature_fraction=max(proportions, default=0),
        plant_sources_present=len({s for r in rows for s in r['plant_seeds']}),
        plant_sources_effectively_visible=len(visible),
        independent_plants_available=20, independent_layouts=len({r['scene_id'] for r in rows}),
        source_lock_sha256=sha(bank/'source_lock.json'),
        mask_method=plan['mask_policy'], samples=[r['view_id'] for r in samples],
        morphology='No new pruning, contraction, displacement or dimensional changes; texture-only drying relief',
        historical_generation_paused=read(Path(plan['source'])/'pause_requested.json')['active'])
    if final:
        assert dict(weather) == plan['weather_counts']
    write(bank/'review_summary.json', summary)
    from PIL import Image, ImageDraw
    tiles=[]
    for row in samples:
        tile=Image.new('RGB',(480,390),'#eeeae2')
        picture=Image.open(row['image']).convert('RGB');picture.thumbnail((480,360))
        tile.paste(picture,(0,30));draw=ImageDraw.Draw(tile)
        draw.text((7,7), row['view_id']+' '+row['lighting']['capture_condition']['sky_type']+' '+row['depth_stratum'],fill='black')
        tiles.append(tile)
    if tiles:
        sheet=Image.new('RGB',(1440,390*((len(tiles)+2)//3)), '#eeeae2')
        for i,tile in enumerate(tiles):sheet.paste(tile,((i%3)*480,(i//3)*390))
        sheet.save(bank/'review_samples.png')
    cards=''.join('<figure><img src="'+html.escape(Path(r['image']).as_uri())+'"><figcaption>'+html.escape(r['view_id']+' '+r['lighting']['capture_condition']['sky_type']+' '+r['depth_stratum'])+'</figcaption></figure>' for r in samples)
    (bank/'review.html').write_text('<meta charset="utf-8"><title>115 corregidas</title><style>body{font:16px sans-serif;background:#eeeae2}figure{display:inline-block;width:46%;margin:1%}img{width:100%}</style><h1>Muestras de la tanda corregida</h1><p>Revisión técnica de Codex; no certificación humana individual ni eficacia demostrada.</p>'+cards, encoding='utf-8')
    print(summary)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('--final',action='store_true')
    args=parser.parse_args();report(args.root.resolve(),args.final)
