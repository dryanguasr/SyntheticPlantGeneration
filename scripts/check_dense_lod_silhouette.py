"""Compare exact orthographic leaf silhouettes of original and LOD triangle assets."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np

def silhouette(folder, organs, center_x):
    mask=np.zeros((800,640),np.uint8);by_mesh={}
    for organ in organs:
        for uri in organ['meshes']:by_mesh.setdefault(uri,set()).add(organ['object'])
    for uri,names in by_mesh.items():
        vertices=[];active=False
        with (folder/uri).open() as stream:
            for line in stream:
                if line.startswith('# source '):active=line.strip()[9:] in names
                elif line.startswith('v '):
                    x,y,z=map(float,line.split()[1:4]);vertices.append((round((x-center_x+1.25)*256),round((2.25-z)*320)))
                elif active and line.startswith('f '):
                    tri=np.array([vertices[int(s.split('/')[0])-1] for s in line.split()[1:]],np.int32)
                    cv2.fillConvexPoly(mask,tri,255)
    return mask

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--lod',type=Path,required=True);p.add_argument('--input',type=Path,required=True)
    a=p.parse_args();m=json.loads((a.source/'manifest.json').read_text());scene=json.loads(a.input.read_text())['scene']
    positions={v['plant_id']:v['position'][0]/8 for v in scene['plant_instances']};rows=[]
    for identifier in ('plant_13','plant_03','plant_27'):
        organs=[o for o in m['organs'] if o['plant_id']==identifier and o['semantic_class']=='leaf' and not o['organ_id'].endswith('_midrib')]
        before=silhouette(a.source,organs,positions[identifier]);after=silhouette(a.lod,organs,positions[identifier])
        union=np.count_nonzero((before>0)|(after>0));inter=np.count_nonzero((before>0)&(after>0))
        row={'plant_id':identifier,'original_pixels':int(np.count_nonzero(before)),'lod_pixels':int(np.count_nonzero(after)),
             'silhouette_iou':inter/union,'coverage_ratio':np.count_nonzero(after)/np.count_nonzero(before)}
        rows.append(row);cv2.imwrite(str(a.lod/f'{identifier}_silhouette_original.png'),before);cv2.imwrite(str(a.lod/f'{identifier}_silhouette_lod.png'),after)
    result={'script_version':'dense-lod-silhouette/1.0','seed':m['seed'],'parameter_preset':m['crown_preset'],
        'method':'binary triangle union in fixed orthographic X/Z window; not perspective RGB or occlusion rate',
        'heuristic_gate':'IoU >= .95 and relative coverage difference <= .05 for all three reviewed crowns',
        'passed':all(r['silhouette_iou']>=.95 and abs(r['coverage_ratio']-1)<=.05 for r in rows),'plants':rows}
    (a.lod/'silhouette_validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
