"""RGB-only loupe and reproducible swatches from the supplied NTC illustration.

The illustration and historical grouping are visual aids, not calibrated
colorimetry or a rule that assigns annotation classes from pixel colors.
"""
from pathlib import Path
import hashlib,json,math,statistics
import tkinter as tk
from tkinter import font,ttk
from PIL import Image,ImageDraw,ImageTk
from .ui_theme import UI

REPO=Path(__file__).resolve().parents[2]
REFERENCE=REPO/'Nuevo Dataset/Norma.webp'
PALETTE=REPO/'docs/references/annotation_norma_palette.json'
VERSION='reference-loupe/2'
LOUPE_WIDTH=336
LOUPE_HEIGHT=148


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def disk_sample(image,center,radius):
    """Channel medians from a declared circular patch; no inferred class."""
    x,y=center;rgb=image.convert('RGB')
    points=[(xx,yy) for yy in range(max(0,y-radius),min(rgb.height,y+radius+1))
            for xx in range(max(0,x-radius),min(rgb.width,x+radius+1))
            if (xx-x)**2+(yy-y)**2<=radius**2]
    if not points:raise ValueError('La región de muestreo está fuera de la imagen')
    values=[rgb.getpixel(p) for p in points]
    return tuple(int(statistics.median(v[channel] for v in values)) for channel in range(3))


def hex_color(rgb):return '#'+''.join(f'{v:02x}' for v in rgb)


def load_palette(path=PALETTE,reference=REFERENCE):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if digest(reference)!=data['source_sha256']:raise ValueError('La lámina de referencia cambió; revisar el muestreo antes de usarla')
    image=Image.open(reference).convert('RGB')
    if list(image.size)!=data['source_size']:raise ValueError('Dimensiones de referencia diferentes')
    for grade in data['grades']:
        for kind in ('calyx','fruit'):
            patch=grade[kind]
            if list(disk_sample(image,patch['center'],patch['radius']))!=patch['rgb']:
                raise ValueError('La paleta no reproduce los píxeles de la lámina')
    return data,image


