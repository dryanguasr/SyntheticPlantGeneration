"""Prepare six offline review lots, private coordination, and the shared app."""
from pathlib import Path
import argparse
import shutil
import sys
import tempfile
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))

from uchuva_annotation_audit.assistance import default_model
from uchuva_annotation_audit.cross_review import CoordinatorStore, REVIEWERS, ReviewerStore, prepare_round
from uchuva_annotation_audit.reference_loupe import REFERENCE, load_palette
from uchuva_annotation_audit.store import atomic_json, sha

STUDENT_MANUAL = REPO / 'docs/guides/manual_estudiantes_revision_cruzada.pdf'


def build_runtime(destination):
    model, expected = default_model()
    if sha(model) != expected:
        raise ValueError('Los pesos locales de MobileSAM no coinciden con la referencia.')
    load_palette()
    files = [
        REPO / name for name in (
            'LICENSE', 'scripts/annotation_audit_app.py', 'scripts/cross_review_app.py',
            'scripts/abrir_revision_cruzada.cmd', 'docs/guides/auditoria_ciega_segmentacion.md',
            'docs/references/annotation_norma_palette.json', 'docs/references/annotation_assistance_model.json',
        )
    ]
    files.extend((REPO / 'src/uchuva_annotation_audit').glob('*.py'))
    files.extend((STUDENT_MANUAL, REFERENCE, model))
    checksums = {}
    for path in sorted(files):
        relative = path.relative_to(REPO)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        checksums[relative.as_posix()] = sha(target)
    atomic_json(destination / 'runtime_manifest.json', dict(files=checksums))


def build_round_runtime(destination):
    build_runtime(destination)
    launcher = destination.parent / 'coordinacion' / 'abrir_coordinacion.cmd'
    launcher.write_bytes(
        b'@echo off\r\n'
        b'call "%~dp0..\\aplicacion\\scripts\\abrir_revision_cruzada.cmd" --coordinator "%~dp0."\r\n'
    )


def distribute_round(round_root, destination):
    """Archive the verified app and each lot, independent of its working sidecars."""
    destination = destination.resolve()
    if destination.exists():
        raise ValueError('La distribución requiere una carpeta nueva.')
    coordinator = CoordinatorStore(round_root / 'coordinacion')
    manual_hash = sha(STUDENT_MANUAL)
    lots = []
    for code in REVIEWERS:
        lot = ReviewerStore(round_root / 'revisores' / code)
        if lot.assignment['round_id'] != coordinator.round['round_id'] or (
            lot.assignment_hash != coordinator.round['package_hashes'][code]
        ):
            raise ValueError(f'El lote {code} no corresponde a esta ronda.')
        for ident, sample in lot.samples.items():
            reference = coordinator.samples[ident]
            if any(sample[key] != reference[key] for key in ('image', 'width', 'height')) or (
                lot.seal['files'][sample['image']] != reference['image_sha256']
            ):
                raise ValueError(f'La imagen {ident} del lote {code} difiere del inventario de la ronda.')
        manual = lot.root / STUDENT_MANUAL.name
        if manual.exists() and sha(manual) != manual_hash:
            raise ValueError(f'El lote {code} ya contiene otro manual. Conserva esa copia antes de actualizarlo.')
        lots.append((code, lot, manual))

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.distribucion-') as temporary:
        staging = Path(temporary)
        archives = staging / 'archivos'
        archives.mkdir()
        runtime = staging / 'aplicacion'
        build_runtime(runtime)
        shutil.make_archive(str(archives / 'aplicacion'), 'zip', staging, runtime.name)
        for code, lot, manual in lots:
            with zipfile.ZipFile(archives / f'{code}.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                for name in sorted({'sealed.json', *lot.seal['files']}):
                    archive.write(lot.root / name, f'{code}/{name}')
                archive.write(STUDENT_MANUAL, f'{code}/{manual.name}')
        for _, _, manual in lots:
            if not manual.exists():
                with STUDENT_MANUAL.open('rb') as source, manual.open('xb') as target:
                    shutil.copyfileobj(source, target)
        archives.rename(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('destination', type=Path)
    prepare.add_argument('--source', type=Path, default=REPO / 'outputs/blind_segmentation_50_20261113')
    distribute = commands.add_parser('distribute')
    distribute.add_argument('round_root', type=Path)
    distribute.add_argument('destination', type=Path)
    merge = commands.add_parser('import')
    merge.add_argument('coordination', type=Path)
    merge.add_argument('deliveries', type=Path, nargs='+')
    report = commands.add_parser('report')
    report.add_argument('coordination', type=Path)
    report.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        print(prepare_round(args.source, args.destination, build_runtime=build_round_runtime, student_manual=STUDENT_MANUAL))
        return
    if args.command == 'distribute':
        print(distribute_round(args.round_root, args.destination))
        return
    store = CoordinatorStore(args.coordination)
    if args.command == 'import':
        for path in args.deliveries:
            print(path.name, store.import_delivery(path))
    else:
        atomic_json(args.destination, store.report(), exclusive=True)
        print(args.destination.resolve())


if __name__ == '__main__':
    main()
