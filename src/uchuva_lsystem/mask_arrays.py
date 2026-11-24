"""Optional array acceleration of the existing exact mask quantization policy.

NumPy is supplied by Blender; importing this module itself needs only stdlib.
The Blender caller falls back to the historical implementation if unavailable.
Unknown colors still use the historical nearest-color/tolerance/tie rule.
"""
from . import blender_annotations as annotations


def quantize_stats(pixels,palette,width,height):
    import numpy as np
    rgba=np.asarray(pixels).reshape((-1,4))
    if len(rgba)!=width*height:raise ValueError('Pixel buffer dimensions differ')
    # Python round in the legacy path is ties-to-even on a double. Widen before
    # multiplying, so float32 multiplication cannot move a rounding boundary.
    rgb=np.rint(np.clip(rgba[:,:3].astype(np.float64),0.,1.)*255).astype(np.uint32)
    rgb[rgba[:,3]<.5]=0
    packed=(rgb[:,0]<<16)|(rgb[:,1]<<8)|rgb[:,2]
    unique,inverse=np.unique(packed,return_inverse=True)
    palette_items=list(palette.items())
    exact={tuple(color):identifier for identifier,color in palette_items}
    mapped=[]
    for value in unique:
        rgb8=(int(value>>16),int((value>>8)&255),int(value&255))
        identifier=exact.get(rgb8)
        if identifier is None:identifier=annotations._nearest_palette_identifier(rgb8,palette_items)
        mapped.append(identifier)
    identifiers=np.asarray(mapped,dtype=np.int32)[inverse]
    size=max(palette)+1
    colors=np.zeros((size,4),dtype=np.float32)
    for identifier,color in palette_items:colors[identifier]=annotations._normalized_rgba(color)
    snapped=colors[identifiers].reshape(-1)
    counts=np.bincount(identifiers,minlength=size)
    offsets=np.arange(width*height,dtype=np.int32)
    xs=offsets%width;ys=height-1-offsets//width
    minx=np.full(size,width,dtype=np.int32);miny=np.full(size,height,dtype=np.int32)
    maxx=np.full(size,-1,dtype=np.int32);maxy=np.full(size,-1,dtype=np.int32)
    np.minimum.at(minx,identifiers,xs);np.minimum.at(miny,identifiers,ys)
    np.maximum.at(maxx,identifiers,xs);np.maximum.at(maxy,identifiers,ys)
    stats={}
    for identifier in palette:
        count=int(counts[identifier])
        if not count:
            stats[identifier]=dict(visible_pixels=0,bbox_xywh=None,bbox_area=0,occlusion_proxy=None)
        else:
            w=int(maxx[identifier]-minx[identifier]+1);h=int(maxy[identifier]-miny[identifier]+1)
            stats[identifier]=dict(visible_pixels=count,bbox_xywh=[int(minx[identifier]),int(miny[identifier]),w,h],
                bbox_area=w*h,occlusion_proxy=round(1.-count/max(w*h,1),6))
    return snapped,stats


def snap_and_save_image(source_path,output_path,palette,width,height):
    import bpy
    try:import numpy as np
    except ImportError:return annotations._snap_and_save_image(source_path,output_path,palette,width,height)
    if not bpy.context.scene.get('uchuva_preserve_mask_components',False):
        return annotations._snap_and_save_image(source_path,output_path,palette,width,height)
    source=bpy.data.images.load(str(source_path),check_existing=False)
    try:
        if tuple(source.size)!=(width,height):raise ValueError('Mask render dimensions changed')
        pixels=np.empty(width*height*4,dtype=np.float32);source.pixels.foreach_get(pixels)
    finally:bpy.data.images.remove(source)
    snapped,stats=quantize_stats(pixels,palette,width,height)
    image=bpy.data.images.new(name=f'uchuva_annotation_{output_path.stem}',width=width,height=height,alpha=True,float_buffer=False)
    try:
        image.pixels.foreach_set(snapped);image.file_format='PNG';image.filepath_raw=str(output_path)
        image.save_render(str(output_path),scene=bpy.context.scene)
    finally:bpy.data.images.remove(image)
    return stats
