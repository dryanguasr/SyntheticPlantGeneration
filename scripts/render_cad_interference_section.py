#!/usr/bin/env python3
"""Render a measured X/Z section of unchanged Inventor diagnostic OBJ exports.

Uses existing Pillow only for PNG; SVG and section extraction are stdlib.
The drawing is a 1-um tessellated BRep section, not a changed CAD model.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
import math
from pathlib import Path


COLORS={'housing':'#2563a6','link':'#db7b13','intersection':'#d6293e'}
WELD_M=1e-8  # diagnostic contour joining only, far below 1-um source facets


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def section(path, y):
    vertices,faces=[],[]
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        fields=line.split()
        if not fields:continue
        if fields[0]=='v':vertices.append(tuple(float(v) for v in fields[1:4]))
        elif fields[0]=='f':faces.append(tuple(int(v.split('/')[0])-1 for v in fields[1:]))
    segments={};coplanar=Counter()
    def key(point):return tuple(round(v/WELD_M) for v in point)
    def add(a,b,planar=False):
        a,b=key(a),key(b)
        if a==b:return
        edge=tuple(sorted((a,b)))
        if planar:coplanar[edge]+=1
        else:segments[edge]=True
    for face in faces:
        triangle=[vertices[i] for i in face]
        distances=[p[1]-y for p in triangle]
        if all(abs(d)<=1e-12 for d in distances):
            for i in range(3):
                a,b=triangle[i],triangle[(i+1)%3]
                add((a[0],a[2]),(b[0],b[2]),True)
            continue
        points=[]
        for i in range(3):
            a,b=triangle[i],triangle[(i+1)%3];da,db=distances[i],distances[(i+1)%3]
            if abs(da)<=1e-12:points.append((a[0],a[2]))
            if da*db<0 and abs(da)>1e-12 and abs(db)>1e-12:
                t=da/(da-db);points.append((a[0]+t*(b[0]-a[0]),a[2]+t*(b[2]-a[2])))
        unique={key(p):p for p in points}
        if len(unique)==2:add(*unique.values())
        elif len(unique)>2:raise ValueError('Ambiguous nonplanar triangle section')
    for edge,count in coplanar.items():
        if count%2:segments[edge]=True
    return [[tuple(v*WELD_M*1000 for v in point) for point in edge] for edge in sorted(segments)]


def loops(segments):
    adjacency=defaultdict(list)
    for a,b in segments:
        a,b=tuple(a),tuple(b);adjacency[a].append(b);adjacency[b].append(a)
    if any(len(v)!=2 for v in adjacency.values()):
        raise ValueError('Intersection section is not a collection of closed simple contours')
    unused={tuple(sorted((tuple(a),tuple(b)))) for a,b in segments};result=[]
    while unused:
        first,following=min(unused);polygon=[first];previous=first;current=following
        unused.remove(tuple(sorted((first,following))))
        while current!=first:
            polygon.append(current)
            next_point=next(point for point in adjacency[current] if point!=previous)
            unused.remove(tuple(sorted((current,next_point))))
            previous,current=current,next_point
        result.append(polygon)
    return result


def main():
    from PIL import Image,ImageDraw,ImageFont
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--comparison-evidence',type=Path,
                        help='Optional revised native export for a before/after comparison at the same driver coordinate.')
    parser.add_argument('--driver',type=float,
                        help='Common driver coordinate; required with comparison-evidence.')
    parser.add_argument('--occurrences',nargs=2,
                        help='Select this ordered pair from a multi-pair geometry export.')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plane-y',type=float,default=.002)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a fresh section evidence directory')
    evidence=json.loads((args.evidence/'result.json').read_text(encoding='utf-8-sig'))
    if evidence['status']!='COMPLETED' or not evidence['source_files_unchanged']:
        raise ValueError('Completed source-intact native geometry evidence required')
    if args.comparison_evidence:
        if args.driver is None or not math.isfinite(args.driver):
            raise ValueError('A finite explicit driver coordinate is required for revision comparison')
        comparison=json.loads((args.comparison_evidence/'result.json').read_text(encoding='utf-8-sig'))
        if comparison['status']!='COMPLETED' or not comparison['source_files_unchanged']:
            raise ValueError('Revised native geometry must be complete and source-intact')
        selected=[]
        for root,data in ((args.evidence,evidence),(args.comparison_evidence,comparison)):
            rows=[row for row in data['pairs'] if abs(row['driver_rad']-args.driver)<1e-12]
            if args.occurrences:rows=[row for row in rows if row['occurrences']==args.occurrences]
            if len(rows)!=1:raise ValueError('Expected one native pair at the chosen driver coordinate')
            selected.append((root,rows[0]))
        if selected[0][1]['occurrences']!=selected[1][1]['occurrences']:
            raise ValueError('Before and after native pairs differ')
    else:
        if args.driver is not None:raise ValueError('driver requires comparison-evidence')
        selected=[(args.evidence,next(row for row in evidence['pairs'] if abs(row['driver_rad']-q)<1e-12)) for q in (0,.1)]
    panels=[];inputs={}
    for evidence_root,row in selected:
        inputs[str(evidence_root/'result.json')]=sha(evidence_root/'result.json')
        shapes=[]
        for item in row['visualization_parts']+row['interference_geometry']:
            path=evidence_root/item['uri']
            if sha(path)!=item['sha256']:raise ValueError('Native geometry bytes changed')
            if item['frame']!='gripper_assembly_local' or item['units']!='m':raise ValueError('Unexpected CAD frame or units')
            lines=section(path,args.plane_y)
            shapes.append({'role':item['role'],'segments_xz_mm':lines,
                           'closed_loops_xz_mm':loops(lines) if item['role']=='intersection' else []})
            inputs[str(path)]=sha(path)
        panels.append({'driver_rad':row['driver_rad'],'shapes':shapes,
            'minimum_distance_m':row['minimum_distance_m'],
            'native_interference_volume_mm3':sum(row['interference_volumes_m3'])*1e9})
    args.output.mkdir(parents=True)
    width,height,scale=1600,1050,2
    canvas=Image.new('RGB',(width*scale,height*scale),'#f5f7fb');draw=ImageDraw.Draw(canvas)
    font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    if not Path(font_path).exists():font_path='C:/Windows/Fonts/arial.ttf'
    fonts={size:ImageFont.truetype(font_path,size*scale) for size in (18,20,22,24,30,38)}
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
         '<rect width="100%" height="100%" fill="#f5f7fb"/>']
    def text(x,y,value,size=22,color='#172738'):
        draw.text((x*scale,y*scale),value,font=fonts[size],fill=color)
        svg.append(f'<text x="{x}" y="{y+size}" font-family="DejaVu Sans,Arial,sans-serif" font-size="{size}" fill="{color}">{html.escape(value)}</text>')
    text(70,32,'Corrección local en una copia CAD' if args.comparison_evidence else 'Dónde se produce la interferencia',38)
    subtitle='Sección CAD en Y = 2,000 mm · misma escala y encuadre X/Z'
    if args.comparison_evidence:subtitle+=' · giro '+format(math.degrees(args.driver),'.4f').replace('.',',')+'°'
    text(70,89,subtitle,24)
    for x,role,label in ((70,'housing','Carcasa'),(430,'link','Eslabón L:1'),(820,'intersection','Volumen común BRep')):
        draw.line((x*scale,143*scale,(x+36)*scale,143*scale),fill=COLORS[role],width=5*scale)
        svg.append(f'<path d="M{x},143h36" stroke="{COLORS[role]}" stroke-width="5"/>')
        text(x+48,128,label,22)
    viewport=(20.,32.,-5.,7.);plot_size=620;top=240
    for index,panel in enumerate(panels):
        left=105+index*780
        label=(('CAD original' if index==0 else 'Copia con bisel local') if args.comparison_evidence else
               ('Postura CAD guardada · 0°' if index==0 else 'Engranaje conductor · 5,7296°'))
        text(left-25,181,label,30)
        plot=Image.new('RGB',(plot_size*scale,plot_size*scale),'white');pd=ImageDraw.Draw(plot)
        def xy(point):
            return ((point[0]-viewport[0])/(viewport[1]-viewport[0])*plot_size,
                    (viewport[3]-point[1])/(viewport[3]-viewport[2])*plot_size)
        svg.append(f'<defs><clipPath id="panel{index}"><rect x="{left}" y="{top}" width="{plot_size}" height="{plot_size}"/></clipPath></defs>')
        svg.append(f'<rect x="{left}" y="{top}" width="{plot_size}" height="{plot_size}" fill="white" stroke="#8c9bad"/>')
        svg.append(f'<g clip-path="url(#panel{index})">')
        for value in range(20,33):
            x=xy((value,0))[0]
            pd.line((x*scale,0,x*scale,plot_size*scale),fill='#e4e9f0',width=scale)
            svg.append(f'<path d="M{left+x},{top}v{plot_size}" stroke="#e4e9f0"/>')
        for value in range(-5,8):
            y=xy((0,value))[1]
            pd.line((0,y*scale,plot_size*scale,y*scale),fill='#e4e9f0',width=scale)
            svg.append(f'<path d="M{left},{top+y}h{plot_size}" stroke="#e4e9f0"/>')
        for shape in panel['shapes']:
            color=COLORS[shape['role']]
            for polygon in shape['closed_loops_xz_mm']:
                points=[xy(p) for p in polygon]
                pd.polygon([(x*scale,y*scale) for x,y in points],fill='#f498a2')
                path='M'+' L'.join(f'{left+x:.4f},{top+y:.4f}' for x,y in points)+'Z'
                svg.append(f'<path d="{path}" fill="#f498a2" stroke="none"/>')
            stroke=2.3 if shape['role']!='intersection' else 2.8
            commands=[]
            for a,b in shape['segments_xz_mm']:
                ax,ay=xy(a);bx,by=xy(b)
                pd.line((ax*scale,ay*scale,bx*scale,by*scale),fill=color,width=round(stroke*scale))
                commands.append(f'M{left+ax:.4f},{top+ay:.4f}L{left+bx:.4f},{top+by:.4f}')
            svg.append(f'<path d="{" ".join(commands)}" fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round"/>')
        # Exact 2-mm scale in the shared coordinate mapping.
        a,b=xy((20.7,-4.3)),xy((22.7,-4.3))
        pd.line((a[0]*scale,a[1]*scale,b[0]*scale,b[1]*scale),fill='#223448',width=4*scale)
        svg.append(f'<path d="M{left+a[0]},{top+a[1]}H{left+b[0]}" stroke="#223448" stroke-width="4"/>')
        svg.append('</g>')
        canvas.paste(plot,(left*scale,top*scale))
        text(left+a[0]+20,top+a[1]-35,'2 mm',18)
        for value in range(20,33,2):
            x=xy((value,0))[0];text(left+x-12,top+plot_size+10,str(value),18)
        for value in (-4,-2,0,2,4,6):
            y=xy((0,value))[1];text(left-42,top+y-12,str(value),18)
        text(left-53,top-27,'Z',20);text(left+plot_size-72,top+plot_size+39,'X (mm)',20)
        volume=panel['native_interference_volume_mm3']
        if volume>0:
            note='Rojo: intersección BRep de '+format(volume,'.4f').replace('.',',')+' mm³'
        else:
            note='Sin intersección; holgura 3D: '+format(panel['minimum_distance_m']*1000,'.4f').replace('.',',')+' mm'
        text(left-20,top+plot_size+79,note,20)
    footer=('Original conservado · copia experimental, no prototipo modificado ni validación resistente · sección BRep teselada a 1 µm'
            if args.comparison_evidence else
            'Geometría nativa intacta · sección de mallas BRep con tolerancia de teselación de 1 µm · no es una simulación de cosecha')
    text(70,1001,footer,18)
    svg.append('</svg>')
    (args.output/'seccion_comparativa.svg').write_text('\n'.join(svg),encoding='utf-8')
    canvas.resize((width,height),Image.Resampling.LANCZOS).save(args.output/'seccion_comparativa.png')
    report={'schema_version':'cad-interference-section/1.0','plane_y_m':args.plane_y,'viewport_xz_mm':viewport,
        'contour_join_tolerance_m':WELD_M,'input_sha256':inputs,'script_sha256':sha(__file__),
        'native_result_sha256':sha(args.evidence/'result.json'),'panels':panels,
        'comparison':bool(args.comparison_evidence),'common_driver_rad':args.driver,
        'scope':__doc__,'changes_to_source_geometry_by_this_renderer':False}
    (args.output/'section_geometry.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'output':str(args.output),'panels':len(panels),'closed_red_contours':sum(len(s['closed_loops_xz_mm']) for p in panels for s in p['shapes'])}))


if __name__=='__main__':main()
