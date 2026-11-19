"""Persist blind manual annotations before exposing any proposal or original GT.

Uses sidecars only. The initial manual record is immutable; adjudications are
separate revisions and never become training labels automatically.
"""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import math
import os
import tempfile
import uuid
import zipfile
from .masks import checked_runs,mask_bbox,intervals,interval_iou,polygons_mask,encode_mask,decode_mask
from .assistance import validate_assistance,validate_boundary_handles

CLASSES = {0: 'Pintona', 1: 'Madura', 2: 'Sobremadura', None: 'No resoluble'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def window_process_identity():
    identity = {'pid': os.getpid()}
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        creation, exit_time, system, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *map(ctypes.byref, (creation, exit_time, system, user))):
            raise ctypes.WinError(ctypes.get_last_error())
        identity['creation_tick'] = str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
    return identity


def atomic_json(path, value, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    fd, temporary = tempfile.mkstemp(prefix='.audit-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # Windows rename refuses an existing destination atomically.
            # POSIX link provides the same no-overwrite publication contract.
            if os.name=='nt':os.rename(temporary,path)
            else:os.link(temporary,path)
        else:
            os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_objects(objects, width, height):
    if not isinstance(objects, list) or len(objects) > 1000:
        raise ValueError('Lista de cajas inválida')
    result, ids = [], set()
    for obj in objects:
        if not isinstance(obj, dict):
            raise ValueError('Objeto inválido')
        cid = obj.get('class_id')
        if cid is not None and (type(cid) is not int or cid not in (0, 1, 2)):
            raise ValueError('Clase inválida')
        segmentation=obj.get('segmentation')
        if segmentation is None and obj.get('polygons'):
            segmentation=encode_mask(polygons_mask(obj['polygons'],width,height))
        checked_runs(segmentation,width,height)
        # Ignore caller-supplied boxes; derive the exclusive-edge box from pixels.
        box=mask_bbox(segmentation)
        ident = obj.get('id') or uuid.uuid4().hex
        if not isinstance(ident, str) or ident in ids or len(ident) > 100:
            raise ValueError('Identificador de objeto inválido')
        note = str(obj.get('note', ''))[:2000]
        ids.add(ident)
        result.append(dict(id=ident, class_id=cid, segmentation=copy.deepcopy(segmentation),
                           bbox=box,bbox_source='native_mask_pixels',note=note))
        if obj.get('assistance') is not None:result[-1]['assistance']=validate_assistance(obj['assistance'],(width,height))
        if obj.get('boundary_nodes') is not None:
            result[-1]['boundary_nodes']=validate_boundary_handles(obj['boundary_nodes'],decode_mask(segmentation))
    return result


def iou(a, b):
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / area if area > 0 else 0


def compare_objects(manual, proposed, cutoff=.5):
    # Greedy one-to-one MASK matching, independent of class/confidence.
    # An explicit descriptive review convention, not a detector AP metric.
    cached_a=[intervals(a['segmentation']) for a in manual]
    cached_b=[intervals(b['segmentation']) for b in proposed]
    pairs = sorted(((interval_iou(cached_a[i],cached_b[j]) if iou(a['bbox'],b['bbox']) else 0, i, j) for i, a in enumerate(manual)
                    for j, b in enumerate(proposed)), reverse=True)
    used_a, used_b, matches = set(), set(), []
    for overlap, i, j in pairs:
        if overlap < cutoff:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        matches.append(dict(manual_index=i, proposal_index=j, iou=overlap,
                            manual_class=manual[i]['class_id'], proposal_class=proposed[j]['class_id'],
                            class_agrees=manual[i]['class_id'] == proposed[j]['class_id']))
    resolved = [m for m in matches if m['manual_class'] is not None and m['proposal_class'] is not None]
    return dict(matches=matches, unmatched_manual=[i for i in range(len(manual)) if i not in used_a],
                unmatched_proposal=[j for j in range(len(proposed)) if j not in used_b],
                resolved_pairs=len(resolved), agreeing_resolved_pairs=sum(m['class_agrees'] for m in resolved),
                matching_policy='greedy_native_mask_one_to_one_iou_0.5',
                interpretation='Agreement with first manual; not validated accuracy or AP')


class AuditStore:
    def __init__(self, root, session='principal', verify=True):
        self.root = Path(root).resolve()
        if not session or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in session):
            raise ValueError('Nombre de sesión inválido')
        self.session = self.root / 'audits' / session
        self.public = read(self.root / 'samples.json')
        self.samples = {s['id']: s for s in self.public['samples']}
        if len(self.samples) != len(self.public['samples']):
            raise ValueError('Identificadores duplicados')
        self.seal = read(self.root / 'sealed.json')
        self.runtime_context = {}
        if verify:
            for relative, expected in self.seal['files'].items():
                path = (self.root / relative).resolve()
                if not path.is_relative_to(self.root) or sha(path) != expected:
                    raise ValueError(f'Entrada congelada alterada: {relative}')
            for path,expected in self.seal.get('application_files',{}).items():
                if sha(path)!=expected:raise ValueError(f'La aplicación cambió desde la preparación: {path}')

    def sample(self, ident):
        if ident not in self.samples:
            raise KeyError('Imagen desconocida')
        return copy.deepcopy(self.samples[ident])

    def image_path(self, ident):
        path = (self.root / self.sample(ident)['image']).resolve()
        if not path.is_relative_to(self.root / 'images'):
            raise ValueError('Ruta de imagen fuera del piloto')
        return path

    def manual_path(self, ident):
        self.sample(ident)
        return self.session / 'manual' / f'{ident}.json'

    def manual(self, ident):
        path = self.manual_path(ident)
        return read(path) if path.exists() else None

    def draft(self, ident):
        self.sample(ident)
        path = self.session / 'drafts' / f'{ident}.json'
        return read(path) if path.exists() else dict(objects=[], notes='', elapsed_seconds=0)

    def save_draft(self, ident, objects, notes='', elapsed_seconds=0):
        if self.manual(ident):
            raise PermissionError('La primera versión manual ya está congelada')
        sample = self.sample(ident)
        payload = dict(sample_id=ident, objects=validate_objects(objects, sample['width'], sample['height']),
                       notes=str(notes)[:10000], elapsed_seconds=max(0, float(elapsed_seconds)), updated_at=now(),
                       application_context=copy.deepcopy(self.runtime_context))
        atomic_json(self.session / 'drafts' / f'{ident}.json', payload)
        return payload

    def commit_manual(self, ident, objects, reviewer, notes='', empty_confirmed=False, elapsed_seconds=0):
        sample = self.sample(ident)
        if not reviewer.strip():
            raise ValueError('Indica el nombre o identificador de quien revisa')
        clean = validate_objects(objects, sample['width'], sample['height'])
        if not clean and not empty_confirmed:
            raise ValueError('Confirma explícitamente que no hay instancias para anotar')
        payload = dict(version='blind-manual/1', sample_id=ident, reviewer=reviewer.strip()[:200],
                       objects=clean, notes=str(notes)[:10000], empty_confirmed=bool(empty_confirmed),
                       submitted_at=now(), elapsed_seconds=max(0, float(elapsed_seconds)),
                       image_sha256=sha(self.image_path(ident)), proposal_seen_before_commit=False,
                       immutable_first_manual=True, timing='Window elapsed including idle; not pure active labor')
        payload['application_context']=copy.deepcopy(self.runtime_context)
        payload['annotation_method']='human_prompted_model_assisted' if any(o.get('assistance') for o in clean) or self.runtime_context.get('segmentation_assistance_used') else 'manual_without_segmentation_model'
        atomic_json(self.manual_path(ident), payload, exclusive=True)
        return payload

    def comparison(self, ident):
        manual = self.manual(ident)
        if manual is None:
            raise PermissionError('Guarda primero la anotación manual ciega')
        proposal = read(self.root / 'private' / 'proposals' / f'{ident}.json')
        original = read(self.root / 'private' / 'originals' / f'{ident}.json')
        return dict(manual=manual, proposal=proposal, original=original,
                    comparison=compare_objects(manual['objects'], proposal['objects']),
                    original_comparison=compare_objects(manual['objects'],original['objects']))

    def latest_final(self, ident):
        self.sample(ident)
        paths = sorted((self.session / 'adjudications' / ident).glob('revision_*.json'))
        return read(paths[-1]) if paths else None

    def save_final(self, ident, objects, reviewer, notes=''):
        baseline = self.manual(ident)
        if baseline is None:
            raise PermissionError('No se puede adjudicar antes de guardar el manual ciego')
        if not reviewer.strip():
            raise ValueError('Indica quién adjudica')
        sample = self.sample(ident)
        clean = validate_objects(objects, sample['width'], sample['height'])
        folder = self.session / 'adjudications' / ident
        revision = len(list(folder.glob('revision_*.json'))) + 1
        payload = dict(sample_id=ident, reviewer=reviewer.strip(), objects=clean, notes=str(notes)[:10000],
                       saved_at=now(), revision=revision, first_manual_sha256=sha(self.manual_path(ident)),
                       original_labels_changed=False, automatic_training_export=False)
        payload['application_context']=copy.deepcopy(self.runtime_context)
        atomic_json(folder / f'revision_{revision:04}.json', payload, exclusive=True)
        return payload

    def progress(self):
        return dict(total=len(self.samples), manual=sum(self.manual_path(s).exists() for s in self.samples),
                    adjudicated=sum(self.latest_final(s) is not None for s in self.samples))

    def export(self):
        completed = []
        selection = read(self.root / 'private' / 'selection.json')
        strata = {r['id']: r['stratum'] for r in selection['samples']}
        for ident in self.samples:
            if self.manual(ident) is not None:
                completed.append(dict(sample_id=ident, stratum=strata[ident], **self.comparison(ident),
                                      final=self.latest_final(ident)))
        groups = {}
        for name in ('random', 'difficult'):
            rows = [r for r in completed if r['stratum'] == name]
            matches = sum(r['comparison']['resolved_pairs'] for r in rows)
            agrees = sum(r['comparison']['agreeing_resolved_pairs'] for r in rows)
            by_class={}
            for cid,label in ((0,'Pintona'),(1,'Madura'),(2,'Sobremadura')):
                mm=[m for r in rows for m in r['comparison']['matches']]
                by_class[label]=dict(manual_instances=sum(o['class_id']==cid for r in rows for o in r['manual']['objects']),
                    proposed_instances=sum(o['class_id']==cid for r in rows for o in r['proposal']['objects']),
                    matched_same_class=sum(m['manual_class']==cid and m['proposal_class']==cid for m in mm),
                    manual_class_matched_to_other=sum(m['manual_class']==cid and m['proposal_class'] not in (cid,None) for m in mm))
            groups[name] = dict(images=len(rows), resolved_pairs=matches, agreeing_pairs=agrees,by_class=by_class,
                                class_agreement=agrees / matches if matches else None,
                                unmatched_manual=sum(len(r['comparison']['unmatched_manual']) for r in rows),
                                unmatched_proposal=sum(len(r['comparison']['unmatched_proposal']) for r in rows))
        report = dict(progress=self.progress(), cases=completed, by_stratum=groups,
                      original_labels_changed=False, human_audit_complete=len(completed) == len(self.samples),
                      annotation_contract='native_binary_instance_masks; bounding boxes derived from mask',
                      limitation='Training images seen by detector; proposals use approximate RGB GrabCut masks, not a validated segmentation model. Manual is not independent double-expert truth. No generalization accuracy claim.')
        folder = self.session / 'exports' / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
        folder.mkdir(parents=True)
        atomic_json(folder / 'audit.json', report)
        with zipfile.ZipFile(folder / 'auditoria.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.write(folder / 'audit.json', 'audit.json')
            for r in completed:
                ident = r['sample_id']
                archive.write(self.manual_path(ident), f'manual/{ident}.json')
                for p in (self.session / 'adjudications' / ident).glob('revision_*.json'):
                    archive.write(p, f'adjudications/{ident}/{p.name}')
        return folder / 'auditoria.zip'


class SessionLock:
    """OS lock prevents concurrent windows from changing one review session."""
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open('a+b')
        try:
            if os.fstat(self.stream.fileno()).st_size==0:
                self.stream.write(b'0');self.stream.flush()
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError('Ya hay una ventana abierta para esta sesión')

    def close(self):
        if not self.stream.closed:
            self.stream.close()
