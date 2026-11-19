"""Use one native workbench for blind lots or private coordination."""
from pathlib import Path
import argparse
import copy
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageChops

from annotation_audit_app import AuditApp
from uchuva_annotation_audit.cross_review import CoordinatorStore, ReviewerStore, assistance_status
from uchuva_annotation_audit.masks import decode_mask, encode_mask
from uchuva_annotation_audit.store import CLASSES, atomic_json, compare_objects
from uchuva_annotation_audit.ui_theme import UI


SOURCES = {'human_a': 'Humana A', 'human_b': 'Humana B', 'pilot': 'Piloto'}
REVIEW_STATES = {'sin_sam': 'sin SAM', 'mostrada': 'SAM vista', 'aceptada': 'SAM aceptada'}


class CrossReviewApp(AuditApp):
    def __init__(self, window, store):
        self.coordination = store.role == 'coordinator'
        self.autosave_job = None
        self.loading_image = False
        self.comparison_sources = None
        self.viewport = None
        self.viewport_fit = True
        super().__init__(window, store)
        window.title('Uchuva · Coordinación' if self.coordination else f'Uchuva · Revisión {store.reviewer_id}')

    def build(self):
        super().build()
        for widget in self.workflow.pack_slaves():
            if widget not in self.step_labels:
                widget.destroy()
        self.step_labels[0].configure(text='CONTRASTAR' if self.coordination else 'REVISAR')
        for label in self.step_labels[1:]:
            label.pack_forget()
        self.commit_button.configure(text='Entregar y seguir →')
        for widget in self.blind_controls.pack_slaves():
            if isinstance(widget, ttk.Button) and widget is not self.commit_button:
                widget.destroy()
        ttk.Button(self.blind_controls, text='Guardar borrador [Ctrl+S]', command=self.save_draft).pack(side='right', padx=(6, 0))
        self.profile_badge = ttk.Label(self.workflow, style='Muted.TLabel')
        self.profile_badge.pack(side='right', padx=8)
        self.reviewer.trace_add('write', lambda *_: self.refresh_profile_badge())
        self.refresh_profile_badge()
        self.notes.bind('<<Modified>>', self.notes_changed)
        self.set_focus_indicators()
        if self.coordination:
            self.build_comparison_controls()
        self.style.configure('Muted.TLabel', foreground='#52675d')
        # Keep inactive keyboard controls distinct while retaining a visible focus ring.
        self.style.map('Mode.TButton', bordercolor=[('focus', UI['accent'])])

    def set_focus_indicators(self):
        # ttk's flat theme can suppress the native ring on buttons. Restore it
        # via style and use a border for keyboard focus on the two canvases.
        for style in ('TButton', 'Mode.TButton', 'Accent.TButton', 'ActiveMode.TButton', 'Danger.TButton'):
            self.style.configure(style, focusthickness=2, borderwidth=2)
            light = style in ('ActiveMode.TButton', 'Accent.TButton')
            focus = '#ffffff' if light else '#17362d'
            edge = '#147d59' if light else '#e7eee8'
            for option in ('focuscolor', 'bordercolor', 'lightcolor', 'darkcolor'):
                self.style.map(style, **{option: [('focus', focus), ('!focus', edge)]})
        for view in (self.left, self.right):
            view.canvas.configure(takefocus=True, highlightthickness=2,
                                  highlightbackground='#f3f6f3', highlightcolor=UI['accent'])

    def refresh_profile_badge(self):
        identity = 'Coordinación' if self.coordination else self.store.reviewer_id
        display_name = self.reviewer.get().strip()
        self.profile_badge.configure(text=f'{identity} · {display_name[:36]}' if display_name else identity)

    def build_navigation_bar(self):
        super().build_navigation_bar()
        self.queue.configure(width=17)
        if self.coordination:
            parent = self.fullscreen_button.master  # Header is independent of the review toolbar.
            ttk.Button(parent, text='Importar ZIP', command=self.import_package).pack(side='right', padx=6)

    def open_initial_image(self, last_sample):
        if self.current:
            return
        if self.coordination:
            first = next((ident for ident in self.ids if self.store.received_count(ident) == 2), self.ids[0])
        else:
            first = next((ident for ident in self.ids if not self.store.manual_path(ident).is_file()), self.ids[0])
        self.change_image(last_sample if last_sample in self.ids else first)

    def active_view(self):
        return self.left

    def update_command_help(self):
        super().update_command_help()
        if self.phase == 'delivered':
            self.command_title.set('ENTREGADA · Sólo lectura')
            self.command_actions.set('Consulta tu entrega o elige otra imagen en la barra superior.')
        elif self.coordination:
            self.command_title.set('CONTRASTE · Sólo lectura')
            self.command_actions.set('Importa entregas. Con dos revisiones disponibles, cambia la fuente de cada panel.')
        if hasattr(self, 'profile_badge'):
            self.refresh_profile_badge()
        if hasattr(self, 'step_labels'):
            self.step_labels[0].configure(bg=UI['soft'], fg=UI['accent'])

    def refresh_queue(self):
        progress = self.store.progress()
        if self.coordination:
            self.progress_var.set(f'{progress["complete"]}/{progress["total"]} listas · {progress["submissions"]}/{2*progress["total"]} entregas')
            values = [f'{ident} · {self.store.received_count(ident)}/2' for ident in self.ids]
        else:
            self.progress_var.set(f'{self.store.reviewer_id} · {progress["manual"]}/{progress["total"]} entregadas')
            values = [f'{ident} · {self.image_state(ident)}' for ident in self.ids]
        self.queue.configure(values=values)
        if self.current in self.ids:
            self.queue.current(self.ids.index(self.current))

    def image_state(self, ident):
        if self.store.manual_path(ident).is_file():
            return 'Entregada'
        if (self.store.session / 'drafts' / f'{ident}.json').is_file():
            return 'Borrador'
        return 'Pendiente'

    def notes_changed(self, event=None):
        if self.notes.edit_modified():
            self.notes.edit_modified(False)
            self.queue_autosave()

    def changed(self):
        super().changed()
        self.queue_autosave()

    def queue_autosave(self):
        if self.current and self.phase == 'manual' and not self.coordination and not self.loading_image:
            if self.autosave_job is not None:
                self.window.after_cancel(self.autosave_job)
            self.autosave_job = self.window.after(800, self.autosave)

    def autosave(self):
        self.autosave_job = None
        if not self.left.points and not self.left.assist_points:
            self.save_draft(quiet=True)

    def save_draft(self, quiet=False):
        if self.coordination or self.phase != 'manual':
            return True
        if not super().save_draft(quiet=quiet):
            if quiet and not self.left.points and not self.left.assist_points:
                self.status_var.set('No se pudo guardar automáticamente. Pulsa Ctrl+S para ver el detalle.')
            return False
        if self.current:
            self.phase_var.set(f'{self.current} · Borrador guardado')
            self.status_var.set('Borrador guardado en este equipo.')
            self.refresh_queue()
        return True

    def set_notes(self, value, editable):
        self.notes.configure(state='normal')
        self.notes.delete('1.0', 'end')
        self.notes.insert('1.0', value)
        self.notes.edit_reset()
        self.notes.edit_modified(False)
        if not editable:
            self.notes.configure(state='disabled')

    def change_image(self, ident):
        if ident == self.current:
            return
        if self.current and not self.coordination and self.phase == 'manual' and not self.save_draft():
            return
        if self.autosave_job is not None:
            self.window.after_cancel(self.autosave_job)
            self.autosave_job = None
        image = Image.open(self.store.image_path(ident)).convert('RGB')
        self.current = ident
        self.started = time.monotonic()
        self.empty_var.set(False)
        self.reference_tool.reset()
        self.status_var.set('')
        self.editor_info.set(f'{ident} · {image.width} × {image.height} px')
        if self.coordination:
            self.load_comparison(image)
        else:
            self.load_review(image)
        self.refresh_queue()
        self.save_preferences()
        self.schedule_command_help()

    def load_review(self, image):
        record = self.store.manual(self.current)
        saved = record if record is not None else self.store.draft(self.current)
        self.phase = 'delivered' if record is not None else 'manual'
        self.elapsed_base = saved.get('elapsed_seconds', 0)
        base_context = dict(reference_tool=self.reference_tool.context(),
                            reference_available=self.reference_tool.palette is not None)
        self.store.runtime_context = {**base_context, **copy.deepcopy(saved.get('application_context', {}))}
        if record is None:
            self.store.runtime_context = self.store.review_context(self.current, self.store.runtime_context)
        self.loading_image = True
        try:
            self.set_notes(saved.get('notes', ''), record is None)
            self.left.load(image, saved['objects'], record is None)
            self.left.tool = self.tool_var.get()
            self.left.node_action = self.node_action.get()
        finally:
            self.loading_image = False
        if record is None:
            self.blind_controls.pack(fill='x')
        else:
            self.blind_controls.pack_forget()
        state = self.image_state(self.current)
        self.phase_var.set(f'{self.current} · {"Borrador guardado" if state == "Borrador" else state}')
        self.left_label.configure(text='Tus máscaras entregadas' if record else 'Segmenta la superficie visible del capacho.')
        self.refresh_objects()

    def commit(self):
        if self.coordination or self.phase != 'manual' or not self.current:
            return
        if not self.reviewer.get().strip():
            self.edit_reviewer()
            return
        if not self.save_draft():
            return
        if not self.left.objects and not self.empty_var.get():
            messagebox.showinfo('Confirma la revisión', 'Marca «Sin instancias» sólo si la imagen no tiene capachos que anotar.', parent=self.window)
            return
        if not messagebox.askyesno('Entregar imagen', 'La revisión quedará en sólo lectura. ¿Entregar y continuar?', parent=self.window):
            return
        try:
            self.store.commit_manual(self.current, self.left.payload(), self.reviewer.get(), self.note_text(),
                                     self.empty_var.get(), self.elapsed_base + time.monotonic() - self.started)
        except (OSError, ValueError) as exc:
            messagebox.showerror('No se pudo entregar', str(exc), parent=self.window)
            return
        submitted = self.current
        index = self.ids.index(submitted)
        queue = self.ids[index + 1:] + self.ids[:index]
        target = next((ident for ident in queue if not self.store.manual_path(ident).is_file()), submitted)
        self.current = None
        self.change_image(target)
        self.status_var.set('Lote completo. Exporta el ZIP para coordinación.' if target == submitted else f'{submitted} entregada.')

    def poll_assistance(self):
        job = self.assist_job if self.assist_future is not None and self.assist_future.done() else None
        super().poll_assistance()
        if job:
            view, serial, ident, *_ = job
            if ident == self.current and serial == view.assist_serial and view.assist_preview is not None:
                self.record_sam_usage(view.assist_metadata)

    def accept_sam(self):
        before = len(self.left.objects)
        super().accept_sam()
        if len(self.left.objects) > before:
            self.record_sam_usage(self.left.objects[-1]['assistance'], accepted=True)
            self.queue_autosave()

    def record_sam_usage(self, metadata, *, accepted=False):
        try:
            self.store.record_sam(self.current, metadata, accepted=accepted)
        except OSError:
            self.status_var.set('No se pudo guardar el uso de SAM. Guarda el borrador antes de cerrar.')

    def discard_sam(self):
        super().discard_sam()
        self.queue_autosave()

    def set_tool(self):
        super().set_tool()
        if self.store.runtime_context.get('sam_previews'):
            self.queue_autosave()

    def run_shortcut(self, action, event=None):
        result = super().run_shortcut(action, event)
        if action == 'escape' and result == 'break' and self.store.runtime_context.get('sam_previews'):
            self.queue_autosave()
        return result

    def save_context(self):
        if self.coordination:
            self.record_resolution()
        elif self.phase == 'manual':
            self.save_draft()

    def export(self):
        if not self.coordination and not self.save_draft():
            return
        try:
            if self.coordination:
                path = self.store.session / 'acuerdo.json'
                atomic_json(path, self.store.report())
            else:
                path = self.store.export()
        except (ValueError, OSError) as exc:
            messagebox.showerror('No se pudo exportar', str(exc), parent=self.window)
            return
        self.status_var.set(f'Exportado en {path}')

    def build_comparison_controls(self):
        self.blind_controls.pack_forget()
        for container in (self.right_toolbar, self.comparison_frame):
            container.unbind('<Configure>')
            for child in container.winfo_children():
                child.destroy()
        self.comparison_frame.pack(fill='x')
        self.comparison_label = ttk.Label(self.comparison_frame, style='Muted.TLabel', wraplength=650)
        self.comparison_label.pack(fill='x')
        self.comparison_frame.bind('<Configure>', lambda event: self.comparison_label.configure(wraplength=max(250,event.width-10)))
        self.left_selector = self.source_selector(self.left_frame, 'human_a', before=self.left_label)
        self.right_selector = self.source_selector(self.right_toolbar, 'human_b')
        controls = ttk.Frame(self.comparison_frame, style='Card.TFrame')
        controls.pack(fill='x')
        self.difference = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text='Diferencia de máscaras', variable=self.difference,
                        command=self.update_comparison_views).pack(side='left')
        ttk.Button(controls, text='Registrar resolución…', command=self.record_resolution).pack(side='right')
        for view in (self.left, self.right):
            for gesture in ('<MouseWheel>', '<B2-Motion>', '<B3-Motion>'):
                view.canvas.bind(gesture, lambda event, source=view: self.sync_viewport(source), add='+')
            view.canvas.bind('<Configure>', lambda event: self.resize_comparison(), add='+')
        self.right.on_select = lambda ident: None
        toolbar = next(widget for widget in self.panels.master.pack_slaves() if widget is not self.panels and
                       any(isinstance(child, ttk.Button) and child.cget('text') == '+' for child in widget.winfo_children()))
        for widget in toolbar.winfo_children():
            if isinstance(widget, ttk.Button) and widget.cget('text') in ('+', '−'):
                factor = 1.3 if widget.cget('text') == '+' else 1/1.3
                widget.configure(command=lambda value=factor: self.zoom_comparison(value))
        self.note_button.configure(text='Notas de las entregas')

    def source_selector(self, parent, initial, before=None):
        selector = ttk.Combobox(parent, values=list(SOURCES.values()), state='readonly', width=14)
        selector.current(list(SOURCES).index(initial))
        selector.pack(anchor='w', pady=(0, 3), **({'before': before} if before else {}))
        selector.bind('<<ComboboxSelected>>', lambda event: self.update_comparison_views())
        return selector

    def load_comparison(self, image):
        self.phase = 'coordination'
        self.viewport = None
        self.viewport_fit = True
        self.comparison_sources = None
        self.set_notes('', False)
        received = self.store.received_count(self.current)
        self.phase_var.set(f'{self.current} · {received}/2 entregas humanas')
        for selector in (self.left_selector, self.right_selector):
            selector.configure(state='readonly' if received == 2 else 'disabled')
        self.left.load(image, [], False)
        self.left_label.configure(text='')
        if received < 2:
            if str(self.right_frame) in self.panels.panes():
                self.panels.forget(self.right_frame)
            self.comparison_label.configure(text='La comparación se habilita con las dos entregas.')
            self.refresh_objects()
            return
        if str(self.right_frame) not in self.panels.panes():
            self.panels.add(self.right_frame, weight=1)
        self.right.load(image, [], False)
        self.comparison_sources = self.store.comparison(self.current)['sources']
        self.difference.set(False)
        self.update_comparison_views()
        self.window.after_idle(self.fit)

    def update_comparison_views(self):
        if self.comparison_sources is None:
            return
        first = list(SOURCES)[self.left_selector.current()]
        second = list(SOURCES)[self.right_selector.current()]
        a, b = (self.comparison_sources[key]['objects'] for key in (first, second))
        comparison = compare_objects(a, b)
        self.set_display_masks(self.left, a)
        self.set_display_masks(self.right, mask_differences(a, b, comparison) if self.difference.get() else b)
        class_differences = [
            f'{item["manual_index"]+1} {CLASSES[item["manual_class"]]} / {item["proposal_index"]+1} {CLASSES[item["proposal_class"]]}'
            for item in comparison['matches'] if not item['class_agrees']
        ]
        details = f'{len(comparison["matches"])} pares de máscara · {len(class_differences)} diferencias de clase · '
        details += f'{len(comparison["unmatched_manual"])} sin par a la izquierda y {len(comparison["unmatched_proposal"])} a la derecha.'
        if self.difference.get():
            details += ' A la derecha se ven los píxeles presentes en una sola fuente y las máscaras sin par.'
        self.comparison_label.configure(text=details)
        texts = []
        for key in dict.fromkeys((first, second)):
            record = self.comparison_sources[key]
            if key != 'pilot':
                texts.append(f'{SOURCES[key]} · {REVIEW_STATES[assistance_status(record)]}\n{record.get("notes") or "Sin notas."}')
        if class_differences:
            texts.append('Diferencias de clase\n' + '\n'.join(class_differences))
        resolution = self.store.latest_resolution(self.current)
        if resolution:
            texts.append(f'Resolución de {resolution["reviewer"]}\n{resolution["notes"]}')
        self.set_notes('\n\n'.join(texts), False)
        self.refresh_objects()

    @staticmethod
    def set_display_masks(view, objects):
        view.selected = None
        view.objects = objects
        view.cache.clear()
        view.redraw()

    def sync_viewport(self, source):
        if self.comparison_sources is None or source.scale <= 0:
            return
        center = (
            (source.canvas.winfo_width()/2-source.ox)/source.scale,
            (source.canvas.winfo_height()/2-source.oy)/source.scale,
        )
        self.viewport_fit = False
        self.align_viewports(source.scale, center)

    def align_viewports(self, scale, center):
        self.viewport = scale, center
        for view in (self.left, self.right):
            view.scale = scale
            view.ox = view.canvas.winfo_width()/2 - center[0]*scale
            view.oy = view.canvas.winfo_height()/2 - center[1]*scale
            view.user_view = True
            view.redraw()

    def resize_comparison(self):
        if self.comparison_sources is None:
            return
        if self.viewport_fit or self.viewport is None:
            self.fit()
        else:
            self.align_viewports(*self.viewport)

    def zoom_comparison(self, factor):
        self.left.zoom(factor)
        self.sync_viewport(self.left)

    def fit(self):
        if not self.coordination or self.comparison_sources is None:
            self.left.fit()
            return
        image = self.left.image
        width = min(self.left.canvas.winfo_width(), self.right.canvas.winfo_width())
        height = min(self.left.canvas.winfo_height(), self.right.canvas.winfo_height())
        if min(width, height) > 30:
            self.viewport_fit = True
            self.align_viewports(min((width-30)/image.width, (height-30)/image.height),
                                 (image.width/2, image.height/2))

    def import_package(self):
        path = filedialog.askopenfilename(parent=self.window, title='Importar entregas', filetypes=[('Entregas ZIP', '*.zip')])
        if not path:
            return
        try:
            result = self.store.import_delivery(path)
        except Exception as exc:
            messagebox.showerror('No se pudo importar', str(exc), parent=self.window)
            return
        previous = self.current
        self.current = None
        self.change_image(previous or self.ids[0])
        self.status_var.set(f'{result["imported"]} entregas nuevas · {result["already_present"]} ya registradas.')

    def record_resolution(self):
        if not self.coordination or self.comparison_sources is None:
            return
        if not self.reviewer.get().strip():
            self.edit_reviewer()
            return
        from tkinter import simpledialog
        notes = simpledialog.askstring('Registrar resolución', 'Describe el desacuerdo y el criterio aplicado.', parent=self.window)
        if notes and notes.strip():
            try:
                self.store.resolve(self.current, self.reviewer.get(), notes)
            except (ValueError, OSError) as exc:
                messagebox.showerror('No se pudo guardar', str(exc), parent=self.window)
                return
            self.update_comparison_views()
            self.status_var.set('Resolución registrada por separado.')


