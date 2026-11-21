"""Explicit, sparse reproductive admission from verified contact feedback.

This is an engineering omission of proposed units, not a measured abortion
model. It never edits Blender objects or annotations. Historical generation is
unchanged unless a source-bound plan is passed explicitly to the grammar.
"""
from copy import deepcopy
import hashlib
import json
import math

from .morphology import Plant
from .nodal_repulsion import axes, protected_anatomy

VERSION = "reproductive-space-admission/1"
KEY = "reproductive_space_admission"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def make_admission_plan(plant, conflicts, *, evidence_sha256, max_fruit_fraction=.01):
    """Minimum cardinality cover of confirmed conflicts; fixed organs stay.

    Each conflict is a nonempty set of reproductive unit IDs whose omission
    would eliminate that contact. A contact with a fixed stem has one choice.
    Deterministic tie break preserves lower node indices before higher ones.
    The fraction is a loss safety guard, never a fruit-load target or quota.
    """
    if not math.isfinite(max_fruit_fraction) or not 0 <= max_fruit_fraction <= .05:
        raise ValueError("Sparse admission requires an explicit loss guard <=5%")
    if len(evidence_sha256) != 64 or any(c not in '0123456789abcdef' for c in evidence_sha256):
        raise ValueError("Verified contact evidence SHA256 required")
    units = {n.reproductive_unit.id: n for a in axes(plant.axes) for n in a.nodes
             if n.reproductive_unit is not None}
    edges = sorted({tuple(sorted(set(edge))) for edge in conflicts})
    if any(not edge or len(edge) > 2 for edge in edges):
        raise ValueError("A contact must identify one or two removable units")
    if any(u not in units for edge in edges for u in edge):
        raise ValueError("Contact refers to a reproductive unit absent from this plant")
    if any(units[u].reproductive_unit.fruit is None or units[u].reproductive_unit.calyx is None
           for edge in edges for u in edge):
        raise ValueError("Only complete fruit-with-calyx units are eligible")
    anatomy = protected_anatomy(plant)
    budget = math.floor(anatomy['counts']['fruits'] * max_fruit_fraction + 1e-10)
    rank = lambda u: (-units[u].position_index, u)
    best = None

    def search(selected):
        nonlocal best
        if len(selected) > budget or (best is not None and len(selected) > len(best)):
            return
        pending = [edge for edge in edges if not selected.intersection(edge)]
        if not pending:
            score = (len(selected), tuple(sorted((rank(u) for u in selected))))
            if best is None or score < (len(best), tuple(sorted(rank(u) for u in best))):
                best = set(selected)
            return
        for u in sorted(min(pending, key=lambda e: (len(e), e)), key=rank):
            search(selected | {u})

    search(set())
    if best is None:
        raise ValueError("Verified contacts cannot be covered within the declared sparse-loss guard")
    return dict(version=VERSION, status='engineering_heuristic',
                source_anatomy=anatomy, evidence_sha256=evidence_sha256,
                conflicts=[list(e) for e in edges],
                selected_units=sorted(best), max_fruit_fraction=max_fruit_fraction,
                max_leaf_fraction=0., tie_break='preserve_lower_node_indices_then_unit_id',
                scope='verified static contacts after pose search; not general contact-free generation',
                biological_interpretation='not a measured abortion or developmental probability')


def apply_admission_plan(plant, plan):
    """Accept/omit candidate units before geometry, keeping the RNG stream intact."""
    if KEY in plant.metadata:
        raise ValueError("A reproductive admission has already been applied")
    expected = make_admission_plan(plant, plan['conflicts'],
                                   evidence_sha256=plan['evidence_sha256'],
                                   max_fruit_fraction=plan['max_fruit_fraction'])
    if expected != plan:
        raise ValueError("Admission plan differs from its anatomy, guard or deterministic solution")
    before = protected_anatomy(plant)
    selected = set(plan['selected_units'])
    records = []
    for axis in axes(plant.axes):
        for node in axis.nodes:
            u = node.reproductive_unit
            if u is None or u.id not in selected:
                continue
            if node.axillary_bud is None:
                raise ValueError("Reproductive admission requires the axillary bud")
            records.append(dict(node_id=node.id, reproductive_unit=u.to_dict(),
                                axillary_bud=node.axillary_bud.to_dict()))
    # Validate the entire operation before mutating the plant.
    if len(records) != len(selected):
        raise ValueError("Admission inventory is incomplete")
    for axis in axes(plant.axes):
        for node in axis.nodes:
            if node.reproductive_unit is None or node.reproductive_unit.id not in selected:
                continue
            node.reproductive_unit = None
            bud = node.axillary_bud
            bud.reproductive_unit_id = None
            bud.state = 'branch' if bud.branch_id is not None else 'dormant'
            bud.decision = 'reproductive_space_not_admitted'
            bud.provenance[KEY] = dict(plan_sha256=digest(plan), status='engineering_heuristic',
                                      biological_state='not_inferred')
    after = protected_anatomy(plant)
    plant.metadata[KEY] = dict(plan=deepcopy(plan), plan_sha256=digest(plan),
                               input_anatomy=before, output_anatomy=after,
                               omitted_units=records, omitted_units_sha256=digest(records),
                               materialized_before_geometry=True)
    from .grammar import record_reproductive_counts
    record_reproductive_counts(plant, 'generated')
    return plant.metadata[KEY]


def validate_admission(plant):
    """Undo recorded omissions in memory and verify all other anatomy unchanged."""
    record = plant.metadata.get(KEY)
    if record is None:
        return dict(applied=False)
    plan = record['plan']
    if record['plan_sha256'] != digest(plan) or record['omitted_units_sha256'] != digest(record['omitted_units']):
        raise ValueError("Reproductive admission snapshot hash differs")
    if record['output_anatomy'] != protected_anatomy(plant):
        raise ValueError("Retained anatomy differs from the generation admission")
    restored = deepcopy(plant.to_dict())
    nodes = {}
    def visit(items):
        for a in items:
            nodes.update((n['id'], n) for n in a['nodes'])
            visit(a['child_axes'])
    visit(restored['axes'])
    identities = []
    for item in record['omitted_units']:
        node = nodes[item['node_id']]
        if node['reproductive_unit'] is not None:
            raise ValueError("Omitted reproductive unit reappeared")
        identities.append(item['reproductive_unit']['id'])
        node['reproductive_unit'] = deepcopy(item['reproductive_unit'])
        node['axillary_bud'] = deepcopy(item['axillary_bud'])
    if sorted(identities) != plan['selected_units'] or len(set(identities)) != len(identities):
        raise ValueError("Omission inventory does not match the plan")
    original = Plant.from_dict(restored)
    if protected_anatomy(original) != record['input_anatomy'] or record['input_anatomy'] != plan['source_anatomy']:
        raise ValueError("Undo does not recover the complete original anatomy")
    if make_admission_plan(original, plan['conflicts'], evidence_sha256=plan['evidence_sha256'],
                           max_fruit_fraction=plan['max_fruit_fraction']) != plan:
        raise ValueError("Omission policy cannot be reproduced")
    return dict(applied=True, omitted_fruits=len(identities), omitted_leaves=0,
                retained_counts=record['output_anatomy']['counts'],
                original_anatomy_recovered=True, policy_status='engineering_heuristic')
