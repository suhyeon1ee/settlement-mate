from html import escape

import streamlit as st
from uuid import uuid4

from settlement.backtracking import backtracking_settlement
from settlement.balances import calculate_balances, split_expense
from settlement.csv_io import balances_csv, settlement_csv
from settlement.models import Expense, Participant, Share, Transfer


st.set_page_config(page_title="정산메이트 · 공동 경비 정산", page_icon="🧾", layout="wide")
st.markdown("""
<style>
.stApp {background:linear-gradient(125deg,#fcfdff,#eff4fd);color:#152542;font-family:"Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif}
.stApp :is(h1,h2,h3,p,label,input,button) {font-family:inherit}
.stApp h1 {font-size:clamp(1.85rem,3vw,2.65rem);letter-spacing:-.055em;line-height:1.25}
[data-testid="stMainBlockContainer"] {max-width:1160px;padding-top:3.6rem}
.st-key-brand {font-size:1.55rem;font-weight:750;letter-spacing:-.055em}
.st-key-brand span {display:inline-grid;place-items:center;border-radius:8px;background:#2452e9;color:white;width:1.35em;height:1.35em}
.stApp button[kind*="primary" i] {background:#2452e9;border-color:#2452e9;color:white}
.stApp [role="tab"][aria-selected="true"] {color:#2452e9}
.stApp [data-baseweb="tab-highlight"] {background:#2452e9}
.stApp [data-testid="stForm"] {padding:0;border:none}
.st-key-ticket {position:relative;background:white;color:#152542;border-radius:14px 14px 0 0;padding:1.3rem;box-shadow:0 8px 28px #1e427511}
.st-key-ticket:after {content:"";position:absolute;top:100%;inset-inline:0;height:8px;background:linear-gradient(135deg,white 25%,transparent 25%) -8px 0/16px 16px,linear-gradient(225deg,white 25%,transparent 25%) -8px 0/16px 16px}
.member {padding:.45rem 0;border-bottom:1px solid #e3e8ef;overflow-wrap:anywhere}
.total {display:flex;justify-content:space-between;align-items:center;border-top:1px dashed #aab6ca;padding-top:.9rem}
.total strong {color:#2452e9;font-size:1.5rem;font-variant-numeric:tabular-nums}
@media(prefers-color-scheme:dark){.stApp {background:var(--background-color);color:var(--text-color)}.st-key-ticket {color:#152542}}
.st-key-new_settlement button {min-height:3.15rem;padding:.65rem 1.15rem;border-radius:.75rem;background:#2452e9;color:white}
.st-key-new_settlement button p {font-size:1.08rem;font-weight:700}
</style>
""", unsafe_allow_html=True)
brand, restart = st.columns([4, 1])
brand.markdown('<div class="st-key-brand"><span aria-hidden="true">✈︎</span> 정산메이트</div>', unsafe_allow_html=True)
state = st.session_state
for group in ("people", "expenses", "transfers"):
    state.setdefault(group, {})
    state.setdefault(group + "_revision", 0)
state.setdefault("result", None)
people = list(state.people.values())
names = {p.id: p.name for p in people}
ids = list(names)


def reset_settlement():
    for key in list(state):
        del state[key]


if state.get("confirm_reset"):
    st.warning("새 정산을 시작하면 현재 참여자, 지출, 기존 송금, 계산 결과가 모두 지워져요. 계속할까요?")
    confirm, cancel = st.columns(2)
    confirm.button("내역 지우고 새로 시작", on_click=reset_settlement)
    cancel.button("취소", on_click=state.pop, args=("confirm_reset",))
    st.stop()

restart.button("새 정산 시작", key="new_settlement", type="primary", use_container_width=True, on_click=state.update, args=({"confirm_reset": True},))


def won(amount):
    return f"{amount:,}원"


def save(group, record, remove=False):
    updated = state[group].copy()
    if remove:
        del updated[record.id]
    else:
        updated[record.id] = record
    data = {key: list((updated if key == group else state[key]).values())
            for key in ("people", "expenses", "transfers")}
    try:
        calculate_balances(data["people"], data["expenses"], data["transfers"])
    except ValueError as error:
        st.error(str(error))
        return
    state.pop(group + "_editing", None)
    state[group] = updated
    state[group + "_revision"] += 1
    state.result = None
    st.rerun()


def select_record(group, record_id):
    state[group + "_editing"] = record_id
    state[group + "_revision"] += 1


def editor(group, label):
    selected = state.get(group + "_editing")
    if selected is not None:
        st.subheader(f"{label} 수정")
        st.button("수정 취소", key=group + "_cancel", on_click=select_record, args=(group, None))
    return state[group].get(selected), f"{group}_{state[group + '_revision']}_{selected}"


def saved_records(group, title, describe):
    if state[group]:
        st.subheader(title)
    for record in state[group].values():
        summary, action = st.columns([4, 1])
        summary.text(describe(record))
        action.button("수정", key=f"edit_{group}_{record.id}", on_click=select_record,
                      args=(group, record.id))