def mask_differences(a, b, comparison):
    """XOR per matched instance; unmatched masks are wholly different."""
    result = []
    for row in comparison['matches']:
        first = a[row['manual_index']]
        second = b[row['proposal_index']]
        difference = ImageChops.difference(decode_mask(first['segmentation']), decode_mask(second['segmentation']))
        if difference.getbbox():
            result.append(encode_mask(difference))
    result.extend(a[i]['segmentation'] for i in comparison['unmatched_manual'])
    result.extend(b[i]['segmentation'] for i in comparison['unmatched_proposal'])
    return [dict(id=f'diferencia-{i}', class_id=None, segmentation=mask) for i,mask in enumerate(result)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    role = parser.add_mutually_exclusive_group()
    role.add_argument('--reviewer', type=Path, metavar='LOTE')
    role.add_argument('--coordinator', type=Path, metavar='CARPETA')
    args = parser.parse_args()
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass
    window = tk.Tk()
    window.withdraw()
    try:
        if not args.reviewer and not args.coordinator:
            folder = filedialog.askdirectory(parent=window, title='Selecciona tu lote R01–R06')
            if not folder:
                window.destroy()
                return
            args.reviewer = Path(folder)
        store = ReviewerStore(args.reviewer) if args.reviewer else CoordinatorStore(args.coordinator)
        app = CrossReviewApp(window, store)
    except Exception as exc:
        messagebox.showerror('No se pudo abrir la revisión cruzada', str(exc), parent=window)
        window.destroy()
        return
    app.show()
    window.mainloop()


if __name__ == '__main__':
    main()
