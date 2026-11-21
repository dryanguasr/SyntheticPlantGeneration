"""Exercise blind distribution, paired review, and isolated desktop states."""
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import sys
import unittest
import zipfile

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'src'), str(REPO / 'scripts'), str(REPO / 'tests')]

from cross_review_app import CrossReviewApp, mask_differences
from prepare_cross_review import STUDENT_MANUAL, distribute_round
from test_blind_annotation_audit import shape
from uchuva_annotation_audit.cross_review import (
    CoordinatorStore, REVIEWERS, ReviewerStore, assistance_status, prepare_round,
)
from uchuva_annotation_audit.masks import mask_iou
from uchuva_annotation_audit.store import atomic_json, compare_objects, read, sha


def fake_pilot(root):
    rows = []
    for i in range(1,51):
        ident = f'I{i:02}'
        sample = dict(id=ident, width=40, height=30, image=f'images/{ident}.jpg')
        rows.append(sample)
        image = root / sample['image']
        image.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB',(40,30),(i,2*i,3*i)).save(image, quality=100)
        atomic_json(root / 'private/proposals' / f'{ident}.json', dict(objects=[shape()], method='fixture'))
        atomic_json(root / 'private/originals' / f'{ident}.json', dict(objects=[shape(0)], role='private'))
    atomic_json(root / 'samples.json', dict(samples=rows))
    atomic_json(root / 'private/selection.json', dict(samples=[
        dict(id=row['id'], stratum='random' if i < 30 else 'difficult') for i,row in enumerate(rows)
    ]))
    atomic_json(root / 'sealed.json', dict(files={
        path.relative_to(root).as_posix(): sha(path) for path in root.rglob('*') if path.is_file()
    }))


@contextmanager
def hidden_app(store):
    import tkinter as tk
    window = tk.Tk()
    window.withdraw()
    app = CrossReviewApp(window, store)
    try:
        yield app
    finally:
        if app.assist_executor:
            app.assist_executor.shutdown(wait=True, cancel_futures=True)
        window.update_idletasks()
        for job in window.tk.splitlist(window.tk.call('after','info')):
            window.after_cancel(job)
        app.lock.close()
        window.destroy()


class CrossReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (REPO/'outputs/annotation_audit_unit_tests').mkdir(parents=True,exist_ok=True)

    def setUp(self):
        self.tmp = TemporaryDirectory(dir=REPO/'outputs/annotation_audit_unit_tests')
        self.source = Path(self.tmp.name)/'pilot'
        self.root = Path(self.tmp.name)/'round'
        fake_pilot(self.source)
        prepare_round(self.source, self.root, student_manual=STUDENT_MANUAL)
        self.coordinator = CoordinatorStore(self.root/'coordinacion')
        self.addCleanup(self.tmp.cleanup)

    def reviewer(self, reviewer_id):
        return ReviewerStore(self.root / 'revisores' / reviewer_id)

    def test_distribution_adds_manual_and_excludes_sidecars(self):
        first = self.reviewer('R01')
        (first.root / STUDENT_MANUAL.name).unlink()
        sample_id = next(iter(first.samples))
        first.commit_manual(sample_id, [shape(1)], 'Persona de prueba')
        first.export()
        seal_hash = sha(first.root / 'sealed.json')

        def runtime_stub(runtime):
            runtime.mkdir()
            (runtime / 'LICENSE').write_text('fixture', encoding='utf-8')

        destination = self.root / 'distribucion'
        with patch('prepare_cross_review.build_runtime', side_effect=runtime_stub):
            distribute_round(self.root, destination)
        self.assertEqual(sha(first.root / 'sealed.json'), seal_hash)
        self.assertEqual(sha(first.root / STUDENT_MANUAL.name), sha(STUDENT_MANUAL))
        self.assertEqual({p.stem for p in destination.iterdir()}, {'aplicacion', *REVIEWERS})
        for code in REVIEWERS:
            lot = self.reviewer(code)
            expected = {'sealed.json', STUDENT_MANUAL.name, *lot.seal['files']}
            with zipfile.ZipFile(destination / f'{code}.zip') as archive:
                self.assertEqual(set(archive.namelist()), {f'{code}/{name}' for name in expected})
                self.assertEqual(archive.read(f'{code}/{STUDENT_MANUAL.name}'), STUDENT_MANUAL.read_bytes())

    def test_full_round_has_two_independent_humans_and_one_frozen_proposal(self):
        coordinator = self.coordinator
        self.assertEqual(len(coordinator.samples),50)
        pairs = Counter((row['stratum'],tuple(row['reviewers'])) for row in coordinator.samples.values())
        self.assertEqual(sorted(n for (s,_),n in pairs.items() if s=='random'),[2]*15)
        self.assertEqual(sorted(n for (s,_),n in pairs.items() if s=='difficult'),[1]*10+[2]*5)
        for reviewer_id in REVIEWERS:
            reviewer = self.reviewer(reviewer_id)
            self.assertIn(len(reviewer.samples),(16,17))
            self.assertFalse((reviewer.root/'private').exists())
            self.assertFalse((reviewer.root/'pilot').exists())
            self.assertEqual(sum(coordinator.samples[i]['stratum']=='random' for i in reviewer.samples),10)
            for number, ident in enumerate(reviewer.samples):
                reviewer.runtime_context = {'sam_previews':[{'model_name':'fixture'}]} if number % 2 else {}
                reviewer.commit_manual(ident,[shape(1)],'Persona de prueba')
            delivery = reviewer.export()
            result = coordinator.import_delivery(delivery)
            self.assertEqual(result['imported'],len(reviewer.samples))
            self.assertEqual(coordinator.import_delivery(delivery)['already_present'],len(reviewer.samples))
            with self.assertRaises(PermissionError):
                reviewer.comparison(next(iter(reviewer.samples)))
        report = coordinator.report()
        self.assertEqual(report['progress']['submissions'],100)
        self.assertEqual(report['progress']['complete'],50)
        self.assertEqual(report['pilot_proposals'],50)
        self.assertEqual(sum(group['images'] for group in report['groups']),150)
        case = coordinator.comparison('I01')
        self.assertEqual(set(case['sources']),{'human_a','human_b','pilot'})
        self.assertEqual(case['metrics']['human_a/human_b']['agreeing_resolved_pairs'],1)
        self.assertEqual(case['metrics']['human_a/pilot']['agreeing_resolved_pairs'],0)
        self.assertEqual(sha(coordinator.pilot_path('I01')),sha(self.source/'private/proposals/I01.json'))
        self.assertTrue(coordinator.resolve('I01','Coordinación','Criterio registrado.').is_file())

    def test_zip_guard_retries_atomically_and_rejects_changed_zip(self):
        reviewer = self.reviewer('R01')
        ident, other, *_ = reviewer.samples
        reviewer.save_draft(other,[shape()], 'Borrador privado')
        reviewer.commit_manual(ident,[shape(1)],'Persona de prueba')
        with self.assertRaises(FileExistsError):
            reviewer.commit_manual(ident,[shape(0)],'Persona de prueba')
        delivery = reviewer.export()
        with zipfile.ZipFile(delivery) as archive:
            self.assertEqual(set(archive.namelist()),{'delivery.json',f'submissions/{ident}.json'})
            envelope = json.loads(archive.read('delivery.json'))
            record = json.loads(archive.read(f'submissions/{ident}.json'))
        self.coordinator.import_delivery(delivery)
        with self.assertRaises(PermissionError):
            self.coordinator.comparison(ident)
        with self.assertRaises(PermissionError):
            self.coordinator.resolve(ident, 'Coordinación', 'Insuficiente.')
        bad = self.root/'bad.zip'
        record['reviewer'] = 'Nombre incompatible'
        member = f'submissions/{ident}.json'
        with zipfile.ZipFile(bad,'w') as archive:
            archive.writestr('delivery.json',json.dumps(envelope))
            archive.writestr(member,json.dumps(record))
        with self.assertRaisesRegex(ValueError,'alterada'):
            self.coordinator.import_delivery(bad)
        from hashlib import sha256
        payload = json.dumps(record).encode()
        envelope['submissions'][ident] = sha256(payload).hexdigest()
        with zipfile.ZipFile(bad,'w') as archive:
            archive.writestr('delivery.json',json.dumps(envelope))
            archive.writestr(member,payload)
        with self.assertRaisesRegex(ValueError,'incompatible'):
            self.coordinator.import_delivery(bad)
        self.assertEqual(self.coordinator.progress()['submissions'],1)
        self.assertEqual(self.coordinator.records[('R01',ident)]['reviewer'],'Persona de prueba')

    def test_hidden_ui_delivers_advances_and_reopens_own_record_read_only(self):
        reviewer = self.reviewer('R01')
        first, second, *_ = reviewer.samples
        with hidden_app(reviewer) as app:
            app.reviewer.set('Persona de prueba')
            app.change_image(first)
            app.left.objects = [shape(1)]
            app.notes.insert('1.0','Revisar el borde.')
            app.autosave()
            self.assertEqual(reviewer.draft(first)['notes'],'Revisar el borde.')
            with patch('cross_review_app.messagebox.askyesno',return_value=True):
                app.commit()
            self.assertEqual(app.current,second)
            app.change_image(first)
            self.assertEqual(app.phase,'delivered')
            self.assertFalse(app.left.editable)
            self.assertEqual(app.notes.cget('state'),'disabled')
            self.assertIsNone(app.comparison_sources)
            self.assertEqual(reviewer.manual(first)['notes'],'Revisar el borde.')

    def test_hidden_coordinator_keeps_comparison_locked_then_syncs_sources(self):
        ident = 'I01'
        a,b = self.coordinator.samples[ident]['reviewers']
        first = self.reviewer(a)
        first.commit_manual(ident,[shape(1)],'Persona A')
        self.coordinator.import_delivery(first.export())
        with hidden_app(self.coordinator) as app:
            app.change_image(ident)
            self.assertIsNone(app.comparison_sources)
            self.assertEqual(str(app.left_selector.cget('state')),'disabled')
            second = self.reviewer(b)
            second.commit_manual(ident,[shape(1,2)],'Persona B')
            self.coordinator.import_delivery(second.export())
            app.current = None
            app.change_image(ident)
            self.assertEqual(str(app.right_selector.cget('state')),'readonly')
            app.align_viewports(2,(10,10))
            previous = app.viewport
            app.right_selector.current(2)
            app.difference.set(True)
            app.update_comparison_views()
            self.assertEqual(app.viewport,previous)
            self.assertEqual(app.left.scale,app.right.scale)
            self.assertIn('diferencias de clase',app.comparison_label.cget('text'))
            self.assertFalse(app.right.editable)

    def test_mask_difference_is_zero_for_identical_and_retains_unmatched(self):
        a,b = [shape()],[shape()]
        self.assertEqual(mask_differences(a,b,compare_objects(a,b)),[])
        missing = mask_differences(a,[],compare_objects(a,[]))
        self.assertEqual(mask_iou(missing[0]['segmentation'],a[0]['segmentation']),1)
        self.assertEqual(assistance_status(dict(application_context={'sam_previews':[{}]},objects=[])),'mostrada')

    def test_sam_exposure_survives_discard_and_restart(self):
        reviewer = self.reviewer('R01')
        ident = next(iter(reviewer.samples))
        model = dict(model_name='mobile_sam.pt', model_sha256='a'*64, ultralytics_version='fixture')
        reviewer.record_sam(ident, model)
        restarted = self.reviewer('R01')
        self.assertIsNone(restarted.manual(ident))
        review = restarted.commit_manual(ident, [shape()], 'Persona de prueba')
        self.assertEqual(assistance_status(review), 'mostrada')
        self.assertEqual(review['application_context']['sam_previews'], [model])

    def test_hidden_layout_sizing_for_windows_scale_factors(self):
        reviewer = self.reviewer('R01')
        with hidden_app(reviewer) as app:
            app.change_image(next(iter(reviewer.samples)))
            for dpi in (96,120,144):
                app.window.tk.call('tk','scaling',dpi/72)
                for width,height in ((1366,768),(1920,1080)):
                    app.resize_workspace(SimpleNamespace(widget=app.window,width=width,height=height))
                    app.update_command_help()
                    app.window.update_idletasks()
                    self.assertEqual(app.compact_layout,width==1366)
                    self.assertLessEqual(app.reference_tool.viewport[0],int(app.inspector_shell.cget('width')))
                    controls = [app.commit_button,app.note_button,app.fullscreen_button,*[entry[0] for entry in app.command_buttons]]
                    self.assertTrue(all(c.winfo_reqheight()>=24 and c.winfo_reqwidth()>=24 for c in controls))
                    self.assertTrue(all(c.winfo_reqwidth()<width/2 for c in controls))
                    self.assertTrue(app.window.bind('<F1>'))
                    self.assertTrue(app.window.bind('<F11>'))


if __name__ == '__main__':
    unittest.main()
