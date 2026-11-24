"""Apply an authorized audit UI revision without changing pilot data."""
from pathlib import Path
import sys,copy,shutil,json,hashlib
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
from uchuva_annotation_audit.store import read,sha,atomic_json,AuditStore,now
from uchuva_lsystem.dataset_completion import owner_alive
from uchuva_annotation_audit.assistance import default_model


def refresh(root):
    root=Path(root).resolve();old=read(root/'sealed.json')
    for file in (root/'audits').glob('*/window_identity.json'):
        if owner_alive(read(file)):raise RuntimeError('Cierra la ventana de auditoría, guardando el borrador, antes de actualizar su revisión')
    for relative,expected in old['files'].items():
        if sha(root/relative)!=expected:raise ValueError(f'Entrada de datos alterada: {relative}')
    human_files={str(p):sha(p) for p in (root/'audits').rglob('*.json')}
    desired={str(REPO/path):sha(REPO/path) for path in (
        'scripts/annotation_audit_app.py','src/uchuva_annotation_audit/store.py',
        'src/uchuva_annotation_audit/masks.py','src/uchuva_annotation_audit/__init__.py',
        'src/uchuva_annotation_audit/reference_loupe.py','src/uchuva_annotation_audit/assistance.py',
        'src/uchuva_annotation_audit/ui_theme.py',
        'docs/references/annotation_assistance_model.json','docs/references/annotation_norma_palette.json',
        'Nuevo Dataset/Norma.webp')}
    model,expected=default_model()
    if sha(model)!=expected:raise ValueError('Los pesos SAM locales no coinciden con su procedencia')
    desired[str(model)]=expected
    if old.get('application_files')==desired:
        print('UI revision already verified',AuditStore(root).progress());return
    revision=root/'revisions/fullscreen_layout_20261119';revision.mkdir(parents=True,exist_ok=True)
    backup=revision/'previous_sealed.json'
    if backup.exists():raise FileExistsError('La revisión ya existe; no se sobrescribe su evidencia')
    shutil.copy2(root/'sealed.json',backup)
    updated=copy.deepcopy(old);updated['application_files']=desired
    updated['application_revision']='fullscreen_layout_20261119'
    updated['reference_aid_status']='user-authorized qualitative illustration and sampled RGB; no automatic class assignment'
    assert updated['files']==old['files']
    atomic_json(root/'sealed.json',updated)
    store=AuditStore(root)
    for path,expected in human_files.items():
        if sha(path)!=expected:raise ValueError('Una anotación cambió durante la actualización; revisar concurrencia')
    atomic_json(revision/'manifest.json',dict(revised_at=now(),previous_seal_sha256=sha(backup),
        current_seal_sha256=sha(root/'sealed.json'),application_files=desired,
        data_file_hashes_unchanged=True,human_files_preserved=human_files,
        progress=store.progress(),reference_source='Nuevo Dataset/Norma.webp',
        implementation='Native maximized startup and F11 fullscreen, wrapping toolbars, compact layout for shorter screens, scalable loupe and calyx swatches',
        original_labels_changed=False,proposals_changed=False,new_training=False,new_renders=False))
    print('UI updated. Data and human records preserved.',store.progress())


if __name__=='__main__':refresh(REPO/'outputs/blind_segmentation_50_20261113')
