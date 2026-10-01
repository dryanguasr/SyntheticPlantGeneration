"""Axis-aware aisle feedback; distance to the endpoint cannot dilute cross-track control."""
import math


def desired_velocity(delta):
    x=max(-.16,min(.16,1.1*delta[0]))
    y=max(-.08,min(.08,1.1*delta[1]))
    horizontal=math.hypot(x,y)
    if horizontal>.16:x,y=x*.16/horizontal,y*.16/horizontal
    z=max(-.08,min(.08,1.1*delta[2]))
    return x,y,z
