"""Blender: original Neo-like mesh from official photos; no downloaded CAD.

Only outer dimensions are manufacturer reported. All internal dimensions below
are engineering_heuristic. This is a visual reference, not manufacturing CAD.
"""
import argparse
import json
import math
from pathlib import Path
import sys


def main():
    import bpy
    from mathutils import Vector
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);args.output=args.output.resolve()
    args.output.mkdir(parents=True,exist_ok=False)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    def material(name,color,metal=0):
        mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
        node=mat.node_tree.nodes.get('Principled BSDF');node.inputs['Base Color'].default_value=(*color,1)
        node.inputs['Metallic'].default_value=metal;node.inputs['Roughness'].default_value=.35
        return mat
    shell=material('warm_light_gray',(.62,.65,.66))
    guard=material('guard_gray',(.45,.48,.50))
    black=material('graphite',(.018,.024,.03))
    rubber=material('battery_seam',(.15,.17,.19))
    glass=material('lens_blue',(.015,.055,.08),.5)
    led=material('status_green',(.10,.65,.32))
    def finish(obj,name,mat):
        obj.name=name;obj.data.materials.append(mat)
        for p in obj.data.polygons:p.use_smooth=True
        return obj
    def rounded(name,loc,size,bevel,mat):
        bpy.ops.mesh.primitive_cube_add(size=1,location=loc);obj=bpy.context.object;obj.dimensions=size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        mod=obj.modifiers.new('rounded_edges','BEVEL');mod.width=bevel;mod.segments=5
        mod=obj.modifiers.new('weighted_normals','WEIGHTED_NORMAL')
        return finish(obj,name,mat)
    def cylinder(name,loc,radius,depth,mat,rotation=(0,0,0)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=40,radius=radius,depth=depth,location=loc,rotation=rotation)
        return finish(bpy.context.object,name,mat)
    def tube(name,points,radius,mat):
        data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D';data.bevel_depth=radius;data.bevel_resolution=2
        spline=data.splines.new('POLY');spline.points.add(len(points)-1)
        for p,co in zip(spline.points,points):p.co=(*co,1)
        obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.data.materials.append(mat)
        bpy.context.view_layer.objects.active=obj;obj.select_set(True)
        bpy.ops.object.convert(target='MESH');obj.select_set(False)
        return obj
    def annulus(name,x,y,r0,r1,z0,z1,mat):
        vertices=[];faces=[];n=80
        for z,r in ((z0,r0),(z0,r1),(z1,r0),(z1,r1)):
            vertices.extend((x+r*math.cos(2*math.pi*i/n),y+r*math.sin(2*math.pi*i/n),z) for i in range(n))
        for i in range(n):
            j=(i+1)%n
            faces.extend(((i,j,2*n+j,2*n+i),(n+j,n+i,3*n+i,3*n+j),
                          (j,i,n+i,n+j),(2*n+i,2*n+j,3*n+j,3*n+i)))
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);return finish(obj,name,mat)
    rounded('main_shell',(-.008,0,.003),(.094,.043,.0425),.012,shell)
    rounded('battery',(-.019,0,-.013),(.064,.034,.0225),.006,shell)
    rounded('battery_joint',(-.019,0,-.003),(.065,.035,.0012),.0005,rubber)
    rounded('camera_hood',(.038,0,.016),(.032,.034,.012),.005,shell)
    rounded('camera_gimbal',(.051,0,-.006),(.023,.027,.027),.005,black)
    cylinder('lens_bezel',(.063,0,-.006),.0072,.002,black,(0,math.pi/2,0))
    cylinder('lens',(.0642,0,-.006),.0055,.001,glass,(0,math.pi/2,0))
    rounded('mode_button',(.019,0,.024),(.010,.014,.0005),.0002,rubber)
    for i in range(4):
        rounded(f'battery_led_{i}',(-.021+i*.0035,0,.024),(.0015,.003,.0005),.0002,led)
    rounded('usb_c_rear',(-.0553,0,.006),(.0008,.009,.003),.001,black)
    for side in (-1,1):
        for i in range(5):
            rounded(f'vent_{side}_{i}',(-.025+i*.005,side*.0214,.001),(.0025,.0007,.007),.0003,black)
    centers=((.0315,.045),(-.0315,-.045),(.0315,-.045),(-.0315,.045))
    for i,(x,y) in enumerate(centers):
        annulus(f'duct_{i}',x,y,.0308,.0335,-.0055,.0035,guard)
        annulus(f'upper_rim_{i}',x,y,.0315,.0332,.004,.006,shell)
        cylinder(f'motor_{i}',(x,y,-.001),.0055,.011,rubber)
        cylinder(f'rotor_{i}_hub',(x,y,.006),.004,.002,black)
        for angle in (0,2*math.pi/3,4*math.pi/3):
            # Tapered, swept three-blade propeller. Estimated shape, no aero mesh.
            outline=((.004,-.002),(.014,-.0035),(.027,-.001),(.028,.002),(.015,.0045),(.005,.002))
            vertices=[]
            for z in (.0048,.0058):
                vertices.extend((x+u*math.cos(angle)-v*math.sin(angle),y+u*math.sin(angle)+v*math.cos(angle),z) for u,v in outline)
            faces=[tuple(range(5,-1,-1)),tuple(range(6,12))]+[(k,(k+1)%6,(k+1)%6+6,k+6) for k in range(6)]
            mesh=bpy.data.meshes.new('blade');mesh.from_pydata(vertices,[],faces);mesh.update()
            obj=bpy.data.objects.new(f'rotor_{i}_blade',mesh);bpy.context.collection.objects.link(obj);finish(obj,obj.name,black)
        # Thin elevated grille: one inner hoop plus three diameters, with a dome.
        tube(f'grille_hoop_{i}',[(x+.020*math.cos(j*2*math.pi/64),y+.020*math.sin(j*2*math.pi/64),.012) for j in range(65)],.00065,shell)
        for j in range(3):
            a=j*math.pi/3
            tube(f'grille_bar_{i}_{j}',[(x+s*.0318*math.cos(a),y+s*.0318*math.sin(a),.006+.009*(1-s*s)) for s in [k/8 for k in range(-8,9)]],.0007,shell)
        for j in range(4):
            a=j*math.pi/2
            tube(f'lower_spoke_{i}_{j}',[(x+.005*math.cos(a),y+.005*math.sin(a),-.005),
                                        (x+.032*math.cos(a),y+.032*math.sin(a),-.004)],.001,guard)
        tube(f'arm_{i}',[(x*.65,math.copysign(.016,y),-.002),(x,y,-.002)],.0035,shell)
    # Export original editable geometry before adding the photographic backdrop.
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=str(args.output/'neo_photo_reference.glb'),export_format='GLB',use_selection=True,export_apply=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'neo_photo_reference.blend'))
    source={'script_version':'neo-photo-model/0.1','seed':0,'parameter_preset':'neo_photo_reference',
        'author':'SyntheticPlantGeneration contributors','license':'MIT (original procedural geometry)',
        'reference_photos':'https://store.dji.com/product/dji-neo','dimensions_source':'https://www.dji.com/neo/specs',
        'dimensions_m':[.130,.157,.0485],'internal_dimensions_status':'engineering_heuristic',
        'source_type':'original_mesh_from_visual_reference_not_imported_CAD'}
    (args.output/'source.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32
    scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100
    scene.world.color=(.2,.2,.2)
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.025));bpy.context.object.data.materials.append(material('backdrop',(.12,.15,.18)))
    bpy.ops.object.camera_add(location=(.21,-.25,.23));camera=bpy.context.object
    camera.rotation_euler=(Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=.235;scene.camera=camera
    for loc,power,size in [((.10,-.10,.25),12,.20),((-.15,.10,.18),8,.18)]:
        bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size
        light.rotation_euler=(-light.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(args.output/'preview.png');bpy.ops.render.render(write_still=True)


if __name__=='__main__':main()
