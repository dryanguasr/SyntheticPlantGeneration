"""One owned hidden Blender child; no seed queue or training entry point."""
from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run_nodal_automation import identity


if __name__=='__main__':
    out=Path(sys.argv[1]).resolve()
    command=['C:/Program Files/Blender Foundation/Blender 5.1/blender.exe',
             '--background','--factory-startup','--python-exit-code','1',
             '--python',str(ROOT/'scripts/audit_third_candidate_space_review.py'),'--',str(out)]
    with (out/'blender.stdout.log').open('w',encoding='utf-8') as stdout, (out/'blender.stderr.log').open('w',encoding='utf-8') as stderr:
        child=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        (out/'process.json').write_text(json.dumps(dict(**identity(child.pid,child._handle),command=command),indent=2)+'\n',encoding='utf-8')
        code=child.wait()
    (out/'process_exit.json').write_text(json.dumps(dict(exit_code=code,child_identity_record=str(out/'process.json')))+'\n',encoding='utf-8')
    sys.exit(code)
