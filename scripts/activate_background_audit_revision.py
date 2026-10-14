"""Select only fully audited background revisions; retain original attempts."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--revision',action='append',required=True);a=p.parse_args()
    run=json.loads((a.root/'run.json').read_text());changes={}
    for entry in a.revision:
        seed,folder=entry.split('=',1)
        if Path(folder).name!=folder or int(seed) not in run['background_seeds']:
            raise ValueError('Revision must identify a background seed and local folder')
        path=a.root/'background_audits'/folder/'mesh_audit.json'
        audit=json.loads(path.read_text())
        if audit['seed']!=int(seed) or audit['acceptance']!='passed':
            raise ValueError(f'Revision has not passed full mesh audit: {folder}')
        changes[seed]=dict(folder=folder,audit_sha256=sha(path))
    write(a.root/'background_axis_revision_selection.json',dict(previous=run.get('background_audit_directories',{}),changes=changes))
    run.setdefault('background_audit_directories',{}).update({s:v['folder'] for s,v in changes.items()})
    write(a.root/'run.json',run)


if __name__=='__main__':main()
