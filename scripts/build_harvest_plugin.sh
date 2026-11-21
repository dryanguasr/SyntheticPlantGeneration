#!/usr/bin/env bash
# Build only the isolated native plugin, without changing the Python project.
set -euo pipefail
harvest_repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
harvest_build="${1:-${harvest_repo}/outputs/harvest_plugin_build}"
for harvest_tool in cmake c++ python3; do
  if ! command -v "${harvest_tool}" >/dev/null 2>&1; then
    echo "Missing build prerequisite: ${harvest_tool}. See docs/guides/piloto_cosecha_desmontable.md" >&2
    exit 2
  fi
done
mkdir -p -- "${harvest_build}"
harvest_build="$(cd -- "${harvest_build}" && pwd)"
cmake -S "${harvest_repo}/gazebo/harvest_system" -B "${harvest_build}" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo 2>&1 | tee "${harvest_build}/configure.log"
cmake --build "${harvest_build}" --parallel 2 2>&1 | tee "${harvest_build}/build.log"
python3 - "${harvest_repo}" "${harvest_build}" <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess
import sys
repo, build = map(Path, sys.argv[1:])
library = build / 'libUchuvaHarvestSystem.so'
if not library.is_file():
    raise SystemExit(f'Expected shared library not found: {library}')
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
metadata = {'source_sha256': {name: sha(repo / 'gazebo/harvest_system' / name)
                             for name in ('HarvestSystem.cc', 'CMakeLists.txt')},
            'library_sha256': sha(library),
            'cmake_version': subprocess.check_output(['cmake', '--version'], text=True).splitlines()[0],
            'runtime_validation': 'pending_gazebo'}
(build / 'build_provenance.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(f'Built: {library}')
PY
