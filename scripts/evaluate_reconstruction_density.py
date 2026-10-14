"""Compare observed point sampling in one fixed reconstruction coordinate frame.

Distances are consistency diagnostics, not accuracy against external ground truth.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_reconstruction.geometry import read_colmap_points


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--improved',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    arrays=[]
    report=dict(script_version='reconstruction-pilot/0.2',seed=20261001,
        parameter_preset='fixed_frame_density_comparison',units='arbitrary',
        external_ground_truth=False,physical_accuracy=None,complete_plant=False,
        interpretation='Sampling and cross-resolution consistency in the same camera model and poses; not recovered fraction of plant')
    for name,path in [('baseline',args.baseline),('improved',args.improved)]:
        values=read_colmap_points(path)
        xyz=np.column_stack([values[n] for n in ('x','y','z')])
        arrays.append(xyz)
        distance=cKDTree(xyz).query(xyz,k=2,workers=4)[0][:,1]
        report[name]=dict(path=str(path),points=len(xyz),
            nearest_neighbor_spacing_quantiles=dict(zip(['p10','p50','p90'],np.quantile(distance,[.1,.5,.9]).tolist())))
    for source,target,label in [(arrays[0],arrays[1],'baseline_to_improved'),(arrays[1],arrays[0],'improved_to_baseline')]:
        distances=cKDTree(target).query(source,workers=4)[0]
        report[label]=dict(zip(['p50','p90','p95','p99'],np.quantile(distances,[.5,.9,.95,.99]).tolist()))
    report['point_count_ratio']=len(arrays[1])/len(arrays[0])
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=='__main__':main()
