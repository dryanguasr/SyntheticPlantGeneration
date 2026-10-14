"""Assemble the fixed October appearance pilot for visual review, without labels."""
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def main():
    first = ROOT / 'outputs/appearance_pilot_20261002_v1'
    latest = ROOT / 'outputs/appearance_pilot_20261002_v2'
    output = latest / 'review'
    output.mkdir(exist_ok=False)
    captures = []
    for folder in (first, latest):
        report = json.loads((folder / 'captures.json').read_text())
        assert report['status'] == 'complete'
        assert hashlib.sha256((folder / 'runner_snapshot.py').read_bytes()).hexdigest() == report['runner_sha256']
        for row in report['captures']:
            path = folder / row['file']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
            with Image.open(path) as im:
                assert im.size == (960, 720)
                im.verify()
            captures.append(row)
    assert len(captures) == 10
    assets = ROOT / 'docs/reports/assets/nuevo_dataset_2026-09-23'
    references = json.loads((assets / 'manifest.json').read_text(encoding='utf-8'))
    for name in ('02_detalle_conservado.jpg', '06_plano_medio.jpg'):
        record = next(r for r in references['images'] if r['file'] == name)
        assert record['split'] == 'train'
        shutil.copy2(assets / name, output / name)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 23)
    board = Image.new('RGB', (1440, 1200), '#eeeae1')
    draw = ImageDraw.Draw(board)
    items = [(output/'02_detalle_conservado.jpg', 'Real: sin etiqueta de maduracion'),
             (first/'base_detalle.png', 'Base: capachos de color plano'),
             (first/'textura_detalle.png', 'Texturas: primera iluminacion')]
    items += [(latest/f'foco_{label}.png', f'Propuesta: {label}')
              for label in ('pintona', 'madura', 'sobremadura')]
    for i, (path, label) in enumerate(items):
        x, y = i % 3 * 480, i // 3 * 580
        im = Image.open(path).convert('RGB')
        im.thumbnail((472, 510))
        board.paste(im, (x+(480-im.width)//2, y+45))
        draw.text((x+10, y+12), label, fill='#202822', font=font)
    draw.text((12, 1160), 'Clases del capacho propuestas; revision humana pendiente. Misma geometria.', fill='#202822', font=font)
    board.save(output/'comparacion.jpg', quality=94)
    cards = ''.join(f'<figure><a href="../foco_{label}.png"><img src="../foco_{label}.png"></a><figcaption>{label.capitalize()} — hipótesis pendiente</figcaption></figure>'
                    for label in ('pintona', 'madura', 'sobremadura'))
    html = '''<!doctype html><meta charset="utf-8"><title>Piloto de apariencia de uchuva</title>
<style>body{font:18px system-ui;background:#f3f0e8;color:#203128;max-width:1400px;margin:40px auto;padding:20px}img{width:100%}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}figure{margin:0}p{max-width:1000px;line-height:1.6}a{color:#245c3c}table{border-collapse:collapse}td,th{padding:12px;border:1px solid #bbb}</style>
<h1>Piloto de apariencia · 2 de octubre de 2026</h1>
<p>Diez capturas exploratorias de una misma planta: siete iniciales y tres iteraciones de luz.
Las categorías pintona, madura y sobremadura describen la apariencia del capacho, según el criterio confirmado por el usuario.
La correspondencia de materiales sigue pendiente de revisión humana. No se generó un dataset ni se entrenó.</p>
<img src="comparacion.jpg" alt="Comparación real, base y tres propuestas">
<h2>Tres propuestas con luz revisada</h2><div class="grid">''' + cards + '''</div>
<p>El capacho central es la única instancia que cambia entre estas tres imágenes. Se conservan la planta, las hojas, el resto de capachos, la cámara y la iluminación.
Las asignaciones mixtas del resto de la planta son heurísticas, independientes de la anterior clasificación de cuatro clases.</p>
<h2>Qué contrastar</h2><table><tr><th>Aspecto</th><th>Hallazgo y siguiente ajuste</th></tr>
<tr><td>Nervaduras</td><td>El material texturizado recupera señal, pero la red oscura sigue siendo más discreta que en la referencia real.</td></tr>
<tr><td>Hojas y porte</td><td>Hojas demasiado planas y ordenadas; revisar curvatura, orientación y rugosidad sobre esta misma planta.</td></tr>
<tr><td>Capacho</td><td>Comparar contorno, proporción, pliegues y contraste apical. Los colores propuestos no fijan todavía fronteras de clase.</td></tr>
<tr><td>Contexto</td><td>Fondo simplificado para diagnosticar órganos; falta contrastar tutorado, suelo y vegetación vecina.</td></tr></table>
<p>Se usaron dos referencias ilustrativas de train, sin nuevas consultas a test. Las fotos no tienen etiquetas de maduración adjudicadas aquí.
La auditoría geométrica anterior sigue registrando conflictos; no se certifica validez física ni transferencia al detector.</p>
<p><a href="../piloto_apariencia.blend">Escena editable</a> · <a href="../captures.json">Capturas y hashes</a> · <a href="../appearance_review.json">Propuestas por instancia</a></p>'''
    (output/'index.html').write_text(html, encoding='utf-8')
    (output/'verification.json').write_text(json.dumps(dict(script_version='appearance-review-report/1.0', seed=23092613,
        parameter_preset='individual_bouquet_crown_v4', captures_checked=len(captures),
        hashes_dimensions_and_decode='passed', reference_manifest=references,
        human_review='pending'), indent=2), encoding='utf-8')
    print(output/'index.html')


if __name__ == '__main__':
    main()
