"""Ordered finite-domain search with an interruptible forward-checking loop.

A time cutoff is distinct from exhausting the supplied discrete domains.
Neither outcome proves continuous geometric infeasibility.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ConstraintSearchResult:
    status: str
    selected: tuple | None
    compatibility_calls: int


def solve_ordered_domains(domains, compatible, *, expired):
    calls = 0

    class DeadlineReached(Exception):
        pass

    def check():
        if expired():
            raise DeadlineReached

    def search(position, remaining, chosen):
        nonlocal calls
        check()
        if position == len(remaining):
            return tuple(chosen)
        for candidate in remaining[position]:
            check()
            next_domains = list(remaining)
            possible = True
            for other in range(position+1, len(remaining)):
                filtered = []
                for value in remaining[other]:
                    # Check inside the wide loop, not only at recursion entry.
                    check()
                    calls += 1
                    allowed = compatible(position, candidate, other, value)
                    check()
                    if allowed:
                        filtered.append(value)
                next_domains[other] = filtered
                if not filtered:
                    possible = False
                    break
            if possible:
                selected = search(position+1, next_domains, chosen+[candidate])
                if selected is not None:
                    return selected
        return None

    try:
        selected = search(0, [list(d) for d in domains], [])
    except DeadlineReached:
        return ConstraintSearchResult('time_budget_exhausted', None, calls)
    return ConstraintSearchResult('compatible' if selected is not None else 'discrete_domains_exhausted', selected, calls)
