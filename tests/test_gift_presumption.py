"""증여 예시·추정(상증법 §35·§37·§44·§45·§45의5)과 신고·납부(§68·§70·§71) — 조문 경계 대조 (2026-11-18, 분업 4차).

기대값은 코드가 아니라 법제처 원문(법 MST 276123 · 시행령 290845 · 시행규칙 284609, 2026-11-18 대조)과
상속세 및 증여세 사무처리규정(국세청훈령 제2760호) §42 표에 적힌 기준액·비율에서 손으로 계산한 것이다.
케이스 원본: data/verification/cases.jsonl 의 GP-*, data/verification/node_cases/hidden4_sangjeung.jsonl 의 H4S-*.
"""
import importlib
import json
import pathlib
import sys

import pytest

import tax_params
from gift_presumption import TOOLS, judge_gift_presumption as presume, judge_low_price_transfer_gift as low
from tax_nodes import engine, sangjeung, sangjeung_chujeong as M, sangjeung_rest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
verify_node_cases = importlib.import_module("verify_node_cases")
verify_tool_cases = importlib.import_module("verify_tool_cases")

억 = 100_000_000
_NODE_CASES = [json.loads(l) for l in (ROOT / "data/verification/node_cases/hidden4_sangjeung.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
_TOOL_CASES = [json.loads(l) for l in (ROOT / "data/verification/cases.jsonl").read_text(encoding="utf-8").splitlines()
               if l.strip() and json.loads(l)["case_id"].startswith("GP-")]


# ── 영 §26②: "시가의 100분의 30에 상당하는 가액"과 "3억원" 중 적은 금액 / 법 §35①: 차액이 기준금액 '이상' → 차액 − 기준금액
@pytest.mark.parametrize("시가,대가,기대", [
    (10 * 억, 6 * 억, 1 * 억),                # 차액 4억 − min(3억, 3억)
    (10 * 억, 7 * 억, 0),                     # 차액 3억 = 기준금액 → 대상이나 0
    (10 * 억, 7 * 억 + 1, 0),                 # 차액 < 기준금액
    (5 * 억, 3 * 억, 50_000_000),             # 기준금액 1.5억(30%) — 2억 − 1.5억
    (20 * 억, 10 * 억, 7 * 억),               # 30%는 6억이지만 3억이 적다
    (5 * 억, 9 * 억, 250_000_000),            # 고가 양도
])
def test_related_party_threshold(시가, 대가, 기대):
    assert low(2026, 시가, 대가, related_party=True)["증여재산가액"] == 기대


# ── 영 §26③④: 기준은 시가의 30%, 빼는 금액은 3억원
@pytest.mark.parametrize("시가,대가,기대", [
    (20 * 억, 13 * 억, 4 * 억), (20 * 억, 14 * 억, 3 * 억), (20 * 억, 14 * 억 + 1, 0), (5 * 억, 3 * 억, 0),
])
def test_unrelated_party_threshold(시가, 대가, 기대):
    assert low(2026, 시가, 대가, related_party=False, no_legitimate_reason=True)["증여재산가액"] == 기대


def test_low_price_undetermined_without_facts():
    r = low(2026, 10 * 억, 6 * 억)
    assert r["증여재산가액"] is None and "특수관계인" in r["판정불가_사유"]
    r = low(2026, 20 * 억, 13 * 억, related_party=False)
    assert r["증여재산가액"] is None and "정당한 사유" in r["판정불가_사유"]
    assert low(2026, 20 * 억, 13 * 억, related_party=False, no_legitimate_reason=False)["증여재산가액"] == 0


def test_low_price_chains_into_gift_tax_and_filing():
    """§35 증여재산가액 → §47·§53·§55·§56·§69 → §68 신고기한·§70 분납·§71 연부연납."""
    r = low(2026, 20 * 억, 10 * 억, related_party=True, donor_relation="직계존속", settlement_date="2026-03-10")
    세 = r["증여세"]
    assert r["증여재산가액"] == 7 * 억
    assert 세["과세표준"] == 650_000_000                       # 7억 − 5천만(§53 2호)
    assert 세["산출세액"] == 135_000_000                       # 6.5억 × 30% − 6천만(§26·§56)
    assert 세["납부세액"] == 130_950_000                       # 신고세액공제 3%(§69①)
    assert 세["신고기한"]["기한"] == "2026-06-30"               # 3월 말일부터 3개월(§68①)
    assert 세["분납"] == {"분납가능세액": 65_475_000, "납부기한": "2026-06-30", "분납기한": "2026-08-31"}   # 50%(영 §66②2호), 2개월(§70②)
    assert 세["연부연납"]["기간_년"] == 5 and 세["연부연납"]["연납부액"] == 21_825_000   # ÷(5+1) (§71②2호나목·영 §68①)
    같은값 = sangjeung.증여세_부동산(2026, 증여자관계="직계존속", 평가액=7 * 억)
    assert 같은값["납부세액"] == 세["납부세액"]                 # 기존 증여세 조립 함수와 같은 노드를 탄다
    assert "상속세 및 증여세법 §35①" in r["적용 조문"] and "상속세 및 증여세법 §35②" in [m["표기"] for m in r["미적용 조문"]]
    assert "근거표" not in r and r["다루지 않는 것"]


def test_low_price_input_checks():
    with pytest.raises(ValueError):
        low(2026, 0, 1)
    with pytest.raises(ValueError):
        low(2026, 10 * 억, 6 * 억, direction="저가양도")
    with pytest.raises(ValueError):
        low(2026, 10 * 억, 6 * 억, facts={"시가": 1})
    with pytest.raises(tax_params.ParamNotVerified):
        low(2015, 10 * 억, 6 * 억, related_party=True)          # 검증되지 않은 연도는 계산을 거부한다


# ── 법 §44
def test_family_transfer_presumption_and_exceptions():
    r = presume(2026, "배우자등양도", amount=8 * 억, transferee_relation="직계비속", facts={"양도일": "2026-02-01"})
    assert r["증여추정"] is True and r["증여재산가액"] == 8 * 억
    assert r["증여세"]["과세표준"] == 750_000_000 and r["증여세"]["신고기한"]["기한"] == "2026-05-31"   # 자녀가 본 증여자는 직계존속
    for 사유 in ("경매", "파산", "공매"):
        assert presume(2026, "배우자등양도", amount=8 * 억, transferee_relation="배우자", facts={"처분사유": 사유})["증여추정"] is False
    전부 = {"양도대가": 8 * 억, "대가지급_입증": [{"방법": "신고소득", "금액": 8 * 억}]}
    r = presume(2026, "배우자등양도", amount=8 * 억, transferee_relation="직계존속", facts=전부)
    assert r["증여추정"] is False and r["추정배제"]["호"] == "5" and r["증여세"] is None
    일부 = {"양도대가": 8 * 억, "대가지급_입증": [{"방법": "신고소득", "금액": 8 * 억 - 1}]}
    r = presume(2026, "배우자등양도", amount=8 * 억, transferee_relation="직계존속", facts=일부)
    assert r["증여추정"] is None and r["판정불가_사유"]
    assert presume(2026, "배우자등양도", amount=8 * 억, transferee_relation="형제자매")["증여추정"] is False


def test_indirect_transfer_three_years_and_income_tax_proviso():
    f = {"특수관계인": True, "중간양수일": "2023-06-01", "재양도일": "2026-06-01",
         "당초양도자_소득세결정세액": 50_000_000, "중간양수자_소득세결정세액": 30_000_000}
    r = presume(2026, "우회양도", amount=5 * 억, transferee_relation="직계비속", facts=f)
    assert r["계산"]["추정시_증여세액"] == 80_000_000            # (5억 − 5천만) × 20% − 1천만
    assert r["증여추정"] is True and r["소득세_불부과"] is True    # 합계 8천만은 증여세 8천만보다 '크지' 않다
    f2 = dict(f, 중간양수자_소득세결정세액=30_000_001)
    assert presume(2026, "우회양도", amount=5 * 억, transferee_relation="직계비속", facts=f2)["증여추정"] is False
    assert presume(2026, "우회양도", amount=5 * 억, transferee_relation="직계비속", facts=dict(f, 재양도일="2026-06-02"))["증여추정"] is False
    assert presume(2026, "우회양도", amount=5 * 억, transferee_relation="직계비속", facts=dict(f, 특수관계인=False))["증여추정"] is False


# ── 영 §34① 단서: "100분의 20에 상당하는 금액과 2억원중 적은 금액에 미달하는 경우를 제외"
@pytest.mark.parametrize("가액,입증,기대", [
    (10 * 억, 8 * 억, 2 * 억), (10 * 억, 8 * 억 + 1, 0), (5 * 억, 4 * 억, 1 * 억), (5 * 억, 4 * 억 + 1, 0),
    (15 * 억, 13 * 억, 2 * 억), (15 * 억, 13 * 억 + 1, 0), (10 * 억, 10 * 억, 0), (10 * 억, 11 * 억, 0),
])
def test_fund_source_unproven_threshold(가액, 입증, 기대):
    r = presume(2026, "취득자금", amount=가액, proven_amount=입증)
    assert r["증여재산가액"] == 기대 and r["증여추정"] is bool(기대)
    assert presume(2026, "채무상환", amount=가액, proven_amount=입증)["증여재산가액"] == 기대


# ── 사무처리규정 §42① 표(국세청훈령 제2760호): 30세 미만 5천만·5천만·5천만·1억 / 30세 이상 1.5억·5천만·5천만·2억 / 40세 이상 3억·1억·5천만·4억
@pytest.mark.parametrize("나이,주택,기타,상환,배제", [
    (29, 49_999_999, 0, 0, True), (29, 50_000_000, 0, 0, False),
    (30, 149_999_999, 0, 0, True), (30, 150_000_000, 0, 0, False), (39, 149_999_999, 49_999_999, 0, True),
    (39, 149_999_999, 49_999_999, 2, False),                    # 합계 2억 = 총액한도
    (40, 299_999_999, 0, 0, True), (40, 300_000_000, 0, 0, False), (40, 0, 99_999_999, 0, True), (40, 0, 100_000_000, 0, False),
    (40, 0, 0, 50_000_000, False), (40, 299_999_999, 99_999_999, 2, False),
])
def test_exclusion_thresholds_by_age(나이, 주택, 기타, 상환, 배제):
    r = presume(2026, "취득자금", amount=max(주택, 1), proven_amount=0, age=나이,
                facts={"10년내_주택취득가액": 주택, "10년내_기타재산취득가액": 기타, "10년내_채무상환금액": 상환})
    assert (r["증여추정"] is False) is 배제


def test_presumption_input_checks():
    with pytest.raises(ValueError):
        presume(2026, "증여", amount=1)
    with pytest.raises(ValueError):
        presume(2026, "배우자등양도", amount=1)                    # transferee_relation 없음
    with pytest.raises(ValueError):
        presume(2026, "배우자등양도", amount=1, transferee_relation="배우자", donor_relation="배우자")
    with pytest.raises(ValueError):
        presume(2026, "취득자금")
    with pytest.raises(ValueError):
        presume(2026, "취득자금", amount=1, proven_amount=1, facts={"입증금액": {"소득": 1}})
    assert presume(2026, "취득자금", amount=10 * 억)["증여추정"] is None


# ── 영 §27③·규칙 §10②③: 부동산가액 × 2% 를 (1.1)^n 으로 나눈 5년 합계, 1억원 미만 제외
def test_free_use_conversion_matches_formula():
    계수 = sum(1 / 1.1 ** n for n in range(1, 6))
    for 가액 in (13 * 억, 1_319_000_000, 20 * 억, 50 * 억):
        r = M.부동산무상사용_증여이익(2026, 부동산가액=가액, 특수관계인=True)
        환산 = r["무상사용_계산"]["환산이익"]
        assert abs(환산 - 가액 * 0.02 * 계수) < 1
        assert r["무상사용_증여재산가액"] == (환산 if 환산 >= 1 * 억 else 0)
    assert M.부동산무상사용_증여이익(2026, 부동산가액=13 * 억, 특수관계인=True)["무상사용_증여재산가액"] == 0


# ── 케이스 파일
@pytest.mark.parametrize("case", _NODE_CASES, ids=[c["case_id"] for c in _NODE_CASES])
def test_node_cases(case):
    ok, detail = verify_node_cases.run_case(case)
    assert ok, detail


def test_tool_cases_all_pass():
    assert len(_TOOL_CASES) >= 39
    tools = verify_tool_cases._tools()
    assert set(TOOLS) <= set(tools)
    total, bad, missing, gray = verify_tool_cases.run(only_tool="judge_low_price_transfer_gift")
    assert total and not bad
    total, bad, missing, gray = verify_tool_cases.run(only_tool="judge_gift_presumption")
    assert total and not bad


def test_ruling_cases_cite_case_numbers():
    판례 = [c for c in _NODE_CASES if c.get("rid")] + [c for c in _TOOL_CASES if c.get("rid")]
    assert len(판례) >= 8 and all(str(c["rid"]).startswith("조심 ") for c in 판례)


# ── 노드 형식·연결
def test_new_nodes_cite_current_editions_and_are_reachable():
    새 = [n for n in engine.전체().values() if n.fn.__module__ == M.__name__]
    assert len(새) >= 60
    assert {n.mst for n in 새} == {"276123", "290845", "284609"}
    assert all(n.세목 == "상증세" and n.원문 and n.산출 for n in 새)
    덮음 = {(n.법령, n.조) for n in 새}
    for 조문 in [("상속세 및 증여세법", j) for j in ("35", "37", "44", "45", "45의5", "68", "70", "71")] + \
            [("상속세 및 증여세법 시행령", j) for j in ("3", "10", "15", "16", "27", "34", "45", "66")] + [("상속세 및 증여세법 시행규칙", "10")]:
        assert 조문 in 덮음, 조문
    # 케이스가 건드리지 않는 새 노드가 없어야 한다(단독으로만 도는 노드 금지)
    건드림 = {i for c in _NODE_CASES for i in c["노드"]} | {i.strip() for c in _TOOL_CASES for i in c.get("노드", "").split("·") if i.strip()}
    assert {n.id for n in 새} - 건드림 == set()


def test_existing_nodes_read_new_delegated_nodes_but_default_unchanged():
    # 사실도 새 노드의 입력도 없으면 종전과 같다
    r = sangjeung_rest.상속세_과세가액(2026, 10 * 억, 채무=3 * 억)
    assert r["상속세과세가액"] == 7 * 억
    # 값을 주면 그 값(사실 우선)
    r = sangjeung_rest.상속세_과세가액(2026, 10 * 억, 채무=3 * 억, 채무_증명=True, 채권자유형="그밖", 채무_증빙=False)
    assert r["상속세과세가액"] == 7 * 억
    # 사실을 주면 영 §10① 노드가 판정
    r = sangjeung_rest.상속세_과세가액(2026, 10 * 억, 채무=3 * 억, 채권자유형="그밖", 채무_증빙=False)
    assert r["상속세과세가액"] == 10 * 억
    ctx = engine.실행({"세목구분": "상속", "영농상속재산가액": 5 * 억}, 2026, 세목="상증세")
    assert ctx.값("영농상속공제") == 5 * 억
    ctx = engine.실행({"세목구분": "상속", "영농상속재산가액": 5 * 억, "영농_피상속인": {"영농종사_년": 3, "재촌": True},
                     "영농_상속인": {"연령": 30, "영농종사_년": 3, "재촌": True}}, 2026, 세목="상증세")
    assert ctx.값("영농상속공제", None) is None


def test_gift_judgment_grid_unchanged_without_new_facts():
    """법 §43 노드에 §35·§37 후보를 더했지만, 그 사실이 없으면 기록이 늘지 않는다."""
    r = sangjeung_rest.증여_판정(2026, 금전대출_대출금액=5 * 억, 금전대출_대여자유형="개인", 특수관계인=True)
    assert r["과세특례_적용이익"]["조문"] == "§41의4"
    assert not [m for m in r["미적용 조문"] if "§35" in m["표기"] or "§37" in m["표기"]]
    r = sangjeung_rest.증여_판정(2026, 금전대출_대출금액=5 * 억, 금전대출_대여자유형="개인", 특수관계인=True, 시가=10 * 억, 대가=6 * 억)
    assert r["과세특례_적용이익"] == {"조문": "§35", "이익": 1 * 억, "배제": ["§41의4"]}    # 2,300만 < 1억 — 이익이 가장 큰 하나만(§43①)
