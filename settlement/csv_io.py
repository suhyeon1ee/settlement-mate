import csv
from io import StringIO


def _csv_bytes(header, rows):
    with StringIO(newline="") as output:
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8-sig")


def settlement_csv(plan, names, status_label):
    return _csv_bytes(
        ("순번", "송금자", "수령자", "금액", "결과 상태"),
        ((i, names[p.sender_id], names[p.receiver_id], p.amount, status_label)
         for i, p in enumerate(plan, 1)),
    )


def balances_csv(balances, names):
    return _csv_bytes(
        ("참여자", "총결제액", "총부담액", "이미 보낸 금액", "이미 받은 금액", "정산 잔액"),
        ((names[pid], row.paid, row.owed, row.sent, row.received, row.net)
         for pid, row in balances.items()),
    )
