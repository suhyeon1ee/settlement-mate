from dataclasses import replace
import unittest

from settlement.balances import calculate_balances, split_expense
from settlement.models import Balance, Expense, Participant, Share, Transfer


class BalanceTests(unittest.TestCase):
    def setUp(self):
        self.people = [Participant(key, key, i) for i, key in enumerate("ABC")]
        self.meal = Expense("e1", "식비", "A", 30000, "equal", tuple(map(Share, "ABC")))
        self.transfer = Transfer("t1", "C", "A", 4000)

    def test_t01_balances(self):
        taxi = Expense("e2", "택시비", "B", 12000, "equal", tuple(map(Share, "BC")))
        rows = calculate_balances(self.people, [self.meal, taxi], [self.transfer])
        self.assertEqual(rows, {
            "A": Balance(paid=30000, owed=10000, received=4000),
            "B": Balance(paid=12000, owed=16000),
            "C": Balance(owed=16000, sent=4000),
        })
        self.assertEqual([row.net for row in rows.values()], [16000, -4000, -12000])

    def test_t03_remainder_uses_registration_order(self):
        expense = replace(self.meal, amount=10000, shares=tuple(map(Share, "CBA")))
        self.assertEqual(split_expense(expense, self.people[::-1]), {"A":3334, "B":3333, "C":3333})

    def test_t04_exact_split_without_payer(self):
        expense = replace(self.meal, amount=101, split_type="exact", shares=(Share("B",60), Share("C",41)))
        rows = calculate_balances(self.people, [expense], [])
        self.assertEqual([row.net for row in rows.values()], [101, -60, -41])

    def test_t05_names(self):
        with self.assertRaises(ValueError):
            calculate_balances(self.people + [Participant("D", " A ", 3)], [], [])
        with self.assertRaises(ValueError):
            Participant("D", " ", 3)

    def test_t06_overpayment_and_zero(self):
        expense = replace(self.meal, amount=100, shares=(Share("B"),))
        for amount, expected in [(120, [-20,20,0]), (100, [0,0,0])]:
            rows = calculate_balances(self.people, [expense], [Transfer("t", "B", "A", amount)])
            self.assertEqual([row.net for row in rows.values()], expected)

    def test_t07_invalid_expenses(self):
        for changes in [
            {"amount": -1}, {"amount": 0.5}, {"amount": True}, {"payer_id": "X"},
            {"shares": ()}, {"shares": (Share("X"),)}, {"shares": (Share("B"), Share("B"))},
            {"split_type": "exact", "shares": (Share("B", 1),)},
            {"split_type": "exact", "shares": (Share("B", -1), Share("C", 30001))},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                split_expense(replace(self.meal, **changes), self.people)

    def test_t07_invalid_transfers(self):
        for changes in [{"sender_id":"A"}, {"receiver_id":"X"}, {"amount":0}, {"amount":1.2}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                calculate_balances(self.people, [], [replace(self.transfer, **changes)])

    def test_distinct_transfers_and_recalculation(self):
        transfers = [self.transfer, replace(self.transfer, id="t2")]
        for _ in range(2):
            rows = calculate_balances(self.people, [], transfers)
            self.assertEqual([row.net for row in rows.values()], [-8000, 0, 8000])
