import unittest

from settlement.balances import calculate_balances
from settlement.models import Balance, Expense, Participant, Share
from settlement.solvers import Payment, greedy_settlement


class GreedyTests(unittest.TestCase):
    def test_t02_initial_plan(self):
        people = [Participant(pid, pid, i) for i, pid in enumerate("ABCDE")]
        expenses = [
            Expense("1", "식비", "D", 12000, "exact", (Share("B", 7000), Share("C", 5000))),
            Expense("2", "교통비", "E", 8000, "equal", (Share("A"),)),
        ]
        balances = calculate_balances(people, expenses, [])
        before = {pid: row.net for pid, row in balances.items()}
        plan = greedy_settlement(balances)
        self.assertEqual(plan, [
            Payment("A", "D", 8000), Payment("B", "E", 7000),
            Payment("C", "D", 4000), Payment("C", "E", 1000),
        ])
        self.assertEqual(before, {pid: row.net for pid, row in balances.items()})
        for payment in plan:
            before[payment.sender_id] += payment.amount
            before[payment.receiver_id] -= payment.amount
        self.assertTrue(all(value == 0 for value in before.values()))

    def test_ties_follow_registration_order(self):
        balances = {"B": Balance(owed=2), "A": Balance(owed=2),
                    "D": Balance(paid=2), "C": Balance(paid=2)}
        self.assertEqual(greedy_settlement(balances), [Payment("B", "D", 2), Payment("A", "C", 2)])

    def test_already_settled(self):
        self.assertEqual(greedy_settlement({"A": Balance()}), [])

    def test_unbalanced_input(self):
        with self.assertRaises(ValueError):
            greedy_settlement({"A": Balance(paid=1)})
