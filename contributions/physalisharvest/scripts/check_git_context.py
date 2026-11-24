"""Inspect Git context without fetching, switching branches, or modifying refs."""
import argparse
import os
import re
import sys
import tempfile
from pathlib import Path
from check_common import Report, git

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = 'github.com/amayadiegoalejandro05/PhysalisHarvest'
PERMANENT_BRANCHES = {
    'feat/vision': 'vision',
    'feat/arm': 'brazo',
    'feat/locomotion': 'locomocion',
    'feat/2WD': 'locomocion',
}
SUBSYSTEMS = set(PERMANENT_BRANCHES.values())
TEMPORARY_BRANCH = re.compile(r'(feature|fix|experiment|test|chore)/[A-Za-z0-9._/-]+')
AREA_BRANCHES = {
    'vision': 'feat/vision',
    'arm': 'feat/arm',
    'brazo': 'feat/arm',
    'locomotion': 'feat/locomotion',
    'locomocion': 'feat/locomotion',
    '2WD': 'feat/2WD',
}
ORIGIN_REF = 'refs/remotes/origin/'
OWNED = {'robot_percepcion_decision': 'vision', 'robot_brazo': 'brazo', 'robot_locomocion': 'locomocion'}


def classify_path(path):
    parts = path.split('/')
    # Shared integration paths are defined by location, not assumptions about semantics.
    shared_prefixes = ('.github/', 'docs/interfaces/', 'docs/integracion/', 'ros2_ws/src/robot_interfaces/',
                       'ros2_ws/src/robot_bringup/', 'ros2_ws/src/robot_description/',
                       'ros2_ws/src/robot_integration/', 'config/tf/', 'config/frames/', 'scripts/')
    shared_files = {'AGENTS.md', 'CONTRIBUTING.md', 'requirements.txt', 'requirements-dev.txt',
                    'pyproject.toml', 'ros2_ws/rosdep.yaml', 'ros2_ws/colcon.meta'}
    if path in shared_files or any(path.startswith(prefix) for prefix in shared_prefixes):
        return 'shared'
    if len(parts) >= 4 and parts[:2] == ['ros2_ws', 'src'] and parts[2] in OWNED:
        return OWNED[parts[2]]
    if len(parts) >= 3 and parts[0] == 'hardware' and parts[1] in ('brazo', 'locomocion'):
        return parts[1]
    return 'other'



