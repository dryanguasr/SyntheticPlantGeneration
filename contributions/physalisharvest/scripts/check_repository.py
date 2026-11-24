"""Static checks only; not evidence of robot or ROS operation."""
import argparse
import ast
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

from check_common import Report, git

ROOT = Path(__file__).resolve().parents[1]
FILES = ['README.md', 'CONTRIBUTING.md', '.gitignore', '.github/PULL_REQUEST_TEMPLATE.md',
         'docs/interfaces/contratos-ros2.md', 'docs/arquitectura/README.md', 'docs/pruebas/README.md']
DIRS = ['.github/workflows', 'ros2_ws/src', 'ros2_ws/src/robot_percepcion_decision',
        'ros2_ws/src/robot_brazo', 'ros2_ws/src/robot_locomocion', 'ros2_ws/src/robot_interfaces',
        'simulacion/gazebo', 'simulacion/modelos', 'firmware', 'hardware/brazo', 'hardware/locomocion', 'tests']
EXCLUDE = {'.git', '.venv', 'venv', 'env', '__pycache__', 'build', 'install', 'log', '.pytest_cache'}


def files(root):
    """Tracked and non-ignored files, the same set Git would publish; None outside Git."""
    listing = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
    if listing.returncode:
        return None
    return [root / name for name in sorted(set(listing.stdout.split('\0')) - {''}) if (root / name).is_file()]


def strip_code(markdown):
    markdown = re.sub(r'(?ms)^ {0,3}(`{3,}|~{3,}).*?^ {0,3}\1[^\n]*$', '', markdown)
    return re.sub(r'`[^`\n]*`', '', markdown)


