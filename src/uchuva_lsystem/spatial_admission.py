"""Two independent strict loss guards for camera-free morphological admission.

Whole leaves (blade, midrib and petiole) or complete fruiting reproductive
units can be omitted before geometry. Fixed axes and flowers are never removed.
This is explicit engineering thinning after verified pose feedback.
"""
from copy import deepcopy
import math
import time
from .morphology import Plant
from .nodal_repulsion import axes, protected_anatomy, KEY as POSE_KEY
from .reproductive_space import digest

KEY='spatial_admission_v2'


def strict_five_percent_budget(count):
    if isinstance(count,bool) or not isinstance(count,int) or count<0:
        raise ValueError('Original organ count must be a nonnegative integer')
    return max(0,(count-1)//20)


def eligible_organs(plant):
    result={}
    for a in axes(plant.axes):
        for n in a.nodes:
            if n.leaf:result['leaf:'+n.leaf.id]=('leaf',n)
            u=n.reproductive_unit
            if u and u.fruit and u.calyx:result['fruit:'+u.id]=('fruit',n)
    return result


def leaf_area_proxy(plant):
    """Nominal L*W blade envelope; not measured leaf surface or occlusion."""
    return sum(n.leaf.length_cm*n.leaf.width_cm for a in axes(plant.axes) for n in a.nodes if n.leaf)


def solve_cover(conflicts, kinds, budgets, *, max_seconds=3.):
    """Bounded deterministic vertex cover; never mistake timeout for infeasibility.

    Singleton constraints are forced. Return a feasible cover even when minimum
    cardinality cannot be proved. Separate class budgets always remain hard.
    """
    edges=sorted({tuple(sorted(set(e))) for e in conflicts})
    if any(not e for e in edges):raise ValueError('Fixed-organ collision cannot be thinned')
    if any(len(e)>2 or any(x not in kinds for x in e) for e in edges):raise ValueError('Invalid contact graph')
    forced={e[0] for e in edges if len(e)==1};deadline=time.monotonic()+max_seconds
    def fits(s):return all(sum(kinds[x]==k for x in s)<=budgets[k] for k in budgets)
    if not fits(forced):raise ValueError('Forced omissions exceed an original-count loss guard')
    def pending(s):return [e for e in edges if not s.intersection(e)]
    # Reproducible greedy candidate provides a bounded fallback before search.
    selected=set(forced)
    while (rest:=pending(selected)):
        degree={x:sum(x in e for e in rest) for e in rest for x in e}
        options=[x for x in degree if fits(selected|{x})]
        if not options:break
        x=min(options,key=lambda x:(-degree[x],sum(kinds[y]==kinds[x] for y in selected)/max(1,budgets[kinds[x]]),x))
        selected.add(x)
    best=selected if not pending(selected) else None;timed_out=False
    def search(s):
        nonlocal best,timed_out
        if time.monotonic()>=deadline:timed_out=True;return
        if not fits(s) or (best is not None and len(s)>=len(best)):return
        rest=pending(s)
        if not rest:best=set(s);return
        # A disjoint-edge matching is a safe lower bound for remaining removals.
        used=set();lb=0
        for e in rest:
            if not used.intersection(e):used.update(e);lb+=1
        if best is not None and len(s)+lb>=len(best):return
        edge=min(rest,key=lambda e:(sum(fits(s|{x}) for x in e),e))
        for x in sorted(edge):search(s|{x})
    search(forced)
    if best is None:raise ValueError('No cover found within loss guards'+(' before timeout' if timed_out else ''))
    return sorted(best),not timed_out


def make_plan(plant, conflicts, *, evidence_sha256):
    if KEY in plant.metadata or 'reproductive_space_admission' in plant.metadata:raise ValueError('Admission cannot reset cumulative loss budgets')
    if len(evidence_sha256)!=64 or any(c not in '0123456789abcdef' for c in evidence_sha256):raise ValueError('Evidence SHA256 required')
    organs=eligible_organs(plant);anatomy=protected_anatomy(plant)
    budgets=dict(fruit=strict_five_percent_budget(anatomy['counts']['fruits']),
                 leaf=strict_five_percent_budget(anatomy['counts']['leaves']))
    edges=sorted({tuple(sorted(set(e))) for e in conflicts})
    kinds={x:organs[x][0] for e in edges for x in e if x in organs}
    selected,optimal=solve_cover(edges,kinds,budgets)
    total_area=leaf_area_proxy(plant)
    lost_area=sum(organs[x][1].leaf.length_cm*organs[x][1].leaf.width_cm for x in selected if organs[x][0]=='leaf')
    if lost_area>=.05*total_area and lost_area>0:raise ValueError('Nominal blade-area loss also must be strictly below5%')
    return dict(version='strict-spatial-admission/2',source_anatomy=anatomy,
        conflicts=[list(e) for e in edges],selected=selected,budgets=budgets,
        strict_fraction_denominator=20,evidence_sha256=evidence_sha256,
        optimality_proven=optimal,status='engineering_heuristic',
        original_leaf_area_proxy_cm2=total_area,omitted_leaf_area_proxy_cm2=lost_area,
        biological_interpretation='not measured abscission or abortion',leaf_area_not_a_count='No surviving organ dimensions changed')


def apply_plan(plant,plan):
    if KEY in plant.metadata or 'reproductive_space_admission' in plant.metadata:raise ValueError('Admission already applied; cumulative guards cannot reset')
    organs=eligible_organs(plant)
    if protected_anatomy(plant)!=plan['source_anatomy']:raise ValueError('Plan belongs to another original anatomy')
    expected_budgets=dict(fruit=strict_five_percent_budget(plan['source_anatomy']['counts']['fruits']),leaf=strict_five_percent_budget(plan['source_anatomy']['counts']['leaves']))
    if plan['budgets']!=expected_budgets:raise ValueError('Loss guard changed')
    selected=set(plan['selected'])
    if len(selected)!=len(plan['selected']) or not selected<=organs.keys():raise ValueError('Unknown/duplicate omitted organ')
    if any(not selected.intersection(e) for e in plan['conflicts']):raise ValueError('Plan leaves an uncovered contact')
    for k in expected_budgets:
        if sum(organs[x][0]==k for x in selected)>expected_budgets[k]:raise ValueError('Cumulative loss guard exceeded')
    if any(kind=='fruit' and n.axillary_bud is None for x in selected for kind,n in [organs[x]]):
        raise ValueError('Reproductive unit has no bud')
    area=leaf_area_proxy(plant);lost=sum(organs[x][1].leaf.length_cm*organs[x][1].leaf.width_cm for x in selected if organs[x][0]=='leaf')
    if plan.get('original_leaf_area_proxy_cm2')!=area or plan.get('omitted_leaf_area_proxy_cm2')!=lost or (lost>0 and lost>=.05*area):
        raise ValueError('Nominal blade-area loss guard changed')
    records=[]
    # A node may lose both structures, so store the complete original node once.
    nodes={organs[x][1].id:organs[x][1] for x in selected}
    for n in nodes.values():records.append(n.to_dict())
    for x in sorted(selected):
        kind,n=organs[x]
        if kind=='leaf':n.leaf=None
        else:
            if n.axillary_bud is None:raise ValueError('Reproductive unit has no bud')
            n.reproductive_unit=None;n.axillary_bud.reproductive_unit_id=None
            n.axillary_bud.state='branch' if n.axillary_bud.branch_id else 'dormant'
            n.axillary_bud.decision='spatial_admission_not_materialized'
            n.axillary_bud.provenance[KEY]=dict(plan_sha256=digest(plan),status='engineering_heuristic')
    plant.metadata[KEY]=dict(plan=deepcopy(plan),plan_sha256=digest(plan),
        original_nodes=records,original_nodes_sha256=digest(records),output_anatomy=protected_anatomy(plant))
    from .grammar import record_reproductive_counts
    record_reproductive_counts(plant,'generated')
    validate_plan(plant)


def validate_plan(plant):
    r=plant.metadata.get(KEY)
    if not r:return dict(applied=False)
    p=r['plan']
    if digest(p)!=r['plan_sha256'] or digest(r['original_nodes'])!=r['original_nodes_sha256']:raise ValueError('Spatial admission snapshot changed')
    if protected_anatomy(plant)!=r['output_anatomy']:raise ValueError('Retained anatomy changed after admission')
    restored=deepcopy(plant.to_dict());originals={n['id']:n for n in r['original_nodes']}
    selected=set(p['selected']);seen=set()
    def visit(items):
        for a in items:
            for i,n in enumerate(a['nodes']):
                if n['id'] in originals:
                    old=deepcopy(originals[n['id']]);expected=deepcopy(n)
                    if old.get('leaf') and 'leaf:'+old['leaf']['id'] in selected:
                        if n.get('leaf') is not None:raise ValueError('Omitted leaf reappeared')
                        expected['leaf']=old['leaf'];seen.add('leaf:'+old['leaf']['id'])
                    u=old.get('reproductive_unit')
                    if u and 'fruit:'+u['id'] in selected:
                        if n.get('reproductive_unit') is not None:raise ValueError('Omitted fruit unit reappeared')
                        expected['reproductive_unit']=u;expected['axillary_bud']=old['axillary_bud'];seen.add('fruit:'+u['id'])
                    a['nodes'][i]=expected
            visit(a['child_axes'])
    visit(restored['axes'])
    restored_plant=Plant.from_dict(restored)
    if seen!=selected or protected_anatomy(restored_plant)!=p['source_anatomy']:raise ValueError('Undo does not restore original anatomy')
    original_area=leaf_area_proxy(restored_plant);area_loss=original_area-leaf_area_proxy(plant)
    if not math.isclose(original_area,p['original_leaf_area_proxy_cm2'],rel_tol=1e-12) or not math.isclose(area_loss,p['omitted_leaf_area_proxy_cm2'],rel_tol=1e-9,abs_tol=1e-8):raise ValueError('Nominal blade-area accounting differs')
    if area_loss>1e-8 and area_loss>=.05*original_area:raise ValueError('Nominal blade-area loss guard exceeded')
    before=p['source_anatomy']['counts'];after=r['output_anatomy']['counts']
    losses=dict(fruit=before['fruits']-after['fruits'],leaf=before['leaves']-after['leaves'])
    expected=dict(fruit=strict_five_percent_budget(before['fruits']),leaf=strict_five_percent_budget(before['leaves']))
    if p['budgets']!=expected or any(v<0 or v>expected[k] for k,v in losses.items()):raise ValueError('Strict cumulative loss guard violated')
    return dict(applied=True,losses=losses,original_counts=before,retained_counts=after,
                fruit_loss_fraction=losses['fruit']/max(1,before['fruits']),leaf_loss_fraction=losses['leaf']/max(1,before['leaves']),
                leaf_nominal_area_loss_fraction=area_loss/max(1e-30,original_area),original_anatomy_recovered=True)


def replay_pose(source,target):
    def parts(p):
        for a in axes(p.axes):
            yield from a.internodes
            for n in a.nodes:
                if n.leaf:yield n.leaf
                if n.reproductive_unit:yield n.reproductive_unit;yield n.reproductive_unit.pedicel
    old={p.id:p for p in parts(source)}
    for p in parts(target):
        if POSE_KEY in old[p.id].provenance:p.provenance[POSE_KEY]=deepcopy(old[p.id].provenance[POSE_KEY])
    target.metadata['nodal_mobility_revisions']=deepcopy(source.metadata.get('nodal_mobility_revisions',[]))
    target.metadata['nodal_repulsion_pending']=False
    target.metadata['nodal_repulsion']=dict(method='pose_replay_after_spatial_admission',anatomy_after=protected_anatomy(target))
    from .grammar import record_reproductive_counts
    record_reproductive_counts(target,'adapted')
    validate_plan(target)
