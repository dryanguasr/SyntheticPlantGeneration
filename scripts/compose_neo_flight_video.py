"""Create one review video: chase view with onboard picture-in-picture."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flight',type=Path)
    args=parser.parse_args(); folder=args.flight.resolve()
    result=json.loads((folder/'result.json').read_text())
    if not result['completed'] or result['waypoints_reached']!=result['waypoints_expected']:
        raise ValueError('Only a completed flight may be presented as the full survey')
    output=folder/'vuelo_neo_cultivo.mp4'
    graph=('[0:v]setpts=PTS-STARTPTS[main];'
           '[1:v]setpts=PTS-STARTPTS,scale=384:216,pad=392:224:4:4:white[fpv];'
           '[main][fpv]overlay=W-w-16:16:shortest=1[out]')
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(folder/'chase.mp4'),
        '-i',str(folder/'onboard.mp4'),'-filter_complex',graph,'-map','[out]',
        '-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p',
        '-movflags','+faststart',str(output)],check=True)
    metadata={k:result[k] for k in ('script_version','seed','parameter_preset')}
    metadata.update(source='actual_Gazebo_RGB',layout='chase_with_onboard_inset',
        file=output.name,speed='simulation_time',motion='dynamic_approximation_not_DJI_firmware')
    (folder/'video_composition.json').write_text(json.dumps(metadata,indent=2))
    print(output)


if __name__=='__main__':main()