def magnified_patch(image,point,zoom=4,size=(292,174)):
    """Integer-pixel RGB view; padded outside bounds, never moves the focus."""
    if zoom not in (2,4,8,12):raise ValueError('Aumento inválido')
    rgb=image.convert('RGB');x,y=point
    if not (math.isfinite(x) and math.isfinite(y) and 0<=x<rgb.width and 0<=y<rgb.height):
        raise ValueError('Punto fuera de la imagen')
    x,y=int(x),int(y);w,h=size
    left=x-w//(2*zoom);top=y-h//(2*zoom)
    right=left+math.ceil(w/zoom);bottom=top+math.ceil(h/zoom)
    valid=(max(0,left),max(0,top),min(rgb.width,right),min(rgb.height,bottom))
    output=Image.new('RGB',size,'#142333')
    crop=rgb.crop(valid);crop=crop.resize((crop.width*zoom,crop.height*zoom),Image.Resampling.NEAREST)
    output.paste(crop,((valid[0]-left)*zoom,(valid[1]-top)*zoom))
    neighborhood=[rgb.getpixel((xx,yy)) for yy in range(max(0,y-2),min(rgb.height,y+3))
                  for xx in range(max(0,x-2),min(rgb.width,x+3))]
    median=tuple(int(statistics.median(v[c] for v in neighborhood)) for c in range(3))
    return dict(image=output,pixel=rgb.getpixel((x,y)),median=median,
                point=(x,y),crosshair=((x-left)*zoom+zoom//2,(y-top)*zoom+zoom//2))


class ReferenceLoupe(ttk.Frame):
    """Self-contained reference tool; receives raw RGB, never model records."""
    def __init__(self,parent,on_used,reference=REFERENCE,palette=PALETTE):
        super().__init__(parent,padding=9,style='Card.TFrame',relief='flat',borderwidth=0)
        self.on_used=on_used;self.pending=None;self.scheduled=None;self.last=None;self.selected_grade=None
        self.zoom=tk.IntVar(value=4);self.frozen=tk.BooleanVar(value=False);self.swatches=[];self.reference_window=None
        self.viewport=(LOUPE_WIDTH,LOUPE_HEIGHT)
        self.reference=Path(reference);self.palette_path=Path(palette)
        try:self.palette,self.reference_image=load_palette(palette,reference);self.error=None
        except (OSError,ValueError) as exc:self.palette=None;self.reference_image=None;self.error=str(exc)
        head=ttk.Frame(self,style='Card.TFrame');head.pack(fill='x')
        ttk.Label(head,text='Lupa de inspección',font=('Segoe UI',12,'bold')).pack(side='left')
        self.display=tk.Canvas(self,width=LOUPE_WIDTH,height=LOUPE_HEIGHT,bg='#142333',highlightthickness=0)
        self.display.pack(pady=(5,0))
        self.show_placeholder()
        if self.palette:
            # Put the calyx chips against the ROI, with grade and empirical class below.
            self.palette_canvas=tk.Canvas(self,width=LOUPE_WIDTH,height=88,bg=UI['surface'],highlightthickness=0)
            self.palette_canvas.pack()
            self.grade_font=font.Font(root=self,family='Segoe UI',size=9,weight='bold')
            self.group_font=font.Font(root=self,family='Segoe UI',size=8)
            for i,grade in enumerate(self.palette['grades']):
                x=1+i*48;tag=f'grade_{i}_calyx'
                item=self.palette_canvas.create_rectangle(x,0,x+46,25,fill=grade['calyx']['hex'],outline='#61736d',tags=(tag,))
                self.palette_canvas.create_text(x+23,37,text=str(grade['grade']),font=self.grade_font,tags=(tag,))
                group=grade['agreed_visual_group']
                self.palette_canvas.create_text(x+23,50,text=group,anchor='n',width=46,font=self.group_font,tags=(tag,))
                self.swatches.append((item,i,'calyx'))
                self.palette_canvas.tag_bind(tag,'<Button-1>',lambda e,g=i:self.select_grade(g))
        controls=ttk.Frame(self,style='Card.TFrame');controls.pack(fill='x',pady=(3,0))
        ttk.Combobox(controls,textvariable=self.zoom,values=(2,4,8,12),state='readonly',width=4).pack(side='left')
        ttk.Label(controls,text='×').pack(side='left');ttk.Checkbutton(controls,text='Fijar',variable=self.frozen).pack(side='right')
        self.zoom.trace_add('write',lambda *_:self.refresh_last())
        self.pixel_label=ttk.Label(self,text='Píxel: — · Mediana 5×5: —',style='Muted.TLabel',font=('Segoe UI',8));self.pixel_label.pack(anchor='w',pady=3)
        if self.palette:
            ttk.Label(self,text='Referencia NTC 4580 · grados 0–6',font=('Segoe UI',10,'bold')).pack(anchor='w')
            self.sample_label=ttk.Label(self,text='Capacho: pulsa un color para ver su RGB.',font=('Segoe UI',8));self.sample_label.pack(anchor='w')
            ttk.Label(self,text='Clase empírica · RGB no calibrado.',font=('Segoe UI',8),foreground='#745a30').pack(anchor='w')
            ttk.Button(self,text='Ver lámina y zonas muestreadas',command=self.show_reference).pack(fill='x',pady=(5,0))
        else:
            ttk.Label(self,text='No se pudo cargar la referencia:\n'+self.error,wraplength=288,foreground='#a14437').pack(fill='x')

    def show_placeholder(self):
        width,height=self.viewport
        self.display.delete('all')
        self.display.create_text(width/2,height/2,text='Mueve el cursor sobre la imagen',fill='white',width=width-30)

    def resize(self,width,height):
        self.viewport=(width,height)
        self.display.configure(width=width,height=height)
        if self.palette:
            cell=width/len(self.swatches)
            text_size=min(15,max(9,round(cell*.27)))
            self.group_font.configure(size=-text_size)
            self.grade_font.configure(size=-(text_size+1))
            # Fit the longest ordinary class on its chip, reserving two lines
            # for the longer label Sobremadura.
            while self.group_font.measure('Pintona')>cell-3 and text_size>9:
                text_size-=1
                self.group_font.configure(size=-text_size)
            swatch_height=22 if height<LOUPE_HEIGHT else 25
            grade_center=swatch_height+2+self.grade_font.metrics('linespace')/2
            group_top=swatch_height+4+self.grade_font.metrics('linespace')
            palette_height=group_top+2*self.group_font.metrics('linespace')+3
            self.palette_canvas.configure(width=width,height=palette_height)
            for item,index,_ in self.swatches:
                _,number,group=self.palette_canvas.find_withtag(f'grade_{index}_calyx')
                x=index*cell
                self.palette_canvas.coords(item,x+1,1,x+cell-1,swatch_height)
                self.palette_canvas.coords(number,x+cell/2,grade_center)
                self.palette_canvas.coords(group,x+cell/2,group_top)
                self.palette_canvas.itemconfigure(group,width=int(cell-2))
        if self.last is None:self.show_placeholder()
        else:self.refresh_last(record_usage=False)

    def context(self):
        return dict(tool_version=VERSION,reference_sha256=self.palette['source_sha256'] if self.palette else None,
                    palette_sha256=digest(self.palette_path) if self.palette else None,
                    qualitative_reference=True,no_automatic_class_assignment=True)

    def reset(self):
        self.last=None;self.pending=None;self.frozen.set(False);self.selected_grade=None
        if self.scheduled:self.after_cancel(self.scheduled);self.scheduled=None
        self.show_placeholder()
        self.pixel_label.configure(text='Píxel: — · Mediana 5×5: —')
        if self.palette:
            self.sample_label.configure(text='Capacho: pulsa un color para ver su RGB.')
            for item,_,_ in self.swatches:self.palette_canvas.itemconfigure(item,width=1,outline='#61736d')

    def observe(self,image,point):
        if self.frozen.get() or not self.winfo_ismapped():return
        self.pending=(image,point)
        if self.scheduled is None:self.scheduled=self.after(40,self.refresh_pending)

    def refresh_pending(self):
        self.scheduled=None
        if self.pending is not None:
            self.last=self.pending;self.pending=None;self.refresh_last()

    def refresh_last(self,record_usage=True):
        if self.last is None:return
        image,point=self.last;result=magnified_patch(image,point,self.zoom.get(),self.viewport)
        self.photo=ImageTk.PhotoImage(result['image']);self.display.delete('all');self.display.create_image(0,0,image=self.photo,anchor='nw')
        x,y=result['crosshair']
        for width,color in ((3,'#0a1521'),(1,'#ffffff')):
            self.display.create_line(x-8,y,x-3,y,fill=color,width=width);self.display.create_line(x+3,y,x+8,y,fill=color,width=width)
            self.display.create_line(x,y-8,x,y-3,fill=color,width=width);self.display.create_line(x,y+3,x,y+8,fill=color,width=width)
        self.pixel_label.configure(text=f'Píxel {result["point"]}: {hex_color(result["pixel"])}\nMediana 5×5: {hex_color(result["median"])}')
        if record_usage:self.on_used('loupe',dict(zoom=self.zoom.get()))

    def select_grade(self,grade,kind='calyx'):
        if kind!='calyx':raise ValueError('La escala de la lupa sólo muestra capachos')
        self.selected_grade=grade;sample=self.palette['grades'][grade][kind]
        for item,index,row in self.swatches:self.palette_canvas.itemconfigure(item,width=3 if index==grade and row==kind else 1,outline='#172e26' if index==grade else '#61736d')
        label='Capacho' if kind=='calyx' else 'Fruto'
        self.sample_label.configure(text=f'{label} {grade}: {sample["hex"]} · RGB {tuple(sample["rgb"])}')
        self.on_used('palette',dict(grade=grade,kind=kind))

    def show_reference(self):
        if self.reference_image is None:return
        if self.reference_window is not None and self.reference_window.winfo_exists():self.reference_window.lift();return
        popup=tk.Toplevel(self);popup.title('Lámina de referencia · muestras RGB');popup.resizable(False,False);self.reference_window=popup
        ttk.Label(popup,text='Ilustración suministrada por el usuario. Círculos: regiones de muestreo.',padding=8).pack()
        marked=self.reference_image.copy();ink=ImageDraw.Draw(marked)
        for grade in self.palette['grades']:
            sample=grade['calyx'];x,y=sample['center'];r=sample['radius']
            ink.ellipse((x-r,y-r,x+r,y+r),outline='white',width=3);ink.ellipse((x-r-1,y-r-1,x+r+1,y+r+1),outline='black',width=1)
        popup.photo=ImageTk.PhotoImage(marked);ttk.Label(popup,image=popup.photo).pack(padx=8)
        ttk.Label(popup,text='La escala no clasifica automáticamente y no cubre todo deterioro posible del capacho.',padding=8).pack()
        self.on_used('reference_image',{})
