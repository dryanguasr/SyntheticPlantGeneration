"""Small actual-Blender fixtures; no render or GPU."""
import argparse,json,sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
import bpy
from uchuva_lsystem.blender_environment import audit_plant_ground_clearance

def clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=.125
def mesh(name,vertices,faces,semantic=None):
    data=bpy.data.meshes.new(name);data.from_pydata(vertices,[],faces);data.update()
    obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj)
    if semantic:obj['uchuva_semantic_class']=semantic;obj['uchuva_plant_id']='fixture';obj['uchuva_plant_role']='foreground'
    return obj
def ground():return mesh('uchuva_terrain_agricultural',[(-2,-2,0),(2,-2,0),(2,2,0),(-2,2,0)],[(0,1,2,3)])
def leaf(z,x=0):return mesh('leaf',[(x,0,z),(x+.1,0,z),(x,.1,z)],[(0,1,2)],'leaf')
def check(name,fn):
    clear();ground();fn();bpy.context.view_layer.update();result=audit_plant_ground_clearance(seed=1);reports[name]=result;return result
reports={}
r=check('valid_leaf',lambda:leaf(.02));assert r['status']=='valid';assert abs(r['required_clearance_blender_units']-.008)<1e-12
r=check('positive_clearance_deficit',lambda:leaf(.004));assert r['physical_collision_count']==0 and r['clearance_violation_count']==1 and r['status']=='invalid'
r=check('leaf_below_ground',lambda:leaf(-.02));assert r['physical_collision_count']==1
r=check('triangle_crosses_ground',lambda:mesh('leaf',[(0,0,-.1),(.1,0,.1),(0,.1,.1)],[(0,1,2)],'leaf'));assert r['physical_collisions'][0]['forbidden_triangle_intersections']>0
r=check('terrain_coverage_unknown',lambda:leaf(.02,x=4));assert r['coverage_failure_count']==1 and r['status']=='invalid'
r=check('no_visible_organs',lambda:None);assert r['status']=='invalid'
def basal(points):
    data=bpy.data.curves.new('basal','CURVE');data.dimensions='3D';data.bevel_depth=.01;data.bevel_resolution=0;data.use_fill_caps=True
    spline=data.splines.new('POLY');spline.points.add(len(points)-1)
    for p,co in zip(spline.points,points):p.co=(*co,1)
    obj=bpy.data.objects.new('basal',data);bpy.context.scene.collection.objects.link(obj)
    for k,v in {'uchuva_semantic_class':'stem','uchuva_plant_id':'fixture','uchuva_plant_role':'foreground','uchuva_organ_kind':'axis_segment','uchuva_axis_order':0,'uchuva_internode_index':0,'uchuva_axis_parent_node_id':'','uchuva_node_start_id':''}.items():obj[k]=v
r=check('local_basal_contact',lambda:basal([(0,0,-.005),(0,0,.5)]));assert r['status']=='valid' and r['intentional_contact_count']==1,r
r=check('nonlocal_basal_crossing',lambda:basal([(0,0,-.005),(0,0,.3),(.3,0,-.1)]));assert r['physical_collision_count']==1 and r['status']=='invalid'
def changed_scale():
    leaf(.02)
    bpy.context.scene.unit_settings.scale_length=.25
r=check('explicit_scale_conversion',changed_scale)
assert r['status']=='valid' and abs(r['required_clearance_blender_units']-.004)<1e-12
assert abs(r['objects'][0]['minimum_vertical_clearance_m']-.005)<1e-8
def hidden_interior():
    leaf(.02)
    obj=mesh('hidden_calyx',[(0,0,-1),(.1,0,-1),(0,.1,-1)],[(0,1,2)],'calyx')
    obj.hide_render=True
r=check('hidden_organs_preserved_and_excluded',hidden_interior)
assert r['status']=='valid' and r['tested_object_count']==1 and bpy.data.objects['hidden_calyx'].hide_render
def fruit(z,hidden):
    obj=mesh('fruit',[(0,0,0),(.1,0,0),(0,.1,0)],[(0,1,2)],'ignore')
    obj.location.z=z
    obj['uchuva_organ_kind']='fruit';obj['uchuva_reproductive_instance_id']='fixture:unit0'
    obj['uchuva_rendered_visibility_scale']=.9 if hidden else 1.03
    obj.hide_render=hidden;obj.hide_viewport=hidden;obj.hide_set(hidden)
    return obj
r=check('visible_ignore_fruit_below_soil',lambda:fruit(-.02,False))
assert r['physical_collision_count']==1 and r['objects'][0]['semantic']=='fruit'
assert r['objects'][0]['annotation_semantic_class']=='ignore' and not r['objects'][0]['hidden_in_rgb']
r=check('hidden_internal_fruit_below_soil',lambda:fruit(-.02,True))
assert r['physical_collision_count']==1 and r['objects'][0]['hidden_in_rgb']
assert bpy.data.objects['fruit'].hide_render and bpy.data.objects['fruit'].hide_viewport and bpy.data.objects['fruit'].hide_get()
assert abs(r['objects'][0]['minimum_vertical_clearance_m']+.0025)<1e-8
r=check('hidden_internal_fruit_above_soil',lambda:fruit(.02,True))
assert r['status']=='valid' and abs(r['objects'][0]['rendered_visibility_scale']-.9)<1e-6,r
assert bpy.data.objects['fruit']['uchuva_semantic_class']=='ignore' and bpy.data.objects['fruit'].hide_render
clear();ground();obj=fruit(.02,True)
try:
    audit_plant_ground_clearance(seed=1,required_clearance_m=-1)
    raise AssertionError('Expected invalid clearance')
except ValueError:
    assert obj.hide_render and obj.hide_viewport and obj.hide_get()
reports['failure_restores_hidden_fruit_flags']={'passed':True}
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
result={'tests':14,'all_passed':True,'reports':reports}
if args.output:
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
print('ALL FOURTEEN GROUND FIXTURES PASS',flush=True)
