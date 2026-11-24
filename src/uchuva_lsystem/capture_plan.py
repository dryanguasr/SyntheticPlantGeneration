"""Pure capture scheduling and small atomic indexes, separate from plant load."""
from pathlib import Path
from copy import deepcopy
import random
from .nodal_automation import read, write, sha


def condition_for_view(scene_index,view_index,seed=20261029):
    """Independent appearance stream; never resample morphology or camera.

The existing reviewed diagnostic profiles supply diffuse/field/shade lighting.
Rotations/exposure offsets are engineering heuristics, not field measurements.
All effective values must be persisted with the view.
"""
    rng=random.Random(f'{seed}:capture_conditions:{scene_index}:{view_index}')
    return dict(diagnostic_light=('field','diffuse','shade')[(scene_index+view_index)%3],
                azimuth_offset_deg=rng.uniform(-35.,35.),
                elevation_offset_deg=rng.uniform(-8.,8.),
                exposure_offset_ev=rng.uniform(-.2,.2),
                provenance='engineering_heuristic; independent capture-only stream')


def profiles_for_condition(profiles,condition):
    """Resolve captured conditions without editing reviewed material profiles."""
    result=deepcopy(profiles)
    name=condition['diagnostic_light']
    light=dict(result['lighting']['candidate'])
    light.update(result['diagnostic_lights'][name])
    light['sun_azimuth_deg']+=condition.get('azimuth_offset_deg',0.)
    light['sun_elevation_deg']+=condition.get('elevation_offset_deg',0.)
    light['exposure_ev']+=condition.get('exposure_offset_ev',0.)
    result['diagnostic_lights']['capture_condition']=light
    return result,'capture_condition'


class CaptureJournal:
    """Each complete view.json is its commit; avoid rewriting all instances.

Compatible with spatial_dataset.committed_views(), which reads per-view files.
A small index stores counts/paths. Full legacy manifest is consolidated once.
Only the caller's newly generated view files are written.
"""
    def __init__(self,bank):
        self.bank=Path(bank)
        self.paths=[]
        self.identities=set()
        excluded=set(read(self.bank/'excluded_views.json').get('view_ids',[])) if (self.bank/'excluded_views.json').exists() else set()
        for path in sorted((self.bank/'views').glob('*/view.json')):
            row=read(path)
            if row.get('status')=='complete' and row.get('view_id') not in excluded:
                self.paths.append(str(path.resolve()));self.identities.add(row['view_id'])

    def commit(self,folder,row):
        path=Path(folder).resolve()/'view.json'
        if path.parent.parent != (self.bank/'views').resolve():
            raise ValueError('View commit must be directly inside bank/views')
        if row.get('status')!='complete' or row['view_id'] in self.identities or path.exists():
            raise ValueError('Cannot commit partial, duplicate or overwrite existing view')
        for key in ('image','mask','label'):
            if not Path(row[key]).is_file() or sha(row[key]) != row.get(key+'_sha256'):
                raise ValueError('Complete image/mask/label hashes required')
        write(path,row)
        self.paths.append(str(path));self.identities.add(row['view_id'])
        write(self.bank/'capture_index.json',dict(schema='uchuva.capture_index/1',
            complete_images=len(self.paths),view_records=self.paths,training_started=False))

    def consolidate(self):
        rows=[read(path) for path in self.paths]
        write(self.bank/'manifest.json',dict(views=rows,complete_images=len(rows),training_started=False))
        return rows
