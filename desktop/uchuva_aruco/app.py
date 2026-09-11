"""Windows desktop UI. All inference and I/O stay off the Tk event thread."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import cv2

from .storage import save_capture
from .video import VideoReader
from .vision import Settings, VisionEngine
from .export_video import export_video


class Application:
    def __init__(self, root, assets):
        self.root = root
        self.root.title("Uchuva · ArUco PC 0.3.0")
        self.root.geometry("1200x850")
        self.assets = assets
        self.reader = None
        self.settings = Settings()
        self.selected = None
        self.revision = 0
        self.snapshot = None
        self.pending = queue.Queue(maxsize=2)
        self.closed = threading.Event()
        self.save_directory = Path.home() / "Downloads" / "UchuvaArUco"
        self.prompted = False
        self.photo = None
        self.export_cancel = threading.Event()
        self.exporting = False
        self.status = tk.StringVar(value="Preparando detector…")
        self.export_status = tk.StringVar(value="")
        self.address = tk.StringVar(value="rtmp://127.0.0.1:1935/neo")
        ttk.Label(root, text="UCHUVA / ArUco · PC", font=("Segoe UI", 20)).pack(anchor="w", padx=12, pady=8)
        inputs = ttk.Frame(root); inputs.pack(fill="x", padx=12)
        ttk.Entry(inputs, textvariable=self.address).pack(side="left", fill="x", expand=True)
        ttk.Button(inputs, text="Conectar RTMP", command=lambda: self.connect(self.address.get().strip(), True)).pack(side="left", padx=4)
        ttk.Button(inputs, text="Abrir video", command=self.open_file).pack(side="left")
        controls = ttk.Frame(root); controls.pack(fill="x", padx=12, pady=8)
        for label, command in [("Pausar / continuar", self.pause), ("Desconectar", self.disconnect),
                               ("Medida del ArUco", self.configure), ("Carpeta de guardado", self.choose_folder),
                               ("Abrir guardadas", self.open_folder)]:
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=2)
        self.save_button = ttk.Button(controls, text="Guardar JPEG + JSON", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=2)
        export_controls = ttk.Frame(root); export_controls.pack(fill="x", padx=12)
        ttk.Button(export_controls, text="Exportar video completo + datos", command=self.export).pack(side="left")
        ttk.Button(export_controls, text="Cancelar exportación", command=self.export_cancel.set).pack(side="left", padx=4)
        ttk.Button(export_controls, text="Umbral de confianza", command=self.threshold).pack(side="left")
        ttk.Label(root, textvariable=self.status, wraplength=1100).pack(anchor="w", padx=12)
        ttk.Label(root, textvariable=self.export_status, wraplength=1100).pack(anchor="w", padx=12)
        self.canvas = tk.Canvas(root, background="#101b15", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=8)
        self.canvas.bind("<Button-1>", self.select_marker)
        self.canvas.bind("<Configure>", lambda _: self.render(self.snapshot[0]) if self.snapshot else None)
        ttk.Label(root, text="Estimación sobre el plano del ArUco · Sin profundidad ni corrección de lente. Todos los marcadores deben tener el mismo lado.").pack(pady=6)
        ttk.Label(root, text="DJI Fly publica al servidor RTMP del PC. El receptor no controla el dron. Para el emisor usa la IP del PC, no 127.0.0.1.").pack(pady=3)
        root.protocol("WM_DELETE_WINDOW", self.close)
        threading.Thread(target=self.worker, daemon=True).start()
        root.after(50, self.poll)

    def invalidate(self):
        self.revision += 1
        self.snapshot = None
        self.canvas.delete("all")
        self.save_button.configure(state="disabled")

    def connect(self, source, live):
        self.disconnect()
        try:
            self.reader = VideoReader(source, live)
            self.status.set("Conectando RTMP…" if live else "Abriendo video…")
        except ValueError as error:
            messagebox.showerror("Fuente", str(error))

    def disconnect(self):
        if self.reader:
            self.reader.close()
        self.reader = None
        self.invalidate()
        self.status.set("Análisis detenido")

    def open_file(self):
        path = filedialog.askopenfilename(title="Video descargado del dron", filetypes=[("Videos", "*.mp4 *.mov *.avi *.mkv"), ("Todos", "*.*")])
        if path:
            self.connect(path, False)

    def pause(self):
        if self.reader:
            if self.reader.paused.is_set():
                self.reader.paused.clear()
            else:
                self.reader.paused.set()
                self.status.set("Pausado" + (" · RTMP continúa recibiéndose" if self.reader.live else ""))
                if self.reader.live:
                    self.invalidate()

    def configure(self):
        side = simpledialog.askstring("Medida del ArUco", "¿Cuánto mide el lado negro del ArUco, en centímetros?\nSin el margen blanco. Se aplica a todos los marcadores.",
                                      initialvalue="" if self.settings.side_cm is None else str(self.settings.side_cm))
        if side is None:
            return
        try:
            self.settings = Settings(float(side.replace(",", ".")), self.settings.confidence)
            self.invalidate()
        except ValueError as error:
            messagebox.showerror("Medida", str(error))

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Guardar capturas en…")
        if folder:
            self.save_directory = Path(folder)

    def threshold(self):
        value = simpledialog.askfloat("Detector", "Confianza mínima (0.05–0.95)", initialvalue=self.settings.confidence, minvalue=.05, maxvalue=.95)
        if value is not None:
            self.settings = Settings(self.settings.side_cm, value)
            self.invalidate()

    def export(self):
        if self.exporting:
            messagebox.showinfo("Exportación", "Ya hay una exportación en curso")
            return
        if self.settings.side_cm is None:
            self.configure()
            if self.settings.side_cm is None:
                return
        source = filedialog.askopenfilename(title="Video completo a procesar", filetypes=[("Videos", "*.mp4 *.mov *.avi *.mkv")])
        if not source:
            return
        self.exporting = True
        self.export_cancel.clear()
        self.export_status.set("Preparando exportación…")
        settings, selected, directory = self.settings, self.selected, self.save_directory
        def run():
            try:
                saved = export_video(source, directory, self.assets, settings, selected, self.export_cancel,
                                     lambda message: self.post(("export", message)))
                self.post(("export", f"Video anotado y datos guardados en {saved}"))
            except Exception as error:
                self.post(("export", str(error)))
            finally:
                self.exporting = False
        threading.Thread(target=run, daemon=False).start()

    def open_folder(self):
        self.save_directory.mkdir(parents=True, exist_ok=True)
        os.startfile(self.save_directory)

    def save(self):
        snapshot = self.snapshot
        if not snapshot:
            return
        image, result, reader, received = snapshot
        if reader.live and time.monotonic() - received > 1.5:
            self.invalidate()
            return
        folder = self.save_directory
        def write():
            try:
                saved = save_capture(folder, image, result)
                self.post(("notice", f"Guardada imagen y JSON en {saved}"))
            except Exception as error:
                self.post(("notice", f"No se pudo guardar: {error}"))
        threading.Thread(target=write, daemon=False).start()

    def select_marker(self, event):
        if not self.snapshot or not hasattr(self, "display_transform"):
            return
        scale, ox, oy = self.display_transform
        point = ((event.x-ox)/scale, (event.y-oy)/scale)
        import numpy as np
        for marker in self.snapshot[1]["markers"]:
            if cv2.pointPolygonTest(np.array(marker["corners_px"], np.float32), point, False) >= 0:
                self.selected = marker["id"]
                self.invalidate()
                return

    def post(self, item):
        while not self.closed.is_set():
            try:
                self.pending.put(item, timeout=.1)
                return
            except queue.Full:
                continue

    def worker(self):
        try:
            engine = VisionEngine(self.assets)
        except Exception as error:
            self.post(("notice", f"Análisis no disponible: {error}"))
            return
        self.post(("notice", "Listo. Conecta RTMP o abre un video."))
        last_key = None
        while not self.closed.wait(.01):
            reader, revision, settings, selected = self.reader, self.revision, self.settings, self.selected
            if not reader or reader.paused.is_set() or not reader.latest:
                continue
            frame = reader.latest
            key = (reader, frame.number, revision)
            if key == last_key or (reader.live and time.monotonic()-frame.monotonic > 1.5):
                continue
            last_key = key
            try:
                image, result = engine.analyze(frame.image, settings, frame.number, "rtmp" if reader.live else "file", selected,
                                               frame.received_at, frame.media_time_ms)
                self.post(("frame", reader, revision, frame.monotonic, image, result))
            except Exception as error:
                self.post(("notice", f"Análisis no disponible: {error}"))

    def poll(self):
        try:
            while True:
                event = self.pending.get_nowait()
                if event[0] == "notice":
                    self.status.set(event[1])
                elif event[0] == "export":
                    self.export_status.set(event[1])
                else:
                    _, reader, revision, received, image, result = event
                    if reader is not self.reader or revision != self.revision:
                        continue
                    if reader.live and (reader.paused.is_set() or time.monotonic()-received > 1.5):
                        continue
                    self.snapshot = (image, result, reader, received)
                    if self.selected is None:
                        self.selected = result["reference"]["selected_id"]
                    count = len(result["detections"])
                    self.status.set((f"Capachos detectados: {count}" if count else "Sin detecciones") +
                                    f' · ArUcos: {len(result["markers"])} · {result["analysis_ms"]:.0f} ms' +
                                    (" · confirma el lado en centímetros" if self.settings.side_cm is None else ""))
                    self.render(image)
                    self.save_button.configure(state="normal")
                    if result["markers"] and self.settings.side_cm is None and not self.prompted:
                        self.prompted = True
                        self.root.after_idle(self.configure)
        except queue.Empty:
            pass
        if self.reader and self.reader.error:
            self.status.set(self.reader.error)
            if self.snapshot:
                self.invalidate()
        elif self.snapshot and self.reader and self.reader.live and time.monotonic()-self.snapshot[3] > 1.5:
            self.invalidate()
            self.status.set("Esperando un fotograma actualizado RTMP…")
        self.root.after(50, self.poll)

    def render(self, image):
        h, w = image.shape[:2]
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = min(cw/w, ch/h)
        preview = cv2.resize(image, (max(1, round(w*scale)), max(1, round(h*scale))))
        self.photo = tk.PhotoImage(data=cv2.imencode(".png", preview)[1].tobytes())
        self.canvas.delete("all")
        self.canvas.create_image(cw/2, ch/2, image=self.photo)
        self.display_transform = (scale, (cw-w*scale)/2, (ch-h*scale)/2)

    def close(self):
        self.closed.set()
        self.export_cancel.set()
        if self.reader:
            self.reader.close()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    default = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets"
    if not (default / "detector.onnx").exists():
        default = Path(__file__).resolve().parents[2] / "mobile/android/app/src/main/assets"
    parser.add_argument("--assets", type=Path, default=default)
    parser.add_argument("--self-test", type=Path, help="Write a packaged-runtime diagnostic JSON and exit")
    args = parser.parse_args()
    if args.self_test:
        import json
        import numpy as np
        probe = tk.Tk()
        probe.withdraw()
        probe.update()
        probe.destroy()
        image = np.full((480, 640, 3), 255, np.uint8)
        marker = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 0, 180)
        image[40:220, 40:220] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        _, result = VisionEngine(args.assets).analyze(image, Settings(10))
        if len(result["markers"]) != 1:
            raise RuntimeError("Packaged ArUco detector failed")
        args.self_test.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return
    root = tk.Tk()
    Application(root, args.assets)
    root.mainloop()


if __name__ == "__main__":
    main()
