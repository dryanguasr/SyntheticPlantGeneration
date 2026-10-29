"""Verify a budget-only authorized revision without rewriting a frozen lock."""
from pathlib import Path
from .nodal_automation import read,sha


def verify_frozen_inputs(root,inputs):
    root=Path(root);changed=[]
    lineage=read(root/'authorized_budget_revision.json') if (root/'authorized_budget_revision.json').exists() else None
    for name,expected in inputs.items():
        if sha(name)==expected:continue
        if Path(name).resolve()==(root/'budget.json').resolve() and lineage:
            previous=Path(lineage['previous_budget']);authorization=Path(lineage['authorization'])
            if (sha(previous)==expected==lineage['previous_sha256']
                and sha(name)==lineage['current_sha256'] and sha(authorization)==lineage['authorization_sha256']):
                old=read(previous);new=read(name);approval=read(authorization)
                if (new['awake_started_seconds']==old['awake_started_seconds']
                    and new['excluded_intervals']==old['excluded_intervals']
                    and new['limit_active_seconds']==approval['previous_active_seconds']+28800
                    and new['limit_active_seconds']>=old['limit_active_seconds']):
                    continue
        changed.append(name)
    return changed
