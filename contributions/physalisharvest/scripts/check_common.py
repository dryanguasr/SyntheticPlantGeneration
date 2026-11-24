"""Shared reporting for local repository checks."""
import datetime
import json
import platform
import subprocess
import sys
from pathlib import Path


def git(root, *args, env=None):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)


class Report:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.checks = []

    def add(self, identifier, status, explanation, action):
        self.checks.append(dict(id=identifier, status=status, explanation=explanation, action=action))

    def finish(self, output=None):
        for item in self.checks:
            print(f"[{item['status']}] {item['id']}: {item['explanation']} Acción: {item['action']}")
        totals = {s: sum(c['status'] == s for c in self.checks) for s in ('PASS', 'FAIL', 'SKIP')}
        print('Resumen: ' + ', '.join(f'{k}={v}' for k, v in totals.items()))
        if output:
            branch = git(self.root, 'symbolic-ref', '--quiet', '--short', 'HEAD')
            sha = git(self.root, 'rev-parse', 'HEAD')
            data = dict(branch=branch.stdout.strip() or None, sha=sha.stdout.strip() or None,
                        date_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        environment=dict(platform=platform.platform(), python=sys.version.split()[0]),
                        checks=self.checks, totals=totals)
            Path(output).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return 1 if totals['FAIL'] else 0
