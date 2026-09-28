"""Capture actual Gazebo RGB messages using installed Harmonic Python bindings.

Run inside Linux/WSL while the field server is running. Writes PNG via stdlib.
"""
import argparse
import json
from pathlib import Path
import struct
import threading
import zlib


def png(width, height, data, step):
    def chunk(kind, value):
        return struct.pack('>I',len(value))+kind+value+struct.pack('>I',zlib.crc32(kind+value)&0xffffffff)
    rows = b''.join(b'\0'+data[y*step:y*step+width*3] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',width,height,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))


def main():
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=90)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((args.output.parent/'manifest.json').read_text())
    provenance={k:manifest[k] for k in ('script_version','seed','parameter_preset')}
    node=Node()
    events=[]
    callbacks=[]
    for name in ('overview','drone_camera'):
        event=threading.Event()
        events.append(event)
        received=[0]
        def callback(msg, name=name, event=event, received=received):
            if event.is_set(): return
            if msg.pixel_format_type != 3:  # gz.msgs.PixelFormatType.RGB_INT8
                return
            received[0]+=1
            # Keep a short sensor warm-up instead of saving the initial frame.
            if received[0] < 6: return
            (args.output/f'{name}.png').write_bytes(png(msg.width,msg.height,msg.data,msg.step))
            (args.output/f'{name}.json').write_text(json.dumps({
                **provenance,'source':'gazebo_transport_live','topic':f'/uchuva/{name}/image',
                'width':msg.width,'height':msg.height,'step':msg.step,'received_frames':received[0],
                'simulation_stamp':{'sec':msg.header.stamp.sec,'nsec':msg.header.stamp.nsec}}))
            event.set()
        callbacks.append(callback)
        if not node.subscribe(Image,f'/uchuva/{name}/image',callback):
            raise RuntimeError(f'Cannot subscribe to {name}')
    if not all(event.wait(args.timeout) for event in events):
        raise TimeoutError('No RGB received from all Gazebo cameras')
    print('Captured both live Gazebo cameras',flush=True)


if __name__=='__main__':
    main()
