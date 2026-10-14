"""WSL: narrated-by-labels 4x overview, retaining complete original videos."""
import argparse
import json
from pathlib import Path
import subprocess


def ass_time(t):
    value=max(0,round(t*100));h,value=divmod(value,360000);m,value=divmod(value,6000);s,cs=divmod(value,100)
    return f'{h}:{m:02d}:{s:02d}.{cs:02d}'


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run.resolve()
    result=json.loads((run/'result.json').read_text())
    if not result['completed']:raise RuntimeError('Do not label an incomplete flight as complete')
    trace=json.loads((run/'telemetry.json').read_text())['samples'];start=trace[0]['t']
    intervals=[];current=trace[0]
    for sample in trace[1:]:
        if sample['phase']!=current['phase']:
            intervals.append((current,sample['t']));current=sample
    intervals.append((current,trace[-1]['t']+1))
    header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,23,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,3,2,0,7,16,16,16,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events=[]
    for item,end in intervals:
        phase=item['phase']
        if phase.startswith('row_'):
            _,row,side,stage=phase.split('_');label=f'Hilera {int(row)+1}/6 | cara {"A" if side=="-1" else "B"}'
            if stage=='entry':label+=' | aproximacion'
        else:label='Transicion fuera del cultivo'
        label+=' | Gazebo v4 | reproduccion 4x'
        events.append(f'Dialogue: 0,{ass_time(item["t"]-start)},{ass_time(end-start)},Default,,0,0,0,,{label}\n')
    (run/'route.ass').write_text(header+''.join(events),encoding='utf-8')
    filters='[1:v]scale=384:216[inset];[0:v][inset]overlay=W-w-16:H-h-16:shortest=1,subtitles=route.ass,setpts=PTS/4[v]'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','2','-i','onboard.mp4','-threads','2','-i','chase.mp4','-filter_complex_threads','2',
        '-filter_complex',filters,'-map','[v]','-an','-r','30','-c:v','libx264','-preset','fast','-threads','2','-crf','20',
        '-pix_fmt','yuv420p','-movflags','+faststart','vuelo_completo_4x.mp4'],cwd=run,check=True)
    checks={}
    for name in ('onboard.mp4','chase.mp4','vuelo_completo_4x.mp4'):
        subprocess.run(['ffmpeg','-v','error','-i',str(run/name),'-f','null','-'],check=True)
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height,nb_frames,r_frame_rate',
            '-of','json',str(run/name)],capture_output=True,text=True,check=True)
        checks[name]=json.loads(probe.stdout)
    (run/'video_validation.json').write_text(json.dumps(checks,indent=2))

if __name__=='__main__':main()
