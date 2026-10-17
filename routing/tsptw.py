"""One nurse's day as a travelling salesman problem with time windows (TSPTW).

Times are minutes after midnight. travel[a][b] is indexed by node; node 0 is the lab and each visit carries its own
node. A route may pass by the lab between visits to drop samples off: the solver adds those stops only when the
maximum sample age requires them, and add_lab_breaks adds optional ones afterwards.
"""
import math
from dataclasses import dataclass, field

LAB = 0
MAX_EXACT = 14
EPS = 1e-6


@dataclass(frozen=True)
class Visit:
    key: object
    opens: float
    closes: float
    service: float
    node: int


@dataclass
class Leg:
    key: object
    arrival: float
    start: float
    departure: float
    travel: float
    wait: float
    late: float
    kind: str = "visit"


@dataclass
class Route:
    legs: list = field(default_factory=list)
    depart: float = 0
    back: float = 0
    travel: float = 0
    late: float = 0
    method: str = "exact"
    oldest_age: float = 0
    sequence: list = field(default_factory=list)
    via: frozenset = frozenset()

    @property
    def keys(self):
        return [leg.key for leg in self.legs if leg.kind == "visit"]

    @property
    def visit_legs(self):
        return [leg for leg in self.legs if leg.kind == "visit"]


def evaluate(visits, travel, sequence, start_time, origin=LAB, via=frozenset(), drop=0, oldest=None,
             method="fixed"):
    """Times for visiting visits[i] for i in sequence, starting at node origin at start_time.

    via holds the positions in sequence that are preceded by a stop at the lab. The nurse leaves as late as the
    next visit allows, so waiting happens at the lab rather than on the road whenever she passes by it.
    """
    via = frozenset(via)
    if not sequence:
        back = start_time + travel[origin][LAB]
        age = back - oldest if oldest is not None else 0
        return Route(depart=start_time, back=back, travel=travel[origin][LAB], method=method, oldest_age=age)
    first = visits[sequence[0]]
    lead = travel[origin][first.node] if 0 not in via else 0
    depart = max(start_time, first.opens - lead) if 0 not in via else start_time
    clock, prev, total, late, legs = depart, origin, 0.0, 0.0, []
    trip_first, worst_age = oldest, 0.0
    for position, i in enumerate(sequence):
        visit = visits[i]
        if position in via and prev != LAB:
            leg = travel[prev][LAB]
            arrive = clock + leg
            if trip_first is not None:
                worst_age = max(worst_age, arrive - trip_first)
            leave = max(arrive + drop, visit.opens - travel[LAB][visit.node])
            legs.append(Leg(None, arrive, arrive, leave, leg, leave - arrive - drop, 0.0, "lab"))
            total += leg
            clock, prev, trip_first = leave, LAB, None
        leg = travel[prev][visit.node]
        arrival = clock + leg
        start = max(arrival, visit.opens)
        legs.append(Leg(visit.key, arrival, start, start + visit.service, leg, start - arrival,
                        max(0.0, start - visit.closes)))
        late += legs[-1].late
        total += leg
        clock, prev = start + visit.service, visit.node
        if trip_first is None:
            trip_first = clock
    back = clock + travel[prev][LAB]
    if trip_first is not None:
        worst_age = max(worst_age, back - trip_first)
    return Route(legs, depart, back, total + travel[prev][LAB], late, method, worst_age, list(sequence), via)


def is_feasible(route, shift_end, max_age=None):
    if route.late > EPS or route.back > shift_end + EPS:
        return False
    return max_age is None or route.oldest_age <= max_age + EPS


@dataclass
class _Label:
    cost: float
    ready: float
    first: float
    parent: object
    visit: int
    via: bool


def _add(states, key, label):
    labels = states.setdefault(key, [])
    if any(o.cost <= label.cost + EPS and o.ready <= label.ready + EPS and o.first >= label.first - EPS
           for o in labels):
        return
    labels[:] = [o for o in labels if not (label.cost <= o.cost + EPS and label.ready <= o.ready + EPS
                                           and label.first >= o.first - EPS)]
    labels.append(label)


def _unwind(label):
    sequence, via = [], set()
    chain = []
    while label is not None:
        chain.append(label)
        label = label.parent
    for position, label in enumerate(reversed(chain)):
        sequence.append(label.visit)
        if label.via:
            via.add(position)
    return sequence, frozenset(via)


