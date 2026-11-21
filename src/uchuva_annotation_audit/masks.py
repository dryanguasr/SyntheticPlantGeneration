"""Native binary instance masks. Row-major RLE preserves parts and holes.

Bounding boxes are derived from occupied mask pixels, never used as masks.
Polygons are rasterized with Pillow ImageDraw at native integer coordinates.
"""
import math
from PIL import Image, ImageDraw

VERSION='row-major-binary-rle/1'


def encode_mask(image):
    image=image.convert('L').point(lambda p:255 if p else 0)
    data=image.tobytes()
    try:
        import numpy as np
        pixels=np.frombuffer(data,dtype=np.uint8)
        edges=np.flatnonzero(pixels[1:]!=pixels[:-1])+1
        counts=np.diff(np.concatenate(([0],edges,[len(pixels)]))).tolist()
        if len(pixels) and pixels[0]:counts.insert(0,0)
        return dict(version=VERSION,size=[image.height,image.width],counts=counts)
    except ImportError:
        pass
    counts=[];last=0;run=0
    for pixel in data:
        value=int(pixel!=0)
        if value==last:run+=1
        else:counts.append(run);run=1;last=value
    counts.append(run)
    return dict(version=VERSION,size=[image.height,image.width],counts=counts)


def checked_runs(segmentation,width=None,height=None):
    if not isinstance(segmentation,dict) or segmentation.get('version')!=VERSION:
        raise ValueError('Se requiere una máscara de instancia, no sólo una caja')
    size=segmentation.get('size');counts=segmentation.get('counts')
    if not isinstance(size,list) or len(size)!=2 or any(type(v) is not int or v<=0 for v in size):
        raise ValueError('Tamaño de máscara inválido')
    h,w=size
    if w*h>50_000_000 or (width is not None and (w!=width or h!=height)):
        raise ValueError('La máscara no coincide con la imagen')
    if not isinstance(counts,list) or not counts or any(type(v) is not int or v<0 for v in counts) or sum(counts)!=w*h:
        raise ValueError('RLE inválido')
    return counts,w,h


def decode_mask(segmentation):
    counts,w,h=checked_runs(segmentation)
    data=b''.join(bytes([255 if i%2 else 0])*n for i,n in enumerate(counts))
    return Image.frombytes('L',(w,h),data)


def intervals(segmentation):
    counts,w,h=checked_runs(segmentation)
    start=0;result=[]
    for i,n in enumerate(counts):
        if i%2 and n:result.append((start,start+n))
        start+=n
    return result


def area(segmentation):
    return sum(checked_runs(segmentation)[0][1::2])


def mask_bbox(segmentation):
    counts,w,h=checked_runs(segmentation);runs=intervals(segmentation)
    if not runs:raise ValueError('Máscara vacía: elimina la instancia o dibuja su superficie visible')
    x1=w;y1=h;x2=0;y2=0
    for start,end in runs:
        first_y,first_x=divmod(start,w);last_y,last_x=divmod(end-1,w)
        y1=min(y1,first_y);y2=max(y2,last_y+1)
        if first_y!=last_y:x1=0;x2=w
        else:x1=min(x1,first_x);x2=max(x2,last_x+1)
    return [x1,y1,x2,y2]


def interval_iou(a,b):
    i=j=0;intersection=0
    while i<len(a) and j<len(b):
        intersection+=max(0,min(a[i][1],b[j][1])-max(a[i][0],b[j][0]))
        if a[i][1]<b[j][1]:i+=1
        else:j+=1
    union=sum(y-x for x,y in a)+sum(y-x for x,y in b)-intersection
    return intersection/union if union else 0


def mask_iou(a,b):
    if a['size']!=b['size']:raise ValueError('Tamaños de máscara diferentes')
    return interval_iou(intervals(a),intervals(b))


def polygons_mask(rings,width,height):
    if not isinstance(rings,list) or not rings:raise ValueError('Polígonos vacíos')
    output=Image.new('L',(width,height))
    outer=[r for r in rings if r.get('role','outer')=='outer']
    holes=[r for r in rings if r.get('role')=='hole']
    if not outer:raise ValueError('Falta un contorno exterior')
    for ring in outer+holes:
        if ring.get('role','outer') not in ('outer','hole'):raise ValueError('Tipo de contorno inválido')
        points=ring.get('points')
        if not isinstance(points,list) or len(points)<3:raise ValueError('Un polígono requiere al menos tres puntos')
        for p in points:
            if not isinstance(p,(list,tuple)) or len(p)!=2 or any(type(v) not in (float,int) or not math.isfinite(v) for v in p) or not(0<=p[0]<=width and 0<=p[1]<=height):
                raise ValueError('Vértice fuera de la imagen o inválido')
        ImageDraw.Draw(output).polygon([(min(width-1,int(x)),min(height-1,int(y))) for x,y in points],fill=0 if ring in holes else 255)
    if output.getbbox() is None:raise ValueError('El polígono no ocupa píxeles')
    return output
