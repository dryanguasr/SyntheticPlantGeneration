"""Native desktop segmentation audit: manual first, proposals only after save.

Launch with the training Python (Pillow and Tkinter already available). All
human work stays in sidecars under the pilot; original data is never edited.
"""
from pathlib import Path
import argparse,copy,math,os,sys,time,uuid
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from concurrent.futures import ThreadPoolExecutor
from PIL import Image,ImageTk,ImageDraw,ImageChops,ImageFilter
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
from uchuva_annotation_audit.store import AuditStore,SessionLock,CLASSES,atomic_json,read,window_process_identity
from uchuva_annotation_audit.masks import encode_mask,decode_mask,mask_bbox,area
from uchuva_annotation_audit.reference_loupe import ReferenceLoupe
from uchuva_annotation_audit.assistance import SamAssistant,default_model,mask_contours,apply_contour_edit,nearest_edge,boundary_handles,checked_ring
from uchuva_annotation_audit.ui_theme import apply_theme,UI,brand

COLORS={0:'#36ce9c',1:'#ffc25c',2:'#ff72bd',None:'#b5c0ce'}
MODE_KEYS=(('P','Polígono','polygon',None),('S','SAM','sam',None),
    ('V','Seleccionar','select',None),('B','Pincel','brush',None),('E','Borrador','erase',None),
    ('M','Mover nodo','nodes','drag'),('I','Insertar nodo','nodes','insert'),('D','Eliminar nodo','nodes','delete'))
SHORT_MODE_LABELS={'V':'Selección','M':'Mover','I':'Insertar','D':'Eliminar'}

TOOL_HELP={
    'P': 'Haz clic sobre el borde visible del capacho para colocar vértices. Pulsa Enter para cerrar el polígono.\n\nCtrl+Z quita el último vértice. Esc cancela el contorno. Selecciona una instancia y usa + Parte o − Hueco para añadir una región o recortarla.',
    'S': 'Haz clic dentro del capacho. Usa Shift+clic sobre el fondo o sobre otra instancia para excluirlos.\n\nRevisa la máscara azul. Pulsa Enter para aceptarla, Ctrl+Z para quitar el último punto o Esc para descartarla. El modelo local propone la superficie y tú eliges la clase.',
    'V': 'Haz clic sobre una máscara o elige una instancia en la barra superior. Usa Acercar para inspeccionarla, o elige su clase en la barra de arriba si es editable. Supr elimina la instancia completa.',
    'B': 'Selecciona una instancia para retocarla, o empieza sobre el lienzo para crear otra. Ajusta el radio en píxeles de la imagen. Mantén pulsado el botón izquierdo y arrastra para añadir superficie. Ctrl+Z deshace un trazo.',
    'E': 'Selecciona la instancia que quieres retocar y ajusta el radio. Mantén pulsado el botón izquierdo y arrastra para quitar superficie. Ctrl+Z deshace un trazo.',
    'M': 'Selecciona una instancia y arrastra un nodo blanco para ajustar el borde. Shift+clic junto a un segmento añade un nodo y Ctrl+clic sobre un nodo lo elimina. Ctrl+Z deshace el ajuste.',
    'I': 'Haz clic junto a un segmento de la instancia seleccionada para insertar un nodo. La máscara conserva sus píxeles hasta que muevas el nodo. Pulsa M para arrastrarlo.',
    'D': 'Haz clic sobre un nodo de la instancia seleccionada para eliminarlo. Se requieren al menos tres nodos por contorno. Ctrl+Z restaura el nodo y la máscara.',
    'general': 'Alt+← / Alt+→ cambian de imagen. F encaja la foto, la rueda amplía y el botón derecho mueve la vista.\n\nN inicia una instancia. Las teclas 1–4 eligen la clase. Supr elimina la instancia completa. Ctrl+S guarda el borrador o la adjudicación editable.',
}