def pick(label, default, key):
    return st.selectbox(label, ids, index=ids.index(default), format_func=names.get, key=key)


def save_person(name, person=None):
    name = name.strip()
    if not name:
        st.error("참여자 이름을 입력하세요.")
        return
    if any(other.name == name and other != person for other in people):
        st.error("이미 등록된 이름이에요. 구분할 수 있는 이름으로 입력해 주세요.")
        return
    if person is None:
        order = max((p.registration_order for p in people), default=0) + 1
        person = Participant(uuid4().hex, name, order)
    save("people", Participant(person.id, name, person.registration_order))


def participants():
    st.caption("두 명 이상 등록하면 지출을 입력할 수 있어요." if len(people) < 2
               else "등록을 마쳤다면 ‘지출’ 탭에서 결제 내역을 입력하세요.")
    with st.form(f"add_person_{state.people_revision}"):
        field, action = st.columns([3, 1], vertical_alignment="bottom")
        name = field.text_input("참여자 이름", placeholder="이름 입력", label_visibility="collapsed")
        if action.form_submit_button("추가", type="primary"):
            save_person(name)


def edit_person(p):
    name = st.text_input("수정할 이름", value=p.name, key=f"rename_{p.id}_{state.people_revision}",
                         label_visibility="collapsed")
    save_col, cancel_col, delete_col = st.columns(3)
    if save_col.button("저장"):
        save_person(name, p)
    cancel_col.button("취소", on_click=select_record, args=("people", None))
    if delete_col.button("참여자 삭제"):
        delete_person(p)


def delete_person(p):
    used = any(e.payer_id == p.id or any(s.participant_id == p.id for s in e.shares)
               for e in state.expenses.values())
    if used or any(p.id in (t.sender_id, t.receiver_id) for t in state.transfers.values()):
        st.error("이 참여자를 참조하는 지출이나 기존 송금을 먼저 수정하거나 삭제하세요.")
    else:
        save("people", p, remove=True)


