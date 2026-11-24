"""Blender CPU geometry extraction only: no render or GPU workload."""
import json
from pathlib import Path
import sys
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology

def main():
    root=ROOT/'outputs/integral_diagnosis_20261014'
    out=root/'basal_balance_diagnostic';out.mkdir(exist_ok=False)
    reports=[]
    for seed in (814140,814141,814142):
        plant=Plant.from_dict(json.loads((root/'fixtures'/f'basal_{seed}_3.json').read_text()))
        selected=plant.metadata['basal_architecture']['selected_axes']
        groups={};metrics=[dict(nodes=0,reproductive_units=0,axis_path_length=0.,subtree_length=0.) for _ in range(3)]
        def walk(axis,group):
            if axis.id in selected:group=selected.index(axis.id)+1
            groups[axis.id]=group
            base=2 if axis is plant.axes[0] else 0
            length=sum(s.length_cm for s in axis.internodes[base:])
            metrics[group]['subtree_length']+=length
            metrics[group]['nodes']+=len(axis.nodes)-base
            metrics[group]['reproductive_units']+=sum(n.reproductive_unit is not None for n in axis.nodes[base:])
            if axis is plant.axes[0] or axis.id in selected:metrics[group]['axis_path_length']=length
            for child in axis.child_axes:walk(child,group)
        walk(plant.axes[0],0)
        reports.append(dict(seed=seed,groups=metrics))
        if seed!=814140:continue
        cleanup_scene();build_geometry_from_morphology(plant,create_project_materials(seed),add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update();curves=[]
        for obj in bpy.context.scene.objects:
            if obj.get('uchuva_semantic_class')!='stem' or obj.type!='CURVE':continue
            axis=obj.get('uchuva_axis_id');group=groups.get(axis)
            if group is None:raise ValueError(f'Unknown axis {axis}: {list(obj.keys())}')
            for spline in obj.data.splines:
                pts=[obj.matrix_world@p.co for p in spline.bezier_points] if spline.type=='BEZIER' else [obj.matrix_world@p.co.xyz for p in spline.points]
                curves.append(dict(group=group,axis=axis,points=[list(p) for p in pts],base=axis==plant.axes[0].id and obj.get('uchuva_internode_index',99)<2))
        if not curves:raise ValueError('No stem geometry extracted')
        (out/'stems.json').write_text(json.dumps(curves))
    (out/'metrics.json').write_text(json.dumps(dict(reports=reports,group_names=['Continuacion principal','Rama basal 2','Rama basal 3'],
        note='Current unmodified pilot. Counts partition existing morphology, shared basal nodes excluded. Lengths compared as ratios; no measured real distribution.',version='basal-balance-diagnostic/1.0'),indent=2))

if __name__=='__main__':main()
