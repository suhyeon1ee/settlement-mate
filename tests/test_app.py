import codecs
import csv
from io import StringIO
from unittest.mock import patch

import streamlit as st

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
            self.click("추가")
        self.ids = {p.name: p.id for p in self.app.session_state["people"].values()}

    def test_new_settlement(self):
        self.register(["A", "B"])
        self.expense("식비", "A", 100, ["A", "B"])
        self.click("정산 계산")
        self.click("새 정산 시작")
        self.click("취소")
        self.assertIsNotNone(self.app.session_state["result"])
        self.assertEqual(len(self.app.session_state["expenses"]), 1)
        self.click("새 정산 시작")
        self.click("내역 지우고 새로 시작")
        for group in ("people", "expenses", "transfers"):
            self.assertEqual(self.app.session_state[group], {})
        self.assertIsNone(self.app.session_state["result"])
        self.register(["A"])

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
        self.app.button(key=f"edit_transfers_{transfer}").click().run()
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
        self.click("편집")
        self.app.button(key=f"edit_people_{self.ids['A']}").click().run()
        self.widget("text_input", "수정할 이름").input("임시")
        self.click("취소")
        self.assertEqual(self.app.session_state["people"][self.ids["A"]].name, "A")
        self.app.button(key=f"edit_people_{self.ids['A']}").click().run()
        self.click("참여자 삭제")
        self.assertTrue(self.app.error)
        self.assertIsNotNone(self.app.session_state["result"])
        self.widget("text_input", "수정할 이름").input(" B ")
        self.click("저장")
        self.assertTrue(self.app.error)
        self.widget("text_input", "수정할 이름").input("C")
        self.click("저장")
        self.assertIsNone(self.app.session_state["result"])
        self.assertEqual(self.app.session_state["people"][self.ids["A"]].name, "C")
        self.click("정산 계산")
        rows, _ = self.app.session_state["result"]
        self.assertEqual(rows[self.ids["A"]].owed, 51)

    def test_cancel_expense_edit_returns_to_new_entry(self):
        self.register("AB")
        self.expense("식비", "A", 100, "AB")
        expense_id = next(iter(self.app.session_state["expenses"]))
        self.app.button(key=f"edit_expenses_{expense_id}").click().run()
        self.assertEqual(self.widget("text_input", "지출명").value, "식비")
        self.widget("text_input", "지출명").input("교통비")
        self.app.button(key="expenses_cancel").click().run()
        self.assertEqual(self.widget("text_input", "지출명").value, "")
        self.assertEqual(self.app.session_state["expenses"][expense_id].title, "식비")

    def test_download_files_follow_current_result(self):
        self.register(['A, "팀"', 'B'])
        self.expense("교통비", 'A, "팀"', 101, ["B"])
        with patch.object(st, "download_button", wraps=st.download_button) as download:
            self.click("정산 계산")
            def exported_rows():
                rows = {}
                for call in download.call_args_list:
                    data = call.kwargs["data"]
                    self.assertTrue(data.startswith(codecs.BOM_UTF8))
                    rows[call.kwargs["file_name"]] = list(csv.reader(StringIO(data.decode("utf-8-sig"))))
                return rows

            files = exported_rows()
            self.assertEqual(files["settlement.csv"], [
                ["순번", "송금자", "수령자", "금액", "결과 상태"],
                ["1", "B", 'A, "팀"', "101", "최소 송금 횟수 확정"],
            ])
            self.assertEqual(files["balances.csv"], [
                ["참여자", "총결제액", "총부담액", "이미 보낸 금액", "이미 받은 금액", "정산 잔액"],
                ['A, "팀"', "101", "0", "0", "0", "101"],
                ["B", "0", "101", "0", "0", "-101"],
            ])
            self.widget("selectbox", "송금자").select(self.ids["B"])
            self.widget("selectbox", "수령자").select(self.ids['A, "팀"'])
            self.widget("number_input", "이미 보낸 금액(원)").set_value(101)
            download.reset_mock()
            self.click("기존 송금 저장")
            self.assertFalse(self.app.get("download_button"))
            self.click("정산 계산")
            updated = exported_rows()
            self.assertEqual(updated["settlement.csv"], files["settlement.csv"][:1])
            self.assertEqual([r[-1] for r in updated["balances.csv"][1:]], ["0", "0"])
