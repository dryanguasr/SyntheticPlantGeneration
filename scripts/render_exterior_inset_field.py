"""Render the recorded field from a fixed exterior camera (Blender)."""
import bpy, json, sys, math, xml.etree.ElementTree as ET
import numpy as np
from pathlib import Path
from mathutils import Vector, Euler
root=Path(sys.argv[sys.argv.index('--')+1]).resolve()
out=root/'presentation/exterior_inset';out.mkdir(exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
field=root/'field_batched';tree=ET.parse(field/'field.sdf');materials={}; texture_colors={}
for i,v in enumerate(tree.findall('.//visual')):
 color=tuple(map(float,v.findtext('material/diffuse','0.4 0.5 0.2 1').split()))
 texture=v.findtext('material/pbr/metal/albedo_map')
 if texture:
  if texture not in texture_colors:
   img=bpy.data.images.load(str(field/texture)); pixels=np.array(img.pixels[:]).reshape(-1,4); texture_colors[texture]=tuple(pixels[:,:3].mean(axis=0))+(1.0,);bpy.data.images.remove(img)
  color=texture_colors[texture]
 if color not in materials:
  m=bpy.data.materials.new(str(color));m.diffuse_color=color;materials[color]=m
 geom=v.find('geometry');pose=list(map(float,v.findtext('pose','0 0 0 0 0 0').split()))
 if geom.find('mesh') is not None:
  verts=[];faces=[]
  with (field/geom.findtext('mesh/uri')).open() as f:
   for line in f:
    if line.startswith('v '):verts.append(tuple(map(float,line.split()[1:4])))
    elif line.startswith('f '):faces.append(tuple(int(x.split('/')[0])-1 for x in line.split()[1:]))
  mesh=bpy.data.meshes.new(v.attrib['name']);mesh.from_pydata(verts,[],faces);mesh.update()
  obj=bpy.data.objects.new(v.attrib['name'],mesh);bpy.context.collection.objects.link(obj)
  obj.scale=tuple(map(float,geom.findtext('mesh/scale','1 1 1').split()))
 else:
  bpy.ops.mesh.primitive_cube_add(size=1);obj=bpy.context.object;obj.dimensions=tuple(map(float,geom.findtext('box/size').split()))
 obj.location=pose[:3];obj.rotation_euler=Euler(pose[3:]);obj.data.materials.append(materials[color])
 if i%300==0:print('IMPORT',i,flush=True)
scene=bpy.context.scene
bpy.ops.object.camera_add(location=(11,-15,17));cam=bpy.context.object
cam.rotation_euler=(Vector((0,0,.3))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=22
scene.camera=cam;scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
scene.render.resolution_x=480;scene.render.resolution_y=320;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out/'field.png')
bpy.context.view_layer.update()
projection=cam.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=480,y=320) @ cam.matrix_world.inverted()
(out/'camera.json').write_text(json.dumps({'projection':[list(r) for r in projection],'width':480,'height':320}))
bpy.ops.render.render(write_still=True)
