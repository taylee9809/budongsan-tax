"""검증 정본(data/verification/cases.jsonl)을 엔진에 돌리는 회귀 테스트.

정본 케이스는 지금까지 비공개 하네스에서만 돌았다. 여기서는 공개 저장소만으로 돌린다.

- 도구 래퍼(tax_server)로 호출할 수 있으면 래퍼로, 래퍼가 케이스 입력을 받지 못하면 엔진(tax_judgment)으로 돌린다.
- 래퍼가 엔진보다 입력이 적은 '래퍼 드리프트'는 아래 KNOWN_WRAPPER_DRIFT로 고정한다. MCP 사용자는 그 입력을
  넘길 수 없어 기본값으로 판정받는다. 생성기(scripts/extract_tax_server.py, 비공개)로 tax_server.py를 다시
  만들면 줄어들어야 하고, 새로 늘면 실패한다.
"""
import inspect
import json
import pathlib

import pytest

import tax_judgment as tj
import tax_server

ROOT = pathlib.Path(__file__).resolve().parent.parent
CASES = [json.loads(line) for line in
         (ROOT / "data/verification/cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
ACTIVE = [c for c in CASES if c.get("활성", 1)]

# 공개 저장소에 없는 도구 또는 엔진 시그니처가 다른 케이스 — 돌릴 수 없다.
NOT_RUNNABLE = {
    "judge_ltv_limit": "대출 규제 도구 — 공개판 범위 밖(CONTRIBUTING '하지 않는 것')",
}
NOT_RUNNABLE_CASES = {
    "S155-05": "homes_at_sale 입력 — 래퍼·엔진 어디에도 없음(비공개 서버 전용)",
    "S155-06": "homes_at_sale 입력 — 래퍼·엔진 어디에도 없음(비공개 서버 전용)",
}
# 알려진 불일치 — findings.jsonl에 기록된 것만.
KNOWN_MISMATCH = {
    "T155-18": "finding 2 (설계반영) — 임차인 잔존 지연 전입은 사실판단 회색지대, 엔진은 보수적으로 불충족",
}

KNOWN_WRAPPER_DRIFT = {
    "judge_155_special": {"homes_at_sale"},
    "judge_business_dealer_status": {"self_built_kind"},
    "judge_co_inherited_owner": {"is_first_priority", "sale_date", "same_household_at_inheritance",
                                 "shares_changed_after_inheritance"},
    "judge_family_loan": {"is_related", "justifiable_reason", "loan_date"},
    "judge_farmland_daeto": {"has_income_exclusion_period", "new_acquired_by_inheritance_or_gift"},
    "judge_farmland_reduction": {"distance_km", "heir_continuous_1yr", "inherited_decedent_years",
                                 "inherited_sold_within_3yr"},
    "judge_first_home_acquisition_relief": {"household_income", "in_capital_area"},
    "judge_inherited_house_priority": {"agreed_label", "demolished_label"},
    "judge_reconstruction_membership_transfer": {"permit_application_date"},
    "judge_second_home_exclusion": {"land_area_m2", "transfer_date"},
    "judge_temporary_two_homes": {"other_homes_at_acquisition", "prev_adjusted_after_new_contract"},
}


def _params(fn):
    return set(inspect.signature(fn).parameters)


def _get(result, key):
    cur = result
    for k in key.split("."):
        if not (isinstance(cur, dict) and k in cur):
            return "<<키 없음>>"
        cur = cur[k]
    return cur


def _callable_for(case):
    args = json.loads(case["input_json"])
    for mod in (tax_server, tj):
        fn = getattr(mod, case["tool"], None)
        if fn is not None and set(args) <= _params(fn):
            return fn, args
    return None, args


def _marks(case):
    if case["case_id"] in KNOWN_MISMATCH:
        return [pytest.mark.xfail(reason=KNOWN_MISMATCH[case["case_id"]], strict=True)]
    return []


@pytest.mark.parametrize("case", [pytest.param(c, id=c["case_id"], marks=_marks(c)) for c in ACTIVE])
def test_case(case):
    if case["tool"] in NOT_RUNNABLE:
        pytest.skip(NOT_RUNNABLE[case["tool"]])
    if case["case_id"] in NOT_RUNNABLE_CASES:
        pytest.skip(NOT_RUNNABLE_CASES[case["case_id"]])
    fn, args = _callable_for(case)
    assert fn is not None, f"{case['case_id']}: {case['tool']}이(가) 이 입력을 받지 못한다 — {sorted(args)}"
    got = _get(fn(**args), case["expected_key"])
    assert got == json.loads(case["expected_json"]), f"{case['case_id']} {case['expected_사유']}"


def test_wrapper_drift_is_known():
    drift = {}
    for c in ACTIVE:
        fn = getattr(tax_server, c["tool"], None)
        if fn is None:
            continue
        extra = set(json.loads(c["input_json"])) - _params(fn)
        if extra:
            drift.setdefault(c["tool"], set()).update(extra)
    new = {k: v - KNOWN_WRAPPER_DRIFT.get(k, set()) for k, v in drift.items()}
    new = {k: v for k, v in new.items() if v}
    assert not new, f"래퍼가 받지 못하는 케이스 입력이 새로 생겼다: {new}"
    fixed = {k: v - drift.get(k, set()) for k, v in KNOWN_WRAPPER_DRIFT.items()}
    fixed = {k: v for k, v in fixed.items() if v}
    assert not fixed, f"드리프트가 해소됐다 — KNOWN_WRAPPER_DRIFT에서 지울 것: {fixed}"
