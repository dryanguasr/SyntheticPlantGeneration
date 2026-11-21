"""Experimental allocation contract, not a generated or validated plant.

Balances descendant node budgets before geometry. Uniform scaffold count and
vigor jitter are trial coverage choices, not botanical population estimates.
"""
from dataclasses import dataclass,asdict
import random


@dataclass(frozen=True)
class ScaffoldBudget:
    seed: int
    scaffold_count: int
    total_descendant_nodes: int
    node_budgets: tuple[int,...]
    version: str = 'scaffold-budget/1.0'
    parameter_status: str = 'engineering_heuristic_not_measured'
    count_distribution: str = 'uniform_trial_coverage_2_to_5_not_botanical'
    density_center_vs_exterior: str = 'pending_real_reference_characterization'
    geometry_generated: bool = False

    def to_dict(self):return asdict(self)


def allocate_scaffold_budget(total_nodes,seed,count=None):
    """Preserve total growth budget, using modest unequal vigor per scaffold.

    This budget excludes the common base. A later morphology generator must
    honor node attachments and branch order; this does not rearrange organs.
    """
    if type(total_nodes) is not int or total_nodes<10:raise ValueError('At least ten descendant nodes required')
    rng=random.Random(seed)
    if count is None:count=rng.randint(2,5)
    if type(count) is not int or count not in range(2,6):raise ValueError('Scaffold count must be 2..5')
    weights=[rng.uniform(.85,1.15) for _ in range(count)]
    exact=[total_nodes*w/sum(weights) for w in weights]
    budgets=[int(v) for v in exact]
    # Largest-remainder allocation preserves every node in the budget.
    order=sorted(range(count),key=lambda i:exact[i]-budgets[i],reverse=True)
    for i in order[:total_nodes-sum(budgets)]:budgets[i]+=1
    if min(budgets)<=0 or sum(budgets)!=total_nodes:raise AssertionError('Invalid budget partition')
    return ScaffoldBudget(seed,count,total_nodes,tuple(budgets))
