"""Regenerate ONLY the third candidate with explicit sparse contact admission."""
from pathlib import Path
from copy import deepcopy
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_lsystem.grammar import generate_morphology_tree, record_reproductive_counts
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import KEY, axes, protected_anatomy
from uchuva_lsystem.reproductive_space import make_admission_plan, validate_admission, digest


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def main():
    import argparse
    import hashlib
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    prior = ROOT/'outputs/nodal_controller_automation_20261027/plants/seed_2026102602_retry03'
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    raw = Plant.from_dict(read(prior/'raw.json'))
    pose = Plant.from_dict(read(prior/'plant.json'))
    assert raw.seed == pose.seed == 2026102602
    assert protected_anatomy(raw) == protected_anatomy(pose)
    mesh = read(prior/'final_independent_mesh.json')
    if mesh['truncated'] or len(mesh['physical_collisions']) != mesh['physical_collision_count']:
        raise ValueError('Complete confirmed mesh contacts required')
    calyces = {'uchuva_'+n.reproductive_unit.calyx.id: n.reproductive_unit.id
               for a in axes(raw.axes) for n in a.nodes
               if n.reproductive_unit and n.reproductive_unit.calyx}
    conflicts = []
    diagnostic = []
    for contact in mesh['physical_collisions']:
        eligible = [calyces[contact['object_'+s]] for s in ('a','b')
                    if contact['semantic_'+s] == 'calyx']
        if not eligible: raise ValueError('A contact without a reproductive endpoint cannot use this policy')
        conflicts.append(eligible)
        diagnostic.append({k:v for k,v in contact.items() if not k.startswith('triangle')})
    evidence = hashlib.sha256((prior/'final_independent_mesh.json').read_bytes()).hexdigest()
    plan = make_admission_plan(raw, conflicts, evidence_sha256=evidence, max_fruit_fraction=.01)
    kwargs = dict(params=raw.metadata['effective_parameters'],
                  phenology_profile=raw.metadata['phenology_profile'],
                  phenology_model=raw.metadata['phenology_model'], resolve_growth=False)
    regenerated = generate_morphology_tree(raw.seed, **kwargs)
    assert protected_anatomy(regenerated) == protected_anatomy(raw)
    plant = generate_morphology_tree(raw.seed, **kwargs, reproductive_space_plan=plan)
    generated_anatomy = protected_anatomy(plant)
    write(out/'raw_regenerated_unconstrained.json', regenerated.to_dict())
    write(out/'generated_before_pose.json', plant.to_dict())
    source_parts = {}
    target_parts = []
    def parts(p):
        for a in axes(p.axes):
            yield from a.internodes
            for n in a.nodes:
                if n.leaf: yield n.leaf
                if n.reproductive_unit:
                    yield n.reproductive_unit
                    yield n.reproductive_unit.pedicel
    source_parts = {p.id:p for p in parts(pose)}
    for part in parts(plant):
        if KEY in source_parts[part.id].provenance:
            part.provenance[KEY] = deepcopy(source_parts[part.id].provenance[KEY])
    plant.metadata['nodal_mobility_revisions'] = deepcopy(pose.metadata['nodal_mobility_revisions'])
    plant.metadata['nodal_repulsion_pending'] = False
    plant.metadata['nodal_repulsion'] = dict(method='explicit_replay_of_previous_pose',
        anatomy_before=generated_anatomy, anatomy_after=protected_anatomy(plant),
        source_pose_sha256=hashlib.sha256((prior/'plant.json').read_bytes()).hexdigest(),
        new_pose_search_executed=False)
    record_reproductive_counts(plant, 'adapted')
    assert generated_anatomy == protected_anatomy(plant)
    validation = validate_admission(plant)
    write(out/'admission_plan.json', plan)
    write(out/'plant.json', plant.to_dict())
    write(out/'diagnosis.json', dict(seed=plant.seed, confirmed_contacts=diagnostic,
        model_cause='Independent full-sized cohort assignment on short higher-order internodes; no space-admission gate before geometry.',
        search_limit='Fixed-length direction search left three verified contacts; infeasibility not proven.',
        correction='Sparse site admission after verified pose feedback, before geometry; whole units omitted in regenerated morphology.',
        omission_fraction=len(plan['selected_units'])/protected_anatomy(raw)['counts']['fruits'],
        limitations='Source-pose-specific contact plan; not an autonomous collision-free growth model or botanical abortion model.',
        generation_reproduced_original_anatomy=True, no_new_seeds=True, no_training=True,
        plan_sha256=digest(plan), validation=validation))
    print(json.dumps(dict(seed=plant.seed, omitted=plan['selected_units'], counts=generated_anatomy['counts'])))


if __name__ == '__main__': main()