def check(root, target=None, subsystem=None, environ=None):
    root = Path(root).resolve()
    env = os.environ if environ is None else environ
    report = Report(root)
    def run(*args): return git(root, *args)
    bases = {}
    def merge_base(ref):
        if ref not in bases:
            result = run('merge-base', 'HEAD', ref)
            bases[ref] = result.stdout.strip() if result.returncode == 0 else None
        return bases[ref]
    top = run('rev-parse', '--show-toplevel')
    if top.returncode:
        report.add('GIT-REPO', 'FAIL', 'No se encontró un repositorio Git.', 'Ejecutar en el repositorio correcto.')
        return report
    report.add('GIT-REPO', 'PASS', 'Repositorio: ' + top.stdout.strip(), 'Confirmar el directorio de trabajo.')
    fetch_urls = run('remote', 'get-url', '--all', 'origin')
    push_urls = run('remote', 'get-url', '--push', '--all', 'origin')
    # GitHub does not distinguish case in owner or repository names.
    accepted_urls = {
        f'{base}{suffix}'.lower()
        for base in (f'https://{EXPECTED}', f'git@{EXPECTED.replace("/", ":", 1)}', f'ssh://git@{EXPECTED}')
        for suffix in ('', '.git')
    }
    valid_origin = all(
        result.returncode == 0 and result.stdout.splitlines()
        and {url.lower() for url in result.stdout.splitlines()} <= accepted_urls
        for result in (fetch_urls, push_urls)
    )
    report.add('GIT-ORIGIN', 'PASS' if valid_origin else 'FAIL',
               f'origin de lectura y escritura verificado: {EXPECTED}.' if valid_origin
               else f'Alguna URL de lectura o escritura de origin falta o no apunta a {EXPECTED}.',
               'Confirmar el destino antes de operar.' if valid_origin else 'Revisar con git remote -v.')
    if not valid_origin:
        return report
    head = run('rev-parse', '--verify', 'HEAD')
    sha = head.stdout.strip()
    valid_head = head.returncode == 0 and re.fullmatch(r'[0-9a-f]{40,64}', sha)
    report.add('GIT-HEAD', 'PASS' if valid_head else 'FAIL', 'HEAD: ' + (sha or 'no disponible'), 'Registrar este SHA en la evidencia.' if valid_head else 'Crear o recuperar un commit válido.')
    branch_result = run('symbolic-ref', '--quiet', '--short', 'HEAD')
    branch = branch_result.stdout.strip()
    is_pr = env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_EVENT_NAME') in ('pull_request', 'pull_request_target')
    source = env.get('GITHUB_HEAD_REF', '') if is_pr else branch
    permanent = source in PERMANENT_BRANCHES
    temporary = TEMPORARY_BRANCH.fullmatch(source) is not None
    hints = {AREA_BRANCHES[token] for token in re.split(r'[/_.-]', source.split('/', 1)[-1])
             if token in AREA_BRANCHES} if temporary else set()
    if branch:
        report.add('GIT-BRANCH', 'PASS', 'Rama activa: ' + branch, 'Confirmar la rama antes de modificar.')
    elif is_pr and source:
        report.add('GIT-BRANCH', 'SKIP', 'HEAD separado en validación de PR; rama declarada: ' + source, 'No tratar el commit temporal como HEAD de la rama fuente.')
    else:
        report.add('GIT-BRANCH', 'SKIP', 'HEAD separado; no hay rama activa.', 'Especificar el contexto antes de integrar.')
    upstream = run('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}') if branch else None
    tracking = upstream.stdout.strip() if upstream and upstream.returncode == 0 else ''
    report.add('GIT-UPSTREAM', 'PASS' if tracking else 'SKIP', 'Seguimiento: ' + tracking if tracking else 'No hay seguimiento configurado o HEAD está separado.', 'Configurar seguimiento cuando se publique la rama.' if not tracking else 'Actualizar referencias antes de integrar.')
    status = run('--no-optional-locks', 'status', '--porcelain=v1', '--untracked-files=all')
    if status.returncode: report.add('GIT-WORKTREE', 'FAIL', 'No se pudo leer el estado.', 'Revisar el repositorio.')
    elif status.stdout: report.add('GIT-WORKTREE', 'SKIP', 'Hay cambios locales sin confirmar o archivos no rastreados (no se enumeran).', 'Revisar git status y conservar los cambios antes de integrar.')
    else: report.add('GIT-WORKTREE', 'PASS', 'Árbol de trabajo limpio.', 'Mantener evidencia de cambios.')
    def compare(identifier, ref, label):
        if not ref:
            report.add(identifier, 'SKIP', f'{label} no especificado o no disponible.', 'Indicar referencia y actualizarla cuando proceda.')
            return
        exists = run('rev-parse', '--verify', '--quiet', ref + '^{commit}')
        if exists.returncode:
            report.add(identifier, 'SKIP', f'Referencia {ref} no disponible localmente.', 'Consultar el remoto verificado y hacer fetch antes de integrar.')
            return
        count = run('rev-list', '--left-right', '--count', f'{ref}...HEAD')
        if count.returncode:
            report.add(identifier, 'FAIL', f'No se pudo comparar con {ref}.', 'Revisar el historial y repositorio.')
            return
        behind, ahead = map(int, count.stdout.split())
        # For a PR merge checkout HEAD already contains the base; this is not source branch divergence.
        suffix = ' Comparación del checkout de PR, no necesariamente de la rama fuente.' if is_pr and not branch else ''
        state = 'SKIP' if behind or shallow or (is_pr and not branch) else 'PASS'
        relation = 'divergente' if behind and ahead else ('atrasada' if behind else ('adelantada' if ahead else 'sincronizada con referencia local'))
        if shallow: suffix += ' Historial superficial: la comparación puede estar incompleta.'
        report.add(identifier, state, f'{ref}: {relation}; HEAD detrás {behind}, delante {ahead} commits.' + suffix, 'Sincronizar o revisar la base antes de integrar; fetch puede revelar cambios nuevos.' if behind else 'Actualizar referencias antes de integrar; no se consulta la red.')
    shallow = run('rev-parse', '--is-shallow-repository').stdout.strip() == 'true'
    compare('GIT-TRACKING-DIVERGENCE', tracking, 'Seguimiento')
    target_name = target or (env.get('GITHUB_BASE_REF') if is_pr else None)
    if not target_name:
        if permanent or source == 'main':
            target_name = 'main'
        elif len(hints) == 1:
            target_name = next(iter(hints))
    target_ref = None
    if target_name:
        branch_name = target_name.removeprefix(ORIGIN_REF).removeprefix('origin/')
        candidate = ORIGIN_REF + branch_name
        if run('check-ref-format', candidate).returncode == 0 and not branch_name.startswith('refs/'):
            target_ref = candidate
        else:
            report.add('GIT-TARGET-REF', 'FAIL', 'El destino debe identificar una rama de origin.',
                       'Indicar el nombre de la rama remota, por ejemplo feat/vision.')
    main_ref = ORIGIN_REF + 'main'
    compare('GIT-TARGET-DIVERGENCE', target_ref, 'Destino')
    if target_ref != main_ref:
        compare('GIT-MAIN-DIVERGENCE', main_ref, 'main')
    # Real merge simulation; new objects go to a temporary directory so the repository is not modified.
    if not target_ref or (is_pr and not branch):
        report.add('GIT-CONFLICTS', 'SKIP', 'Destino o rama fuente no verificable en este checkout.', 'Comparar la rama fuente en un clon completo.')
    elif not merge_base(target_ref):
        report.add('GIT-CONFLICTS', 'SKIP', 'No se encontró ancestro común local.', 'Actualizar referencias y revisar historial.')
    else:
        objects = run('rev-parse', '--path-format=absolute', '--git-path', 'objects').stdout.strip()
        with tempfile.TemporaryDirectory() as scratch:
            preview = git(root, 'merge-tree', '--write-tree', '--name-only', '--no-messages', 'HEAD', target_ref,
                          env={**os.environ, 'GIT_OBJECT_DIRECTORY': scratch, 'GIT_ALTERNATE_OBJECT_DIRECTORIES': objects})
        conflicted = sorted(set(preview.stdout.splitlines()[1:]))
        if preview.returncode == 1:
            report.add('GIT-CONFLICTS', 'SKIP', 'Conflictos en árboles confirmados: ' + ', '.join(conflicted), 'Revisar y resolver con responsables antes del PR.')
        elif preview.returncode:
            report.add('GIT-CONFLICTS', 'SKIP', 'No fue posible simular la integración (requiere Git 2.38 o posterior).', 'Revisar integración en un entorno aislado.')
        else:
            report.add('GIT-CONFLICTS', 'PASS', 'La integración simulada de árboles confirmados no produce conflictos.', 'Repetir con referencias actuales; no cubre cambios locales ni garantiza compatibilidad.')
    changes = set()
    for args in [('diff', '--name-only', '--no-renames', 'HEAD'), ('ls-files', '--others', '--exclude-standard')]:
        result = run(*args)
        if result.returncode == 0: changes.update(result.stdout.splitlines())
    incoming = set()
    base_ref = target_ref or main_ref
    committed_known = bool(merge_base(base_ref))
    if committed_known:
        own = run('diff', '--name-only', '--no-renames', merge_base(base_ref), 'HEAD')
        if own.returncode == 0: changes.update(own.stdout.splitlines())
        result = run('diff', '--name-only', '--no-renames', merge_base(base_ref), base_ref)
        if result.returncode == 0: incoming.update(result.stdout.splitlines())
    overlap = sorted(changes & incoming)
    unknown = f'Sin base común con {base_ref.removeprefix(ORIGIN_REF)}: solo se examinaron cambios sin confirmar.'
    if not committed_known:
        report.add('GIT-INCOMING', 'SKIP', unknown, 'Obtener la rama destino (git fetch origin) y repetir.')
    else:
        report.add('GIT-INCOMING', 'SKIP' if overlap else 'PASS',
                   'Archivos modificados también en ' + base_ref.removeprefix(ORIGIN_REF) + ': ' + ', '.join(overlap) if overlap
                   else f'{len(incoming)} archivos cambiados en el destino desde la base común; ninguno coincide con los propios.',
                   'Sincronizar con el destino y revisar esos archivos con sus responsables.' if overlap else 'Sincronizar antes de integrar si hay cambios entrantes.')
    grouped = {group: sorted(p for p in changes if classify_path(p) == group) for group in ('vision', 'brazo', 'locomocion', 'shared', 'other')}
    risky = grouped['shared']
    owners = [group for group in ('vision', 'brazo', 'locomocion') if grouped[group]]
    report.add('GIT-OWNERS', 'PASS' if owners else 'SKIP', '; '.join(f'{owner}: {", ".join(grouped[owner])}' for owner in owners) if owners else 'No se detectaron rutas exclusivas de subsistema.', 'Revisar propiedad y semántica de los cambios.')
    report.add('GIT-SHARED', 'PASS' if committed_known and not risky else 'SKIP', 'Rutas compartidas para revisar: ' + ', '.join(risky) if risky else ('Sin rutas compartidas conocidas en los cambios examinados.' if committed_known else unknown), 'Solicitar revisión de integración y equipos afectados.' if risky else 'La clasificación por rutas no garantiza compatibilidad ROS ni detecta toda dependencia.')
    cross = len(owners) > 1 or bool(risky and owners)
    report.add('GIT-CROSS', 'PASS' if committed_known and not cross else 'SKIP', 'Cambios en varios subsistemas o en subsistema e integración compartida.' if cross else ('No se detectó combinación transversal por rutas.' if committed_known else unknown), 'Solicitar revisión conjunta de los equipos afectados.' if cross else 'Revisar manualmente el impacto semántico.')
    if grouped['other']:
        report.add('GIT-OTHER', 'SKIP', 'Rutas no clasificadas: ' + ', '.join(grouped['other']), 'Determinar responsables y posible impacto transversal manualmente.')
    recognized = permanent or temporary or source == 'main'
    if not source:
        report.add('GIT-SUBSYSTEM', 'SKIP', 'No se conoce la rama fuente.', 'Indicar la rama y el subsistema.')
    elif not recognized:
        report.add('GIT-SUBSYSTEM', 'FAIL', 'Rama no reconocida: ' + source, 'Usar una rama principal o prefijo temporal permitido.')
    else:
        markers = {PERMANENT_BRANCHES[source]} if permanent else {PERMANENT_BRANCHES[hint] for hint in hints}
        if source == 'feat/2WD':
            report.add('GIT-2WD', 'PASS', 'Rama experimental 2WD del área de locomoción.',
                       'Revisar el banco por separado y exigir aprobación antes de integrar resultados.')
        if subsystem and (markers and markers != {subsystem} or source == 'main'):
            report.add('GIT-SUBSYSTEM', 'FAIL', f'Rama {source} incompatible con subsistema {subsystem}.', 'Usar una rama del subsistema indicado.')
        elif subsystem and not markers:
            report.add('GIT-SUBSYSTEM', 'SKIP', f'{source} no identifica un subsistema en su nombre.', 'Confirmar manualmente su procedencia y destino.')
        elif not markers:
            report.add('GIT-SUBSYSTEM', 'SKIP', f'Rama reconocida: {source}; no se identifica un subsistema.', 'Confirmar manualmente que corresponde a cambios compartidos y su destino.')
        else:
            report.add('GIT-SUBSYSTEM', 'PASS', f'Rama reconocida: {source}; subsistemas nombrados: {", ".join(sorted(markers))}.', 'Confirmar el destino de los cambios compartidos.')
    report.add('GIT-FRESHNESS', 'SKIP', 'Las referencias locales no prueban el estado actual del servidor.', 'Ejecutar git fetch origin y repetir antes de integrar.')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--target', help='Rama destino, por ejemplo main o feat/vision')
    parser.add_argument('--subsystem', choices=sorted(SUBSYSTEMS))
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    sys.exit(check(args.root, args.target, args.subsystem).finish(args.json))