class MaskCanvas(ttk.Frame):
    def __init__(self,parent,on_change,on_select,class_getter,**kwargs):
        super().__init__(parent,**kwargs)
        self.canvas=tk.Canvas(self,bg=UI['canvas'],highlightthickness=0,cursor='crosshair')
        self.canvas.pack(fill='both',expand=True)
        self.on_change=on_change;self.on_select=on_select;self.class_getter=class_getter
        self.image=None;self.objects=[];self.cache={};self.selected=None;self.editable=True
        self.scale=1.;self.ox=0.;self.oy=0.;self.tool='polygon';self.operation='new';self.points=[];self.user_view=False
        self.brush=10;self.show_boxes=False;self.opacity=.22;self.panning=None;self.painting=None;self.undo_stack=[]
        self.cursor_callback=None;self.assist_callback=None;self.error_callback=None;self.context_callback=None
        self.assist_serial=0;self.assist_points=[];self.assist_labels=[];self.assist_preview=None;self.assist_metadata=None
        self.node_rings=[];self.node_drag=None;self.node_action='drag'
        self.canvas.bind('<Configure>',self.resize_view)
        self.canvas.bind('<Button-1>',self.press)
        self.canvas.bind('<B1-Motion>',self.motion)
        self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<Double-Button-1>',lambda e:self.finish_polygon())
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<Motion>',self.hover)
        self.canvas.bind('<Button-2>',self.pan_start);self.canvas.bind('<B2-Motion>',self.pan_motion)
        self.canvas.bind('<Button-3>',self.pan_start);self.canvas.bind('<B3-Motion>',self.pan_motion)

    def load(self,image,objects,editable):
        self.clear_assistance();self.node_rings=[];self.node_drag=None
        self.image=image.copy();self.objects=copy.deepcopy(objects);self.cache={};self.selected=None
        self.editable=editable;self.points=[];self.undo_stack=[];self.operation='new';self.fit()

    def mask(self,obj):
        if obj['id'] not in self.cache:self.cache[obj['id']]=decode_mask(obj['segmentation']).convert('1')
        return self.cache[obj['id']]

    def snapshot(self):
        self.flush_masks();self.undo_stack.append(copy.deepcopy(self.objects))
        self.undo_stack=self.undo_stack[-20:]

    def flush_masks(self):
        for obj in self.objects:
            if obj.get('_dirty'):
                obj.pop('boundary_nodes',None)
                obj['segmentation']=encode_mask(self.cache[obj['id']]);obj.pop('_dirty',None)
                if area(obj['segmentation']):obj['bbox']=mask_bbox(obj['segmentation'])

    def payload(self):
        self.flush_masks()
        return [{k:v for k,v in o.items() if not k.startswith('_')} for o in self.objects]

    def fit(self):
        if self.image is None:return
        self.user_view=False
        w=self.canvas.winfo_width()
        h=self.canvas.winfo_height()
        # Before mapping, Tk reports a 1 × 1 placeholder; resize_view fits again.
        if min(w,h)<=30:return
        self.scale=min((w-30)/self.image.width,(h-30)/self.image.height)
        self.ox=(w-self.image.width*self.scale)/2;self.oy=(h-self.image.height*self.scale)/2;self.redraw()

    def resize_view(self,event=None):
        if self.user_view:self.redraw()
        else:self.fit()

    def focus_selected(self):
        obj=next((o for o in self.objects if o['id']==self.selected),None)
        if not obj:return
        b=self.mask(obj).getbbox()
        if b is None:return
        self.user_view=True
        w,h=self.canvas.winfo_width(),self.canvas.winfo_height()
        self.scale=min(12,.8*w/max(1,b[2]-b[0]),.8*h/max(1,b[3]-b[1]))
        self.ox=w/2-(b[0]+b[2])*self.scale/2;self.oy=h/2-(b[1]+b[3])*self.scale/2;self.redraw()

    def source_point(self,event):
        if self.image is None:return None
        x=(event.x-self.ox)/self.scale;y=(event.y-self.oy)/self.scale
        return (max(0,min(self.image.width-1,x)),max(0,min(self.image.height-1,y)))

    def inside(self,event):
        return self.image is not None and self.ox<=event.x<self.ox+self.image.width*self.scale and self.oy<=event.y<self.oy+self.image.height*self.scale

    def zoom(self,factor,x=None,y=None):
        if self.image is None:return
        self.user_view=True
        x=self.canvas.winfo_width()/2 if x is None else x;y=self.canvas.winfo_height()/2 if y is None else y
        old=self.scale;self.scale=max(.035,min(20,self.scale*factor))
        self.ox=x-(x-self.ox)*self.scale/old;self.oy=y-(y-self.oy)*self.scale/old;self.redraw()

    def wheel(self,event):self.zoom(1.2 if event.delta>0 else 1/1.2,event.x,event.y)
    def hover(self,event):
        if self.cursor_callback is not None and self.inside(event):self.cursor_callback(self.image,self.source_point(event))
    def pan_start(self,event):self.user_view=True;self.panning=(event.x,event.y,self.ox,self.oy)
    def pan_motion(self,event):
        if self.panning:
            x,y,ox,oy=self.panning;self.ox=ox+event.x-x;self.oy=oy+event.y-y;self.redraw()

    def redraw(self,event=None):
        c=self.canvas;c.delete('all')
        if self.image is None:return
        cw,ch=max(1,c.winfo_width()),max(1,c.winfo_height())
        ix1=max(0,-self.ox/self.scale);iy1=max(0,-self.oy/self.scale)
        ix2=min(self.image.width,(cw-self.ox)/self.scale);iy2=min(self.image.height,(ch-self.oy)/self.scale)
        if ix2>ix1 and iy2>iy1:
            pw=max(1,round((ix2-ix1)*self.scale));ph=max(1,round((iy2-iy1)*self.scale))
            box=(ix1,iy1,ix2,iy2);background=self.image.resize((pw,ph),Image.Resampling.BILINEAR,box=box).convert('RGBA')
            for obj in self.objects:
                mask=self.mask(obj);bounds=mask.getbbox()
                if not bounds or bounds[2]<ix1 or bounds[0]>ix2 or bounds[3]<iy1 or bounds[1]>iy2:continue
                mx1,my1=max(ix1,bounds[0]),max(iy1,bounds[1]);mx2,my2=min(ix2,bounds[2]),min(iy2,bounds[3])
                dx,dy=round((mx1-ix1)*self.scale),round((my1-iy1)*self.scale)
                mw,mh=min(pw-dx,max(1,round((mx2-mx1)*self.scale))),min(ph-dy,max(1,round((my2-my1)*self.scale)))
                if mw<=0 or mh<=0:continue
                visible=mask.resize((mw,mh),Image.Resampling.NEAREST,box=(mx1,my1,mx2,my2)).convert('L')
                overlay=Image.new('RGBA',(mw,mh),COLORS[obj['class_id']])
                alpha=visible.point(lambda v:int(255*self.opacity) if v else 0);overlay.putalpha(alpha)
                background.alpha_composite(overlay,dest=(dx,dy))
                edge=ImageChops.subtract(visible.filter(ImageFilter.MaxFilter(3)),visible.filter(ImageFilter.MinFilter(3)))
                outline=Image.new('RGBA',(mw,mh),'#ffffff' if obj['id']==self.selected else COLORS[obj['class_id']]);outline.putalpha(edge)
                background.alpha_composite(outline,dest=(dx,dy))
            self.photo=ImageTk.PhotoImage(background)
            c.create_image(ix1*self.scale+self.ox,iy1*self.scale+self.oy,image=self.photo,anchor='nw')
        for index,obj in enumerate(self.objects):
            bounds=self.mask(obj).getbbox()
            if bounds is None:continue
            a,b,d,e=[bounds[0]*self.scale+self.ox,bounds[1]*self.scale+self.oy,bounds[2]*self.scale+self.ox,bounds[3]*self.scale+self.oy]
            if self.show_boxes:c.create_rectangle(a,b,d,e,outline='#ffffff',dash=(4,4))
            if obj['id']==self.selected and self.show_boxes:c.create_rectangle(a-3,b-3,d+3,e+3,outline='#ffffff',dash=(2,4),width=2)
            label=f'{index+1} '+CLASSES[obj['class_id']]
            tx=max(3,min(cw-115,a));ty=max(3,min(ch-20,b))
            c.create_text(tx+1,ty+1,text=label,anchor='nw',fill='#09111b',font=('Segoe UI',10,'bold'))
            c.create_text(tx,ty,text=label,anchor='nw',fill=COLORS[obj['class_id']],font=('Segoe UI',10,'bold'))
        if self.points:
            screen=[v for p in self.points for v in (p[0]*self.scale+self.ox,p[1]*self.scale+self.oy)]
            if len(screen)>=4:c.create_line(*screen,fill='#ffffff',width=2)
            for x,y in zip(screen[::2],screen[1::2]):c.create_oval(x-3,y-3,x+3,y+3,fill='#ffffff',outline='')
        if self.assist_preview is not None and ix2>ix1 and iy2>iy1:
            # Preview has no instance/class and is never part of payload until accepted.
            visible=self.assist_preview.resize((pw,ph),Image.Resampling.NEAREST,box=box)
            tint=Image.new('RGBA',visible.size,'#43d8ff');tint.putalpha(visible.point(lambda v:85 if v else 0))
            self.assist_photo=ImageTk.PhotoImage(tint)
            c.create_image(ix1*self.scale+self.ox,iy1*self.scale+self.oy,image=self.assist_photo,anchor='nw')
        for (x,y),label in zip(self.assist_points,self.assist_labels):
            x=x*self.scale+self.ox;y=y*self.scale+self.oy;color='#40ff9b' if label else '#ff5b68'
            c.create_oval(x-6,y-6,x+6,y+6,fill=color,outline='#12252d',width=2)
            c.create_text(x,y,text='+' if label else '−',fill='#111c29',font=('Segoe UI',9,'bold'))
        if self.tool=='nodes' and self.editable:
            for ring in self.node_rings:
                xy=[v for x,y in ring['points'] for v in (x*self.scale+self.ox,y*self.scale+self.oy)]
                if len(xy)>=6:c.create_line(*(xy+xy[:2]),fill='#eafffe',width=1,dash=(3,2))
                for x,y in zip(xy[::2],xy[1::2]):c.create_rectangle(x-4,y-4,x+4,y+4,fill='#ffffff',outline='#176e88')
        if self.context_callback:self.context_callback()

    def choose(self,ident):
        self.selected=ident;self.refresh_nodes();self.on_select(ident);self.redraw()

    def refresh_nodes(self):
        obj=next((o for o in self.objects if o['id']==self.selected),None)
        self.node_rings=[]
        if obj is not None and self.tool=='nodes' and self.editable:
            mask=self.mask(obj);saved=obj.get('boundary_nodes')
            if saved and saved.get('mask_sha256')==boundary_handles(mask,[])['mask_sha256']:
                self.node_rings=copy.deepcopy(saved['rings'])
            else:
                self.node_rings=mask_contours(mask)
                # Do not persist pathological contour handles; brush editing remains available.
                try:
                    for ring in self.node_rings:checked_ring(ring['points'],mask.size)
                except ValueError:self.node_rings=[]
                obj['boundary_nodes']=boundary_handles(mask,self.node_rings)

    def clear_assistance(self):
        self.assist_serial+=1;self.assist_points=[];self.assist_labels=[];self.assist_preview=None;self.assist_metadata=None

    def accept_assistance(self):
        if not self.editable or self.assist_preview is None:return None
        self.snapshot();obj=self.new_object(self.assist_preview.copy())
        obj['assistance']=copy.deepcopy(self.assist_metadata)
        self.clear_assistance();self.flush_masks();self.on_change();self.choose(obj['id'])
        return obj

    def start_node_edit(self,point,event):
        self.refresh_nodes()
        action='delete' if getattr(event,'state',0)&4 else 'insert' if getattr(event,'state',0)&1 else self.node_action
        if action=='insert':self.insert_node(point);return
        hits=[(math.dist(point,p)*self.scale,r,i) for r,ring in enumerate(self.node_rings) for i,p in enumerate(ring['points'])]
        nearest=min(hits,default=(float('inf'),None,None))
        if nearest[0]>9:
            x,y=map(int,point);hit=next((o for o in reversed(self.objects) if self.mask(o).getpixel((x,y))),None)
            self.choose(hit['id'] if hit else None);return
        if action=='delete':self.remove_node(nearest[1],nearest[2]);return
        _,r,i=nearest;obj=next(o for o in self.objects if o['id']==self.selected)
        self.snapshot();self.node_drag=dict(obj=obj,ring=copy.deepcopy(self.node_rings[r]),r=r,i=i,mask=self.mask(obj).copy())

    def insert_node(self,point):
        if not self.editable or self.selected is None:return
        distance,r,index,projected=nearest_edge(point,self.node_rings)
        if distance*self.scale>10:return
        ring=self.node_rings[r]
        if any(math.dist(projected,p)*self.scale<4 for p in ring['points']):return
        new_points=copy.deepcopy(ring['points']);new_points.insert(index,projected)
        try:checked_ring(new_points,self.image.size)
        except ValueError as exc:
            if self.error_callback:self.error_callback(str(exc))
            return
        self.snapshot();ring['points']=new_points
        obj=next(o for o in self.objects if o['id']==self.selected)
        # Insertion only splits an edge: never rasterize or change mask pixels.
        obj['boundary_nodes']=boundary_handles(self.mask(obj),self.node_rings)
        self.on_change();self.redraw()

    def remove_node(self,r,index):
        if not self.editable or self.selected is None:return
        ring=self.node_rings[r];points=copy.deepcopy(ring['points'])
        if len(points)<=3:
            if self.error_callback:self.error_callback('El contorno debe conservar al menos tres nodos.')
            return
        points.pop(index);obj=next(o for o in self.objects if o['id']==self.selected)
        try:result=apply_contour_edit(self.mask(obj),ring,points)
        except ValueError as exc:
            if self.error_callback:self.error_callback(str(exc))
            return
        self.snapshot();self.node_rings[r]['points']=points
        self.cache[obj['id']]=result;obj['_dirty']=True
        if obj.get('assistance'):obj['assistance']['boundary_edited']=True
        self.flush_masks();obj['boundary_nodes']=boundary_handles(result,self.node_rings)
        self.on_change();self.redraw()

    def end_node_edit(self):
        drag=self.node_drag;self.node_drag=None
        if drag is None:return
        obj=drag['obj'];points=self.node_rings[drag['r']]['points']
        if points==drag['ring']['points']:self.undo_stack.pop();return
        try:result=apply_contour_edit(drag['mask'],drag['ring'],points)
        except ValueError as exc:
            self.undo_stack.pop();self.refresh_nodes();self.redraw()
            if self.error_callback:self.error_callback(str(exc))
            return
        self.cache[obj['id']]=result;obj['_dirty']=True
        if obj.get('assistance'):obj['assistance']['boundary_edited']=True
        self.flush_masks();obj['boundary_nodes']=boundary_handles(result,self.node_rings)
        self.on_change();self.redraw()

    def press(self,event):
        self.canvas.focus_set()
        if not self.inside(event):return
        point=self.source_point(event)
        if self.tool=='select' or not self.editable:
            x,y=map(int,point)
            hit=next((o for o in reversed(self.objects) if self.mask(o).getpixel((x,y))),None)
            self.choose(hit['id'] if hit else None);return
        if self.tool=='sam':
            self.assist_points.append(point);self.assist_labels.append(0 if getattr(event,'state',0)&1 else 1)
            self.assist_serial+=1;self.assist_preview=None;self.assist_metadata=None;self.redraw()
            if self.assist_callback:self.assist_callback(self)
            return
        if self.tool=='nodes':self.start_node_edit(point,event);return
        if self.tool=='polygon':
            if not self.points or math.dist(point,self.points[-1])>1:self.points.append(point)
            self.redraw();return
        if self.tool in ('brush','erase'):
            self.snapshot()
            obj=next((o for o in self.objects if o['id']==self.selected),None)
            if obj is None:
                if self.tool=='erase':return
                obj=self.new_object(Image.new('L',self.image.size))
            self.cache[obj['id']]=self.mask(obj).convert('L')
            self.painting=(obj,point);self.paint(point,point);self.redraw()

    def new_object(self,mask):
        ident=uuid.uuid4().hex
        obj=dict(id=ident,class_id=self.class_getter(),segmentation=encode_mask(mask),note='')
        self.objects.append(obj);self.cache[ident]=mask;self.selected=ident
        return obj

    def paint(self,a,b):
        obj,_=self.painting;mask=self.mask(obj);ink=ImageDraw.Draw(mask);radius=self.brush
        fill=0 if self.tool=='erase' else 255
        ink.line([a,b],fill=fill,width=2*radius)
        for x,y in (a,b):ink.ellipse((x-radius,y-radius,x+radius,y+radius),fill=fill)
        obj['_dirty']=True

    def motion(self,event):
        self.hover(event)
        if self.node_drag and self.editable:
            drag=self.node_drag;self.node_rings[drag['r']]['points'][drag['i']]=list(self.source_point(event));self.redraw();return
        if self.painting and self.editable:
            obj,last=self.painting;p=self.source_point(event);self.paint(last,p);self.painting=(obj,p);self.redraw()

    def release(self,event):
        if self.node_drag:self.end_node_edit();return
        if self.painting:
            self.painting=None;self.flush_masks();self.on_change();self.redraw()

    def finish_polygon(self):
        if not self.editable or len(self.points)<3:return
        points=self.points;self.points=[]
        region=Image.new('L',self.image.size);ImageDraw.Draw(region).polygon(points,fill=255)
        if region.getbbox() is None:return
        self.snapshot();obj=next((o for o in self.objects if o['id']==self.selected),None)
        if self.operation=='new' or obj is None:
            obj=self.new_object(region)
        else:
            mask=self.mask(obj).convert('L')
            self.cache[obj['id']]=ImageChops.subtract(mask,region) if self.operation=='subtract' else ImageChops.lighter(mask,region)
            obj['_dirty']=True
        self.operation='new';self.flush_masks();self.on_change();self.choose(obj['id'])

    def delete_selected(self):
        if self.editable and self.selected:
            self.snapshot();self.objects=[o for o in self.objects if o['id']!=self.selected]
            self.cache.pop(self.selected,None);self.selected=None;self.node_rings=[];self.on_change();self.redraw()

    def undo(self):
        if self.node_drag:self.cancel_polygon();return
        if self.tool=='sam' and self.assist_points:
            self.assist_points.pop();self.assist_labels.pop();self.assist_serial+=1;self.assist_preview=None;self.assist_metadata=None
            if self.assist_points and self.assist_callback:self.assist_callback(self)
            self.redraw();return
        if self.points:self.points.pop();self.redraw();return
        if self.editable and self.undo_stack:
            self.objects=self.undo_stack.pop();self.cache={}
            if not any(o['id']==self.selected for o in self.objects):self.selected=None
            self.refresh_nodes();self.on_change();self.redraw()

    def cancel_polygon(self):
        self.points=[];self.clear_assistance()
        if self.node_drag:
            self.node_drag=None;self.undo_stack.pop();self.refresh_nodes()
        self.redraw()


