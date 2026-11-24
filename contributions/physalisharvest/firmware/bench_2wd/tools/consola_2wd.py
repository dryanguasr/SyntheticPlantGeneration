"""Consola Windows de PhysalisHarvest. El control se ejecuta en ROS 2."""

import argparse
import base64
from binascii import Error as Base64Error
from contextlib import suppress
from datetime import datetime
from hashlib import sha256
import json
from math import atan2, degrees
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Lock, Thread
import time
import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np

from drv8833_ros_usb import FIRMWARE
import reproducir_drv8833 as launcher


BG, PANEL, INSET, LINE = "#101720", "#172330", "#111c27", "#2c3c4d"
TEXT, MUTED, TEAL, AMBER, RED = "#edf3f7", "#9bb0c3", "#63e0c7", "#efc680", "#ffadb1"
FONT, MONO = "Segoe UI", "Consolas"
ROOT_ROS = "/bench_2wd/drv8833"
ROUTE = (0, 1, 2)
ACTIVE_ID = 0
CALIBRATION_HASH = "4b06398231164640534c33fe549be33a85165a2ca5e61eb9fdc1819a79ce0583"
EMBLEM = Path(__file__).with_name("assets") / "physalisharvest-2wd.png"


def preview_scene(marker_id=ACTIVE_ID):
    """Plano de prueba sintético para el modo desconectado."""
    width, height = 768, 480
    v, u = np.mgrid[:height, :width]
    rng = np.random.default_rng(807)
    illumination = np.clip(1 - ((u - 390) / 630) ** 2 - ((v - 210) / 620) ** 2, 0.25, 1)
    grain = rng.normal(0, 1.7, (height, width))
    surface = np.clip(45 + 43 * illumination + grain, 0, 255).astype(np.uint8)
    rgb = cv2.merge((surface + 10, surface + 4, surface))
    for x in range(-520, 1200, 115):
        cv2.line(rgb, (width // 2, 173), (x, height), (101, 94, 86), 1, cv2.LINE_AA)
    for y in (244, 270, 304, 351, 421):
        cv2.line(rgb, (0, y), (width, y), (101, 94, 86), 1, cv2.LINE_AA)
    quad = np.float32([(307, 137), (488, 156), (464, 363), (287, 336)])
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, marker_id, 180)
    marker = cv2.copyMakeBorder(marker, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=235)
    corners = np.float32([(0, 0), (227, 0), (227, 227), (0, 227)])
    transform = cv2.getPerspectiveTransform(corners, quad)
    card = cv2.warpPerspective(marker, transform, (width, height))
    mask = np.zeros((height, width), np.uint8)
    outline = quad.astype(np.int32)
    cv2.fillConvexPoly(mask, outline, 255)
    rgb[mask != 0] = card[mask != 0, None]
    depth = np.clip(54 + (v / height) * 120 + (u / width) * 24, 0, 255).astype(np.uint8)
    depth[mask != 0] = 195
    layer = cv2.applyColorMap(depth, cv2.COLORMAP_TURBO)
    cv2.polylines(rgb, [outline], True, (199, 224, 99), 2, cv2.LINE_AA)
    for x, y in outline:
        cv2.circle(rgb, (x, y), 4, (199, 224, 99), -1)
    center = tuple(np.mean(quad, axis=0).astype(int))
    cv2.drawMarker(rgb, center, (199, 224, 99), cv2.MARKER_CROSS, 24, 2)
    return rgb, layer


class Dashboard:
    def __init__(self, root, args):
        self.root, self.args = root, args
        self.preview = args.vista_previa
        self.diagnostic = getattr(args, "diagnostico", False)
        self.events = Queue()
        self.jobs = {}
        self.frame_lock = Lock()
        self.received_frame = None
        self.frame = preview_scene(args.ruta[0]) if self.preview else None
        self.photo = None
        self.graph = {}
        self.graph_at = 0.0
        self.last_frame_at = 0.0
        self.render_needed = True
        self.bridge_id = self.bridge_stopped = self.bridge_online = self.armed = self.checking = False
        self.active_id = None
        self.arrived_ids = set()
        self.request_id = 0
        self.request = None
        self.closing = None
        self.port = tk.StringVar(value=args.puerto)
        self.opacity = tk.DoubleVar(value=32)
        root.title("PhysalisHarvest | Consola 2WD")
        root.geometry("1250x790")
        root.minsize(1060, 715)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.build()
        if self.preview:
            self.log("VISTA PREVIA", "Escena sintética. Hardware desactivado.", TEAL)
            self.log("ROS 2", "A la espera del monitor.")
            self.log("ESP32", "Sin sesión USB.")
        else:
            self.log("BANCO", "Comienza por verificar conexiones. El banco inicia desarmado.")
        self.tick()

    def label(self, parent, text, size=11, ink=TEXT, bold=False, bg=PANEL, mono=False, **kwargs):
        return tk.Label(parent, text=text, bg=bg, fg=ink,
                        font=(MONO if mono else FONT, size, "bold" if bold else "normal"), **kwargs)

    def card(self, parent, bg=PANEL):
        return tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=LINE)

    def brand(self, parent):
        tile = tk.Frame(parent, bg=BG)
        tile.pack(side="left", padx=(0, 12))
        if not EMBLEM.is_file():
            self.label(tile, "PH", 14, BG, True, TEAL, padx=11, pady=9).pack()
            return
        pixels = cv2.imdecode(np.frombuffer(EMBLEM.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)
        if pixels is None or pixels.ndim != 3 or pixels.shape[2] != 4:
            self.label(tile, "PH", 14, BG, True, TEAL, padx=11, pady=9).pack()
            return
        # La cabecera muestra únicamente la zona del símbolo.
        glyph = pixels[:int(pixels.shape[0] * 0.885)]
        bounds = cv2.boundingRect((glyph[:, :, 3] > 90).astype(np.uint8))
        x, y, w, h = bounds
        if not w or not h:
            self.label(tile, "PH", 14, BG, True, TEAL, padx=11, pady=9).pack()
            return
        scale = 38 / max(w, h)
        glyph = cv2.resize(glyph[y:y+h, x:x+w], (round(w * scale), round(h * scale)),
                           interpolation=cv2.INTER_AREA)
        _, png = cv2.imencode(".png", glyph)
        self.emblem = tk.PhotoImage(data=base64.b64encode(png).decode("ascii"))
        badge = tk.Frame(tile, bg="#d8efe9", width=49, height=46)
        badge.pack()
        tk.Label(badge, image=self.emblem, bg=badge["bg"], bd=0).place(relx=0.5, rely=0.5, anchor="center")

    def button(self, parent, text, callback, variant="quiet"):
        palettes = {"quiet": (INSET, TEXT), "primary": (TEAL, BG), "danger": ("#522c37", "#ffe5e8")}
        bg, fg = palettes[variant]
        return tk.Button(parent, text=text, command=callback, bg=bg, fg=fg, activebackground=LINE,
                         activeforeground=TEXT, disabledforeground="#77899c",
                         font=(FONT, 10, "bold"), bd=0, relief="flat", cursor="hand2", padx=13, pady=7)

    def build(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=23, pady=(14, 12))
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(2, weight=1)
        header = tk.Frame(outer, bg=BG)
        header.grid(row=0, column=0, sticky="ew")
        self.brand(header)
        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left")
        self.label(titles, "PhysalisHarvest", 10, TEAL, True, BG, anchor="w").pack(fill="x")
        self.label(titles, "Consola de locomoción 2WD", 21, TEXT, True, BG, anchor="w").pack(fill="x")
        mode = "VISTA PREVIA · SIN CONEXIONES" if self.preview else (
            "DIAGNÓSTICO RGB-D · 800 ms" if self.diagnostic else "BANCO LOCAL"
        )
        self.mode = self.label(header, mode,
                               10, AMBER, True, INSET, padx=12, pady=8)
        self.mode.pack(side="right")

        strip = self.card(outer)
        strip.grid(row=1, column=0, sticky="ew", pady=(13, 12))
        strip.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.status = {}
        for column, (key, title) in enumerate((
            ("ros", "ROS 2 / JAZZY"), ("astra", "ASTRA PRO"), ("usb", "ESP32 / USB"), ("driver", "DRV8833"),
        )):
            item = tk.Frame(strip, bg=PANEL)
            item.grid(row=0, column=column, sticky="ew", padx=13, pady=7)
            self.label(item, title, 8, MUTED, True, anchor="w").pack(fill="x")
            self.status[key] = self.label(item, "Sin conexión", 10, TEXT, anchor="w")
            self.status[key].pack(fill="x")
        self.verify_btn = self.button(strip, "Verificar conexiones", self.verify)
        self.verify_btn.grid(row=0, column=4, padx=(5, 9), pady=6)
        self.start_btn = self.button(strip, "Iniciar banco", self.start_bank, "primary")
        self.start_btn.grid(row=0, column=5, padx=(0, 9), pady=6)

        body = tk.Frame(outer, bg=BG)
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2, minsize=365)
        body.grid_rowconfigure(0, weight=1)
        camera = self.card(body)
        camera.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        camera.grid_columnconfigure(0, weight=1)
        camera.grid_rowconfigure(1, weight=1)
        top = tk.Frame(camera, bg=PANEL)
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=8)
        self.label(top, "Cámara RGB-D", 13, TEXT, True).pack(side="left")
        self.camera_btn = self.button(top, "Mostrar cámara", self.toggle_camera)
        self.camera_btn.pack(side="right")
        self.canvas = tk.Canvas(camera, bg=INSET, bd=0, highlightthickness=0, width=540, height=220)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=11)
        self.canvas.bind("<Configure>", lambda _: setattr(self, "render_needed", True))

        bottom = tk.Frame(camera, bg=PANEL)
        bottom.grid(row=2, column=0, sticky="ew", padx=12, pady=(6, 9))
        bottom.grid_columnconfigure(0, weight=1)
        self.xyz = self.label(bottom, "X —   Y —   Z —   θ —", 11, TEXT, mono=True, anchor="w")
        self.xyz.grid(row=0, column=0, sticky="ew")
        alpha = tk.Frame(bottom, bg=PANEL)
        alpha.grid(row=0, column=1, sticky="e")
        self.label(alpha, "Profundidad", 9, MUTED).pack(side="left", padx=(0, 4))
        slider = ttk.Scale(alpha, from_=0, to=100, variable=self.opacity, length=75,
                           command=lambda _: setattr(self, "render_needed", True))
        slider.pack(side="left")

        side = tk.Frame(body, bg=BG)
        side.grid(row=0, column=1, sticky="nsew")
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(2, weight=1)
        control = self.card(side)
        control.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        control.grid_columnconfigure((0, 1), weight=1)
        self.label(control, "Control de movimiento", 13, TEXT, True, anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(9, 2))
        self.state = self.label(control, "DESARMADO", 15, AMBER, True, anchor="w")
        self.state.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12)
        self.ack = self.label(control, "ESP32 · sin acuse", 9, MUTED, mono=True, anchor="w")
        self.ack.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(1, 6))
        self.arm_btn = self.button(control, "Armar", lambda: self.command(True), "primary")
        self.arm_btn.grid(row=3, column=0, sticky="ew", padx=(12, 5), pady=(0, 10))
        self.stop_btn = self.button(control, "Parar", lambda: self.command(False), "danger")
        self.stop_btn.grid(row=3, column=1, sticky="ew", padx=(5, 12), pady=(0, 10))

        route = self.card(side)
        route.grid(row=1, column=0, sticky="ew", pady=(0, 9))
        self.label(route, "Marcadores", 12, TEXT, True).pack(anchor="w", padx=12, pady=(7, 4))
        if len(self.args.ruta) > 3:
            track = tk.Canvas(route, height=40, highlightthickness=0, bg=PANEL)
            track.pack(fill="x", padx=12)
            row = tk.Frame(track, bg=PANEL)
            track.create_window(0, 0, window=row, anchor="nw")
            row.bind("<Configure>", lambda _: track.configure(scrollregion=track.bbox("all")))
            bar = ttk.Scrollbar(route, orient="horizontal", command=track.xview)
            bar.pack(fill="x", padx=12, pady=(0, 5))
            track.configure(xscrollcommand=bar.set)
        else:
            row = tk.Frame(route, bg=PANEL)
            row.pack(fill="x", padx=12, pady=(0, 8))
        self.route_labels = {}
        for index, marker_id in enumerate(self.args.ruta):
            row.grid_columnconfigure(index, weight=1)
            item = tk.Frame(row, bg="#203c42" if marker_id == self.active_id else INSET)
            item.grid(row=0, column=index, padx=(0 if index == 0 else 4, 0), sticky="ew")
            self.label(item, f"ID {marker_id:02}", 9, TEAL if marker_id == self.active_id else TEXT, True,
                       item["bg"], mono=True).pack(pady=(3, 0))
            status = self.label(item, "Disponible", 8, MUTED,
                                bg=item["bg"])
            status.pack(pady=(0, 4))
            self.route_labels[marker_id] = status

        hardware = self.card(side)
        hardware.grid(row=2, column=0, sticky="nsew")
        hardware.grid_columnconfigure(1, weight=1)
        self.label(hardware, "Configuración local", 12, TEXT, True, anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(8, 3))
        self.label(hardware, "Puerto", 9, MUTED).grid(row=1, column=0, sticky="w", padx=(12, 6))
        self.entry = tk.Entry(hardware, width=7, textvariable=self.port, font=(MONO, 10),
                              bg=INSET, fg=TEXT, insertbackground=TEXT, bd=0,
                              disabledbackground=INSET, disabledforeground=MUTED)
        self.entry.grid(row=1, column=1, sticky="w", ipady=4)
        self.active_label = self.label(hardware, f"Dominio {self.args.dominio}   ·   ID —", 9, MUTED, mono=True)
        self.active_label.grid(
            row=1, column=2, sticky="e", padx=(6, 12))
        actions = tk.Frame(hardware, bg=PANEL)
        actions.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(6, 8))
        self.identify_btn = self.button(actions, "Identificar ESP32", lambda: self.bridge(True))
        self.identify_btn.pack(side="left", padx=(0, 6))
        self.build_btn = self.button(actions, "Compilar ROS 2", self.compile)
        self.build_btn.pack(side="left")

        detail = tk.Frame(outer, bg=BG)
        detail.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        detail.grid_columnconfigure(0, weight=3)
        detail.grid_columnconfigure(1, weight=2, minsize=365)
        graph = self.card(detail)
        graph.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        graph_title = tk.Frame(graph, bg=PANEL)
        graph_title.pack(fill="x", padx=12, pady=(5, 2))
        self.label(graph_title, "Grafo ROS 2", 12, TEXT, True).pack(side="left")
        self.rate = self.label(graph_title, "XYZ  — Hz  ·  Edad — ms", 9, MUTED, mono=True)
        self.rate.pack(side="right")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Bench.Treeview", background=INSET, fieldbackground=INSET,
                        foreground=TEXT, rowheight=23, borderwidth=0, font=(MONO, 9))
        style.configure("Bench.Treeview.Heading", background=PANEL, foreground=MUTED, font=(FONT, 9))
        style.configure("TNotebook", background=PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", background=INSET, foreground=MUTED, padding=(9, 3))
        style.map("TNotebook.Tab", background=[("selected", LINE)], foreground=[("selected", TEXT)])
        for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar", "Horizontal.TScale"):
            style.configure(name, background=LINE, troughcolor=INSET, bordercolor=LINE,
                            lightcolor=LINE, darkcolor=LINE, arrowcolor=MUTED)
        tabs = ttk.Notebook(graph)
        tabs.pack(fill="both", expand=True, padx=9, pady=(0, 8))
        self.tables = {}
        for key, title, header in (("topics", "Tópicos", "Tipo / estado"),
                                   ("nodes", "Nodos", "Estado"),
                                   ("services", "Servicios", "Tipo / estado")):
            tab = tk.Frame(tabs, bg=INSET)
            tabs.add(tab, text=title)
            tree = ttk.Treeview(tab, columns=("name", "status"), show="headings",
                                height=3, style="Bench.Treeview")
            tree.heading("name", text="Recurso", anchor="w")
            tree.heading("status", text=header, anchor="w")
            tree.column("name", width=350)
            tree.column("status", width=200)
            bar = ttk.Scrollbar(tab, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=bar.set)
            bar.pack(side="right", fill="y")
            tree.pack(side="left", fill="both", expand=True)
            self.tables[key] = tree

        logs = self.card(detail)
        logs.grid(row=0, column=1, sticky="nsew")
        log_top = tk.Frame(logs, bg=PANEL)
        log_top.pack(fill="x", padx=12, pady=(4, 2))
        self.label(log_top, "Eventos", 12, TEXT, True).pack(side="left")
        self.button(log_top, "Copiar", self.copy_log).pack(side="right")
        self.log_view = tk.Text(logs, height=6, width=40, state="disabled", bg=INSET, fg=TEXT,
                                bd=0, padx=9, pady=5, font=(MONO, 9), wrap="word")
        self.log_view.pack(fill="both", expand=True, padx=9, pady=(0, 8))
        self.update_graph({})

    def log(self, sender, message, ink=MUTED):
        self.log_view.configure(state="normal")
        self.log_view.tag_configure(ink, foreground=ink)
        self.log_view.insert("end", f"{datetime.now():%H:%M:%S}  {sender}\n", ink)
        self.log_view.insert("end", message + "\n")
        if int(self.log_view.index("end").split(".")[0]) > 500:
            self.log_view.delete("1.0", "101.0")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_view.get("1.0", "end-1c"))

    def launch(self, name, command):
        if self.preview or self.closing is not None or name in self.jobs:
            return False
        try:
            process = subprocess.Popen(
                command, cwd=launcher.ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            self.log(name.upper(), str(error), AMBER)
            return False
        self.jobs[name] = process

        def read():
            for line in process.stdout:
                line = line.strip()
                if name == "camera" and line.startswith("FRAME "):
                    with self.frame_lock:
                        self.received_frame = (process, line[6:])
                elif line:
                    self.events.put((name, process, line))
            self.events.put((name, process, process.wait()))

        Thread(target=read, daemon=True).start()
        return True

    def close_job(self, name):
        process = self.jobs.get(name)
        if process:
            with suppress(OSError):
                process.stdin.close()

    def monitor(self):
        setup = ("source /opt/ros/jazzy/setup.bash && source install/setup.bash && "
                 f"export ROS_DOMAIN_ID={self.args.dominio} ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST && "
                 "exec ros2 run bench_2wd_drv8833 monitor --ros-args -p 'ruta:=["
                 + ",".join(map(str, self.args.ruta)) + "]'")
        if self.diagnostic:
            setup += " -p diagnostico:=true"
        self.launch("ros", launcher.wsl(self.args, setup))

    def verify(self):
        self.monitor()
        if self.checking:
            return
        self.checking = True

        def check():
            try:
                from serial.tools import list_ports
                ports = sorted(port.device for port in list_ports.comports())
                usb = " · ".join(ports) if ports else "Sin puertos detectados"
            except (ImportError, OSError) as error:
                usb = str(error)
            try:
                command = launcher.viewer(self.args)
                profile = Path(command[command.index("--calibration") + 1])
                expected = (self.args.sha256 or CALIBRATION_HASH).lower()
                if sha256(profile.read_bytes()).hexdigest() != expected:
                    raise ValueError("El hash de la calibración difiere del perfil.")
                astra = "SDK y perfil disponibles"
            except (OSError, ValueError) as error:
                astra = str(error)
            self.events.put(("check", None, (usb, astra)))

        Thread(target=check, daemon=True).start()

    def bridge(self, identify=False):
        if self.diagnostic or "puente" in self.jobs or "identificar" in self.jobs or "compilar" in self.jobs:
            return
        port = self.port.get().strip()
        if not port:
            self.log("USB", "Indica el puerto del ESP32.", AMBER)
            return
        if not identify:
            self.monitor()
            self.bridge_id = self.bridge_stopped = self.bridge_online = False
        command = [sys.executable, "-B", str(Path(__file__).with_name("drv8833_ros_usb.py")),
                   "--port", port, "--distro", self.args.distro, "--domain-id", str(self.args.dominio),
                   "--ruta", *map(str, self.args.ruta)]
        self.launch("identificar" if identify else "puente", command + (["--check"] if identify else ["--managed"]))

    def start_bank(self):
        if "puente" in self.jobs:
            self.close_job("puente")
            self.close_job("camera")
            return
        self.verify()
        self.bridge()

    def compile(self):
        if {"puente", "camera", "identificar"} & self.jobs.keys():
            return
        self.close_job("ros")
        self.launch("compilar", launcher.wsl(
            self.args, "source /opt/ros/jazzy/setup.bash && colcon build --packages-select bench_2wd bench_2wd_drv8833",
        ))

    def toggle_camera(self):
        if "camera" in self.jobs:
            if self.armed or self.request:
                self.command(False)
            self.close_job("camera")
            return
        try:
            command = launcher.viewer(self.args)
        except (ValueError, OSError) as error:
            self.log("ASTRA", str(error), AMBER)
            return
        self.monitor()
        if self.diagnostic:
            command.append("--diagnostico")
        self.launch("camera", command + ["--preview-pipe"])

    def control_ready(self):
        return (self.graph.get("ticket") is not None and self.bridge_id and self.bridge_stopped
                and self.bridge_online and "puente" in self.jobs
                and self.graph.get("ready", False) and time.monotonic() - self.graph_at < 2.5)

    def command(self, enabled):
        if self.preview or self.diagnostic or (enabled and (not self.control_ready() or self.armed or self.request)):
            return
        ros = self.jobs.get("ros")
        if ros is None or not self.graph.get("ready") or time.monotonic() - self.graph_at >= 2.5:
            if not enabled:
                self.close_job("puente")
                self.log("PARADA", "Sin servicio ROS. Se solicitó cerrar el puente; verifica el acuse o corta VM.", AMBER)
            return
        self.request_id += 1
        try:
            ros.stdin.write(json.dumps({"id": self.request_id, "enable": enabled,
                                        "ticket": self.graph.get("ticket")}) + "\n")
            ros.stdin.flush()
            self.request = (self.request_id, enabled, time.monotonic() + 2.2)
        except (ValueError, OSError):
            self.close_job("puente")
            self.log("ROS", "Se perdió el monitor. Se solicitó cerrar el puente.", AMBER)

    def update_graph(self, graph):
        target = ROOT_ROS + "/aruco_target"
        if self.active_id:
            target += f"_id_{self.active_id}"
        expected = {
            "topics": [target + "_diagnostico"] if self.diagnostic else [
                target, target + "_visual", ROOT_ROS + "/state"],
            "services": [ROOT_ROS + "/enable"],
            "nodes": ["/bench_2wd_drv8833_aruco", "/bench_2wd_drv8833_controller", "/bench_2wd_drv8833_console"],
        }
        for key, tree in self.tables.items():
            online = graph.get(key, {})
            names = expected[key] + sorted(set(online) - set(expected[key]))
            rows = []
            for name in names:
                status = "Ausente"
                if name in online:
                    status = "Disponible" if key == "nodes" else ", ".join(online[name])
                if key == "topics" and name in expected[key] and name in online and not graph.get("publishers", {}).get(name):
                    status = "Sin publicador"
                rows.append((name, status))
            if rows != [tuple(tree.item(item, "values")) for item in tree.get_children()]:
                tree.delete(*tree.get_children())
                for row in rows:
                    tree.insert("", "end", values=row)

        age, hz, xyz = graph.get("age"), graph.get("hz"), graph.get("xyz")
        recent = xyz is not None and age is not None and -30 <= age <= 800
        if recent:
            x, y, z = xyz
            suffix = "  ·  Solo visual" if self.diagnostic or age > 250 else ""
            marker = graph.get("marker")
            prefix = f"ID {marker:02} · " if marker is not None else ""
            angle = degrees(atan2(x, z))
            self.xyz.configure(text=f"{prefix}X {x:+.3f}  Y {y:+.3f}  Z {z:.3f} m  θ {angle:+.1f}°{suffix}")
        else:
            self.xyz.configure(text="X —   Y —   Z —   θ —")
        rate = "—" if hz is None else f"{hz:.1f}"
        latency = "—" if age is None else f"{age:.0f}"
        self.rate.configure(text=f"XYZ  {rate} Hz  ·  Edad {latency} ms")

    def handle_ros(self, line):
        try:
            data = json.loads(line)
        except ValueError:
            self.log("ROS", line, AMBER)
            return
        if not isinstance(data, dict):
            self.log("ROS", "Formato inesperado de telemetría.", AMBER)
            return
        kind = data.get("kind")
        if kind == "graph":
            self.graph, self.graph_at = data, time.monotonic()
            self.status["ros"].configure(text="Grafo visible" if data["ready"] else "Servicio de control ausente")
            self.update_graph(data)
        elif kind == "state":
            event = data["text"]
            action, _, detail = event.partition(" ")
            if action == "TARGET" and detail.isdecimal() and int(detail) in self.route_labels:
                self.active_id = int(detail)
                self.armed = True
                self.state.configure(text=f"OBJETIVO ID {self.active_id:02}", fg=TEAL)
                self.active_label.configure(text=f"Dominio {self.args.dominio}   ·   ID {self.active_id}")
                for marker, label in self.route_labels.items():
                    status = "Alcanzado" if marker in self.arrived_ids else "Disponible"
                    fill = "#203c42" if marker == self.active_id else INSET
                    label.master.configure(bg=fill)
                    for child in label.master.winfo_children():
                        child.configure(bg=fill)
                    label.configure(text="Activo" if marker == self.active_id else status,
                                    fg=TEAL if marker == self.active_id else MUTED)
            elif action == "ARRIVED" and detail.isdecimal() and int(detail) in self.route_labels:
                self.arrived_ids.add(int(detail))
                self.route_labels[int(detail)].configure(text="Alcanzado", fg=TEAL)
            elif action == "SCAN":
                self.armed = True
                self.state.configure(text="BUSCANDO ARUCO · IZQUIERDA", fg=AMBER)
            elif action in {"ARMED", "WAIT"}:
                self.armed = True
                self.active_id = None
                if action == "ARMED":
                    self.arrived_ids.clear()
                self.active_label.configure(text=f"Dominio {self.args.dominio}   ·   ID —")
                for marker, label in self.route_labels.items():
                    label.master.configure(bg=INSET)
                    for child in label.master.winfo_children():
                        child.configure(bg=INSET)
                    label.configure(text="Alcanzado" if marker in self.arrived_ids else "Disponible", fg=MUTED)
                self.state.configure(text="ARMADO · ESPERANDO ARUCO", fg=AMBER)
            elif action == "DRIVE":
                self.armed = True
                direction = {"F": "AVANCE RECTO", "L": "CORRECCIÓN IZQUIERDA", "R": "CORRECCIÓN DERECHA"}
                self.state.configure(text=direction.get(detail.partition(" ")[0], "ORDEN ROS"), fg=TEAL)
            elif action == "STOP":
                self.armed = False
                self.active_id = None
                self.active_label.configure(text=f"Dominio {self.args.dominio}   ·   ID —")
                self.state.configure(text="DESARMADO", fg=AMBER)
            self.log("ROS", event, TEAL)
        elif kind == "response" and self.request and data["id"] == self.request[0]:
            _, enabled, _ = self.request
            self.request = None
            self.log("SERVICIO", data["text"], TEAL if data["ok"] else AMBER)
            if not enabled and not data["ok"]:
                self.close_job("puente")
        elif kind == "error":
            self.log("ROS", data["text"], AMBER)

    def handle(self, name, process, payload):
        if name == "check":
            self.checking = False
            usb, astra = payload
            self.status["usb"].configure(text=usb if len(usb) < 25 else "Consulta eventos")
            if "camera" not in self.jobs:
                self.status["astra"].configure(text=astra if len(astra) < 25 else "Consulta eventos")
            self.log("CONEXIONES", f"{usb}\n{astra}")
            return
        if self.jobs.get(name) is not process:
            return
        if isinstance(payload, int):
            self.jobs.pop(name)
            self.log(name.upper(), f"Proceso cerrado · código {payload}", MUTED if payload == 0 else AMBER)
            if name == "camera":
                self.frame = None
                self.render_needed = True
                self.status["astra"].configure(text="Cámara cerrada")
            elif name == "puente":
                self.bridge_id = self.bridge_stopped = self.bridge_online = self.armed = False
                self.state.configure(text="PUENTE CERRADO", fg=AMBER)
                self.status["driver"].configure(text="Sin sesión USB")
            elif name == "ros":
                self.graph = {}
                self.update_graph({})
                self.status["ros"].configure(text="Monitor cerrado")
                if "puente" in self.jobs:
                    self.close_job("puente")
            return
        if name == "ros":
            self.handle_ros(payload)
            return
        if name == "puente" and payload == "CONTROLLER_READY":
            self.bridge_online = True
            self.status["driver"].configure(text="Puente disponible")
        elif name in {"puente", "identificar"} and payload == FIRMWARE:
            self.status["driver"].configure(text="Firmware identificado")
            if name == "puente":
                self.bridge_id = True
        elif name in {"puente", "identificar"} and payload.startswith("OK "):
            self.ack.configure(text=f"ESP32 · {payload}")
            if name == "puente":
                self.bridge_stopped = payload == "OK S 0000"
                if self.bridge_stopped and not self.armed:
                    self.state.configure(text="DESARMADO", fg=AMBER)
        self.log(name.upper(), payload, TEAL if payload.startswith("OK ") else MUTED)

    def paint(self):
        self.canvas.delete("all")
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if min(width, height) < 10:
            return
        if self.frame is not None:
            rgb, layer = self.frame
            a = self.opacity.get() / 100
            overlay = cv2.addWeighted(rgb, 1 - a, layer, a, 0)
            blank = np.max(layer, axis=2) < 12
            overlay[blank] = rgb[blank]
            scale = min(width / rgb.shape[1], height / rgb.shape[0])
            image = cv2.resize(overlay, (int(scale * rgb.shape[1]), int(scale * rgb.shape[0])))
            ok, encoded = cv2.imencode(".png", image)
            if ok:
                self.photo = tk.PhotoImage(data=base64.b64encode(encoded).decode("ascii"))
                self.canvas.create_image(width / 2, height / 2, image=self.photo)
            if self.preview:
                self.canvas.create_rectangle(13, 12, 252, 37, fill=BG, outline=LINE)
                self.canvas.create_text(22, 24, text="SIMULACIÓN · Generado con IA",
                                        anchor="w", fill=TEAL, font=(FONT, 9, "bold"))
        else:
            self.canvas.create_text(width / 2, height / 2, text="Cámara sin imagen", fill=MUTED, font=(FONT, 15))

    def tick(self):
        for _ in range(100):
            try:
                self.handle(*self.events.get_nowait())
            except Empty:
                break
        with self.frame_lock:
            received, self.received_frame = self.received_frame, None
        now = time.monotonic()
        if received and received[0] is self.jobs.get("camera"):
            try:
                raw = np.frombuffer(base64.b64decode(received[1], validate=True), np.uint8)
                image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            except (Base64Error, cv2.error):
                image = None
            if image is not None and image.shape[1] % 2 == 0:
                self.frame = tuple(np.hsplit(image, 2))
                self.last_frame_at = now
                self.render_needed = True
                self.status["astra"].configure(text="Vídeo RGB-D" if self.graph.get("xyz") else "Vídeo · XYZ pendiente")
        if not self.preview and self.frame is not None and now - self.last_frame_at >= 1.5:
            self.frame = None
            self.render_needed = True
            self.status["astra"].configure(text="Imagen vencida")
        if self.graph and now - self.graph_at >= 2.5:
            self.graph = {}
            self.update_graph({})
            self.status["ros"].configure(text="Sin telemetría reciente")
            if self.armed or self.request:
                self.close_job("puente")
        if self.request and now >= self.request[2]:
            self.request = None
            self.close_job("puente")
            self.log("ROS", "Sin confirmación de la solicitud. Se solicitó cerrar el puente.", AMBER)
        if self.render_needed:
            self.render_needed = False
            self.paint()
        self.refresh_buttons()
        if self.closing is not None:
            if not self.jobs:
                self.root.destroy()
                return
            if now - self.closing > 6:
                for process in self.jobs.values():
                    with suppress(OSError):
                        process.terminate()
                self.root.destroy()
                return
        self.root.after(85, self.tick)

    def refresh_buttons(self):
        active = not self.preview and self.closing is None
        hardware_active = active and not self.diagnostic
        running = self.jobs.keys()
        allowed = {
            self.verify_btn: active and not self.checking and "compilar" not in running,
            self.start_btn: hardware_active and not ({"identificar", "compilar"} & running),
            self.camera_btn: active and "compilar" not in running,
            self.arm_btn: hardware_active and self.control_ready() and not self.armed and self.request is None,
            self.stop_btn: hardware_active and ("puente" in running or self.graph.get("ready", False)),
            self.identify_btn: hardware_active and not ({"puente", "identificar", "compilar"} & running),
            self.build_btn: active and not ({"puente", "camera", "identificar", "compilar"} & running),
        }
        for widget, enabled in allowed.items():
            widget.configure(state="normal" if enabled else "disabled")
        self.start_btn.configure(text="Cerrar banco" if "puente" in running else "Iniciar banco")
        self.camera_btn.configure(text="Ocultar cámara" if "camera" in running else "Mostrar cámara")
        self.entry.configure(state="normal" if active and not ({"puente", "identificar"} & running) else "disabled")

    def close(self):
        if self.closing is not None:
            return
        self.closing = time.monotonic()
        self.close_job("puente")
        for name in self.jobs.keys() - {"puente"}:
            self.close_job(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vista-previa", action="store_true", help="Escena sintética sin procesos ni hardware")
    parser.add_argument("--diagnostico", action="store_true", help="Cámara y ROS sin control de motores")
    parser.add_argument("--puerto", default="COM3")
    parser.add_argument("--distro", default="Ubuntu-24.04")
    parser.add_argument("--dominio", type=int, default=83, choices=range(1, 102), metavar="1..101")
    parser.add_argument("--indice-rgb", type=int, default=1)
    parser.add_argument("--astra", type=Path, default=launcher.ROOT.parent / "COORDENADAS_ORBBECASTRA")
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--calibracion", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--ids", "--ruta", dest="ruta", nargs="+", type=int, default=ROUTE, metavar="ID")
    args = parser.parse_args()
    if len(set(args.ruta)) != len(args.ruta) or any(
        not 0 <= marker < 50 for marker in args.ruta
    ):
        parser.error("La ruta debe contener IDs únicos de 0 a 49.")
    cv2.setNumThreads(1)
    root = tk.Tk()
    Dashboard(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
