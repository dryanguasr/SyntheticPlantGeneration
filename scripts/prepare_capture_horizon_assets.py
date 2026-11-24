"""Blender --python this.py -- SOURCE_HDR OUTPUT_FOLDER; no render or plants."""
from pathlib import Path
from array import array
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import bpy
from uchuva_lsystem.horizon_matte import separate_panorama
from uchuva_lsystem.nodal_automation import write,sha


def prepare(source,out):
    out.mkdir(parents=True,exist_ok=False)
    original=bpy.data.images.load(str(source),check_existing=False)
    width,height=original.size[:];pixels=array('f',[0.])*(width*height*4);original.pixels.foreach_get(pixels)
    clean,matte,metadata=separate_panorama(pixels,width,height)
    paths={}
    for name,buffer,format,suffix in [('landscape_clean',clean,'OPEN_EXR','.exr'),('sky_matte',matte,'PNG','.png')]:
        image=bpy.data.images.new(name,width,height,float_buffer=True,is_data=name=='sky_matte')
        if name=='sky_matte':image.colorspace_settings.name='Non-Color'
        image.pixels.foreach_set(buffer);image.update()
        image.filepath_raw=str(out/(name+suffix));image.file_format=format
        image.save();paths[name]=str((out/(name+suffix)).resolve())
        paths[name+'_sha256']=sha(paths[name]);bpy.data.images.remove(image)
    check=bpy.data.images.load(paths['sky_matte'],check_existing=False)
    if check.pixels[(height-1)*width*4]<.99 or check.pixels[0]>.01:
        raise ValueError('Saved sky matte lost its pixel buffer')
    paths.update(source_hdr=str(source),source_hdr_sha256=sha(source),metadata=metadata)
    write(out/'manifest.json',paths);print('HORIZON_ASSETS_READY',out,flush=True)


if __name__=='__main__':prepare(*[Path(p).resolve() for p in sys.argv[sys.argv.index('--')+1:]])
