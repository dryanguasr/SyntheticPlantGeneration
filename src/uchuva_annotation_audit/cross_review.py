"""Offline assignments, immutable human submissions, and three-source comparison."""
from collections import Counter, defaultdict
from itertools import combinations, pairwise
from pathlib import Path
import copy
import hashlib
import json
import random
import re
import shutil
import tempfile
import zipfile

from .store import AuditStore, SessionLock, atomic_json, compare_objects, now, read, sha, validate_objects

VERSION = 'cross-review/1'
REVIEWERS = tuple(f'R{i:02d}' for i in range(1, 7))
SEED = 20261119


def content_id(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def assign_images(strata, seed=SEED):
    """Each pair gets two random and one difficult image plus a balanced extra."""
    if Counter(strata.values()) != {'random': 30, 'difficult': 20}:
        raise ValueError('Se esperan 30 imágenes aleatorias y 20 difíciles.')
    rng = random.Random(seed)
    pairs = list(combinations(REVIEWERS, 2))
    rng.shuffle(pairs)
    path = rng.sample(REVIEWERS, len(REVIEWERS))
    difficult_pairs = pairs + [tuple(sorted(pair)) for pair in pairwise(path)]
    rng.shuffle(difficult_pairs)
    pair_slots = dict(random=[pair for pair in pairs for _ in range(2)], difficult=difficult_pairs)
    assignments = {}
    for stratum, slots in pair_slots.items():
        images = sorted(ident for ident, kind in strata.items() if kind == stratum)
        rng.shuffle(images)
        assignments.update(zip(images, slots, strict=True))
    queues = {}
    for reviewer in REVIEWERS:
        queue = sorted(ident for ident, pair in assignments.items() if reviewer in pair)
        rng.shuffle(queue)
        queues[reviewer] = queue
    return assignments, queues


def prepare_round(source, destination, *, build_runtime=None, student_manual=None):
    """Build a fresh release beside the sealed pilot and never alter its files."""
    source = AuditStore(source)
    destination = Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(source.root):
        raise ValueError('La ronda requiere una carpeta nueva fuera del piloto.')
    selection = read(source.root / 'private/selection.json')['samples']
    strata = {row['id']: row['stratum'] for row in selection}
    if set(strata) != set(source.samples) or any(not re.fullmatch(r'I[0-9]+', key) for key in strata):
        raise ValueError('El inventario y la selección sellada no coinciden.')
    assignments, queues = assign_images(strata)
    images = {}
    for ident, pair in sorted(assignments.items()):
        sample = source.sample(ident)
        image = source.image_path(ident)
        proposal = source.root / 'private/proposals' / f'{ident}.json'
        for sealed in (image, proposal):
            if sha(sealed) != source.seal['files'].get(sealed.relative_to(source.root).as_posix()):
                raise ValueError(f'Entrada heredada alterada: {ident}')
        validate_objects(read(proposal)['objects'], sample['width'], sample['height'])
        images[ident] = dict(
            id=ident, image=f'images/{ident}.jpg', width=sample['width'], height=sample['height'],
            image_sha256=sha(image), proposal_sha256=sha(proposal),
            stratum=strata[ident], reviewers=list(pair),
        )
    if len({image['image_sha256'] for image in images.values()}) != len(images):
        raise ValueError('El piloto contiene imágenes duplicadas.')
    round_id = content_id(dict(version=VERSION, seed=SEED, images=images, queues=queues))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.revision-cruzada-') as temporary:
        release = Path(temporary) / 'release'
        coordination = release / 'coordinacion'
        for name in ('images', 'pilot'):
            (coordination / name).mkdir(parents=True, exist_ok=True)
        for ident, row in images.items():
            shutil.copyfile(source.image_path(ident), coordination / row['image'])
            shutil.copyfile(source.root / 'private/proposals' / f'{ident}.json', coordination / 'pilot' / f'{ident}.json')
        package_hashes = {}
        for reviewer, queue in queues.items():
            package = release / 'revisores' / reviewer
            (package / 'images').mkdir(parents=True)
            samples = [{key: images[ident][key] for key in ('id', 'image', 'width', 'height')} for ident in queue]
            manifest = dict(version=VERSION, round_id=round_id, reviewer_id=reviewer, sample_ids=queue)
            atomic_json(package / 'assignment.json', manifest)
            package_hashes[reviewer] = sha(package / 'assignment.json')
            atomic_json(package / 'samples.json', dict(samples=samples))
            files = {'samples.json': sha(package / 'samples.json'), 'assignment.json': package_hashes[reviewer]}
            for row in samples:
                shutil.copyfile(coordination / row['image'], package / row['image'])
                files[row['image']] = images[row['id']]['image_sha256']
            atomic_json(package / 'sealed.json', dict(version=VERSION, files=files))
            ReviewerStore(package)
            if student_manual is not None:
                shutil.copyfile(student_manual, package / student_manual.name)
        atomic_json(coordination / 'round.json', dict(
            version=VERSION, round_id=round_id, seed=SEED, images=images, queues=queues,
            package_hashes=package_hashes, source_seal_sha256=sha(source.root / 'sealed.json'),
        ))
        CoordinatorStore(coordination)
        if build_runtime is not None:
            build_runtime(release / 'aplicacion')
        release.rename(destination)
    return destination


class ReviewerStore(AuditStore):
    """One portable lot. No peer submissions, labels, or pilot masks exist here."""

    role = 'reviewer'

    def __init__(self, root):
        assignment_path = Path(root) / 'assignment.json'
        self.assignment = read(assignment_path)
        self.reviewer_id = self.assignment['reviewer_id']
        if self.assignment['version'] != VERSION or self.reviewer_id not in REVIEWERS:
            raise ValueError('Lote de revisión inválido.')
        super().__init__(root, self.reviewer_id)
        self.assignment_hash = sha(assignment_path)
        if self.assignment_hash != self.seal['files'].get('assignment.json') or self.assignment['sample_ids'] != list(self.samples):
            raise ValueError('La asignación y el índice de imágenes no coinciden.')
        expected = {'assignment.json', 'samples.json', *(row['image'] for row in self.samples.values())}
        if set(self.seal['files']) != expected or any(not re.fullmatch(r'I[0-9]+', key) for key in self.samples):
            raise ValueError('Inventario del lote inválido.')

    def commit_manual(self, ident, objects, reviewer, notes='', empty_confirmed=False, elapsed_seconds=0):
        sample = self.sample(ident)
        if not reviewer.strip():
            raise ValueError('Indica el nombre o identificador de quien revisa.')
        clean = validate_objects(objects, sample['width'], sample['height'])
        if not clean and not empty_confirmed:
            raise ValueError('Confirma explícitamente que no hay instancias.')
        record = dict(
            version=VERSION, round_id=self.assignment['round_id'], reviewer_id=self.reviewer_id,
            assignment_sha256=self.assignment_hash, sample_id=ident, reviewer=reviewer.strip()[:200],
            objects=clean, notes=str(notes)[:10000], empty_confirmed=bool(empty_confirmed),
            elapsed_seconds=max(0., float(elapsed_seconds)), submitted_at=now(),
            image_sha256=sha(self.image_path(ident)), application_context=self.review_context(ident, self.runtime_context),
        )
        validate_submission(record, sample)
        if record['image_sha256'] != self.seal['files'][sample['image']]:
            raise ValueError('La imagen cambió desde la preparación del lote.')
        atomic_json(self.manual_path(ident), record, exclusive=True)
        return record

    def review_context(self, ident, context):
        self.sample(ident)
        merged = copy.deepcopy(context)
        path = self.session / 'sam_exposure' / f'{ident}.json'
        if path.is_file():
            for event, models in read(path).items():
                history = merged.setdefault(event, [])
                history.extend(model for model in models if model not in history)
        return merged

    def record_sam(self, ident, metadata, *, accepted=False):
        self.sample(ident)
        if self.manual(ident) is not None:
            raise PermissionError('La entrega ya quedó cerrada.')
        path = self.session / 'sam_exposure' / f'{ident}.json'
        key = 'sam_accepted_models' if accepted else 'sam_previews'
        model = {field: metadata[field] for field in ('model_name', 'model_sha256', 'ultralytics_version')}
        current = self.runtime_context.setdefault(key, [])
        if model not in current:
            current.append(model)
        recorded = read(path) if path.is_file() else {}
        history = recorded.setdefault(key, [])
        if model not in history:
            history.append(model)
            atomic_json(path, recorded)

    def comparison(self, ident):
        raise PermissionError('La comparación está reservada a coordinación.')

    def save_final(self, *args, **kwargs):
        raise PermissionError('La resolución está reservada a coordinación.')

    def progress(self):
        return dict(total=len(self.samples), manual=sum(self.manual_path(key).is_file() for key in self.samples))

    def export(self):
        submitted = [ident for ident in self.samples if self.manual_path(ident).is_file()]
        if not submitted:
            raise ValueError('Entrega al menos una imagen antes de exportar.')
        folder = self.session / 'exports'
        folder.mkdir(parents=True, exist_ok=True)
        envelope = dict(
            version=VERSION, round_id=self.assignment['round_id'], reviewer_id=self.reviewer_id,
            assignment_sha256=self.assignment_hash,
            submissions={ident: sha(self.manual_path(ident)) for ident in submitted},
        )
        output = folder / f'{self.reviewer_id}_{content_id(envelope)[:16]}.zip'
        with tempfile.NamedTemporaryFile(dir=folder, suffix='.zip', delete=False) as stream:
            staging = Path(stream.name)
        try:
            with zipfile.ZipFile(staging, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('delivery.json', json.dumps(envelope, ensure_ascii=False))
                for ident in submitted:
                    archive.write(self.manual_path(ident), f'submissions/{ident}.json')
            staging.replace(output)
        finally:
            staging.unlink(missing_ok=True)
        return output


def validate_submission(record, sample):
    value = record.get('elapsed_seconds')
    if not isinstance(value, (int, float)) or not 0 <= value < float('inf'):
        raise ValueError('Tiempo de revisión inválido.')
    if not isinstance(record.get('reviewer'), str) or not record['reviewer'].strip():
        raise ValueError('La entrega carece de identificación de la persona revisora.')
    if not isinstance(record.get('application_context'), dict):
        raise ValueError('Falta el contexto de anotación.')
    clean = validate_objects(record.get('objects'), sample['width'], sample['height'])
    if clean != record['objects']:
        raise ValueError('La entrega contiene máscaras no canónicas.')
    if record.get('empty_confirmed') is not (not clean):
        raise ValueError('La opción «Sin instancias» debe coincidir con el contenido de la entrega.')


def assistance_status(record):
    context = record['application_context']
    if context.get('segmentation_assistance_used') or context.get('sam_accepted_models') or any(obj.get('assistance') for obj in record['objects']):
        return 'aceptada'
    if context.get('sam_previews'):
        return 'mostrada'
    return 'sin_sam'


class CoordinatorStore:
    role = 'coordinator'

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.session = self.root / 'local'
        self.round = read(self.root / 'round.json')
        self.samples = self.round['images']
        self.public = {}
        self.runtime_context = {}
        self.records = {}
        self.validate_round()
        self.reload()

    def validate_round(self):
        round_data = self.round
        assignments, queues = assign_images({ident: row['stratum'] for ident, row in self.samples.items()}, round_data['seed'])
        expected_id = content_id(dict(version=VERSION, seed=round_data['seed'], images=self.samples, queues=queues))
        if round_data['version'] != VERSION or round_data['round_id'] != expected_id or round_data['queues'] != queues:
            raise ValueError('La asignación congelada de coordinación no coincide.')
        for ident, row in self.samples.items():
            if not re.fullmatch(r'I[0-9]+', ident) or row['image'] != f'images/{ident}.jpg':
                raise ValueError('Identificador o ruta de imagen inválidos.')
            if row['reviewers'] != list(assignments[ident]):
                raise ValueError(f'Pareja distinta de la asignada: {ident}')
            if sha(self.image_path(ident)) != row['image_sha256'] or sha(self.pilot_path(ident)) != row['proposal_sha256']:
                raise ValueError(f'Imagen o propuesta congelada alterada: {ident}')

    def image_path(self, ident):
        path = (self.root / self.samples[ident]['image']).resolve()
        if not path.is_relative_to(self.root / 'images'):
            raise ValueError('Ruta de imagen fuera de coordinación.')
        return path

    def pilot_path(self, ident):
        self.samples[ident]
        return self.root / 'pilot' / f'{ident}.json'

    def validate_record(self, record, reviewer, ident):
        sample = self.samples[ident]
        header = dict(version=VERSION, round_id=self.round['round_id'], reviewer_id=reviewer,
                      sample_id=ident, assignment_sha256=self.round['package_hashes'][reviewer],
                      image_sha256=sample['image_sha256'])
        if reviewer not in sample['reviewers'] or any(record.get(key) != value for key, value in header.items()):
            raise ValueError(f'La entrega no pertenece a la asignación: {reviewer} / {ident}')
        validate_submission(record, sample)

    def reload(self):
        records = {}
        for path in sorted((self.root / 'receipts').glob('*.json')):
            entries = read(path)
            if path.stem != content_id(entries):
                raise ValueError(f'Acta de recepción alterada: {path.name}')
            for record in entries:
                key = record['reviewer_id'], record['sample_id']
                self.validate_record(record, *key)
                if key in records:
                    raise ValueError(f'La entrega ya existe: {key}')
                records[key] = record
        self.records = records

    def import_delivery(self, path):
        """Validate the entire ZIP before reserving any submission."""
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 18 or any(entry.file_size > 64 * 1024**2 for entry in entries):
                raise ValueError('El tamaño de la entrega supera el límite del lote.')
            delivery = json.loads(archive.read('delivery.json'))
            reviewer = delivery.get('reviewer_id')
            expected = dict(version=VERSION, round_id=self.round['round_id'],
                            assignment_sha256=self.round['package_hashes'].get(reviewer))
            if reviewer not in REVIEWERS or any(delivery.get(key) != value for key, value in expected.items()):
                raise ValueError('Entrega de otro lote o ronda.')
            submissions = delivery.get('submissions')
            if not isinstance(submissions, dict) or not submissions or not submissions.keys() <= set(self.round['queues'][reviewer]):
                raise ValueError('El ZIP lista imágenes que no pertenecen al revisor.')
            names = ['delivery.json', *(f'submissions/{ident}.json' for ident in submissions)]
            if Counter(archive.namelist()) != Counter(names):
                raise ValueError('El ZIP contiene entradas adicionales o duplicadas.')
            received = {}
            for ident in sorted(submissions):
                payload = archive.read(f'submissions/{ident}.json')
                if hashlib.sha256(payload).hexdigest() != submissions[ident]:
                    raise ValueError(f'Entrega alterada: {ident}')
                record = json.loads(payload)
                self.validate_record(record, reviewer, ident)
                received[(reviewer, ident)] = record

        lock = SessionLock(self.root / 'receipts.lock')
        try:
            self.reload()
            for key, record in received.items():
                if key in self.records and content_id(record) != content_id(self.records[key]):
                    raise ValueError(f'Entrega incompatible para {key[0]} / {key[1]}. Se conserva la recibida primero.')
            new_entries = [record for key, record in received.items() if key not in self.records]
            if new_entries:
                atomic_json(self.root / 'receipts' / f'{content_id(new_entries)}.json', new_entries, exclusive=True)
                self.records.update({key: record for key, record in received.items() if key not in self.records})
            return dict(imported=len(new_entries), already_present=len(received)-len(new_entries))
        finally:
            lock.close()

    def received_count(self, ident):
        return sum((reviewer, ident) in self.records for reviewer in self.samples[ident]['reviewers'])

    def comparison(self, ident):
        row = self.samples[ident]
        if self.received_count(ident) != 2:
            raise PermissionError('La comparación requiere las dos entregas humanas.')
        proposal = self.pilot_path(ident)
        if sha(proposal) != row['proposal_sha256']:
            raise ValueError('La propuesta congelada cambió.')
        first, second = (self.records[(reviewer, ident)] for reviewer in row['reviewers'])
        sources = dict(human_a=first, human_b=second, pilot=read(proposal))
        metrics = {f'{a}/{b}': compare_objects(sources[a]['objects'], sources[b]['objects'])
                   for a,b in (('human_a','human_b'),('human_a','pilot'),('human_b','pilot'))}
        return dict(sample_id=ident, stratum=row['stratum'], sources=sources, metrics=metrics)

    def progress(self):
        return dict(total=len(self.samples), submissions=len(self.records),
                    complete=sum(self.received_count(ident) == 2 for ident in self.samples),
                    by_reviewer={reviewer: sum(key[0] == reviewer for key in self.records) for reviewer in REVIEWERS})

    def resolve(self, ident, reviewer, notes):
        if self.received_count(ident) != 2:
            raise PermissionError('La resolución requiere las dos entregas humanas.')
        if not reviewer.strip() or not notes.strip():
            raise ValueError('Indica quién resuelve y el criterio aplicado.')
        path = self.root / 'resolutions' / ident / f'{now().replace(":", "")}.json'
        atomic_json(path, dict(sample_id=ident, reviewer=reviewer.strip(), notes=notes.strip(),
                              recorded_at=now()), exclusive=True)
        return path

    def latest_resolution(self, ident):
        self.samples[ident]
        entries = sorted((self.root / 'resolutions' / ident).glob('*.json'))
        return read(entries[-1]) if entries else None

    def report(self):
        grouped = defaultdict(Counter)
        cases = []
        for ident in self.samples:
            if self.received_count(ident) != 2:
                continue
            case = self.comparison(ident)
            assisted = {source: assistance_status(case['sources'][source]) for source in ('human_a','human_b')}
            cases.append(dict(sample_id=ident, stratum=case['stratum'], assistance=assisted,
                              pairs=case['metrics'], resolution=self.latest_resolution(ident)))
            for pair, metrics in case['metrics'].items():
                a, b = pair.split('/')
                counts = grouped[(case['stratum'], pair, assisted[a], assisted.get(b, 'piloto'))]
                counts.update(images=1, matched=len(metrics['matches']),
                              resolved_class_pairs=metrics['resolved_pairs'],
                              matching_class=metrics['agreeing_resolved_pairs'],
                              unmatched_a=len(metrics['unmatched_manual']),
                              unmatched_b=len(metrics['unmatched_proposal']))
        groups = [
            dict(stratum=stratum, pair=pair, sam_a=sam_a, sam_b=sam_b, **counts,
                 class_agreement=counts['matching_class']/counts['resolved_class_pairs'] if counts['resolved_class_pairs'] else None)
            for (stratum, pair, sam_a, sam_b), counts in sorted(grouped.items())
        ]
        return dict(version=VERSION, round_id=self.round['round_id'], progress=self.progress(),
                    pilot_proposals=len(self.samples), groups=groups, cases=cases,
                    interpretation='Concordancia descriptiva de máscaras de entrenamiento, con propuestas GrabCut aproximadas. No estima generalización.')
