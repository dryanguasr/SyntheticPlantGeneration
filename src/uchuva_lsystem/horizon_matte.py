"""Separate the frozen panorama's sky and decontaminate its skyline.

Pure pixel-array contract. It never reads or modifies a morphological tree.
Thresholds describe this photographic panorama only, not physical validation.
"""
from array import array
import math


def separate_panorama(pixels,width,height,threshold=.22,lower_fraction=.44,upper_fraction=.60,edge_cleanup_rows=2):
    if width<4 or height<8 or len(pixels)!=width*height*4:raise ValueError('RGBA panorama dimensions differ')
    if not 0<lower_fraction<upper_fraction<1:raise ValueError('Invalid horizon search interval')
    clean=array('f',pixels);matte=array('f',[0.,0.,0.,1.])*(width*height)
    low=int(height*lower_fraction);high=int(height*upper_fraction);horizon=[];missing=[]
    for x in range(width):
        boundary=None
        for y in range(high,low-1,-1):
            i=(y*width+x)*4
            if .2126*pixels[i]+.7152*pixels[i+1]+.0722*pixels[i+2]<threshold:
                boundary=y;break
        if boundary is None:missing.append(x);boundary=low
        horizon.append(boundary)
    if missing:raise ValueError('Horizon not found for '+str(len(missing))+' panorama columns')
    smooth=[.25*horizon[(x-1)%width]+.5*horizon[x]+.25*horizon[(x+1)%width] for x in range(width)]
    for x,boundary in enumerate(horizon):
        clean_from=max(0,math.floor(min(boundary,smooth[x]))-edge_cleanup_rows+1)
        anchor=max(0,clean_from-2);i=(anchor*width+x)*4
        color=array('f',pixels[i:i+4]);color[3]=1.
        # Extend clean foreground color into all removed sky texels. Linear
        # texture filtering then cannot bleed the former white sky back into
        # the new silhouette. Clean a narrow old antialiased boundary as well.
        for y in range(clean_from,height):
            i=(y*width+x)*4;clean[i:i+4]=color
            t=max(0.,min(1.,(y-smooth[x]+1.)/2.));alpha=t*t*(3.-2.*t)
            matte[i:i+4]=array('f',[alpha,alpha,alpha,1.])
    return clean,matte,dict(version='connected_column_horizon/2',width=width,height=height,
        luminance_threshold=threshold,search_fraction=[lower_fraction,upper_fraction],
        edge_cleanup_rows=edge_cleanup_rows,horizon_rows=horizon,smoothed_horizon_rows=smooth,
        horizontal_filter=[.25,.5,.25],vertical_feather_half_width_pixels=1.,missing_columns=missing,
        original_sky_texels_retained=False,provenance='engineering_heuristic specific to frozen farmland_overcast HDR; not general segmentation')