def expenses():
    e, key = editor("expenses", "지출")
    if e is None:
        st.caption("한 번의 결제마다 결제자와 비용을 나눌 사람을 선택하세요.")
    title = st.text_input("지출명", placeholder="예: 첫날 저녁 식비", value=e.title if e else "", key=key + "_title")
    payer = pick("결제자", e.payer_id if e else ids[0], key + "_payer")
    amount = st.number_input("지출 금액(원)", min_value=0, value=e.amount if e else 0, key=key + "_amount")
    selected = st.multiselect("부담자", ids, default=[s.participant_id for s in e.shares] if e else [],
                              format_func=names.get, key=key + "_members")
    mode = st.radio("분담 방식", ["균등 분담", "직접 지정"],
                    index=int(bool(e and e.split_type == "exact")), horizontal=True, key=key + "_mode")
    shares = []
    if mode == "균등 분담":
        st.caption("나머지 금액은 선택한 부담자의 등록 순서대로 1원씩 배분합니다.")
        shares = [Share(pid) for pid in selected]
    else:
        defaults = {s.participant_id: s.amount for s in e.shares} if e else {}
        for pid in selected:
            individual = st.number_input(f"{names[pid]} 부담액(원)", min_value=0,
                                         value=defaults.get(pid) or 0, key=key + "_" + pid)
            shares.append(Share(pid, individual))
    entry = Expense(e.id if e else uuid4().hex, title.strip(), payer, amount,
                    "equal" if mode == "균등 분담" else "exact", tuple(shares))
    submitted = st.button("지출 저장", type="primary")
    if e and st.button("지출 삭제"):
        save("expenses", e, remove=True)
    try:
        amounts = split_expense(entry, people)
    except ValueError as error:
        if submitted or (title and selected and amount):
            st.error(str(error))
        return
    st.table([{"부담자": names[pid], "예상 부담액": won(n)} for pid, n in amounts.items()])
    if entry.split_type == "equal" and amount % len(amounts):
        extra = [names[pid] for pid, share in amounts.items() if share > amount // len(amounts)]
        st.caption("나머지 1원씩 배정: " + ", ".join(extra))
    st.caption(f"분담 합계 {won(sum(amounts.values()))}")
    if submitted:
        save("expenses", entry)


def transfers():
    t, key = editor("transfers", "기존 송금")
    if t is None:
        st.caption("이미 주고받은 돈이 있을 때 기록하세요. 없으면 바로 정산 결과로 이동하세요.")
    sender = pick("송금자", t.sender_id if t else ids[0], key + "_sender")
    receiver = pick("수령자", t.receiver_id if t else ids[1], key + "_receiver")
    amount = st.number_input("이미 보낸 금액(원)", min_value=0, value=t.amount if t else 0, key=key + "_amount")
    if st.button("기존 송금 저장", type="primary"):
        save("transfers", Transfer(t.id if t else uuid4().hex, sender, receiver, amount))
    if t and st.button("기존 송금 삭제"):
        save("transfers", t, remove=True)


def payments(plan):
    if plan:
        st.table([{"순번": i, "송금자": names[p.sender_id], "수령자": names[p.receiver_id],
                   "금액": won(p.amount)} for i, p in enumerate(plan, 1)])
    else:
        st.write("추가로 보낼 금액이 없습니다.")


def results():
    if st.button("정산 계산", type="primary"):
        rows = calculate_balances(people, state.expenses.values(), state.transfers.values())
        state.result = rows, backtracking_settlement(rows)
    if state.result is None:
        st.info("저장한 내역으로 정산하려면 정산 계산을 누르세요.")
        return
    rows, result = state.result
    labels = {"optimal": "최소 송금 횟수 확정", "timeout": "시간 제한 내 현재까지 찾은 최선",
              "settled": "추가 송금 없음"}
    st.subheader(f"{labels[result.status]} · {len(result.plan)}건")
    payments(result.plan)
    st.download_button("송금 목록 CSV 다운로드", data=settlement_csv(result.plan, names, labels[result.status]),
                       file_name="settlement.csv", mime="text/csv")
    st.subheader("개인별 정산 근거")
    st.caption("정산 잔액 = 결제액 − 부담액 + 이미 보낸 금액 − 이미 받은 금액. 양수는 받을 금액, 음수는 보낼 금액입니다.")
    st.table([{"참여자": names[pid], "결제액": won(r.paid), "부담액": won(r.owed),
               "이미 보냄": won(r.sent), "이미 받음": won(r.received), "정산 잔액": won(r.net)}
              for pid, r in rows.items()])
    st.download_button("개인별 잔액 CSV 다운로드", data=balances_csv(rows, names),
                       file_name="balances.csv", mime="text/csv")
    pid = st.selectbox("지출별 계산 근거를 볼 참여자", ids, format_func=names.get)
    details = []
    for e in state.expenses.values():
        parts = split_expense(e, people)
        if e.payer_id == pid or pid in parts:
            details.append({"지출명": e.title, "내 결제액": won(e.amount if e.payer_id == pid else 0),
                            "내 부담액": won(parts.get(pid, 0))})
    if details:
        st.table(details)
    else:
        st.caption("이 참여자와 관련된 지출이 없습니다.")
    with st.expander("송금 횟수와 알고리즘 비교"):
        comparison(result)


def comparison(result):
    st.table([{"방식": "그리디", "송금 건수": len(result.greedy_plan), "시간(ms)": f"{result.greedy_ms:.3f}"},
              {"방식": "백트래킹", "송금 건수": len(result.plan), "시간(ms)": f"{result.search_ms:.3f}"}])
    st.write(f"{len(result.greedy_plan) - len(result.plan)}건 절감 · 방문 상태 {result.visited}개 · "
             f"하한 가지치기 {result.bound_cuts}개 · 중복 상태 생략 {result.duplicate_cuts}개")
    st.write("그리디 송금 목록")
    payments(result.greedy_plan)


def toggle_receipt():
    state.receipt_edit = not state.get("receipt_edit", False)
    select_record("people", None)


def receipt():
    with st.container(key="ticket"):
        title, mode = st.columns([2, 1])
        title.subheader(f"참여자 {len(people)}명")
        editing = state.get("receipt_edit", False)
        if people:
            mode.button("편집 완료" if editing else "편집", on_click=toggle_receipt)
        else:
            st.caption("등록한 이름이 여기에 표시돼요.")
        for p in people:
            if editing and state.get("people_editing") == p.id:
                edit_person(p)
            else:
                row = st.container()
                if editing:
                    row, pen, remove = st.columns([3, 1, 1.4])
                    if remove.button("삭제", key=f"delete_people_{p.id}", help=f"{p.name} 삭제"):
                        delete_person(p)
                    pen.button("✎", key=f"edit_people_{p.id}", help=f"{p.name} 수정",
                               on_click=select_record, args=("people", p.id))
                row.markdown(f'<div class="member">{escape(p.name)}</div>', unsafe_allow_html=True)
        total = sum(e.amount for e in state.expenses.values())
        st.markdown(f'<div class="total">총지출<strong>{won(total)}</strong></div>',
                    unsafe_allow_html=True)


person_tab, expense_tab, transfer_tab, result_tab = st.tabs(["참여자", "지출", "기존 송금", "정산 결과"])
with person_tab:
    form, preview = st.columns([1.55, 1], gap="large")
    with form:
        st.title("누구와 함께 정산할까요?")
        participants()
    with preview:
        receipt()
for tab, render in ((expense_tab, expenses), (transfer_tab, transfers), (result_tab, results)):
    with tab:
        if len(people) < 2:
            st.info("참여자를 2명 이상 등록하세요.")
        else:
            render()
            if tab is expense_tab:
                saved_records("expenses", "저장된 지출", lambda e: f"{e.title} · {names[e.payer_id]} · {won(e.amount)}")
            elif tab is transfer_tab:
                saved_records("transfers", "기존 송금 내역",
                              lambda t: f"{names[t.sender_id]} → {names[t.receiver_id]} · {won(t.amount)}")
