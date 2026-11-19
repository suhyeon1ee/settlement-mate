from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from math import isfinite
from time import perf_counter
from typing import Literal

from .models import Balance
from .solvers import Payment, greedy_settlement


@dataclass
class SettlementResult:
    greedy_plan: list[Payment]
    plan: list[Payment]
    status: Literal["settled", "optimal", "timeout"]
    greedy_ms: float
    search_ms: float
    visited: int
    bound_cuts: int
    duplicate_cuts: int


def _pairs(state, senders, receivers, deadline):
    for exact_first in (True, False):
        for sender in senders:
            for receiver in receivers:
                if deadline is not None and perf_counter() >= deadline:
                    raise TimeoutError
                debt, credit = -state[sender], state[receiver]
                if (debt == credit) == exact_first:
                    yield sender, receiver, min(debt, credit)


def backtracking_settlement(
    balances: Mapping[str, Balance], *, use_pruning: bool = True,
    time_limit: float | None = 5.0,
) -> SettlementResult:
    """Minimize additional payments. Use an unlimited, unpruned run for small tests."""
    if time_limit is not None and (not isfinite(time_limit) or time_limit < 0):
        raise ValueError("time_limit must be finite and nonnegative")

    start = perf_counter()
    greedy = greedy_settlement(balances)
    greedy_ms = (perf_counter() - start) * 1000
    best = greedy.copy()
    ids = [pid for pid, row in balances.items() if row.net]
    initial = tuple(balances[pid].net for pid in ids)
    root_bound = max(sum(n < 0 for n in initial), sum(n > 0 for n in initial))
    started = perf_counter()
    deadline = None if time_limit is None else started + time_limit
    seen = {}
    path = []
    # Each suspended iterator belongs to its parent's immutable balance state.
    stack: list[tuple[tuple[int, ...], Iterator[tuple[int, int, int]]]] = []
    state = initial
    visited = bound_cuts = duplicate_cuts = 0
    status = "optimal" if initial else "settled"
    try:
        while True:
            visited += 1
            senders = [i for i, n in enumerate(state) if n < 0]
            receivers = [i for i, n in enumerate(state) if n > 0]
            depth = len(path)
            if not senders:
                if depth < len(best):
                    best = path.copy()
            elif use_pruning and depth + max(len(senders), len(receivers)) >= len(best):
                bound_cuts += 1
            elif use_pruning and state in seen and seen[state] <= depth:
                duplicate_cuts += 1
            else:
                if use_pruning:
                    seen[state] = depth
                stack.append((state, _pairs(state, senders, receivers, deadline)))

            if use_pruning and len(best) == root_bound:
                break
            while stack:
                del path[len(stack) - 1:]
                parent, candidates = stack[-1]
                move = next(candidates, None)
                if move is not None:
                    sender, receiver, amount = move
                    child = list(parent)
                    child[sender] += amount
                    child[receiver] -= amount
                    state = tuple(child)
                    path.append(Payment(ids[sender], ids[receiver], amount))
                    break
                stack.pop()
            else:
                break
    except TimeoutError:
        status = "timeout"

    search_ms = (perf_counter() - started) * 1000
    remaining = {pid: row.net for pid, row in balances.items()}
    for payment in best:
        remaining[payment.sender_id] += payment.amount
        remaining[payment.receiver_id] -= payment.amount
    if any(remaining.values()):
        raise RuntimeError("Settlement plan leaves outstanding balances")
    return SettlementResult(greedy, best, status, greedy_ms, search_ms,
                            visited, bound_cuts, duplicate_cuts)
