"""Export complete synthetic row views into exact raster supervision, never corner crops."""
import argparse,collections,hashlib,json,shutil
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args();root=args.root.resolve();protocol=json.loads((root/'protocol.json').read_text());out=root/'dataset';out.mkdir(exist_ok=False)
 rows=[];counts=collections.Counter();seen_hashes={};seeds={};contact_review=json.loads((root/'visual_admission.json').read_text()) if (root/'visual_admission.json').exists() else {}
 for scene in protocol['scenes']:
  split=scene['split'];seeds.setdefault(split,set()).update(x['seed'] for x in scene['plants'])
  for item in scene['plants']:assert sha(Path(item['path']))==item['sha256']
  folder=root/scene['name'];mapping=json.loads((folder/'class_mapping_private.json').read_text())
  captures=sorted(folder.glob('view_*/capture.json'));assert len(captures)==scene['views'],(scene['name'],len(captures))
  for capture in captures:
   f=capture.parent;meta=json.loads(capture.read_text());ann=json.loads((f/'annotations_private.json').read_text());assert sha(f/'rgb.png')==meta['rgb_sha256'];assert sha(f/'mask_calyx_crisp_v2.png')==meta['mask_sha256']
   rgb=cv2.imread(str(f/'rgb.png'));raw=np.array(Image.open(f/'mask_calyx_crisp_v2.png').convert('RGB'));assert rgb.shape==raw.shape==(720,1280,3);raster=np.zeros(raw.shape[:2],np.uint16);instances=[]
   known=np.all(raw==0,axis=2)
   for key,item in ann['items'].items():
    if key=='0':continue
    mask=np.all(raw==ann['palette'][key],axis=2);known|=mask;pixels=int(mask.sum());assert pixels==item['visible_pixels']
    if not pixels:continue
    assert item['semantic_class']=='calyx';label=mapping[item['instance_id']];cl=label['class_id'];assert cl in (0,1,2)
    mask_id=len(instances)+1;raster[mask]=mask_id;y,x=np.where(mask)
    instances.append(dict(mask_id=mask_id,instance_id=item['instance_id'],class_id=cl,bbox=[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],pixels=pixels));counts[(split,cl)]+=1
   assert known.all(),'Unexpected palette pixels';assert instances,'Empty frame: retain only if registered negative; none planned here'
   digest=meta['rgb_sha256'];assert digest not in seen_hashes,'Repeated RGB';seen_hashes[digest]=split
   name=scene['name']+'_'+f.name;impath=Path('images')/split/(name+'.png');mpath=Path('masks')/split/(name+'.png')
   for p in (out/impath,out/mpath):p.parent.mkdir(parents=True,exist_ok=True)
   shutil.copy2(f/'rgb.png',out/impath);assert cv2.imwrite(str(out/mpath),raster);assert np.array_equal(cv2.imread(str(out/mpath),-1),raster)
   admitted=contact_review.get('views',{}).get(scene['name']+'/'+f.name,{})
   rows.append(dict(image=impath.as_posix(),mask=mpath.as_posix(),image_size=[1280,720],split=split,scene=scene['name'],seeds=meta['seeds'],instances=instances,rgb_sha256=digest,raster_sha256=sha(out/mpath),contacts_visible=meta['visible_contact_pairs'],visual_admission=admitted))
 for a in seeds:
  assert not seeds[a]&set(range(914140,914146))
  for b in seeds:
   if a!=b:assert not seeds[a]&seeds[b]
 eligible=all(r['visual_admission'].get('accepted_for_recognition') is True for r in rows)
 (out/'raster_manifest.json').write_text(json.dumps(dict(version='synthetic-row-raster/181',images=rows),indent=2),encoding='utf-8')
 (out/'dataset.yaml').write_text('path: '+out.as_posix()+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: pintona\n  1: madura\n  2: sobremadura\n')
 contract=dict(version='synthetic-row-contract/181',training_eligible=eligible,technical_only=True,images=len(rows),instances=sum(len(r['instances']) for r in rows),class_counts={s:{str(c):counts[s,c] for c in range(3)} for s in seeds},seeds={s:sorted(v) for s,v in seeds.items()},image_shape=[1280,720],whole_frame=True,corners_only=False,all_visible_instances_included=True,split_disjoint_by_plant_and_scene=True,reserved_seeds_used=False,source='synthetic_only',preprocessing='INTER_LINEAR RGB matching standard inference; historical weights require compatibility explicitly',label_scope='calyx appearance only, not internal fruit maturity',limitations=[protocol['shared_topology_limitation'],'Small pilot, no claim of real-world generalization','Visibility sampling and manual review are recognition admission, not physics certification'],pending=[] if eligible else ['Visible-contact review not fully signed; no training'])
 (out/'dataset_contract.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
 # Inspectable RGB+mask overlays and contact locations, without changing training RGB.
 review=root/'dataset_review';review.mkdir(exist_ok=True);links=[]
 for i,row in enumerate(rows):
  rgb=np.array(Image.open(out/row['image']).convert('RGB'));mask=np.array(Image.open(out/row['mask']));overlay=rgb.copy()
  colors=[(255,180,40),(40,210,255),(240,90,200)]
  for item in row['instances']:
   m=mask==item['mask_id'];overlay[m]=(overlay[m]*.55+np.array(colors[item['class_id']])*.45).astype(np.uint8)
  im=Image.fromarray(overlay);im.thumbnail((640,360));im.save(review/f'{i:03d}.jpg',quality=93)
  links.append(f'<figure><a href="../dataset/{row["image"]}"><img src="{i:03d}.jpg"></a><figcaption>{row["scene"]} | {row["split"]} | {len(row["instances"])} capachos visibles | {row["contacts_visible"]} contactos visibles muestreados</figcaption></figure>')
 (review/'index.html').write_text('<meta charset="utf-8"><title>Piloto V142 en cultivo</title><style>body{background:#152126;color:#eee;font:16px system-ui}main{display:grid;grid-template-columns:repeat(2,1fr)}img{width:100%}figure{margin:10px}</style><h1>Cultivos V142 · RGB y máscaras sintéticas</h1><p>Color: pintona naranja · madura cian · sobremadura magenta. Clic para RGB completo. Sin recortes. Admisión para reconocimiento: '+str(eligible)+'</p><main>'+''.join(links)+'</main>',encoding='utf-8')
 print(json.dumps(contract),flush=True)
if __name__=='__main__':main()