def check(root):
    root = Path(root).resolve()
    report = Report(root)
    missing = [p for p in FILES if not (root / p).is_file()] + [p for p in DIRS if not (root / p).is_dir()]
    report.add('REP-STRUCTURE', 'FAIL' if missing else 'PASS', 'Faltan: ' + ', '.join(missing) if missing else 'Estructura y documentación requeridas presentes.', 'Restaurar las rutas requeridas.' if missing else 'Mantener la estructura acordada.')
    paths = files(root)
    in_git = paths is not None
    if not in_git:
        paths = [p for p in root.rglob('*') if p.is_file() and not (set(p.relative_to(root).parts) & EXCLUDE)]
    for suffix, identifier in [('.py', 'REP-PYTHON'), ('.json', 'REP-JSON'), ('.yaml', 'REP-YAML')]:
        selected = [p for p in paths if p.suffix.lower() in (('.yaml', '.yml') if suffix == '.yaml' else (suffix,))]
        if suffix == '.yaml':
            try:
                import yaml
            except ImportError:
                report.add(identifier, 'SKIP', 'PyYAML no está disponible.' if selected else 'No hay archivos YAML.', 'Instalar PyYAML en un entorno aislado si se requiere validar YAML.')
                continue
        errors = []
        for p in selected:
            try:
                content = p.read_text(encoding='utf-8-sig')
                if suffix == '.py': ast.parse(content, filename=str(p))
                elif suffix == '.json': json.loads(content)
                else: list(yaml.safe_load_all(content))
            except Exception as exc:
                errors.append(f'{p.relative_to(root)}: {type(exc).__name__}')
        report.add(identifier, 'FAIL' if errors else ('PASS' if selected else 'SKIP'), '; '.join(errors) if errors else f'{len(selected)} archivos examinados.', 'Corregir la sintaxis.' if errors else 'Revisar al agregar archivos.')
    manifests = [p for p in paths if p.name == 'package.xml' and p.relative_to(root).parts[:2] == ('ros2_ws', 'src')]
    errors = []
    names = set()
    for p in manifests:
        try:
            element = ET.parse(p).getroot()
            name = (element.findtext('name') or '').strip()
            if element.tag != 'package' or not name or name != p.parent.name or not re.fullmatch(r'[a-z][a-z0-9_]*', name) or name in names:
                errors.append(str(p.relative_to(root)))
            names.add(name)
        except ET.ParseError:
            errors.append(str(p.relative_to(root)))
    report.add('REP-ROS-MANIFEST', 'FAIL' if errors else ('PASS' if manifests else 'SKIP'), 'Manifiestos inválidos: ' + ', '.join(errors) if errors else f'{len(manifests)} manifiestos reales examinados; las carpetas reservadas no son paquetes.', 'Corregir XML y nombres.' if errors else 'Comprobar paquetes cuando se implementen.')
    broken = []
    for p in [p for p in paths if p.suffix.lower() == '.md']:
        content = strip_code(p.read_text(encoding='utf-8-sig'))
        # Inline links and images outside code; anchors are not validated.
        for raw in re.findall(r'!?\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)', content):
            target = raw.strip('<>')
            parts = urlsplit(target)
            if parts.scheme or parts.netloc or not parts.path: continue
            # GitHub resolves a leading slash from the repository root.
            local = root / unquote(parts.path).lstrip('/') if parts.path.startswith('/') else p.parent / unquote(parts.path)
            if not local.exists(): broken.append(f'{p.relative_to(root)} → {target}')
    report.add('REP-LINKS', 'FAIL' if broken else 'PASS', '; '.join(broken) if broken else 'Enlaces locales Markdown examinados.', 'Corregir rutas.' if broken else 'Revisar anclas y enlaces complejos manualmente.')
    if not in_git:
        report.add('REP-CONTENT', 'FAIL', 'No se pudo enumerar el contenido de Git.', 'Ejecutar dentro de un repositorio Git.')
    else:
        problems = []
        secret = re.compile(rb'(?i)(?:api[_-]?key|token|password|secret)\s*[=:]\s*["\'][^"\'\r\n]{12,}["\']|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}')
        forbidden = re.compile(r'(?i)(?:^|/)(?:\.venv|venv|datasets|build|install|log)/|(?:^|/)\.env(?:$|\.(?!example$))|\.(?:pem|key|bag|db3|mcap|pt|pth|onnx|engine|weights)$')
        for p in paths:
            name = p.relative_to(root).as_posix()
            if forbidden.search(name): problems.append(name + ' (ruta restringida)')
            if not p.is_file() or p.is_symlink(): continue
            if p.stat().st_size > 10 * 1024 * 1024: problems.append(name + ' (>10 MiB)'); continue
            # Avoid displaying matched secret values and scanning binary files.
            data = p.read_bytes()
            if b'\0' not in data and secret.search(data): problems.append(name + ' (posible secreto)')
        report.add('REP-CONTENT', 'FAIL' if problems else 'PASS', '; '.join(problems) if problems else 'Rutas y patrones básicos examinados.', 'Revisar los archivos señalados sin divulgar valores.' if problems else 'Revisar también el diff y usar herramientas especializadas de secretos.')
    metadata = root / 'docs/ai_usage.json'
    narrative = root / 'docs/AI_USAGE.md'
    if not metadata.exists() and not narrative.exists():
        report.add('REP-AI', 'SKIP', 'No existen registros de IA.', 'Crear registros cuando corresponda según AGENTS.md.')
    else:
        errors = []
        if not metadata.is_file() or not narrative.is_file(): errors.append('Falta uno de los dos registros.')
        else:
            try:
                data = json.loads(metadata.read_text(encoding='utf-8-sig'))
                if not isinstance(data.get('uses'), list): raise ValueError('uses debe ser una lista')
                for entry in data['uses']:
                    if not isinstance(entry, dict) or not isinstance(entry.get('paths'), list) or not entry['paths']: raise ValueError('paths debe ser una lista no vacía')
                    for name in entry['paths']:
                        if not isinstance(name, str) or Path(name).is_absolute() or not (root / name).resolve().is_relative_to(root) or not (root / name).exists(): errors.append(f'Ruta de IA inválida: {name}')
            except (ValueError, TypeError, AttributeError, OSError) as exc: errors.append(f'Metadatos inválidos: {type(exc).__name__}')
        report.add('REP-AI', 'FAIL' if errors else 'PASS', '; '.join(errors) if errors else 'Referencias declaradas existentes.', 'Corregir registros y rutas.' if errors else 'Mantener actualizada la trazabilidad.')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--json', type=Path, help='Ruta del informe JSON')
    args = parser.parse_args()
    sys.exit(check(args.root).finish(args.json))
