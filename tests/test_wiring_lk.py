"""분업 2차 '연결' 묶음 (2026-11-17) — 단독으로만 돌던 조문 노드를 계산 흐름에 이은 것의 회귀.

1. 농어촌특별세법 §4 비과세 → 양도소득세 감면분(§5①1호)·취득세분(§5①6호)
2. 종합부동산세법 시행령 §3⑦ 임대기간 계산 → §3① 합산배제 임대주택
3. 지방세특례제한법 §2①8호 '직접 사용' → 공통 추징 판정
4. 소득세법 §104의3①1호 — 가목 단서 예외 농지와 나목(findings 70)
5. judge_155_special 의 homes_at_sale (합가 당시 주택수와 양도일 현재 주택수의 구분)
케이스 원본은 data/verification/node_cases/lk_wiring.jsonl (LK-*). 여기서는 그 파일 전체와, 연결 전 호출이 그대로인지를 본다.
"""
import importlib
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tax_judgment  # noqa: E402
import tax_nodes.chwideuk  # noqa: E402,F401
import tax_nodes.chwideuk_saryeo  # noqa: E402,F401
import tax_nodes.jiteuk_entity  # noqa: E402,F401
import tax_nodes.jiteuk_jeongui  # noqa: E402,F401
import tax_nodes.jongbu_imdaegigan  # noqa: E402,F401
import tax_nodes.jongbu_setdae  # noqa: E402,F401
import tax_nodes.nongteuk  # noqa: E402,F401
import tax_nodes.yangdo_bisaeop  # noqa: E402,F401
import tax_nodes.yangdo_gigan  # noqa: E402,F401
from tax_nodes.engine import 실행  # noqa: E402

