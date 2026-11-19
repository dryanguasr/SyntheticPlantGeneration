"""User-prompted SAM inference and local contour edits, independent of pilot GT.

No detector proposals, original annotations, class inference or auto-downloads.
OpenCV contours are editing handles only: the native mask stays exact until a
person moves a node. Polygon deltas preserve untouched parts and holes.
"""
from pathlib import Path
import copy
import hashlib,json,math
from PIL import Image,ImageDraw,ImageChops

REPO=Path(__file__).resolve().parents[2]
MODEL_CONFIG=REPO/'docs/references/annotation_assistance_model.json'
VERSION='human-prompted-sam/1'
SUPPORTED=('mobile_sam.pt','sam_b.pt','sam_l.pt','sam_h.pt',
           'sam2_t.pt','sam2_s.pt','sam2_b.pt','sam2_l.pt',
           'sam2.1_t.pt','sam2.1_s.pt','sam2.1_b.pt','sam2.1_l.pt')


def file_sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def default_model():
    config=json.loads(MODEL_CONFIG.read_text(encoding='utf-8'))
    return REPO/config['local_path'],config['sha256']


def checked_prompts(points,labels,size):
    if not points or len(points)!=len(labels) or len(points)>256 or not any(v==1 for v in labels):
        raise ValueError('Marca al menos un punto positivo; máximo 256 puntos por instancia')
    w,h=size;clean=[]
    for point,label in zip(points,labels):
        if label not in (0,1) or len(point)!=2 or any(not math.isfinite(v) for v in point):
            raise ValueError('Punto SAM inválido')
        x,y=point
        if not(0<=x<w and 0<=y<h):raise ValueError('Punto SAM fuera de la imagen')
        clean.append([float(x),float(y)])
    return clean,[int(v) for v in labels]


def validate_assistance(value,size):
    if not isinstance(value,dict) or value.get('version')!=VERSION:raise ValueError('Procedencia SAM inválida')
    digest=value.get('model_sha256','')
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Falta hash de pesos SAM')
    points,labels=checked_prompts(value.get('points'),value.get('labels'),size)
    if value.get('model_name') not in SUPPORTED or value.get('native_size')!=list(size):raise ValueError('Modelo o tamaño de asistencia inválido')
    return dict(version=VERSION,model_name=value['model_name'],model_sha256=digest,
        ultralytics_version=str(value.get('ultralytics_version','unknown'))[:40],device=str(value.get('device','unknown'))[:20],
        points=points,labels=labels,class_source='human',native_size=list(size),boundary_edited=bool(value.get('boundary_edited')))


class SamAssistant:
    """One worker owns this object and its cached image encoder."""
    def __init__(self,model_path=None,device='auto',expected_sha=None):
        if model_path is None:model_path,expected_sha=default_model()
        self.path=Path(model_path).resolve()
        if not self.path.is_file():raise FileNotFoundError('No hay pesos SAM locales. Selecciona un archivo compatible.')
        if self.path.name not in SUPPORTED:raise ValueError('Modelo no compatible: usa MobileSAM, SAM o SAM2 de Ultralytics')
        self.sha=file_sha(self.path)
        if expected_sha and self.sha!=expected_sha:raise ValueError('Los pesos SAM no coinciden con su hash declarado')
        import torch,ultralytics
        from ultralytics.models.sam import Predictor,SAM2Predictor
        self.device=('0' if torch.cuda.is_available() else 'cpu') if device=='auto' else device
        predictor=SAM2Predictor if self.path.name.startswith('sam2') else Predictor
        self.predictor=predictor(overrides=dict(model=str(self.path),device=self.device,
            task='segment',mode='predict',imgsz=1024,conf=0.0,verbose=False,save=False))
        self.version=ultralytics.__version__;self.image_key=None

    def predict(self,image,points,labels):
        import numpy as np
        points,labels=checked_prompts(points,labels,image.size)
        rgb=image.convert('RGB');key=(rgb.size,hashlib.sha256(rgb.tobytes()).hexdigest())
        if key!=self.image_key:
            self.predictor.reset_image()
            self.predictor.set_image(np.asarray(rgb)[:,:,::-1].copy())
            self.image_key=key
        # The outer dimension groups ALL positive/negative clicks into ONE object.
        result=self.predictor(points=[points],labels=[labels],multimask_output=False)[0]
        if result.masks is None or len(result.masks.data)!=1:raise ValueError('SAM no devolvió una máscara única; ajusta los puntos')
        pixels=result.masks.data[0].detach().cpu().numpy()
        if pixels.shape!=(rgb.height,rgb.width):raise ValueError('SAM no devolvió la resolución nativa; máscara rechazada')
        mask=Image.fromarray((pixels>0).astype('uint8')*255)
        if not mask.getbbox():raise ValueError('Máscara vacía; añade o mueve puntos')
        return mask,dict(version=VERSION,model_name=self.path.name,model_sha256=self.sha,
            ultralytics_version=self.version,device=str(self.device),points=points,labels=labels,
            class_source='human',native_size=list(rgb.size),boundary_edited=False)


