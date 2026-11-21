"""Native, dependency-free visual system for the annotation workbench."""
import tkinter as tk
from tkinter import ttk

UI=dict(background='#eff3ef',surface='#ffffff',ink='#17362d',muted='#64776e',
        line='#dce6de',forest='#123e31',accent='#147d59',soft='#e7f4ec',canvas='#14251f')


def apply_theme(window):
    window.configure(background=UI['background'])
    style=ttk.Style(window);style.theme_use('clam')
    style.configure('.',font=('Segoe UI',10),background=UI['background'],foreground=UI['ink'])
    style.configure('TFrame',background=UI['background'])
    style.configure('Card.TFrame',background=UI['surface'],borderwidth=0,relief='flat')
    style.configure('TLabel',background=UI['surface'],foreground=UI['ink'])
    style.configure('Muted.TLabel',foreground=UI['muted'],font=('Segoe UI',9))
    style.configure('Eyebrow.TLabel',foreground=UI['muted'],font=('Segoe UI',9,'bold'))
    style.configure('Section.TLabel',font=('Segoe UI',12,'bold'))
    style.configure('Phase.TLabel',background=UI['soft'],foreground=UI['forest'],font=('Segoe UI',10),padding=(16,8))
    style.configure('TButton',padding=(10,7),background='#edf4ef',foreground=UI['forest'],borderwidth=0,relief='flat',focusthickness=0,font=('Segoe UI',10))
    style.map('TButton',background=[('disabled','#f2f4f2'),('pressed','#c9dfd0'),('active','#deece3')],foreground=[('disabled','#9aa99f')])
    style.configure('Accent.TButton',background=UI['accent'],foreground='white',font=('Segoe UI',10,'bold'),padding=(14,9))
    style.map('Accent.TButton',background=[('disabled','#94b3a2'),('pressed','#0b583d'),('active','#106a4b')],foreground=[('disabled','#eff6f1')])
    style.configure('Danger.TButton',background='#fff0ed',foreground='#a54b38')
    style.map('Danger.TButton',background=[('active','#f7dfd7')])
    style.configure('Mode.TButton',font=('Segoe UI',10),padding=(9,7),background=UI['surface'])
    style.configure('ActiveMode.TButton',font=('Segoe UI',10,'bold'),padding=(9,7),foreground='white',background=UI['forest'])
    style.map('ActiveMode.TButton',background=[('active',UI['accent'])],foreground=[('disabled','#a7b9ad')])
    for name,color in (('Pintona','#d8ae45'),('Madura','#ca8640'),('Sobre','#997481'),('Unknown','#81958b')):
        key=name+'.TRadiobutton'
        style.layout(key,[('Radiobutton.padding',dict(sticky='nswe',children=[('Radiobutton.label',dict(sticky='w'))]))])
        style.configure(key,padding=(10,8),background='#f5f8f5',foreground=UI['ink'],font=('Segoe UI',10),anchor='w',borderwidth=0)
        style.map(key,background=[('selected',UI['soft']),('active','#eef5ef')],foreground=[('selected',UI['accent'])])
    style.configure('Tab.TRadiobutton',padding=(10,7),background='#f3f7f3',foreground=UI['muted'],indicatorcolor=UI['accent'])
    style.map('Tab.TRadiobutton',background=[('selected',UI['soft'])],foreground=[('selected',UI['accent'])])
    style.configure('TCheckbutton',background=UI['surface'],padding=3)
    style.map('TCheckbutton',background=[('active',UI['surface'])])
    style.configure('TRadiobutton',background=UI['surface'],padding=3)
    style.configure('TEntry',padding=7,fieldbackground='#f7faf7',bordercolor=UI['line'],lightcolor=UI['line'],darkcolor=UI['line'])
    style.map('TEntry',bordercolor=[('focus',UI['accent'])])
    style.configure('TCombobox',padding=5,fieldbackground='#f7faf7',background='#edf4ef',bordercolor=UI['line'],arrowsize=12)
    style.configure('Horizontal.TScale',background=UI['surface'],troughcolor='#dce8de',sliderlength=22,borderwidth=0)
    style.configure('Vertical.TScrollbar',background='#b9cec0',troughcolor=UI['background'],borderwidth=0,arrowsize=10)
    style.configure('TPanedwindow',background=UI['line'],sashwidth=6)
    return style


def card(parent,title,subtitle=None,**pack):
    shell=ttk.Frame(parent,style='Card.TFrame',padding=13)
    shell.pack(fill='x',pady=(0,10),**pack)
    ttk.Label(shell,text=title,style='Eyebrow.TLabel').pack(anchor='w',pady=(0,8))
    if subtitle:
        description=ttk.Label(shell,text=subtitle,style='Muted.TLabel',wraplength=180)
        description.pack(anchor='w',pady=(0,6))
        shell.bind('<Configure>',lambda e:description.configure(wraplength=max(100,e.width-26)))
    return shell


def list_style(widget):
    widget.configure(bg=UI['surface'],fg=UI['ink'],selectbackground=UI['soft'],selectforeground=UI['accent'],
        relief='flat',borderwidth=0,highlightthickness=0,activestyle='none',font=('Segoe UI',10))


def brand(parent):
    emblem=tk.Canvas(parent,width=42,height=42,bg=UI['forest'],highlightthickness=0)
    emblem.create_oval(1,1,41,41,fill='#28634b',outline='')
    emblem.create_polygon(13,10,27,13,31,23,22,34,12,23,fill='#c8d993',outline='#dbe6b4',smooth=True)
    emblem.create_line(21,13,22,31,fill=UI['forest'],width=2)
    emblem.create_line(22,14,25,7,fill='#dbe6b4',width=2)
    return emblem
