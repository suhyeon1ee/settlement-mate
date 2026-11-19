import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class SettlementScreenTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "app.py"
        self.app = AppTest.from_file(str(path), default_timeout=60).run()

    def widget(self, kind, label):
        return next(w for w in getattr(self.app, kind) if w.label == label)

    def click(self, label):
        self.widget("button", label).click().run()
        self.assertFalse(self.app.exception)

    def register(self, names):
        for name in names:
            self.widget("text_input", "참여자 이름").input(name)
            self.click("참여자 저장")
        self.ids = {p.name: p.id for p in self.app.session_state["people"].values()}

    def expense(self, title, payer, amount, members, amounts=None):
        self.widget("text_input", "지출명").input(title)
        self.widget("selectbox", "결제자").select(self.ids[payer])
        self.widget("number_input", "지출 금액(원)").set_value(amount)
        self.widget("multiselect", "부담자").set_value([self.ids[n] for n in members])
        if amounts:
            self.widget("radio", "분담 방식").set_value("직접 지정").run()
            for name, share in zip(members, amounts):
                self.widget("number_input", f"{name} 부담액(원)").set_value(share)
        self.click("지출 저장")

    def test_expenses_previous_transfer_and_recalculation(self):
        self.register("ABC")
        self.expense("식비", "A", 30000, "ABC")
        self.expense("택시비", "B", 12000, "BC")
        self.widget("selectbox", "송금자").select(self.ids["C"])
        self.widget("selectbox", "수령자").select(self.ids["A"])
        self.widget("number_input", "이미 보낸 금액(원)").set_value(4000)
        self.click("기존 송금 저장")
        self.click("정산 계산")
        rows, result = self.app.session_state["result"]
        self.assertEqual([r.net for r in rows.values()], [16000, -4000, -12000])
        self.assertEqual([p.amount for p in result.plan], [12000, 4000])
        transfer = next(iter(self.app.session_state["transfers"]))
        self.widget("selectbox", "기존 송금 선택").select(transfer).run()
        self.widget("number_input", "이미 보낸 금액(원)").set_value(5000)
        self.click("기존 송금 저장")
        self.assertIsNone(self.app.session_state["result"])
        for _ in range(2):
            self.click("정산 계산")
            rows, _result = self.app.session_state["result"]
            self.assertEqual([r.net for r in rows.values()], [15000, -4000, -11000])
            self.assertEqual(len(self.app.session_state["transfers"]), 1)

    def test_exact_split_and_comparison(self):
        self.register("ABCDE")
        self.expense("공동 구매", "D", 12000, "BC", [7000, 5000])
        self.expense("교통비", "E", 8000, "A")
        self.click("정산 계산")
        _rows, result = self.app.session_state["result"]
        self.assertEqual((len(result.greedy_plan), len(result.plan)), (4, 3))
        self.assertIn("최소 송금 횟수 확정 · 3건", [h.value for h in self.app.subheader])

    def test_rename_and_referenced_participant_deletion(self):
        self.register("AB")
        self.expense("식비", "A", 101, "AB")
        self.click("정산 계산")
        self.widget("selectbox", "참여자 선택").select(self.ids["A"]).run()
        self.click("참여자 삭제")
        self.assertTrue(self.app.error)
        self.assertIsNotNone(self.app.session_state["result"])
        self.widget("text_input", "참여자 이름").input(" B ")
        self.click("참여자 저장")
        self.assertTrue(self.app.error)
        self.widget("text_input", "참여자 이름").input("C")
        self.click("참여자 저장")
        self.assertIsNone(self.app.session_state["result"])
        self.assertEqual(self.app.session_state["people"][self.ids["A"]].name, "C")
        self.click("정산 계산")
        rows, _ = self.app.session_state["result"]
        self.assertEqual(rows[self.ids["A"]].owed, 51)
