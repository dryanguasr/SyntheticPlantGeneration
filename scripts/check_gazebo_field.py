"""Bounded real Gazebo smoke test (run in Ubuntu/WSL with Harmonic installed)."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('world',type=Path)
    parser.add_argument('--timeout',type=int,default=180)
    args=parser.parse_args()
    world=args.world.resolve()
    output=world.parent/'smoke'
    output.mkdir(exist_ok=True)
    env=dict(os.environ, GZ_PARTITION=f'uchuva_check_{os.getpid()}',
             GZ_SIM_RESOURCE_PATH=str(world.parent)+os.pathsep+os.environ.get('GZ_SIM_RESOURCE_PATH',''))
    validation=subprocess.run(['gz','sdf','-k',str(world)],capture_output=True,text=True,env=env)
    (output/'sdf_check.log').write_text(validation.stdout+validation.stderr)
    if validation.returncode:
        raise RuntimeError('SDF validation failed; see sdf_check.log')
    with (output/'server.log').open('w') as log:
        server=subprocess.Popen(['gz','sim','-s','-r','--headless-rendering','-v','3',str(world)],
                                stdout=log,stderr=subprocess.STDOUT,env=env)
        try:
            capture=subprocess.run([sys.executable,str(Path(__file__).with_name('gazebo_capture.py')),
                '--output',str(output),'--timeout',str(args.timeout)],env=env,timeout=args.timeout+10)
            if capture.returncode or server.poll() is not None:
                raise RuntimeError('Gazebo camera smoke failed; inspect server.log')
            manifest=json.loads((world.parent/'manifest.json').read_text())
            result={k:manifest[k] for k in ('script_version','seed','parameter_preset')}
            result.update(sdf_validation='passed',runtime='Gazebo Harmonic',
                          camera_transport='two_RGB_frames_received',
                          flight_control='not_implemented',harvest_contact='not_validated')
            (output/'result.json').write_text(json.dumps(result,indent=2))
            print(json.dumps(result),flush=True)
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__=='__main__':
    main()
