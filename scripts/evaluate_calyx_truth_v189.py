"""Private error audit of frozen V188; no associations modified using truth."""
import json,hashlib
from pathlib import Path
import numpy as np
r=Path('outputs/integral_diagnosis_20261014');o=r/'field_geometry_evaluation_v189'
truth=json.loads((o/'evaluator_private/calyx_centers.json').read_text());b=json.loads((r/'field_tracking_v187/evaluator_private/board_private.json').read_text());R=np.array(b['R_world_from_marker']);center=np.array(b['center_world_bu'])
fits=json.loads((r/'field_localization_v188/triangulation.json').read_text());support=json.loads((r/'field_localization_v188/track_support_private.json').read_text());report={}
for variant,items in fits.items():
 rows=[];excluded=[]
 for fit in items:
  if fit['status']!='estimated':continue
  associations=support[variant]['support'][fit['track_id']]
  if len(associations)!=1:
   excluded.append(dict(track_id=fit['track_id'],reason='mixed_truth' if associations else 'no_native_match'));continue
  identity=next(iter(associations));actual=R.T@(np.array(truth['items'][identity]['center_world_bu'])-center)*.125
  delta=np.array(fit['position_marker_m'])-actual
  rows.append(dict(track_id=fit['track_id'],truth_id=identity,matched_support=associations[identity],error_m=float(np.linalg.norm(delta)),signed_error_marker_m=delta.tolist(),truth_center_marker_m=actual.tolist(),predicted_marker_m=fit['position_marker_m']))
 values=[v['error_m'] for v in rows]
 report[variant]=dict(evaluated_tracks=len(rows),unique_calyces=len(set(v['truth_id'] for v in rows)),median_error_m=float(np.median(values)),p90_error_m=float(np.percentile(values,90)),maximum_error_m=float(max(values)),tracks_below_5cm=sum(v<.05 for v in values),weak_single_frame_support=sum(v['matched_support']==1 for v in rows),excluded=excluded,rows=rows)
result=dict(definition=truth['definition'],units='metres',evaluation_selection='Only tracks with one unique class-aware IoU>=0.5 truth identity; excluded tracks retained, not silently scored as correct',variants=report,frozen_estimator_sha256=hashlib.sha256((r/'field_localization_v188/triangulation.json').read_bytes()).hexdigest(),production_promotion=False,campaign_complete=False)
(o/'evaluation_private.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:{a:b for a,b in v.items() if a not in ('rows','excluded')} for k,v in report.items()}))
