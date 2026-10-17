"""Several nurses: the best single-nurse route for every subset of visits, then the cheapest split of the visits.

The split is exact up to MAX_EXACT pending visits. Bigger days are assigned greedily and each nurse's route is then
solved exactly. Optional lab returns are added per nurse afterwards; required returns for sample age are only
modelled in the single-nurse solver, so here the age limit just rules routes out.
"""
import math
from dataclasses import dataclass
from functools import lru_cache

from . import tsptw

MAX_EXACT = 16
EPS = tsptw.EPS


@dataclass
class Shift:
    """One nurse's starting point for the part of the day still to plan."""
    key: object
    start: float
    end: float
    origin: int = tsptw.LAB
    oldest: float | None = None


@dataclass
class _Label:
    cost: float
    ready: float
    first: float
    parent: object
    visit: int


def subset_routes(visits, travel, shift, max_age=None):
    """Best route for every feasible subset of visits, as {bitmask: (travel, label)}. The empty subset is the
    trip back to the lab."""
    n = len(visits)
    track_age = max_age is not None
    none_on_board = math.inf
    start, origin = shift.start, shift.origin
    reach = [[k for k in range(n) if k != j and visits[j].opens + visits[j].service + travel[visits[j].node][
        visits[k].node] <= visits[k].closes + EPS] for j in range(n)]
    first_moves = [k for k in range(n) if start + travel[origin][visits[k].node] <= visits[k].closes + EPS]

    def push(states, key, label):
        bucket = states.setdefault(key, [])
        for other in bucket:
            if other.cost <= label.cost + EPS and other.ready <= label.ready + EPS and other.first >= label.first - EPS:
                return
        bucket[:] = [o for o in bucket if not (label.cost <= o.cost + EPS and label.ready <= o.ready + EPS
                                               and label.first >= o.first - EPS)]
        bucket.append(label)

    initial = (shift.oldest if shift.oldest is not None else none_on_board) if track_age else 0
    best = {}
    back = start + travel[origin][tsptw.LAB]
    if back <= shift.end + EPS and (not track_age or initial == none_on_board or back - initial <= max_age + EPS):
        best[0] = (travel[origin][tsptw.LAB], None)

    def extend(states, mask, node, label_ready, label_first, label_cost, parent, candidates):
        for k in candidates:
            bit = 1 << k
            if mask & bit:
                continue
            visit = visits[k]
            start_k = max(label_ready + travel[node][visit.node], visit.opens)
            if start_k > visit.closes + EPS:
                continue
            done = start_k + visit.service
            first = min(label_first, done) if track_age else 0
            if track_age and done - first > max_age + EPS:
                continue
            push(states, (mask | bit, k), _Label(label_cost + travel[node][visit.node], done, first, parent, k))

    layer = {}
    extend(layer, 0, origin, start, initial, 0.0, None, first_moves)
    while layer:
        following = {}
        for (mask, j), labels in layer.items():
            node = visits[j].node
            for label in labels:
                home = label.ready + travel[node][tsptw.LAB]
                if home <= shift.end + EPS and (not track_age or home - label.first <= max_age + EPS):
                    total = label.cost + travel[node][tsptw.LAB]
                    if total < best.get(mask, (math.inf,))[0] - EPS:
                        best[mask] = (total, label)
                extend(following, mask, node, label.ready, label.first, label.cost, label, reach[j])
        layer = following
    return best


def sequence_of(label):
    order = []
    while label is not None:
        order.append(label.visit)
        label = label.parent
    return order[::-1]


def split(tables, full):
    """Cheapest way to hand out the visits in full, one table per nurse. Returns (travel, masks) or None."""
    ordered = [sorted((cost, mask) for mask, (cost, _) in table.items()) for table in tables]
    last = len(tables) - 1

    @lru_cache(maxsize=None)
    def best(k, remaining):
        if k == last:
            entry = tables[k].get(remaining)
            return (entry[0], (remaining,)) if entry else (math.inf, None)
        found = (math.inf, None)
        for cost, mask in ordered[k]:
            if cost >= found[0]:
                break
            if mask & ~remaining:
                continue
            rest = best(k + 1, remaining ^ mask)
            if cost + rest[0] < found[0] - EPS:
                found = (cost + rest[0], (mask,) + rest[1])
        return found

    value, masks = best(0, full)
    return None if masks is None else (value, masks)


def plan(visits, travel, shifts, max_age=None):
    """Routes for every nurse, as a list of visit-index lists in shift order, or None when no split works."""
    n = len(visits)
    if n > MAX_EXACT:
        return _greedy(visits, travel, shifts, max_age)
    tables = [subset_routes(visits, travel, shift, max_age) for shift in shifts]
    result = split(tables, (1 << n) - 1)
    if result is None:
        return None
    routes = []
    for table, mask in zip(tables, result[1]):
        routes.append(sequence_of(table[mask][1]) if mask else [])
    return routes


def _greedy(visits, travel, shifts, max_age):
    assigned = [[] for _ in shifts]
    for k in sorted(range(len(visits)), key=lambda i: (visits[i].opens, visits[i].closes)):
        options = []
        for index, shift in enumerate(shifts):
            current = [visits[i] for i in assigned[index]]
            base = tsptw.evaluate(current, travel, list(range(len(current))), shift.start, shift.origin,
                                  oldest=shift.oldest)
            for position in range(len(current) + 1):
                trial = assigned[index][:position] + [k] + assigned[index][position:]
                route = tsptw.evaluate([visits[i] for i in trial], travel, list(range(len(trial))), shift.start,
                                       shift.origin, oldest=shift.oldest)
                if tsptw.is_feasible(route, shift.end, max_age):
                    options.append((route.travel - base.travel, index, position))
        if not options:
            return None
        _, index, position = min(options)
        assigned[index].insert(position, k)
    routes = []
    for index, shift in enumerate(shifts):
        subset = [visits[i] for i in assigned[index]]
        route = tsptw.solve(subset, travel, shift.start, shift.end, max_age, shift.origin, oldest=shift.oldest)
        routes.append([assigned[index][i] for i in route.sequence] if route else assigned[index])
    return routes
