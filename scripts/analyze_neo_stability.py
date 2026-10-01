"""Compare recorded hover experiments without modifying the original telemetry."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_gazebo.flight_control import angular_rate_from_poses, flight_metrics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('telemetry',type=Path,nargs='+')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plot',action='store_true',help='Optional: requires an already installed matplotlib')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    reports=[];traces=[]
    for path in args.telemetry:
        data=json.loads(path.read_text(encoding='utf-8'));samples=data['samples']
        if len(samples)<2:raise ValueError(f'Insufficient telemetry: {path}')
        for previous,current in zip(samples,samples[1:]):
            current['angular_velocity']=angular_rate_from_poses(previous['quaternion_xyzw'],
                current['quaternion_xyzw'],current['t']-previous['t'])
        samples[0]['angular_velocity']=(0,0,0)
        window=[s for s in samples if 10<=s['t']-samples[0]['t']<=25]
        if not window:raise ValueError(f'No samples in 10–25 s window: {path}')
        rms=lambda values:math.sqrt(sum(v*v for v in values)/len(values))
        reports.append({'experiment':path.parent.parent.name,'path':str(path.resolve()),
            'telemetry_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            **{k:data[k] for k in ('script_version','seed','parameter_preset')},
            'metrics':flight_metrics(samples),
            'window_10_25_seconds':{'samples':len(window),
                'roll_rms_deg':math.degrees(rms([s['roll'] for s in window])),
                'pitch_rms_deg':math.degrees(rms([s['pitch'] for s in window])),
                'position_error_rms_m':rms([s['position_error_m'] for s in window])}})
        traces.append(samples)
    result={'script_version':'neo-stability-analysis/0.1',
        'seed':reports[0]['seed'] if all(r['seed']==reports[0]['seed'] for r in reports) else None,
        'parameter_preset':'hover_ablation_10_25_seconds','experiments':reports,
        'angular_rate_source':'quaternion_shortest_arc_interval_estimate',
        'scope':'simulation_only_no_DJI_physical_validation'}
    (args.output/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(3,1,figsize=(10,8),sharex=True)
        for report,samples in zip(reports,traces):
            times=[s['t']-samples[0]['t'] for s in samples]
            for axis,key in zip(axes,('roll','pitch','position_error_m')):
                factor=180/math.pi if key!='position_error_m' else 1
                axis.plot(times,[s[key]*factor for s in samples],label=report['experiment'],linewidth=1)
        for axis,label in zip(axes,('Alabeo [°]','Cabeceo [°]','Error de posición [m]')):
            axis.set_ylabel(label);axis.grid(alpha=.2);axis.set_xlim(0,25)
        axes[0].legend(loc='upper right');axes[-1].set_xlabel('Tiempo simulado [s]')
        fig.suptitle('Estacionario en Gazebo: comparación del controlador')
        fig.tight_layout();fig.savefig(args.output/'comparison.png',dpi=160);plt.close(fig)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
