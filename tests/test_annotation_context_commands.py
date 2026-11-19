"""Context command bar, mode hotkeys, text focus and read-only protections."""
from pathlib import Path
import sys,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageDraw
REPO=Path(__file__).resolve().parents[1];sys.path[:0]=[str(REPO/'src'),str(REPO/'scripts'),str(REPO/'tests')]
from test_blind_annotation_audit import fixture
from test_annotation_assistance import metadata
from uchuva_annotation_audit.store import AuditStore,read
from annotation_audit_app import AuditApp,MODE_KEYS


class ContextCommandTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        base=REPO/'outputs/annotation_audit_unit_tests';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.store=AuditStore(fixture(Path(self.tmp.name)))
        self.window=tk.Tk();self.window.withdraw();self.app=AuditApp(self.window,self.store);self.app.change_image('I01')
    def tearDown(self):
        self.app.assist_closed=True
        if self.app.assist_executor:self.app.assist_executor.shutdown(wait=True,cancel_futures=True)
        self.window.update_idletasks()
        for pending in self.window.tk.splitlist(self.window.tk.call('after','info')):
            self.window.after_cancel(pending)
        self.app.lock.close()
        self.window.destroy()
        self.tmp.cleanup()

    def test_all_identified_mode_keys_change_actual_tool_and_context(self):
        app=self.app
        self.assertEqual(app.command_bar.pack_info()['side'],'bottom')
        self.assertEqual(len(app.command_buttons),8)
        for (key,_,tool,action),(button,_,_) in zip(MODE_KEYS,app.command_buttons):
            self.assertIn(f'[{key}]',button.cget('text'))
            self.assertEqual(app.run_shortcut(key,SimpleNamespace(state=0)),'break')
            app.update_command_help()
            self.assertEqual(app.left.tool,tool)
            if action:self.assertEqual(app.left.node_action,action)
            self.assertIn(key+' ·',app.command_title.get())
            self.assertEqual(button.cget('style'),'ActiveMode.TButton')
            self.assertTrue(self.window.bind(f'<KeyPress-{key.lower()}>'))

    def test_navigation_dropdown_resets_on_blocked_change_and_saves_corner_notes(self):
        app=self.app
        self.assertFalse(app.notes.winfo_manager())
        app.toggle_notes()
        app.notes.insert('1.0','Revisar borde.')
        app.toggle_notes()
        app.left.points=[(3,3)]
        app.queue.current(1)
        with patch('annotation_audit_app.messagebox.showinfo'):
            app.queue_change()
        self.assertEqual(app.queue.current(),0)
        self.assertEqual(app.current,'I01')
        app.left.points=[]
        app.queue.current(1)
        app.queue_change()
        self.assertEqual(app.current,'I02')
        self.assertEqual(self.store.draft('I01')['notes'],'Revisar borde.')
        self.assertEqual(app.note_text(),'')

    def test_instance_dropdown_and_active_options_help(self):
        app=self.app
        app.left.new_object(Image.new('L',(40,30),255))
        app.left.new_object(Image.new('L',(40,30),255))
        app.refresh_objects()
        app.instances.current(1)
        app.object_selected()
        self.assertEqual(app.left.selected,app.left.objects[0]['id'])
        for key,expected in [('P','polygon'),('S','sam'),('B','brush'),('I',None)]:
            app.run_shortcut(key)
            app.update_command_help()
            self.assertEqual([name for name,panel in app.tool_options.items() if panel.winfo_manager()],
                             [expected] if expected else [])
        help_window=app.show_tool_help()
        self.assertEqual(help_window.title(),'Ayuda · Insertar nodo')
        help_window.destroy()

    def test_reviewer_profile_updates_preferences_and_preserves_current_image(self):
        from tkinter import ttk
        app=self.app
        self.assertFalse(app.reviewer.get())
        app.edit_reviewer()
        popup=app.profile_window
        panel=popup.winfo_children()[0]
        field=next(widget for widget in panel.winfo_children() if isinstance(widget,ttk.Entry))
        buttons=next(widget for widget in panel.winfo_children() if isinstance(widget,ttk.Frame))
        save=next(widget for widget in buttons.winfo_children() if widget.cget('text')=='Guardar perfil')
        save.invoke()
        self.assertIs(app.profile_window,popup)
        field.insert(0,'  Etiquetador de prueba  ')
        save.invoke()
        self.assertIsNone(app.profile_window)
        self.assertEqual(read(self.store.session/'preferences.json'),{'reviewer':'Etiquetador de prueba','last_sample':'I01'})
        app.edit_reviewer()
        panel=app.profile_window.winfo_children()[0]
        self.assertEqual(next(widget for widget in panel.winfo_children() if isinstance(widget,ttk.Entry)).get(),
                         'Etiquetador de prueba')

    def test_typing_and_modifier_combinations_do_not_switch_tools_or_edit(self):
        import tkinter as tk
        from tkinter import ttk
        app=self.app
        for widget in (app.notes,tk.Entry(self.window),ttk.Combobox(self.window),ttk.Spinbox(self.window)):
            with patch.object(self.window,'focus_get',return_value=widget):
                before=app.left.payload();tool=app.left.tool;cid=app.class_var.get()
                for action in ('P','S','B','E','M','I','D','N','1','delete_instance','escape','undo','enter','next'):
                    self.assertIsNone(app.run_shortcut(action,SimpleNamespace(state=0)))
                self.assertEqual(app.left.tool,tool);self.assertEqual(app.class_var.get(),cid);self.assertEqual(app.left.payload(),before)
                app.update_command_help();self.assertIn('ESCRITURA',app.command_title.get())
                with patch.object(app,'save_context') as save:
                    app.run_shortcut('save');save.assert_called_once()
        with patch.object(app,'in_text',return_value=False):
            alt=0x20000 if app.windowing_system=='win32' else 8
            for state in (4,alt):self.assertIsNone(app.run_shortcut('P',SimpleNamespace(state=state)))

    def test_sam_with_windows_numlock_and_capslock_and_platform_alt(self):
        app=self.app;app.windowing_system='win32'
        for state in (8,8|2,8|1):
            app.run_shortcut('P');app.run_shortcut('S',SimpleNamespace(state=state))
            self.assertEqual(app.left.tool,'sam')
        app.windowing_system='x11';app.run_shortcut('P')
        self.assertIsNone(app.run_shortcut('S',SimpleNamespace(state=8)))
        self.assertEqual(app.left.tool,'polygon')

    def test_enter_is_contextual_and_readonly_never_edits(self):
        app=self.app;view=app.left;app.run_shortcut('P')
        view.points=[(4,4),(15,4),(8,16)];app.update_command_help()
        self.assertIn('3 vértices',app.command_title.get());app.run_shortcut('enter')
        self.assertEqual(len(view.objects),1)
        app.run_shortcut('S')
        mask=Image.new('L',(40,30));ImageDraw.Draw(mask).rectangle((22,5,30,16),fill=255)
        view.assist_points=[(26,10)];view.assist_labels=[1];view.assist_preview=mask;view.assist_metadata=metadata(mask.size)
        app.update_command_help();self.assertIn('máscara lista',app.command_title.get())
        app.run_shortcut('enter');self.assertEqual(len(view.objects),2);self.assertEqual(view.tool,'nodes')
        self.assertIsNone(app.comparison_data)
        with self.assertRaises(PermissionError):self.store.comparison('I01')
        app.phase='compare';app.right.load(view.image,view.payload(),False);before=app.right.payload()
        app.update_command_help();self.assertIn('sólo lectura',app.command_title.get())
        for action in ('N','B','E','I','D','1','delete_instance','enter','undo'):app.run_shortcut(action)
        self.assertEqual(app.right.payload(),before)
        for button,tool,_ in app.command_buttons:
            self.assertEqual(str(button.cget('state')),'normal' if tool=='select' else 'disabled')
        with patch.object(app,'save_final') as save:
            app.run_shortcut('save');save.assert_not_called()
        self.assertIn('sólo lectura',app.status_var.get())

    def test_save_dispatches_to_current_phase(self):
        app=self.app
        with patch.object(app,'save_draft') as draft:
            app.run_shortcut('save');draft.assert_called_once()
        app.phase='compare';app.right.editable=True
        with patch.object(app,'save_final') as final:
            app.run_shortcut('save');final.assert_called_once()

    def test_initial_resize_fits_photo_but_preserves_deliberate_zoom(self):
        view=self.app.left;view.load(Image.new('RGB',(640,480)),[],True)
        with patch.object(view.canvas,'winfo_width',return_value=800),patch.object(view.canvas,'winfo_height',return_value=450):
            view.resize_view();self.assertAlmostEqual(view.scale,420/480)
            view.zoom(2);zoom=view.scale;view.resize_view();self.assertEqual(view.scale,zoom)
            view.new_object(Image.new('L',(640,480),255));view.focus_selected();focused=view.scale
            view.resize_view();self.assertEqual(view.scale,focused);self.assertTrue(view.user_view)
            view.fit();self.assertAlmostEqual(view.scale,420/480)
        self.assertFalse(view.user_view)


if __name__=='__main__':unittest.main()
