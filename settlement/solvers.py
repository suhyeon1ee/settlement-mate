from collections.abc import Mapping
from dataclasses import dataclass

from .models import Balance


@dataclass(frozen=True)
class Payment:
    sender_id: str
    receiver_id: str
    amount: int


def greedy_settlement(balances: Mapping[str, Balance]) -> list[Payment]:
    """Build a payment plan from calculate_balances' registration-ordered rows."""
    remaining = {pid: row.net for pid, row in balances.items() if row.net}
    if sum(remaining.values()) != 0:
        raise ValueError("정산 잔액의 합이 0원이어야 합니다.")

    plan = []
    while remaining:
        sender = min(remaining, key=remaining.__getitem__)
        receiver = max(remaining, key=remaining.__getitem__)
        amount = min(-remaining[sender], remaining[receiver])
        plan.append(Payment(sender, receiver, amount))
        remaining[sender] += amount
        remaining[receiver] -= amount
        if remaining[sender] == 0:
            del remaining[sender]
        if remaining[receiver] == 0:
            del remaining[receiver]
    return plan
