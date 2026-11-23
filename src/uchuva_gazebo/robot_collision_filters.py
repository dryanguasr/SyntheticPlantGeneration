"""Compile declared extra exclusions into exact SDF 16-bit collision masks.

DART already excludes neighboring joints. Additional mechanical pairs must
have zero mask intersection without suppressing any other physical pair.
The construction is verified exhaustively before an SDF may be exported.
"""
from __future__ import annotations
import itertools
import random


def collision_masks(data):
    active = [row['name'] for row in data['links'] if row['collisions']]
    neighbors = {tuple(sorted((j['parent'],j['child']))) for j in data['joints']}
    declared = {tuple(sorted(row['links'])) for row in data['collision_policy']['excluded_pairs']}
    if not neighbors <= declared:
        raise ValueError('DART adjacency exclusions must be declared')
    all_pairs = {tuple(sorted(p)) for p in itertools.combinations(active,2)}
    extra = (declared-neighbors) & all_pairs
    required = all_pairs-declared
    if not extra:
        return {row['name']:65535 for row in data['links']}
    # A clique contributes one bit. Only extra forbidden pairs constrain the
    # cliques; native adjacency handles its own exclusions. Dense complement
    # graphs for linkage closures typically require fewer than sixteen bits.
    forbidden = {name:set() for name in active}
    for a,b in extra:
        forbidden[a].add(b); forbidden[b].add(a)
    generator = random.Random(20261123)
    candidates = set()
    for index in range(2048):
        order = list(active)
        if index:
            generator.shuffle(order)
        clique = []
        for name in order:
            if not any(other in forbidden[name] for other in clique):
                clique.append(name)
        candidates.add(tuple(sorted(clique)))
    coverage = [(clique,{tuple(sorted(p)) for p in itertools.combinations(clique,2)} & required)
                for clique in sorted(candidates)]
    masks = {row['name']:0 for row in data['links']}
    remaining = set(required)
    bit = 0
    while remaining:
        clique, covered = max(coverage, key=lambda item:len(item[1]&remaining))
        if bit >= 16 or not covered & remaining:
            raise ValueError('Declared pair graph cannot be represented by the verified 16-bit adapter')
        for name in clique:
            masks[name] |= 1<<bit
        remaining -= covered
        bit += 1
    for name in active:
        if masks[name] == 0:
            # An isolated collision body must still contact external all-bit
            # environment bodies, even if it has no allowed internal neighbor.
            if bit >= 16:
                raise ValueError('No collision bit available for isolated body')
            masks[name] = 1<<bit
            bit += 1
    if any(masks[a]&masks[b] for a,b in extra) or any(not masks[a]&masks[b] for a,b in required):
        raise ValueError('Collision mask compilation failed exact pair verification')
    return masks