class AuditApp:
    def __init__(self,window,store):
        self.window=window;self.store=store;self.lock=SessionLock(store.session/'window.lock')
        self.windowing_system=str(window.tk.call('tk','windowingsystem'))
        atomic_json(store.session/'window_identity.json',dict(**window_process_identity(),application='annotation_audit_app',demonstration=bool(store.public.get('demonstration'))))
        self.current=None;self.phase='manual';self.comparison_data=None;self.started=time.monotonic();self.elapsed_base=0
        self.ids=list(store.samples);self.history=[];self.syncing=False
        self.assist_executor=None;self.assist_future=None;self.assist_backend=None;self.assist_pending=None;self.assist_closed=False
        self.assist_model_path=None;self.assist_expected_sha=None
        prefs=read(store.session/'preferences.json') if (store.session/'preferences.json').exists() else {}
        self.reviewer=tk.StringVar(value=prefs.get('reviewer',''))
        self.class_var=tk.StringVar(value='0');self.tool_var=tk.StringVar(value='polygon')
        self.node_action=tk.StringVar(value='drag')
        self.right_var=tk.StringVar(value='proposal');self.box_var=tk.BooleanVar(value=False);self.empty_var=tk.BooleanVar(value=False)
        self.status_var=tk.StringVar();self.phase_var=tk.StringVar();self.progress_var=tk.StringVar()
        self.command_title=tk.StringVar();self.command_actions=tk.StringVar();self.command_help_pending=None
        self.profile_window=None
        self.assist_device=tk.StringVar(value='auto');self.assist_model_label=tk.StringVar(value='MobileSAM…')
        prefix='DEMOSTRACIÓN | ' if store.public.get('demonstration') else ''
        window.title(prefix+'Uchuva | Auditoría ciega de segmentación')
        window.geometry('1120x700')
        window.minsize(800,540);self.style=apply_theme(window)
        self.layout_size=None
        self.compact_layout=False
        self.editor_info=tk.StringVar(value='Lienzo de anotación');self.step_labels=[]
        self.build()
        window.bind('<Configure>',self.resize_workspace,add='+')
        self.store.runtime_context=dict(reference_tool=self.reference_tool.context(),
            reference_available=self.reference_tool.palette is not None,loupe_used_for_this_image=False,
            palette_grades_consulted=[],reference_image_opened=False)
        window.protocol('WM_DELETE_WINDOW',self.close)
        self.bind_shortcuts()
        for variable in (self.tool_var,self.node_action,self.phase_var,self.right_var,self.class_var):variable.trace_add('write',lambda *_:self.schedule_command_help())
        window.bind('<FocusIn>',lambda e:self.schedule_command_help(),add='+')
        window.bind('<FocusOut>',lambda e:self.schedule_command_help(),add='+')
        self.update_command_help()
        window.after(120,lambda:self.open_initial_image(prefs.get('last_sample')))
        if not self.reviewer.get().strip():
            self.profile_map_binding=window.bind('<Map>',self.ask_for_initial_profile,add='+')

    def show(self):
        self.window.deiconify()
        if self.windowing_system in ('win32','aqua'):
            self.window.state('zoomed')
        else:
            try:
                self.window.attributes('-zoomed',True)
            except tk.TclError:
                self.window.geometry(f'{self.window.winfo_screenwidth()}x{self.window.winfo_screenheight()}+0+0')

    def toggle_fullscreen(self,event=None):
        enabled=not self.window.attributes('-fullscreen')
        self.window.attributes('-fullscreen',enabled)
        self.fullscreen_button.configure(text='Salir [F11]' if enabled else 'Pantalla [F11]')
        return 'break'

    def resize_workspace(self,event):
        if event.widget is not self.window or (event.width,event.height)==self.layout_size:
            return
        self.layout_size=(event.width,event.height)
        scaling=float(self.window.tk.call('tk','scaling'))
        compact=event.height<820+max(0,scaling-4/3)*240
        if compact!=self.compact_layout:
            self.compact_layout=compact
            self.apply_workspace_density()
            for (button,_,_),(key,label,_,_) in zip(self.command_buttons,MODE_KEYS):
                name=SHORT_MODE_LABELS.get(key,label) if compact else label
                button.configure(text=f'[{key}] {name}')
            self.schedule_command_help()
        self.header.configure(pady=4 if compact else 14)
        if compact:
            self.workflow.pack_forget()
            self.header_subtitle.pack_forget()
        else:
            self.workflow.pack(fill='x',before=self.phase_label)
            self.header_subtitle.pack(fill='x',before=self.header_title)
        self.header_title.configure(font=('Segoe UI',-23 if compact else 20,'bold'))
        self.style.configure('Phase.TLabel',padding=(16,4 if compact else 8))
        inspector_width=max(260,min(386,round(event.width*.29)))
        self.inspector_shell.configure(width=inspector_width)
        self.reference_tool.resize(min(336,inspector_width-38),104 if compact else 148)

    def apply_workspace_density(self):
        # Limit chrome size on a short, high-DPI display without scaling the image
        # or the source coordinates used by the mask editor.
        compact=self.compact_layout
        size=-min(16,round(10*float(self.window.tk.call('tk','scaling')))) if compact else 10
        normal=('Segoe UI',size)
        bold=('Segoe UI',size,'bold')
        for name in ('.','TButton','Mode.TButton','ActiveMode.TButton','Accent.TButton','Phase.TLabel'):
            self.style.configure(name,font=bold if name in ('ActiveMode.TButton','Accent.TButton') else normal)
        self.style.configure('TButton',padding=(8,5) if compact else (10,7))
        self.style.configure('Mode.TButton',padding=(6,4) if compact else (9,7))
        self.style.configure('ActiveMode.TButton',padding=(6,4) if compact else (9,7))
        self.style.configure('Accent.TButton',padding=(10,6) if compact else (14,9))
        self.command_heading.configure(font=bold if compact else ('Segoe UI',11,'bold'))
        self.command_text.configure(font=normal)
        self.progress_badge.configure(font=bold,pady=7 if compact else 10)

    def open_initial_image(self,last_sample):
        if not self.current and self.ids:
            self.change_image(last_sample if last_sample in self.ids else self.ids[0])

    def ask_for_initial_profile(self,event):
        if event.widget is self.window:
            self.window.unbind('<Map>',self.profile_map_binding)
            if not self.reviewer.get().strip():
                self.window.after_idle(self.edit_reviewer)

    def save_preferences(self):
        atomic_json(self.store.session/'preferences.json',dict(reviewer=self.reviewer.get(),last_sample=self.current))

    def show_centered(self,popup):
        popup.update_idletasks()
        x=self.window.winfo_rootx()+(self.window.winfo_width()-popup.winfo_reqwidth())//2
        y=self.window.winfo_rooty()+(self.window.winfo_height()-popup.winfo_reqheight())//2
        popup.geometry(f'{x:+d}{y:+d}')
        popup.deiconify()

    def edit_reviewer(self):
        if self.profile_window is not None and self.profile_window.winfo_exists():
            self.profile_window.lift()
            return
        popup=tk.Toplevel(self.window)
        popup.withdraw()
        self.profile_window=popup
        popup.title('Perfil del etiquetador')
        popup.transient(self.window)
        popup.resizable(False,False)
        panel=ttk.Frame(popup,style='Card.TFrame',padding=20)
        panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='Perfil del etiquetador',style='Section.TLabel').pack(anchor='w')
        ttk.Label(panel,text='Nombre o identificador',style='Muted.TLabel').pack(anchor='w',pady=(12,4))
        name=tk.StringVar(popup,value=self.reviewer.get())
        field=ttk.Entry(panel,textvariable=name,width=34)
        field.pack(fill='x')
        feedback=tk.StringVar(popup)
        ttk.Label(panel,textvariable=feedback,style='Muted.TLabel').pack(anchor='w',pady=(4,8))
        buttons=ttk.Frame(panel,style='Card.TFrame')
        buttons.pack(fill='x')

        def close(event=None):
            popup.destroy()
            self.profile_window=None
            self.active_view().canvas.focus_set()
            return 'break'

        def save(event=None):
            value=name.get().strip()
            if not 1<=len(value)<=200:
                feedback.set('Escribe un nombre o identificador de hasta 200 caracteres.')
            else:
                previous=self.reviewer.get()
                self.reviewer.set(value)
                try:
                    self.save_preferences()
                except OSError:
                    self.reviewer.set(previous)
                    feedback.set('No se pudo guardar el perfil. Vuelve a intentarlo.')
                else:
                    close()
            return 'break'

        ttk.Button(buttons,text='Cancelar',command=close).pack(side='left')
        ttk.Button(buttons,text='Guardar perfil',style='Accent.TButton',command=save).pack(side='right')
        popup.protocol('WM_DELETE_WINDOW',close)
        popup.bind('<Escape>',close)
        popup.bind('<Return>',save)
        def focus_field(event):
            if event.widget is popup:
                popup.grab_set()
                field.focus_set()
                field.selection_range(0,'end')

        popup.bind('<Map>',focus_field,add='+')
        self.show_centered(popup)

    def in_text(self):return isinstance(self.window.focus_get(),(tk.Entry,tk.Text,ttk.Entry,tk.Spinbox,ttk.Spinbox))
    def current_class(self):return None if self.class_var.get()=='?' else int(self.class_var.get())
    def active_view(self):return self.left if self.phase=='manual' else self.right

    def bind_shortcuts(self):
        for key,_,_,_ in MODE_KEYS:
            for letter in (key.lower(),key):self.window.bind(f'<KeyPress-{letter}>',lambda e,k=key:self.run_shortcut(k,e))
        for key in ('n','N','f','F','1','2','3','4'):
            self.window.bind(f'<KeyPress-{key}>',lambda e,k=key.upper():self.run_shortcut(k,e))
        for sequence,action in (('<Return>','enter'),('<Escape>','escape'),('<Delete>','delete_instance'),
                ('<Control-z>','undo'),('<Control-Z>','undo'),('<Control-s>','save'),('<Control-S>','save'),
                ('<Alt-Left>','previous'),('<Alt-Right>','next')):
            self.window.bind(sequence,lambda e,a=action:self.run_shortcut(a,e))
        self.window.bind('<F1>',lambda event:self.show_tool_help())
        self.window.bind('<F11>',self.toggle_fullscreen)

    def run_shortcut(self,action,event=None):
        # Let entries/text/comboboxes handle typing, paste, selection and undo.
        if self.in_text() and action!='save':return None
        # Win32 Mod1 (0x08) is NumLock, not Alt. X11 uses it for Alt.
        modifiers=4|(0x20000 if self.windowing_system=='win32' else 8)
        if len(action)==1 and event is not None and getattr(event,'state',0)&modifiers:return None
        if action=='save':self.save_context();return 'break'
        if action=='previous':self.navigate(-1);return 'break'
        if action=='next':self.navigate(1);return 'break'
        if action=='F':self.fit();return 'break'
        view=self.active_view()
        mode=next((row for row in MODE_KEYS if row[0]==action),None)
        if mode:
            if view.editable or mode[2]=='select':self.activate_mode(mode[2],mode[3])
        elif view.editable:
            if action in ('1','2','3','4'):self.short_class(action)
            elif action=='N':self.new_instance()
            elif action=='enter':
                if view.tool=='sam':self.accept_sam()
                elif view.tool=='polygon':view.finish_polygon()
            elif action=='escape':view.cancel_polygon()
            elif action=='delete_instance':view.delete_selected()
            elif action=='undo':view.undo()
        self.schedule_command_help();return 'break'

    def activate_mode(self,tool,action=None):
        self.tool_var.set(tool)
        if action is not None:self.node_action.set(action)
        self.set_tool()
        self.active_view().canvas.focus_set()

    def save_context(self):
        if self.phase=='manual':self.save_draft()
        elif self.active_view().editable:self.save_final()
        else:self.status_var.set('Vista de sólo lectura. Activa una adjudicación editable para guardar cambios.')

    def schedule_command_help(self):
        if self.command_help_pending is None:self.command_help_pending=self.window.after_idle(self.update_command_help)

    def update_command_help(self):
        self.command_help_pending=None;view=self.active_view();typing=self.in_text()
        if typing:
            title='ESCRITURA · atajos de herramientas suspendidos'
            actions='Puedes escribir con normalidad. Ctrl+S guarda · Haz clic en la imagen para volver a los atajos de edición.'
        elif not view.editable:
            title='COMPARACIÓN · sólo lectura'
            actions='Clic: seleccionar · Rueda: zoom · Botón derecho: mover vista · Para editar, activa «Adjudicación editable».'
        elif view.tool=='polygon':
            operation={'new':'Nueva instancia','union':'Añadir parte','subtract':'Quitar hueco'}[view.operation]
            title=f'P · POLÍGONO — {operation} · {len(view.points)} vértices'
            actions='Clic: añadir vértice · Enter: cerrar · Ctrl+Z: deshacer · Esc: cancelar'
        elif view.tool=='sam':
            state='máscara lista' if view.assist_preview is not None else 'calculando' if self.assist_future is not None else 'marca el capacho'
            title=f'S · SAM — {state} · {len(view.assist_points)} puntos'
            actions='Clic: incluir · Shift+clic: excluir · Enter: aceptar · Ctrl+Z: quitar punto · Esc: descartar'
        elif view.tool=='nodes':
            key,label={'drag':('M','MOVER'),'insert':('I','INSERTAR'),'delete':('D','ELIMINAR')}[view.node_action]
            title=f'{key} · NODOS — {label} · '+('instancia seleccionada' if view.selected else 'selecciona una instancia')
            actions={'drag':'Arrastra un nodo blanco para moverlo.', 'insert':'Clic junto a un segmento para insertar un nodo.',
                'delete':'Clic sobre un nodo para eliminarlo (mínimo 3).'}[view.node_action]
            actions+='  Shift+clic: insertar · Ctrl+clic: eliminar · Ctrl+Z: deshacer'
        elif view.tool in ('brush','erase'):
            title=('B · PINCEL' if view.tool=='brush' else 'E · BORRADOR')+f' — radio {view.brush} px'
            actions='Clic y arrastrar: '+('añadir superficie' if view.tool=='brush' else 'quitar superficie')+' · Control lateral: radio · Ctrl+Z: deshacer'
        else:
            title='V · SELECCIONAR INSTANCIA'
            actions='Clic sobre la máscara: seleccionar · M / I / D: editar nodos · B / E: pincel / borrador · Supr: eliminar instancia'
        self.command_title.set(title);self.command_actions.set(actions)
        step=0 if self.phase=='manual' else 2 if view.editable else 1
        for index,label in enumerate(self.step_labels):
            label.configure(bg=UI['soft'] if index==step else 'white',fg=UI['accent'] if index<=step else '#9aaba0')
        option_key=('brush' if view.tool=='erase' else view.tool) if view.editable else None
        if option_key!=self.visible_options:
            for panel in self.tool_options.values():
                panel.pack_forget()
            if option_key in self.tool_options:
                self.tool_options[option_key].pack(side='right',padx=(12,0),before=self.command_instructions)
            self.visible_options=option_key
        self.sam_accept.state(['!disabled'] if view.assist_preview is not None else ['disabled'])
        self.class_menu.current(('0','1','2','?').index(self.class_var.get()))
        self.class_menu.configure(state='readonly' if view.editable else 'disabled')
        self.new_instance_button.configure(state='normal' if view.editable else 'disabled')
        for button,tool,action in self.command_buttons:
            active=tool==view.tool and (tool!='nodes' or action==view.node_action)
            button.configure(style='ActiveMode.TButton' if active and not typing else 'Mode.TButton',
                state='normal' if view.editable or tool=='select' else 'disabled')

    def build_command_bar(self):
        # Reserve this space BEFORE the expanding editor so it stays on screen.
        self.command_bar=ttk.Frame(self.window,style='Card.TFrame');self.command_bar.pack(side='bottom',fill='x')
        context=ttk.Frame(self.command_bar,style='Card.TFrame',padding=(14,5));context.pack(fill='x')
        self.visible_options=None
        self.tool_options=self.build_tool_options(context)
        instructions=ttk.Frame(context,style='Card.TFrame')
        self.command_instructions=instructions
        instructions.pack(side='left',fill='x',expand=True)
        title=tk.Label(instructions,textvariable=self.command_title,bg=UI['surface'],fg=UI['accent'],font=('Segoe UI',11,'bold'),anchor='w')
        self.command_heading=title
        title.pack(fill='x')
        actions=tk.Label(instructions,textvariable=self.command_actions,bg=UI['surface'],fg=UI['ink'],font=('Segoe UI',10),justify='left',anchor='w',wraplength=720)
        self.command_text=actions
        actions.pack(fill='x',pady=(3,0))
        def wrap_instructions(event):
            width=max(120,event.width)
            title.configure(wraplength=width,justify='left')
            actions.configure(wraplength=width)

        instructions.bind('<Configure>',wrap_instructions)
        modes=ttk.Frame(self.command_bar,style='Card.TFrame',padding=(12,2,12,5));modes.pack(fill='x');self.command_buttons=[]
        help_button=ttk.Menubutton(modes,text='Ayuda [F1]')
        help_menu=tk.Menu(help_button,tearoff=False)
        help_menu.add_command(label='Herramienta activa',command=self.show_tool_help)
        help_menu.add_separator()
        for key,label,_,_ in MODE_KEYS:
            help_menu.add_command(label=f'{key} · {label}',command=lambda k=key:self.show_tool_help(k))
        help_menu.add_separator()
        help_menu.add_command(label='Atajos generales',command=lambda:self.show_tool_help('general'))
        help_button.configure(menu=help_menu)
        mode_widgets=[]
        for key,label,tool,action in MODE_KEYS:
            button=ttk.Button(modes,text=f'[{key}] {label}',style='Mode.TButton',command=lambda t=tool,a=action:self.activate_mode(t,a))
            mode_widgets.append(button)
            self.command_buttons.append((button,tool,action))
        self.wrap_controls(modes,[*mode_widgets,help_button],padding=24)
        status=ttk.Label(self.command_bar,textvariable=self.status_var,style='Muted.TLabel',
                         padding=(14,0,14,4),wraplength=720)
        self.command_bar.bind('<Configure>',lambda event:status.configure(wraplength=max(280,event.width-28)),add='+')

        def show_status(*args):
            if self.status_var.get():
                status.pack(fill='x')
            else:
                status.pack_forget()

        self.status_var.trace_add('write',show_status)

    def build_tool_options(self,parent):
        options={}
        for tool in ('polygon','sam','brush','select'):
            options[tool]=ttk.Frame(parent,style='Card.TFrame')
        polygon=options['polygon']
        ttk.Button(polygon,text='+ Parte',command=lambda:self.region_operation('union')).pack(side='left',padx=3)
        ttk.Button(polygon,text='− Hueco',command=lambda:self.region_operation('subtract')).pack(side='left')
        sam=options['sam']
        ttk.Button(sam,textvariable=self.assist_model_label,command=self.select_sam_model).pack(side='left',padx=(0,4))
        ttk.Combobox(sam,textvariable=self.assist_device,values=('auto','cpu'),state='readonly',width=4).pack(side='left')
        self.sam_accept=ttk.Button(sam,text='Aceptar [Enter]',style='Accent.TButton',command=self.accept_sam)
        self.sam_accept.pack(side='left',padx=(6,0))
        ttk.Button(sam,text='Descartar [Esc]',command=self.discard_sam).pack(side='left',padx=(5,0))
        brush=options['brush']
        ttk.Label(brush,text='Radio',style='Muted.TLabel').pack(side='left',padx=(0,7))
        self.brush_scale=ttk.Scale(brush,from_=1,to=45,length=126,command=self.brush_change)
        self.brush_scale.set(10)
        self.brush_scale.pack(side='left')
        selected=options['select']
        ttk.Button(selected,text='Acercar',command=lambda:self.active_view().focus_selected()).pack(side='left',padx=3)
        ttk.Button(selected,text='Eliminar instancia [Supr]',style='Danger.TButton',command=lambda:self.active_view().delete_selected()).pack(side='left')
        return options

    def show_tool_help(self,key=None):
        view=self.active_view()
        if key is None:
            key=next((k for k,_,tool,action in MODE_KEYS if view.tool==tool and
                      (action is None or action==view.node_action)),'V') if view.editable else 'V'
        title=next((label for letter,label,_,_ in MODE_KEYS if letter==key),'Atajos generales')
        popup=tk.Toplevel(self.window)
        popup.withdraw()
        popup.title(f'Ayuda · {title}')
        popup.transient(self.window)
        popup.resizable(False,False)
        panel=ttk.Frame(popup,style='Card.TFrame',padding=20)
        panel.pack(fill='both',expand=True)
        ttk.Label(panel,text=title if key=='general' else f'{title}  [{key}]',style='Section.TLabel').pack(anchor='w')
        ttk.Label(panel,text=TOOL_HELP[key],wraplength=405,justify='left').pack(anchor='w',pady=12)
        ttk.Button(panel,text='Cerrar',command=popup.destroy).pack(anchor='e')
        popup.bind('<Escape>',lambda event:popup.destroy())
        self.show_centered(popup)
        return popup

    def enable_column_scroll(self,canvas,content):
        def wheel(event):
            canvas.yview_scroll(-1 if event.delta>0 else 1,'units');return 'break'
        def visit(widget):
            if not isinstance(widget,(tk.Listbox,tk.Text,ttk.Combobox,tk.Entry,ttk.Entry)):
                widget.bind('<MouseWheel>',wheel,add='+')
            for child in widget.winfo_children():visit(child)
        visit(content);canvas.bind('<MouseWheel>',wheel)

    @staticmethod
    def wrap_controls(parent,widgets,padding=0):
        """Flow groups intact onto the next row using their native DPI sizes."""
        row_frames=[ttk.Frame(parent,style='Card.TFrame') for _ in widgets]
        row_frames[0].pack(fill='x')
        counts=(len(widgets),)
        for widget in widgets:
            widget.pack(side='left',padx=2,in_=row_frames[0])

        def layout(event):
            nonlocal counts
            available=event.width-padding
            next_rows=[[]]
            used=0
            for widget in widgets:
                width=widget.winfo_reqwidth()+4
                if next_rows[-1] and used+width>available:
                    next_rows.append([])
                    used=0
                next_rows[-1].append(widget)
                used+=width
            signature=tuple(len(row) for row in next_rows)
            if signature==counts:
                return
            counts=signature
            for widget in widgets:
                widget.pack_forget()
            for frame in row_frames:
                frame.pack_forget()
            for frame,group in zip(row_frames,next_rows):
                frame.pack(fill='x')
                for widget in group:
                    widget.pack(side='left',padx=2,pady=1,in_=frame)

        parent.bind('<Configure>',layout,add='+')

    def build_navigation_bar(self):
        toolbar=ttk.Frame(self.window,style='Card.TFrame',padding=(13,6))
        toolbar.pack(fill='x')
        images=ttk.Frame(toolbar,style='Card.TFrame')
        ttk.Button(images,text='←',width=2,command=lambda:self.navigate(-1)).pack(side='left')
        ttk.Button(images,text='→',width=2,command=lambda:self.navigate(1)).pack(side='left',padx=(3,9))
        ttk.Label(images,text='Imagen').pack(side='left',padx=(0,4))
        self.queue=ttk.Combobox(images,width=11,state='readonly',height=14)
        self.queue.pack(side='left')
        self.queue.bind('<<ComboboxSelected>>',self.queue_change)
        instances=ttk.Frame(toolbar,style='Card.TFrame')
        ttk.Label(instances,text='Instancia').pack(side='left',padx=(0,4))
        self.instances=ttk.Combobox(instances,width=13,state='readonly',height=14)
        self.instances.pack(side='left')
        self.instances.bind('<<ComboboxSelected>>',self.object_selected)
        classes=ttk.Frame(toolbar,style='Card.TFrame')
        ttk.Label(classes,text='Clase').pack(side='left',padx=(0,4))
        self.class_menu=ttk.Combobox(classes,values=tuple(f'{n} · {name}' for n,name in enumerate(CLASSES.values(),1)),
                                     width=14,state='readonly')
        self.class_menu.pack(side='left',padx=(0,7))
        self.class_menu.bind('<<ComboboxSelected>>',self.choose_class)
        self.new_instance_button=ttk.Button(classes,text='Nueva [N]',command=self.new_instance)
        self.new_instance_button.pack(side='left')
        actions=ttk.Frame(toolbar,style='Card.TFrame')
        ttk.Button(actions,text='Perfil…',command=self.edit_reviewer).pack(side='left')
        ttk.Button(actions,text='Exportar',command=self.export).pack(side='left',padx=3)
        self.wrap_controls(toolbar,[images,instances,classes,actions],padding=26)

    def toggle_notes(self):
        if self.notes.winfo_manager():
            self.notes.pack_forget()
            self.note_button.configure(text='Notas de revisión')
            self.active_view().canvas.focus_set()
        else:
            self.notes.pack(fill='x',pady=(5,0))
            self.note_button.configure(text='Ocultar notas')
            self.notes.focus_set()

    def choose_class(self,event=None):
        index=self.class_menu.current()
        if index>=0 and self.active_view().editable:
            self.class_var.set(('0','1','2','?')[index])
            self.set_class()
        self.active_view().canvas.focus_set()

    def build(self):
        header=tk.Frame(self.window,bg=UI['forest'],padx=20,pady=14);header.pack(fill='x')
        self.header=header
        brand(header).pack(side='left',padx=(0,12))
        identity=tk.Frame(header,bg=UI['forest']);identity.pack(side='left')
        self.header_subtitle=tk.Label(identity,text='UCHUVA  /  ANNOTATION LAB',bg=UI['forest'],
                                      fg='#b4d4bf',font=('Segoe UI',9,'bold'),anchor='w')
        self.header_subtitle.pack(fill='x')
        self.header_title=tk.Label(identity,text='Auditoría de segmentación',bg=UI['forest'],
                                   fg='white',font=('Segoe UI',20,'bold'),anchor='w')
        self.header_title.pack(fill='x')
        self.fullscreen_button=ttk.Button(header,text='Pantalla [F11]',command=self.toggle_fullscreen)
        self.fullscreen_button.pack(side='right')
        self.progress_badge=tk.Label(header,textvariable=self.progress_var,bg='#275744',fg='#e1f2e5',
                                    font=('Segoe UI',10,'bold'),padx=14,pady=10)
        self.progress_badge.pack(side='right',padx=(0,10))
        workflow=tk.Frame(self.window,bg='white',padx=18,pady=8);workflow.pack(fill='x')
        self.workflow=workflow
        for text in ('01  ANOTAR','02  CONTRASTAR','03  ADJUDICAR'):
            label=tk.Label(workflow,text=text,bg='white',fg=UI['muted'],font=('Segoe UI',9,'bold'),padx=9,pady=4)
            label.pack(side='left',padx=(0,10));self.step_labels.append(label)
        ttk.Label(workflow,text='Originales protegidos · Guardado local',style='Muted.TLabel').pack(side='right')
        self.phase_label=ttk.Label(self.window,textvariable=self.phase_var,style='Phase.TLabel')
        self.phase_label.pack(fill='x')
        self.phase_label.bind('<Configure>',lambda event:self.phase_label.configure(wraplength=max(280,event.width-32)))
        self.build_navigation_bar()
        self.build_command_bar()
        body=ttk.Frame(self.window,padding=(12,12,0,0));body.pack(fill='both',expand=True)
        # The inspector has its own column: it never covers annotation pixels.
        inspector_shell=ttk.Frame(body,width=372);inspector_shell.pack(side='right',fill='y',padx=(0,12));inspector_shell.pack_propagate(False)
        self.inspector_shell=inspector_shell
        note_corner=ttk.Frame(inspector_shell,style='Card.TFrame',padding=(8,5))
        note_corner.pack(side='bottom',fill='x')
        self.note_button=ttk.Button(note_corner,text='Notas de revisión',command=self.toggle_notes)
        self.note_button.pack(anchor='e')
        self.notes=tk.Text(note_corner,height=3,font=('Segoe UI',10),wrap='word',
            bg='#f7faf7',fg=UI['ink'],insertbackground=UI['accent'],undo=True,
            relief='flat',highlightthickness=1,highlightbackground=UI['line'],highlightcolor=UI['accent'],padx=7,pady=5)
        inspector_canvas=tk.Canvas(inspector_shell,bg=UI['background'],highlightthickness=0)
        inspector_scroll=ttk.Scrollbar(inspector_shell,orient='vertical',command=inspector_canvas.yview)
        inspector_scroll.pack(side='right',fill='y');inspector_canvas.pack(side='left',fill='both',expand=True)
        inspector_canvas.configure(yscrollcommand=inspector_scroll.set)
        inspector=ttk.Frame(inspector_canvas);inspector_item=inspector_canvas.create_window(0,0,window=inspector,anchor='nw')
        inspector.bind('<Configure>',lambda e:inspector_canvas.configure(scrollregion=inspector_canvas.bbox('all')))
        inspector_canvas.bind('<Configure>',lambda e:inspector_canvas.itemconfigure(inspector_item,width=e.width))
        dock=ttk.Frame(inspector,style='Card.TFrame',height=420);dock.pack(fill='x',pady=(0,10))
        self.reference_tool=ReferenceLoupe(dock,on_used=self.reference_used)
        self.reference_tool.place(relx=1.0,x=0,y=0,anchor='ne');self.reference_tool.lift()
        self.reference_tool.bind('<Configure>',lambda e:dock.configure(height=e.height))
        self.window.after_idle(lambda:dock.configure(height=self.reference_tool.winfo_reqheight()))
        work=ttk.Frame(body,style='Card.TFrame',padding=10);work.pack(side='left',fill='both',expand=True,padx=(0,12))
        toolbar=ttk.Frame(work,style='Card.TFrame');toolbar.pack(fill='x',pady=(0,8))
        ttk.Label(toolbar,textvariable=self.editor_info,style='Eyebrow.TLabel').pack(side='left')
        ttk.Checkbutton(toolbar,text='Ver cajas',variable=self.box_var,command=self.toggle_boxes).pack(side='left',padx=12)
        ttk.Button(toolbar,text='Encajar  [F]',command=self.fit).pack(side='right')
        ttk.Button(toolbar,text='−',width=3,command=lambda:self.active_view().zoom(1/1.3)).pack(side='right',padx=3)
        ttk.Button(toolbar,text='+',width=3,command=lambda:self.active_view().zoom(1.3)).pack(side='right')
        editor_bottom=ttk.Frame(work,style='Card.TFrame');editor_bottom.pack(side='bottom',fill='x')
        self.panels=ttk.Panedwindow(work,orient='horizontal');self.panels.pack(fill='both',expand=True)
        left_frame=ttk.Frame(self.panels,style='Card.TFrame')
        self.left_label=ttk.Label(left_frame,text='Superficie visible del capacho',style='Muted.TLabel',padding=(2,0,0,7));self.left_label.pack(fill='x')
        self.left=MaskCanvas(left_frame,self.changed,self.canvas_selected,self.current_class);self.left.pack(fill='both',expand=True)
        self.panels.add(left_frame,weight=1);self.left_frame=left_frame
        self.right_frame=ttk.Frame(self.panels,style='Card.TFrame');self.right_toolbar=ttk.Frame(self.right_frame,style='Card.TFrame');self.right_toolbar.pack(fill='x')
        comparison_tabs=[]
        for value,label in [('proposal','Propuesta'),('original','Original'),('final','Adjudicación')]:
            comparison_tabs.append(ttk.Radiobutton(self.right_toolbar,text=label,value=value,variable=self.right_var,
                                                    style='Tab.TRadiobutton',command=self.show_right))
        self.wrap_controls(self.right_toolbar,comparison_tabs)
        self.right=MaskCanvas(self.right_frame,self.changed,self.canvas_selected,self.current_class);self.right.pack(fill='both',expand=True)
        self.comparison_frame=ttk.Frame(editor_bottom,style='Card.TFrame',padding=5)
        self.comparison_label=ttk.Label(self.comparison_frame,text='',wraplength=700,style='Muted.TLabel');self.comparison_label.pack(fill='x')
        self.comparison_frame.bind('<Configure>',lambda event:self.comparison_label.configure(wraplength=max(280,event.width-10)))
        actions=ttk.Frame(self.comparison_frame,style='Card.TFrame');actions.pack(fill='x',pady=4)
        self.wrap_controls(actions,[
            ttk.Button(actions,text='Copiar manual',command=lambda:self.adopt('manual')),
            ttk.Button(actions,text='Copiar propuesta',command=lambda:self.adopt('proposal')),
            ttk.Button(actions,text='Guardar adjudicación',style='Accent.TButton',command=self.save_final),
        ])
        self.blind_controls=ttk.Frame(editor_bottom,style='Card.TFrame',padding=(0,8,0,0));self.blind_controls.pack(fill='x')
        ttk.Checkbutton(self.blind_controls,text='Sin instancias',variable=self.empty_var).pack(side='left')
        ttk.Button(self.blind_controls,text='Borrador  [Ctrl+S]',command=self.save_draft).pack(side='right',padx=(6,0))
        self.commit_button=ttk.Button(self.blind_controls,text='Guardar y comparar →',style='Accent.TButton',command=self.commit);self.commit_button.pack(side='right')
        self.left.cursor_callback=self.right.cursor_callback=self.reference_tool.observe
        for view in (self.left,self.right):
            view.assist_callback=self.request_assistance;view.error_callback=lambda error:messagebox.showinfo('Edición de borde',error)
            view.context_callback=self.schedule_command_help
        self.enable_column_scroll(inspector_canvas,inspector)

    def select_sam_model(self):
        if self.assist_future is not None:
            messagebox.showinfo('SAM ocupado','Espera a que termine la segmentación actual.');return
        path=filedialog.askopenfilename(title='Pesos locales MobileSAM / SAM / SAM2',filetypes=[('Pesos SAM','*.pt')])
        if not path:return
        from uchuva_annotation_audit.assistance import SUPPORTED
        if Path(path).name not in SUPPORTED:
            messagebox.showerror('Modelo incompatible','Usa un nombre de pesos MobileSAM, SAM o SAM2 compatible con Ultralytics.');return
        self.assist_model_path=path;self.assist_expected_sha=None;self.assist_backend=None
        self.assist_model_label.set(Path(path).stem+'…');self.discard_sam()

    def request_assistance(self,view):
        if not view.editable or view.image is None:return
        if not any(view.assist_labels):
            self.status_var.set('SAM: añade un clic positivo dentro del capacho. Shift+clic excluye fondo.');return
        self.assist_pending=(view,view.assist_serial,self.current,view.image.copy(),copy.deepcopy(view.assist_points),view.assist_labels[:])
        self.start_assistance_job()

    def start_assistance_job(self):
        if self.assist_future is not None or self.assist_pending is None or self.assist_closed:return
        job=self.assist_pending;self.assist_pending=None
        view,serial,ident,image,points,labels=job
        if ident!=self.current or serial!=view.assist_serial or not view.editable or view.tool!='sam':return
        path=self.assist_model_path;expected=self.assist_expected_sha;device=self.assist_device.get()
        if self.assist_executor is None:self.assist_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='audit-sam')
        def infer():
            key=(path,device,expected)
            if self.assist_backend is None or self.assist_backend[0]!=key:
                self.assist_backend=(key,SamAssistant(path,device,expected))
            return self.assist_backend[1].predict(image,points,labels)
        self.assist_future=self.assist_executor.submit(infer);self.assist_job=job
        self.status_var.set('SAM calculando máscara… Puedes añadir clics + o Shift+clic −; la clase la eliges tú.')
        self.window.after(80,self.poll_assistance)

    def poll_assistance(self):
        if self.assist_closed:return
        if not self.assist_future.done():self.window.after(80,self.poll_assistance);return
        future=self.assist_future;view,serial,ident,*_=self.assist_job;self.assist_future=None
        current=ident==self.current and serial==view.assist_serial and view.editable and view.tool=='sam'
        try:
            mask,metadata=future.result()
            if current:
                view.assist_preview=mask;view.assist_metadata=metadata;view.redraw()
                self.status_var.set('Máscara provisional azul: acepta o añade puntos. Shift+clic excluye; Ctrl+Z quita el último punto.')
        except Exception as exc:
            if current:messagebox.showerror('No se pudo segmentar',str(exc))
        self.start_assistance_job()

    def discard_sam(self):
        view=self.active_view();view.clear_assistance();view.redraw()
        if self.assist_pending is not None and self.assist_pending[0] is view:self.assist_pending=None

    def accept_sam(self):
        view=self.active_view()
        if view.assist_preview is None:
            self.status_var.set('Selecciona SAM y marca el capacho. Espera la máscara antes de aceptarla.');return
        obj=view.accept_assistance()
        if obj is None:return
        self.store.runtime_context['segmentation_assistance_used']=True
        self.tool_var.set('nodes');self.node_action.set('drag');view.node_action='drag';view.tool='nodes';view.refresh_nodes();view.redraw()
        self.status_var.set('Máscara aceptada como instancia nueva. Arrastra los nodos blancos o usa pincel/borrador; la clase sigue siendo manual.')

    def reference_used(self,kind,details):
        context=self.store.runtime_context
        if kind=='loupe':context['loupe_used_for_this_image']=True;context['last_loupe_zoom']=details['zoom']
        elif kind=='palette':context['palette_grades_consulted']=sorted(set(context.get('palette_grades_consulted',[])+[details['grade']]))
        elif kind=='reference_image':context['reference_image_opened']=True

    def fit(self):
        self.left.fit()
        if self.phase!='manual':self.right.fit()
    def toggle_boxes(self):
        for view in (self.left,self.right):view.show_boxes=self.box_var.get();view.redraw()
    def set_tool(self):
        view=self.active_view();view.tool=self.tool_var.get();view.node_action=self.node_action.get()
        view.cancel_polygon();view.refresh_nodes();view.redraw()
    def set_node_action(self):
        self.tool_var.set('nodes');self.set_tool();self.active_view().node_action=self.node_action.get()
    def brush_change(self,value):
        if hasattr(self,'left'):
            self.left.brush=self.right.brush=max(1,round(float(value)))
            self.schedule_command_help()
    def short_class(self,key):
        if not self.in_text():self.class_var.set({'1':'0','2':'1','3':'2','4':'?'}[key]);self.set_class()
    def set_class(self):
        view=self.active_view()
        if view.editable and view.selected:
            view.snapshot()
            next(o for o in view.objects if o['id']==view.selected)['class_id']=self.current_class()
            view.redraw();self.changed()
    def new_instance(self):
        view=self.active_view()
        if not view.editable:return
        view.clear_assistance();view.node_rings=[];view.selected=None;view.operation='new';view.points=[]
        if self.tool_var.get()!='sam':view.tool='polygon';self.tool_var.set('polygon')
        view.redraw();self.refresh_objects()
    def region_operation(self,operation):
        view=self.active_view()
        if not view.editable:return
        if not view.selected:messagebox.showinfo('Selecciona una instancia','Selecciona primero la máscara a la que añadir una parte o quitar un hueco.');return
        view.operation=operation;view.points=[];view.tool='polygon';self.tool_var.set('polygon')
        self.status_var.set('Dibuja el contorno de la región y pulsa Enter. La instancia conserva sus otras partes.')
    def canvas_selected(self,ident):
        obj=next((o for o in self.active_view().objects if o['id']==ident),None)
        if obj:self.class_var.set('?' if obj['class_id'] is None else str(obj['class_id']))
        self.refresh_objects()
    def object_selected(self,event=None):
        if self.syncing:return
        view=self.active_view()
        index=self.instances.current()-1
        if -1<=index<len(view.objects):
            view.choose(view.objects[index]['id'] if index>=0 else None)
        view.canvas.focus_set()
    def refresh_objects(self):
        self.syncing=True
        view=self.active_view()
        self.instances.configure(values=('Sin selección',*(f'{n} · {CLASSES[obj["class_id"]]}' for n,obj in enumerate(view.objects,1))))
        index=next((n for n,obj in enumerate(view.objects,1) if obj['id']==view.selected),0)
        self.instances.current(index)
        self.syncing=False
    def changed(self):
        self.refresh_objects();self.status_var.set('Máscaras editadas. Guarda el borrador o la adjudicación.')
    def queue_change(self,event=None):
        index=self.queue.current()
        if not self.syncing and 0<=index<len(self.ids):
            self.change_image(self.ids[index])
            # A pending edit may have prevented navigation.
            if self.current in self.ids:self.queue.current(self.ids.index(self.current))
        self.active_view().canvas.focus_set()
    def refresh_queue(self):
        progress=self.store.progress();self.progress_var.set(f'{progress["manual"]} / {progress["total"]} revisadas   ·   {progress["adjudicated"]} adjudicadas')
        self.syncing=True
        self.queue.configure(values=tuple(ident+(' · Revisada' if self.store.manual(ident) else '') for ident in self.ids))
        if self.current in self.ids:self.queue.current(self.ids.index(self.current))
        self.syncing=False
    def note_text(self):return self.notes.get('1.0','end').strip()
    def save_draft(self,quiet=False):
        if self.current and self.phase=='manual':
            if self.left.assist_points:
                if not quiet:messagebox.showinfo('Máscara SAM pendiente','Acepta la máscara o descarta los puntos antes de guardar o cambiar de imagen.')
                return False
            if self.left.points:
                if not quiet:messagebox.showinfo('Polígono abierto','Cierra el polígono con Enter o cancélalo con Escape antes de guardar.')
                return False
            try:self.store.save_draft(self.current,self.left.payload(),self.note_text(),self.elapsed_base+time.monotonic()-self.started)
            except Exception as exc:
                if not quiet:messagebox.showerror('No se pudo guardar',str(exc))
                return False
            if not quiet:self.status_var.set('Borrador guardado; la propuesta sigue oculta.')
        return True
    def navigate(self,delta):
        if self.current:self.change_image(self.ids[max(0,min(len(self.ids)-1,self.ids.index(self.current)+delta))])
    def change_image(self,ident):
        if ident==self.current:return
        if self.current and self.phase=='manual' and not self.save_draft():return
        if self.current and self.phase=='compare' and self.right.editable and self.right.undo_stack:
            if not messagebox.askyesno('Adjudicación sin guardar','Hay cambios en la adjudicación. ¿Cambiar de imagen sin guardarlos?'):return
        self.current=ident;self.started=time.monotonic();self.comparison_data=None;self.empty_var.set(False)
        self.reference_tool.reset()
        self.store.runtime_context.update(loupe_used_for_this_image=False,palette_grades_consulted=[],reference_image_opened=False)
        self.store.runtime_context['segmentation_assistance_used']=False
        image=Image.open(self.store.image_path(ident)).convert('RGB');manual=self.store.manual(ident)
        self.editor_info.set(f'{ident}  /  LIENZO    ·    {image.width} × {image.height} px')
        self.notes.delete('1.0','end')
        if manual is None:
            self.phase='manual';draft=self.store.draft(ident);self.elapsed_base=draft.get('elapsed_seconds',0)
            self.left.load(image,draft['objects'],True);self.notes.insert('1.0',draft.get('notes',''))
            self.store.runtime_context['segmentation_assistance_used']=bool(draft.get('application_context',{}).get('segmentation_assistance_used') or any(o.get('assistance') for o in draft['objects']))
            if str(self.right_frame) in self.panels.panes():self.panels.forget(self.right_frame)
            self.comparison_frame.pack_forget();self.blind_controls.pack(fill='x')
            self.phase_var.set(f'{ident} · PASO 1: anota manualmente. Propuestas y etiquetas originales ocultas.')
            self.left_label.configure(text='Tu segmentación manual · empieza sin contornos de ayuda')
            self.status_var.set('')
        else:
            self.phase='compare';self.comparison_data=self.store.comparison(ident)
            self.left.load(image,manual['objects'],False)
            if str(self.right_frame) not in self.panels.panes():self.panels.add(self.right_frame,weight=1)
            self.blind_controls.pack_forget();self.comparison_frame.pack(fill='x')
            self.left_label.configure(text='Primera anotación manual congelada · sin cambios posteriores')
            self.phase_var.set(f'{ident} · PASO 2: compara y, si quieres, guarda una adjudicación separada.')
            self.right_var.set('proposal');self.show_right()
            stats=self.comparison_data['comparison']
            self.comparison_label.configure(text=f'Manual / propuesta — IoU de MÁSCARA ≥0,5: {len(stats["matches"])} pares; '+
                f'{stats["agreeing_resolved_pairs"]}/{stats["resolved_pairs"]} coinciden en clase; '+
                f'{len(stats["unmatched_manual"])} instancias manuales sin par y {len(stats["unmatched_proposal"])} propuestas sin par. Es acuerdo, no exactitud validada.')
            self.notes.insert('1.0',(self.store.latest_final(ident) or {}).get('notes',''))
        self.notes.edit_reset()
        self.left.tool=self.right.tool=self.tool_var.get()
        self.left.node_action=self.right.node_action=self.node_action.get()
        self.active_view().refresh_nodes();self.refresh_objects();self.refresh_queue()
        self.save_preferences()
        self.window.after(80,self.fit)
    def show_right(self):
        if self.phase!='compare' or self.comparison_data is None:return
        if self.right.editable and self.right.undo_stack:
            if not messagebox.askyesno('Cambios sin guardar','¿Descartar los cambios de adjudicación al cambiar de vista?'):
                self.right_var.set('final');return
        choice=self.right_var.get()
        if choice=='final':objects=(self.store.latest_final(self.current) or self.comparison_data['manual'])['objects']
        else:objects=self.comparison_data[choice]['objects']
        self.right.load(self.left.image,objects,choice=='final');self.right.tool=self.tool_var.get();self.refresh_objects()
        self.window.after(30,self.right.fit)
    def adopt(self,kind):
        if self.phase!='compare':return
        if not messagebox.askyesno('Copia editable',f'Crear una copia de {"tu manual" if kind=="manual" else "la propuesta"} para adjudicar. La primera versión manual se conserva intacta. ¿Continuar?'):return
        self.right_var.set('final');self.right.load(self.left.image,self.comparison_data[kind]['objects'],True)
        self.right.tool=self.tool_var.get();self.refresh_objects();self.status_var.set('Edita la adjudicación y guárdala por separado. Ninguna etiqueta de entrenamiento se sobrescribe.')
    def commit(self):
        if self.phase!='manual':return
        if not self.save_draft():return
        if not self.reviewer.get().strip():messagebox.showinfo('Persona revisora','Indica tu nombre o identificador antes de guardar.');return
        if not messagebox.askyesno('Congelar primera anotación manual','Se guardará tu segmentación manual y después se revelará la propuesta. Esta primera versión no se sobrescribirá. ¿Terminaste de anotar esta imagen?'):return
        try:
            self.store.commit_manual(self.current,self.left.payload(),self.reviewer.get(),self.note_text(),self.empty_var.get(),self.elapsed_base+time.monotonic()-self.started)
        except Exception as exc:messagebox.showerror('No se pudo guardar',str(exc));return
        ident=self.current;self.current=None;self.change_image(ident)
    def save_final(self):
        if self.phase!='compare' or not self.right.editable:messagebox.showinfo('Adjudicación','Activa «Adjudicación editable» o crea una copia del manual/propuesta.');return
        if self.right.points:messagebox.showinfo('Polígono abierto','Cierra el polígono antes de guardar.');return
        if self.right.assist_points:messagebox.showinfo('Máscara SAM pendiente','Acepta o descarta la máscara antes de guardar.');return
        try:payload=self.store.save_final(self.current,self.right.payload(),self.reviewer.get(),self.note_text())
        except Exception as exc:messagebox.showerror('No se pudo guardar',str(exc));return
        self.right.undo_stack=[];self.refresh_queue();self.status_var.set(f'Adjudicación revisión {payload["revision"]} guardada; dataset original intacto.')
    def export(self):
        if self.phase=='manual' and not self.save_draft():return
        try:path=self.store.export()
        except Exception as exc:messagebox.showerror('Error al exportar',str(exc));return
        messagebox.showinfo('Auditoría exportada',f'Sólo incluye imágenes con manual confirmado.\n\n{path}')
        self.status_var.set('Exportado: '+str(path))
    def close(self):
        if self.current and self.phase=='manual' and not self.save_draft():
            if not messagebox.askyesno('Borrador no guardado','¿Cerrar sin guardar los cambios actuales?'):return
        if self.phase=='compare' and self.right.editable and self.right.undo_stack:
            if not messagebox.askyesno('Adjudicación no guardada','¿Cerrar sin guardar la adjudicación actual?'):return
        self.save_preferences()
        self.assist_closed=True
        if self.assist_executor:self.assist_executor.shutdown(wait=False,cancel_futures=True)
        self.lock.close();self.window.destroy()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=REPO/'outputs/blind_segmentation_50_20261113')
    parser.add_argument('--session',default='principal')
    args=parser.parse_args()
    if os.name=='nt':
        # Per-process DPI awareness keeps native canvas input and pixels aligned.
        # This does not change any Windows display setting.
        import ctypes
        try:ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError,OSError):pass
    window=tk.Tk();window.withdraw()
    try:store=AuditStore(args.root,args.session);app=AuditApp(window,store)
    except Exception as exc:messagebox.showerror('No se pudo abrir la auditoría',str(exc));window.destroy();return
    app.show()
    window.mainloop()


if __name__=='__main__':main()