verify_node_cases = importlib.import_module("verify_node_cases")
_CASES = [json.loads(l) for l in (ROOT / "data" / "verification" / "node_cases" / "lk_wiring.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
조특 = "조세특례제한법"


@pytest.mark.parametrize("case", _CASES, ids=[c["case_id"] for c in _CASES])
def test_lk_case(case):
    ok, detail = verify_node_cases.run_case(case)
    assert ok, detail


# ------------------------------------------------------------------ 1. 농특세
def _양도농특세(**사실):
    return 실행(dict({"양도세_감면세액": 10_000_000}, **사실), 2026, 세목="양도세").값("농특세_양도세감면분")


@pytest.mark.parametrize("조, 자경, 세액", [
    ("66", False, 0), ("67", False, 0), ("68", False, 0), ("69", False, 0), ("69의2", False, 0), ("69의3", False, 0), ("69의4", False, 0), ("70", False, 0),
    ("70의2", False, 2_000_000), ("77", False, 2_000_000), ("77", True, 0), ("77의2", False, 2_000_000), ("77의3", False, 2_000_000),
    ("97의3", False, 2_000_000), ("99", False, 2_000_000), ("99의2", False, 2_000_000), ("99의3", False, 2_000_000),
    ("33", False, 0), ("63", False, 0), ("64", False, 0), ("40", False, 0),
])
def test_nongteuk_transfer_relief_by_article(조, 자경, 세액):
    f = {"감면법령": 조특, "감면조": 조}
    if 자경:
        f["자경농지_직접경작"] = True
    assert _양도농특세(**f)["세액"] == 세액


def test_nongteuk_transfer_without_article_is_unchanged():
    # 감면 근거 조문을 주지 않은 기존 호출 — 연결 노드는 미적용, §5①1호 노드 결과 그대로
    r = _양도농특세()
    assert r == {"과세표준": 10_000_000, "세율": 0.2, "세액": 2_000_000, "근거": "호출자가 넘긴 감면세액"}
    ctx = 실행({"1세대1주택_비과세_고가주택": True, "고가주택_과세분_산출세액": 23_995_550, "산출세액_전체": 82_355_100, "양도세_감면율": 1.0}, 2005, 기준일="20050630", 세목="양도세")
    assert ctx.값("농특세_양도세감면분")["세액"] == 4_799_110          # 국심 2006서2200 (R102164-1)


def test_nongteuk_acquisition_share():
    from tax_nodes.chwideuk import 취득세_부동산
    kw = dict(취득가액=500_000_000, 연도=2026, 취득일="2026-06-01")
    assert 취득세_부동산(취득원인="유상.농지", **kw)["농어촌특별세"] == 1_000_000
    assert 취득세_부동산(취득원인="유상.농지", 자경농민_농지임야=True, **kw)["농어촌특별세"] == 0                       # §4 10호
    assert 취득세_부동산(취득원인="주택유상", 환매등기_환매=True, 전용면적=120, **kw)["농어촌특별세"] == 0               # §4 10의4호
    assert 취득세_부동산(취득원인="주택유상", 재산분할=True, 전용면적=120, **kw)["농어촌특별세"] == 1_000_000           # 6호는 대상 아님
    assert 취득세_부동산(취득원인="주택유상", 전용면적=84, **kw)["농어촌특별세"] == 0                                   # §4 11호 — 종전 그대로
    # §13의2 중과가 겹치면 10의4호를 적용하지 않고 종전 계산을 둔다(해석 미확인)
    중과 = 취득세_부동산(취득원인="주택유상", 환매등기_환매=True, 법인=True, 대도시_법인설립전입_부동산=True, **kw)
    assert 중과["농어촌특별세"] == 5_000_000


# ------------------------------------------------------------------ 2. 종부세 임대기간
def _임대(h, 연도=2026):
    base = {"전용면적": 84, "공시가격": 150_000_000, "임대호수_시도": 5, "임대료증가율": 0.03, "수도권": False}
    return 실행({"임대주택목록": [dict(base, **h)], "임대사업자_사업자등록": True}, 연도, 세목="종부세").값("합산배제_임대주택_판정")[0]


@pytest.mark.parametrize("호", range(1, 12))
@pytest.mark.parametrize("기간", [None, 0, 3, 5, 6, 10])
@pytest.mark.parametrize("진행", [None, True, False])
def test_jongbu_direct_period_is_unchanged(호, 기간, 진행):
    """임대기간을 직접 준(또는 아무 기간 사실도 안 준) 호출은 연결 전과 같은 식으로 판정된다."""
    h = {"호": 호}
    if 기간 is not None:
        h["임대기간_연"] = 기간
    if 진행 is not None:
        h["임대의무기간_진행중"] = 진행
    r = _임대(h)
    요건 = {1: 5, 2: 5, 3: 5, 5: 10, 6: 5, 7: 10, 8: 10, 10: 6, 11: 6}.get(호, 0)
    미달 = bool(요건) and (기간 or 0) < 요건 and 진행 is False
    assert ("미만 임대" in r["사유"]) is 미달
    assert "임대기간" not in r


def test_jongbu_period_from_nodes():
    r = _임대(dict(호=8, 임대개시일="2014-01-01", 임대종료일="2025-01-01"))
    assert r["합산배제"] is True and r["임대기간"]["임대월수"] == 132 and r["임대기간"]["기산일"] == "2014-01-01"
    r = _임대(dict(호=8, 임대개시일="2020-01-01", 임대종료일="2024-01-01"))
    assert r["합산배제"] is False and "⑦항 계산 48개월" in r["사유"]
    # 임대사업자 등록 전 임대는 세지 않는다(⑦1호 '임대사업자로서')
    r = _임대(dict(호=2, 임대개시일="2019-01-01", 임대사업자_등록일="2022-01-01", 임대종료일="2026-03-01"))
    assert r["합산배제"] is False and r["임대기간"]["기산일"] == "2022-01-01"
    # 호출자가 진행중을 직접 주면 그 값이 계산값보다 앞선다
    r = _임대(dict(호=8, 임대개시일="2020-01-01", 임대종료일="2024-01-01", 임대의무기간_진행중=True))
    assert r["합산배제"] is True


# ------------------------------------------------------------------ 3. 지특 직접 사용
def _추징(**f):
    return 실행(dict({"취득일": "2022-01-01", "직접사용개시일": "2022-03-01"}, **f), 2026, 기준일="20220101").값("추징_11-3")


def test_jiteuk_direct_use_feeds_recapture():
    assert _추징(판정일="2026-06-01")["해당"] is False
    assert _추징(판정일="2026-06-01", 사용주체="소유자")["해당"] is False
    r = _추징(판정일="2026-06-01", 사용주체="임차인")
    assert r["해당"] is True and "§2①8호" in r["사유"]
    assert _추징(판정일="2026-06-01", 직접사용=True, 사용주체="임차인")["해당"] is False     # 값을 주면 그 값
    assert _추징(처분일="2026-05-01", 사용주체="소유자", 임대사용=True)["해당"] is True          # 직접 사용 기간 없이 처분
    assert _추징(처분일="2026-05-01", 사용주체="소유자")["해당"] is False                       # 50개월 직접 사용 후 처분
    assert _추징(사용주체="임차인")["해당"] is None                                             # 판정일·처분일 없음


# ------------------------------------------------------------------ 4. 비사업용 토지 — 농지 (findings 70)
@pytest.mark.parametrize("호", [1, 3, 4, 5, 7, 8, 9, "9의2", 10])
def test_exception_farmland_in_city_area_follows_item_na(호):
    from tax_nodes.yangdo_bisaeop import 비사업용토지_판정
    보조 = {3: {"이농일": "2025-01-01"}, 7: {"사유전_5년_재촌자경": True, "사유후_재촌": True, "농지법23_임대": True}}.get(호, {})
    kw = dict(토지종류="농지", 양도일="2026-09-01", 취득일="2005-01-01", 농지소재지_거주=False, 자경=False, 농지_예외호=호, **보조)
    assert 비사업용토지_판정(**kw)["비사업용토지"] is False                                                           # 도시지역 밖 — 가목 단서
    assert 비사업용토지_판정(시지역_도시지역=True, 도시지역_편입일="2024-06-01", **kw)["비사업용토지"] is False            # 편입 3년 이내
    r = 비사업용토지_판정(시지역_도시지역=True, 도시지역_편입일="2010-01-01", **kw)
    assert r["비사업용토지"] is True and r["사유"].startswith("나목")
    assert 비사업용토지_판정(시지역_도시지역=True, 도시지역_편입일="2010-01-01", 녹지지역_또는_GB=True, **kw)["비사업용토지"] is False


# ------------------------------------------------------------------ 5. judge_155_special
def test_155_special_homes_at_sale_does_not_change_requirement():
    j = tax_judgment.judge_155_special
    base = dict(kind="혼인", event_date="2022-04-01", sale_date="2026-04-01")
    for at_sale in (None, 1, 2, 3):
        extra = {} if at_sale is None else {"homes_at_sale": at_sale}
        assert j(homes_mine=1, homes_spouse_or_parent=1, **base, **extra)["특례적용"] is True
        assert j(homes_mine=2, homes_spouse_or_parent=2, **base, **extra)["특례적용"] is False
    r = j(homes_mine=1, homes_spouse_or_parent=1, homes_at_sale=3, **base)
    assert r["주택수_판정기준"] == {"합가당시": "1+1", "양도일현재": 3}
    assert "주택수_판정기준" not in j(homes_mine=1, homes_spouse_or_parent=1, **base)
