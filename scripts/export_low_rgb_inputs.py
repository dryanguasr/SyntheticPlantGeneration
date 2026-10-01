"""Publish an RGB-only estimator input bundle; keep truth in the evaluator channel."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    p.add_argument('--run',default='flight');args=p.parse_args()
    config=json.loads((args.package/'mission.json').read_text())
    public={k:config[k] for k in ('script_version','seed','parameter_preset','model_sha256','model_version',
                                  'confidence','additional_nms','camera','marker','triangulation','association')}
    run=args.package/args.run
    pairs=json.loads((run/'pairs.json').read_text())['pairs']
    (run/'rgb_frames.json').write_text(json.dumps([{'stamp_ns':p['stamp_ns'],'filename':Path(p['rgb']).name} for p in pairs]))
    (run/'estimator_config.json').write_text(json.dumps(public,indent=2))


if __name__=='__main__':main()
