"""WSL: encode presentation videos and verify decoding; never creates observations."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);args=p.parse_args()
    run=args.run.resolve();result=json.loads((run/'result.json').read_text())
    if not result['completed']:raise RuntimeError('Full-flight presentation requires a completed mission')
    base=['ffmpeg','-hide_banner','-loglevel','error','-y']
    encoding=['-an','-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart']
    subprocess.run(base+['-i',str(run/'chase.mp4'),'-i',str(run/'onboard.mp4'),
        '-filter_complex','[1:v]scale=416:234[pip];[0:v][pip]overlay=W-w-16:16:shortest=1']+
        encoding+[str(run/'vuelo_bajo.mp4')],check=True)
    conversions=[(run/'anotado_5hz.mp4',run/'vuelo_anotado.mp4'),
                 (run/'evaluation/comparacion_5hz.mp4',run/'evaluation/comparacion_verdad.mp4')]
    for source,target in conversions:
        subprocess.run(base+['-i',str(source),'-r','15']+encoding+[str(target)],check=True)
    outputs=[run/'vuelo_bajo.mp4',*(target for _,target in conversions)]
    info={}
    for path in outputs:
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(path),'-f','null','-'],check=True)
        data=subprocess.check_output(['ffprobe','-v','error','-show_entries',
            'stream=codec_name,width,height,r_frame_rate,nb_frames:format=duration,size','-of','json',str(path)],text=True)
        info[path.name]=json.loads(data)
    metadata={k:result[k] for k in ('script_version','seed','parameter_preset')}
    metadata.update({'videos':info,'analysis_observations_hz':5,'presentation_fps':15,
                     'repeated_presentation_frames_are_not_observations':True,'full_decode_passed':True})
    (run/'video_manifest.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':main()
