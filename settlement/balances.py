from collections.abc import Iterable, Sequence

from .models import Balance, Expense, Participant, Transfer


def _check_amount(value: int, minimum: int) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"금액은 {minimum}원 이상의 정수여야 합니다.")


def _unique(values: Iterable, field: str) -> None:
    seen = set()
    for value in values:
        if value in seen:
            raise ValueError(f"중복된 {field}: {value}")
        seen.add(value)


def _registration_order(participants: Sequence[Participant]) -> dict[str, int]:
    _unique((p.id for p in participants), "참여자 ID")
    _unique((p.name for p in participants), "참여자 이름")
    _unique((p.registration_order for p in participants), "등록 순서")
    return {p.id: p.registration_order for p in participants}


def split_expense(expense: Expense, participants: Sequence[Participant]) -> dict[str, int]:
    """Return each selected participant's share in whole won."""
    return _split_expense(expense, _registration_order(participants))


def _split_expense(expense: Expense, order: dict[str, int]) -> dict[str, int]:
    _check_amount(expense.amount, 1)
    if not expense.title.strip() or not expense.shares:
        raise ValueError("지출명과 부담자를 입력하세요.")
    if expense.payer_id not in order:
        raise ValueError("등록되지 않은 결제자입니다.")
    ids = [share.participant_id for share in expense.shares]
    _unique(ids, "부담자")
    if any(pid not in order for pid in ids):
        raise ValueError("등록되지 않은 부담자입니다.")

    if expense.split_type == "equal":
        if any(share.amount is not None for share in expense.shares):
            raise ValueError("균등 분담에는 개별 금액을 지정할 수 없습니다.")
        quotient, remainder = divmod(expense.amount, len(ids))
        return {
            pid: quotient + int(index < remainder)
            for index, pid in enumerate(sorted(ids, key=order.__getitem__))
        }

    if expense.split_type != "exact":
        raise ValueError("지원하지 않는 분담 방식입니다.")
    amounts = {}
    for share in expense.shares:
        _check_amount(share.amount, 0)
        amounts[share.participant_id] = share.amount
    if sum(amounts.values()) != expense.amount:
        raise ValueError("지정한 부담액 합계가 지출액과 다릅니다.")
    return amounts


def calculate_balances(
    participants: Sequence[Participant],
    expenses: Sequence[Expense],
    transfers: Sequence[Transfer],
) -> dict[str, Balance]:
    """Return all balances keyed by participant ID in registration order."""
    order = _registration_order(participants)
    balances = {pid: Balance() for pid in sorted(order, key=order.__getitem__)}
    _unique((expense.id for expense in expenses), "지출 ID")
    _unique((transfer.id for transfer in transfers), "기존 송금 ID")
    for expense in expenses:
        shares = _split_expense(expense, order)
        balances[expense.payer_id].paid += expense.amount
        for pid, amount in shares.items():
            balances[pid].owed += amount

    for transfer in transfers:
        _check_amount(transfer.amount, 1)
        if transfer.sender_id == transfer.receiver_id:
            raise ValueError("송금자와 수령자는 달라야 합니다.")
        if transfer.sender_id not in balances or transfer.receiver_id not in balances:
            raise ValueError("등록되지 않은 송금 참여자입니다.")
        balances[transfer.sender_id].sent += transfer.amount
        balances[transfer.receiver_id].received += transfer.amount

    if sum(row.net for row in balances.values()) != 0:
        raise ArithmeticError("전체 정산 잔액의 합이 0원이 아닙니다.")
    return balances
