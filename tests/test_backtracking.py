import unittest
from unittest.mock import patch

from settlement.backtracking import backtracking_settlement
from settlement.models import Balance


def rows(values):
    return {chr(65 + i): Balance(paid=max(n, 0), owed=max(-n, 0))
            for i, n in enumerate(values)}


class BacktrackingTests(unittest.TestCase):
    example = [-8000, -7000, -5000, 12000, 8000]

    def check_plan(self, balances, plan):
        remaining = {pid: row.net for pid, row in balances.items()}
        for payment in plan:
            self.assertGreater(payment.amount, 0)
            self.assertLessEqual(payment.amount, -remaining[payment.sender_id])
            self.assertLessEqual(payment.amount, remaining[payment.receiver_id])
            remaining[payment.sender_id] += payment.amount
            remaining[payment.receiver_id] -= payment.amount
        self.assertFalse(any(remaining.values()))

    def test_greedy_improvement_and_pruning(self):
        balances = rows(self.example)
        result = backtracking_settlement(balances)
        exhaustive = backtracking_settlement(balances, use_pruning=False, time_limit=None)
        self.assertEqual(result.status, "optimal")
        self.assertEqual(len(result.greedy_plan), 4)
        self.assertEqual(len(result.plan), 3)
        self.assertEqual(len(exhaustive.plan), 3)
        self.assertLess(result.visited, exhaustive.visited)
        self.assertEqual(exhaustive.bound_cuts + exhaustive.duplicate_cuts, 0)
        for plan in (result.greedy_plan, result.plan, exhaustive.plan):
            self.check_plan(balances, plan)

    def test_small_inputs_match_exhaustive_search(self):
        import random
        rng = random.Random(17)
        for size in range(2, 8):
            for _ in range(8):
                values = [rng.choice((-3, -2, -1, 1, 2, 3)) for _ in range(size - 1)]
                balances = rows(values + [-sum(values)])
                result = backtracking_settlement(balances, time_limit=None)
                full = backtracking_settlement(balances, use_pruning=False, time_limit=None)
                self.assertEqual(len(result.plan), len(full.plan))
                self.check_plan(balances, result.plan)
                self.check_plan(balances, full.plan)

    def test_registration_count_does_not_limit_search(self):
        for values, count in (([-1, 1] * 5 + [0] * 3, 5), ([-1] * 12 + [12], 12),
                              ([0] * 13, 0)):
            balances = rows(values)
            result = backtracking_settlement(balances)
            self.assertEqual(result.status, "optimal" if count else "settled")
            self.assertEqual(len(result.plan), count)
            self.assertEqual(result.visited, 1)
            self.check_plan(balances, result.plan)

    def test_timeout_keeps_valid_incumbent(self):
        balances = rows(self.example)
        with patch("settlement.backtracking.perf_counter", side_effect=[0, 1, 1, 7, 7]):
            result = backtracking_settlement(balances)
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.plan, result.greedy_plan)
        self.check_plan(balances, result.plan)