def mask_contours(mask,epsilon=1.0):
    import cv2,numpy as np
    contours,hierarchy=cv2.findContours(np.asarray(mask.convert('L')).copy(),cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:return []
    rings=[]
    for i,contour in enumerate(contours):
        parent=hierarchy[0][i][3];depth=0
        while parent!=-1:depth+=1;parent=hierarchy[0][parent][3]
        points=cv2.approxPolyDP(contour,epsilon,True).reshape(-1,2).tolist()
        if len(points)>=3:rings.append(dict(role='hole' if depth%2 else 'outer',points=points))
    return rings


def checked_ring(points,size):
    if len(points)<3:raise ValueError('El borde necesita al menos tres nodos')
    w,h=size
    if any(len(p)!=2 or any(not math.isfinite(v) for v in p) or not(0<=p[0]<w and 0<=p[1]<h) for p in points):
        raise ValueError('Nodo fuera de la imagen')
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersects(a,b,c,d):
        def on(a,b,c):return cross(a,b,c)==0 and min(a[0],b[0])<=c[0]<=max(a[0],b[0]) and min(a[1],b[1])<=c[1]<=max(a[1],b[1])
        return (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)
    n=len(points)
    for i,a in enumerate(points):
        b=points[(i+1)%n]
        if a==b:raise ValueError('Hay nodos duplicados')
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1):continue
            if intersects(a,b,points[j],points[(j+1)%n]):raise ValueError('El borde se cruza consigo mismo; movimiento rechazado')
    if abs(sum(points[i][0]*points[(i+1)%n][1]-points[(i+1)%n][0]*points[i][1] for i in range(n)))<1:
        raise ValueError('El borde no tiene superficie')


def apply_contour_edit(mask,old_ring,new_points):
    checked_ring(new_points,mask.size)
    old=Image.new('L',mask.size);new=Image.new('L',mask.size)
    ImageDraw.Draw(old).polygon([tuple(p) for p in old_ring['points']],fill=255)
    ImageDraw.Draw(new).polygon([tuple(p) for p in new_points],fill=255)
    added=ImageChops.subtract(new,old);removed=ImageChops.subtract(old,new)
    if old_ring['role']=='hole':added,removed=removed,added
    result=ImageChops.lighter(ImageChops.subtract(mask.convert('L'),removed),added)
    if not result.getbbox():raise ValueError('La edición elimina toda la instancia')
    return result


def nearest_edge(point,rings):
    """Return distance, ring, insertion index and projected native point."""
    best=(float('inf'),None,None,None)
    for r,ring in enumerate(rings):
        points=ring['points']
        for i,a in enumerate(points):
            b=points[(i+1)%len(points)];dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
            if not length:continue
            t=max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length))
            projected=[a[0]+t*dx,a[1]+t*dy];distance=math.dist(point,projected)
            if distance<best[0]:best=(distance,r,i+1,projected)
    return best


def boundary_handles(mask,rings):
    return dict(version='native-mask-edit-handles/1',
        mask_sha256=hashlib.sha256(mask.convert('L').tobytes()).hexdigest(),rings=copy.deepcopy(rings))


def validate_boundary_handles(value,mask):
    if not isinstance(value,dict) or value.get('version')!='native-mask-edit-handles/1':raise ValueError('Nodos de borde inválidos')
    if value.get('mask_sha256')!=boundary_handles(mask,[])['mask_sha256']:raise ValueError('Los nodos no corresponden a la máscara actual')
    rings=value.get('rings')
    if not isinstance(rings,list) or len(rings)>1000:raise ValueError('Contornos de edición inválidos')
    for ring in rings:
        if not isinstance(ring,dict) or ring.get('role') not in ('outer','hole'):raise ValueError('Tipo de contorno inválido')
        points=ring.get('points')
        if not isinstance(points,list) or len(points)>4096:raise ValueError('Demasiados nodos de edición')
        checked_ring(points,mask.size)
    return boundary_handles(mask,rings)
