"""Read-only verification of the published artifact package. Standard library."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
import hashlib
import json

ROOT = Path(__file__).resolve().parent


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ('src', 'href') and value:
                parsed = urlsplit(value)
                if not parsed.scheme and not parsed.netloc and parsed.path:
                    self.targets.append(unquote(parsed.path))


def check():
    manifest = json.loads((ROOT / 'publication_manifest.json').read_text(encoding='utf-8'))
    errors = []
    for item in manifest['files']:
        p = ROOT / item['path']
        if not p.is_file():
            errors.append('Missing: ' + item['path'])
            continue
        with p.open('rb') as f:
            digest = hashlib.file_digest(f, 'sha256').hexdigest()
        if digest != item['sha256'] or p.stat().st_size != item['bytes']:
            errors.append('Changed: ' + item['path'])
    links = 0
    for p in ROOT.rglob('*.html'):
        parser = Links()
        parser.feed(p.read_text(encoding='utf-8'))
        for target in parser.targets:
            resolved = (p.parent / target).resolve()
            links += 1
            if not resolved.is_relative_to(ROOT) or not resolved.is_file():
                errors.append(f'Broken/outside link: {p.relative_to(ROOT)} -> {target}')
    print(json.dumps({'passed': not errors, 'files':len(manifest['files']), 'html_links':links, 'errors':errors},ensure_ascii=False,indent=2))
    return not errors


if __name__ == '__main__':
    raise SystemExit(0 if check() else 1)
