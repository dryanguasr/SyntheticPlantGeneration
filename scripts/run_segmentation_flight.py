"""Run the existing physical flight controller with evaluator-only paired masks."""
import argparse
from pathlib import Path
import sys
import json
import os
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import check_deadline


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--package',type=Path,required=True);p.add_argument('--name',required=True)
    p.add_argument('--seconds',type=float,default=0);p.add_argument('--wall-timeout',type=float,default=3600)
    p.add_argument('--assimp',action='store_true',help='Use the bundled alternative mesh loader')
    a=p.parse_args();check_deadline(a.root)
    mission_config=json.loads((a.package/'mission.json').read_text())
    if a.assimp:os.environ['GZ_MESH_FORCE_ASSIMP']='true'
    if (a.root/'effective_budget.json').exists():
        from uchuva_lsystem.execution_budget import remaining_seconds
        a.wall_timeout=min(a.wall_timeout,max(1,remaining_seconds(a.root)-30))
    import run_bouquet_flight as runtime
    from run_low_flight import Images
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image
    base=runtime.Recorder
    original_popen=runtime.subprocess.Popen

    class GuardedProcess(original_popen):
        def __init__(self,command,*args,**kwargs):
            super().__init__(command,*args,**kwargs)
            if isinstance(command,list) and command[:2]==['gz','sim']:
                def guard():
                    while self.poll() is None:
                        try:
                            status=Path(f'/proc/{self.pid}/status').read_text()
                            rss=int(next(line.split()[1] for line in status.splitlines() if line.startswith('VmRSS:')))
                            if rss>10*1024*1024 or (a.root/'execution_stop.request').exists():
                                (a.package/a.name/'memory_stop.json').write_text(json.dumps({'pid':self.pid,'rss_kib':rss,'limit_gib':10,'host_stop_request':(a.root/'execution_stop.request').exists()}))
                                self.terminate()
                                try:self.wait(timeout=5)
                                except runtime.subprocess.TimeoutExpired:self.kill()
                                return
                        except (FileNotFoundError,StopIteration):pass
                        time.sleep(2)
                threading.Thread(target=guard,daemon=True).start()
    runtime.subprocess.Popen=GuardedProcess

    class PairedRecorder(base):
        def __init__(self,output,name,*args,**kwargs):
            if mission_config.get('retain_all_sensor_pairs'):kwargs['fps']=30
            super().__init__(output,name,*args,**kwargs)
            self.paired=None
            if name=='onboard':
                folder=output/'paired';folder.mkdir()
                self.paired=Images(folder,pair_rate_hz=None if mission_config.get('retain_all_sensor_pairs') else 5);self.mask_node=Node()
                self.mask_node.subscribe(Image,'/neo/instances/labels_map',lambda msg:self.paired.receive('mask',msg))

        def callback(self,msg):
            super().callback(msg)
            if self.paired:
                self.paired.receive('rgb',msg)
                if self.paired.error:self.error=self.paired.error

        def close(self):
            super().close()
            if self.paired:
                self.paired.close()
                if self.paired.error:raise RuntimeError(self.paired.error)

    runtime.Recorder=PairedRecorder
    sys.argv=['run_bouquet_flight.py',str(a.package),'--name',a.name,
              '--seconds',str(a.seconds),'--wall-timeout',str(a.wall_timeout)]
    runtime.main()


if __name__=='__main__':main()
