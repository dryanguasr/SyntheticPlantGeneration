"""Review actual native ash-drying renders against fixed train references."""
from pathlib import Path
import sys, json, subprocess
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from PIL import Image, ImageDraw, ImageFont
from uchuva_lsystem.nodal_automation import read, write, sha


def report(out):
    prior = Path(read(out / 'plan.json')['previous_review'])
    for p, h in read(out / 'source_lock.json')['files'].items():
        assert sha(p) == h, p
    realroot = REPO / 'outputs/calyx_diffusion_review_20261111'
    for p, h in read(realroot / 'real_reference_verification.json')['files'].items():
        assert sha(p) == h, p
    for p, item in read(out / 'baseline.json')['locks'].items():
        assert sha(p) == item['sha256'], p
        if item.get('files'):
            for f, h in read(p)['files'].items():
                assert sha(f) == h, f
    source = Path(read(out / 'plan.json')['source'])
    assert read(source / 'pause_requested.json')['active']
    for plant in read(source / 'dataset/pool_lock.json')['plants']:
        for k in ('plant', 'admission'):
            assert sha(plant[k]) == plant[k + '_sha256']
    old, now = read(prior / 'organs_result.json'), read(out / 'organs_result.json')
    assert len(old['records']) == len(now['records']) == 2
    for a, b in zip(old['records'], now['records']):
        assert len(a['cells']) == len(b['cells']) == 7
        for x, y in zip(a['cells'], b['cells']):
            for k in ('shape', 'bbox_cm', 'volume_cm3', 'attachment_error_cm', 'nonmanifold_edges'):
                assert x[k] == y[k], k
    detail = read(out / 'dry_detail_result.json')
    assert detail['paired_geometry_camera_lighting_exact']
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 22)
    small = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 19)
    board = Image.new('RGB', (1440, 1220), '#eeeae1'); draw = ImageDraw.Draw(board)
    for j, title in enumerate(('Madura: control sin cambio', 'Sobre: progresión proximal',
                                'Sobre: pigmento entre venas', 'Sobre: secado avanzado')):
        draw.text((j * 360 + 8, 8), title, font=small, fill='#111')
    ids = ['row_0256_box_001', 'row_0297_box_000', 'row_0658_box_002', 'row_0096_box_001']
    before = Image.open(prior / 'organs_0.png').convert('RGB')
    after = Image.open(out / 'organs_0.png').convert('RGB')
    for row, label in enumerate(('REAL · train', 'ANTES · revisión inmediata anterior',
                                  'AHORA · gris progresivo y aspereza')):
        y = 45 + row * 370; draw.text((10, y), label, font=font, fill='#111')
        for j, index in enumerate((0, 3, 4, 5)):
            if row == 0:
                im = Image.open(REPO / 'outputs/calyx_dark_regions_train_20261031/objects' / ids[j] / 'crop.png').convert('RGB')
                draw.text((j * 360 + 10, y + 28), ids[j], font=small, fill='#333')
            else:
                im = (before if row == 1 else after).crop((index * 280, 245, (index + 1) * 280, 495))
            im.thumbnail((340, 285))
            board.paste(im, (j * 360 + (360 - im.width) // 2, y + 58 + (285 - im.height) // 2))
    draw.text((10, 1170), 'Órganos distintos en real y sintética; comparación visual, no secuencia temporal ni escala física común.', font=small, fill='#111')
    board.save(out / 'real_before_refined.png')
    macro = Image.new('RGB', (1200, 680), '#eeeae1'); draw = ImageDraw.Draw(macro)
    for j, (label, rec) in enumerate(zip(('Antes', 'Ahora: secado gris, venas y microaspereza'), detail['records'])):
        draw.text((j * 600 + 10, 10), label, font=small, fill='#111')
        im = Image.open(rec['image']).convert('RGB'); im.thumbnail((600, 600))
        macro.paste(im, (j * 600, 45))
    draw.text((10, 653), 'Misma malla, cámara e iluminación. Relieve óptico: no altera la silueta ni añade pelos físicos.', font=small, fill='#111')
    macro.save(out / 'dry_detail_comparison.png')
    # Two specimen sequences provide the full retained range of drying grades.
    seq = Image.new('RGB', (1960, 900), '#eeeae1'); draw = ImageDraw.Draw(seq)
    names = ('Madura', 'Sobre previa', 'Leve', 'Intermedia', 'Extensa', 'Avanzada', 'Seca/decolorada')
    for i, record in enumerate(now['records']):
        for j, name in enumerate(names):
            draw.text((j * 280 + 8, i * 450 + 10), name, font=font, fill='#111')
        seq.paste(Image.open(record['image']).convert('RGB').crop((0, 120, 1960, 520)), (0, i * 450 + 50))
    seq.save(out / 'shape_comparison.png')
    qa = dict(status='awaiting_user_visual_review', reviewer='Codex', user_approval=False,
              real_reference_crops=16, native_rgb_images=4, isolated_shells=14,
              paired_mesh_camera_lighting_exact=True, shape_states_bounds_volumes_unchanged=True,
              pigment_solver_unchanged=True, bank_images_added=0, bank_generation_paused=True,
              training_started=False, protected_sources_and_plants_verified=True)
    write(out / 'review.json', qa)
    page = '<meta charset="utf-8"><title>Secado gris de sobremaduras</title><style>body{font-family:Arial;background:#eee}img{max-width:100%}</style><h1>Secado gris y aspereza</h1><p>Muestras nativas de Blender. Piloto y banco pausados. Sin aprobación humana ni calibración fisiológica. Capachos huecos aislados; no son nuevas plantas admitidas.</p>'
    for title, name in (('Reales / anterior / ahora', 'real_before_refined.png'),
                        ('Comparación emparejada', 'dry_detail_comparison.png'), ('Grados preservados', 'shape_comparison.png')):
        page += f'<h2>{title}</h2><img src="{name}">'
    (out / 'review.html').write_text(page, encoding='utf-8')
    write(REPO / 'outputs/calyx_approval_samples_20261031/latest_review.json',
          dict(revision=str(out), status=qa['status'], previous_samples_preserved=True,
               bank_generation_paused=True, training_started=False))
    result = subprocess.run([sys.executable, str(REPO / 'scripts/validate_repository_context_graph.py')], capture_output=True, text=True)
    after = (result.stdout + result.stderr).strip()
    (out / 'graph_after.txt').write_text(after + '\n', encoding='utf-8')
    assert after == (out / 'graph_before.txt').read_text(encoding='utf-8').strip()
    write(out / 'report_source_lock.json', dict(files={str(Path(__file__).resolve()): sha(__file__)}))
    print(qa)


if __name__ == '__main__':
    report(Path(sys.argv[1]).resolve())
