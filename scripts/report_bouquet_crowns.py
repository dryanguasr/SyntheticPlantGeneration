"""Metric-scale paired views: no per-plant resizing or perspective ambiguity."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads((args.review/'metrics.json').read_text())
    ids = ['plant_13','plant_03','plant_27']
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 19)
    for face in ('front','back'):
        canvas = Image.new('RGB',(2040,535),(240,240,230))
        draw = ImageDraw.Draw(canvas)
        draw.text((12,8),'Copa frondosa v3 / tutorado abierto v4 | Misma escala: 160 px/m | '+face,font=font,fill='black')
        for k,identifier in enumerate(ids):
            for j,version in enumerate(('before','after')):
                x = 60+(k*2+j)*330
                image = Image.open(args.review/f'{identifier}_{version}_{face}.png').convert('RGBA').resize((320,400))
                canvas.paste(image,(x,75),image)
                row = next(r for r in rows if r['plant_id']==identifier and r['version']==version)
                draw.text((x,43),f'{identifier} {"v3" if j==0 else "v4"}: {row["bounds_m"][2][1]:.2f} m',font=font,fill='black')
                # Camera centre 1 m, vertical extent 2.5 m: top 2.25 m.
                for height in (0,.5,1,1.5,1.8):
                    y = round(75+(2.25-height)*160)
                    draw.line((x,y,x+12,y),fill='black',width=1)
                    if k==0 and j==0: draw.text((1,y-10),str(height),font=font,fill='black')
                    if height in (0,1.8):
                        for tick in range(x,x+320,16): draw.line((tick,y,tick+5,y),fill=(120,120,120))
        draw.text((12,497),'Línea superior: referencia 1,8 m. Se conservan hojas, capachos y nodos. Tutorado: pose heurística, sin simulación de fuerzas.',font=font,fill='black')
        canvas.save(args.review/f'bouquet_{face}.jpg',quality=95)


if __name__=='__main__': main()
