"""Write a new morphology revision after attachment-preserving axis clearance."""
import argparse
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.clearance_bouquet import clear_branch_axes
from uchuva_lsystem.segmentation_cycles import write


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    plant=Plant.from_dict(json.loads(a.source.read_text()));started=time.perf_counter()
    report=clear_branch_axes(plant);write(a.output,plant.to_dict())
    print(json.dumps({'changed_axes':len(report['changes']),'unresolved':len(report['unresolved']),'seconds':time.perf_counter()-started}))


if __name__=='__main__':main()