def solve(visits, travel, start_time, shift_end, max_age=None, origin=LAB, drop=0, oldest=None):
    """Cheapest feasible route through all visits, or None when no order keeps every promise.

    Exact dynamic program over (visited set, last visit) with labels (travel so far, time she can leave, end time
    of the oldest sample on board). With a sample age limit, each move can also go by the lab first.
    """
    n = len(visits)
    if n == 0:
        route = evaluate(visits, travel, [], start_time, origin, oldest=oldest)
        return route if is_feasible(route, shift_end, max_age) else None
    if n > MAX_EXACT:
        return _insertion(visits, travel, start_time, shift_end, max_age, origin, drop, oldest)
    track_age = max_age is not None
    age = max_age if track_age else math.inf
    none_on_board = math.inf
    full = (1 << n) - 1

    def reachable(mask, node, ready):
        return all(mask >> k & 1 or ready + travel[node][visits[k].node] <= visits[k].closes + EPS for k in range(n))

    def moves(mask, node, ready, first, cost, parent):
        for k in range(n):
            if mask >> k & 1:
                continue
            visit = visits[k]
            options = [(ready + travel[node][visit.node], first, cost + travel[node][visit.node], False)]
            if track_age and node != LAB and first < none_on_board:
                at_lab = ready + travel[node][LAB]
                if at_lab - first <= age + EPS:
                    leave = max(at_lab + drop, visit.opens - travel[LAB][visit.node])
                    options.append((leave + travel[LAB][visit.node], none_on_board,
                                    cost + travel[node][LAB] + travel[LAB][visit.node], True))
            for arrival, on_board, new_cost, via in options:
                start = max(arrival, visit.opens)
                if start > visit.closes + EPS:
                    continue
                done = start + visit.service
                new_first = min(on_board, done) if track_age else 0
                if track_age and done - new_first > age + EPS:
                    continue
                if not reachable(mask | 1 << k, visit.node, done):
                    continue
                yield (mask | 1 << k, k), _Label(new_cost, done, new_first, parent, k, via)

    initial = oldest if (track_age and oldest is not None) else (none_on_board if track_age else 0)
    states = {}
    for key, label in moves(0, origin, start_time, initial, 0.0, None):
        _add(states, key, label)

    best = None
    while states:
        following = {}
        for (mask, j), labels in states.items():
            node = visits[j].node
            for label in labels:
                if mask == full:
                    back = label.ready + travel[node][LAB]
                    if back <= shift_end + EPS and (not track_age or back - label.first <= age + EPS):
                        total = label.cost + travel[node][LAB]
                        if best is None or total < best[0] - EPS:
                            best = (total, label)
                    continue
                for key, child in moves(mask, node, label.ready, label.first, label.cost, label):
                    _add(following, key, child)
        states = following
    if best is None:
        return None
    sequence, via = _unwind(best[1])
    return evaluate(visits, travel, sequence, start_time, origin, via, drop, oldest, method="exact")


def _insertion(visits, travel, start_time, shift_end, max_age, origin, drop, oldest):
    sequence = []
    for k in sorted(range(len(visits)), key=lambda i: (visits[i].opens, visits[i].closes)):
        options = []
        for position in range(len(sequence) + 1):
            route = evaluate(visits, travel, sequence[:position] + [k] + sequence[position:], start_time, origin,
                             oldest=oldest)
            if is_feasible(route, shift_end, max_age):
                options.append((route.travel, position))
        if not options:
            return None
        sequence.insert(min(options)[1], k)
    return evaluate(visits, travel, sequence, start_time, origin, oldest=oldest, method="insertion")


def add_lab_breaks(route, visits, travel, start_time, origin=LAB, drop=0, ratio=0.0, min_lab_minutes=0,
                   oldest=None):
    """Adds optional stops at the lab during idle time.

    Between two stops she goes by the lab when the time she would spend there is at least min_lab_minutes and the
    extra driving is at most ratio times that time. Visit start times never change.
    """
    if not ratio or not route.sequence:
        return route
    via = set(route.via)
    nodes = [origin] + [visits[i].node for i in route.sequence]
    for position, leg in enumerate(route.visit_legs):
        before, after = nodes[position], nodes[position + 1]
        if position in via or before == LAB:
            continue
        detour = travel[before][LAB] + travel[LAB][after] - travel[before][after]
        at_lab = leg.wait - detour - drop
        if at_lab >= min_lab_minutes - EPS and detour <= ratio * at_lab + EPS:
            via.add(position)
    if via == set(route.via):
        return route
    return evaluate(visits, travel, route.sequence, start_time, origin, frozenset(via), drop, oldest, route.method)
