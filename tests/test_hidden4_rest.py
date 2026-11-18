"""분업 4차 '요약표 밖 조문' 묶음 (2026-11-18) — 제목 분류 때문에 커버리지 표에 안 잡히고 노드도 없던 조문 23개와 조특법 신설 4개.

1. 케이스 파일 data/verification/node_cases/hidden4_rest.jsonl (H4R-*) 전체 — 기대값은 원문 기준액·산식에서 손으로 계산한 것
2. (법인세 성실신고 소규모 법인 판정은 조정 세션 지시로 제외 — 비공개 원본의 법인세 노드를 가져오기로 했다)
3. 새 노드가 등록돼 있고 원문·MST 를 들고 있는가, 호·목 구멍을 새로 만들지 않았는가
4. 연결 전 호출이 그대로인가 — 새 사실을 주지 않으면 기존 합성 함수의 결과에 새 키가 붙지 않고 값도 같다
5. 서로 대조되는 두 구현이 같은 답을 내는가 — 영 §167의2① 통산(새 노드) vs 법 §102② 노드, 영 §168의7 vs 법인세법 시행령 §92의4,
   항목별 개발비용 vs 총액 입력, 날짜로 센 보유연수 vs 직접 준 보유연수
"""
import importlib
import itertools
import json
import pathlib
import random
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tax_judgment  # noqa: E402
import tax_params  # noqa: E402
from tax_nodes.engine import 모두올림, 실행, 전체  # noqa: E402

모두올림()
from tax_nodes import jaegeonchuk, jongbu, yangdo_bisaeop, yangdo_tongsan  # noqa: E402

verify_node_cases = importlib.import_module("verify_node_cases")
node_coverage = importlib.import_module("node_coverage")

_CASES = [json.loads(l) for l in (ROOT / "data" / "verification" / "node_cases" / "hidden4_rest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
_새모듈 = ("jaegeonchuk_gaebalbiyong", "yangdo_tongsan", "yangdo_jotuk_ijeon", "jongbu_napbu", "chwideuk_singo", "jotuk_sinseol")
_새노드 = {k: n for k, n in 전체().items() if n.fn.__module__.rsplit(".", 1)[-1] in _새모듈}

#: 이번에 노드가 생긴 조문 — (법령, 조). 요약표 밖 23개 + 조특법 신설 4개 + 호·목 1개가 걸린 조문.
_대상조문 = [
    ("재건축초과이익 환수에 관한 법률", "2"), ("재건축초과이익 환수에 관한 법률", "6"), ("재건축초과이익 환수에 관한 법률", "11"),
    ("재건축초과이익 환수에 관한 법률 시행령", "8"), ("재건축초과이익 환수에 관한 법률 시행령", "9"), ("재건축초과이익 환수에 관한 법률 시행령", "10"),
    ("재건축초과이익 환수에 관한 법률 시행령", "10의2"), ("재건축초과이익 환수에 관한 법률 시행령", "13의2"),
    ("소득세법", "104의2"), ("소득세법", "118의13"), ("소득세법 시행령", "167의2"), ("소득세법 시행령", "168의7"),
    ("조세특례제한법", "32"), ("조세특례제한법 시행령", "70"),
    ("종합부동산세법", "20의2"), ("종합부동산세법 시행령", "4의5"), ("종합부동산세법 시행령", "16의2"), ("농어촌특별세법", "6"), ("농어촌특별세법", "7"),
    ("지방세법", "20"), ("지방세법 시행령", "34"), ("지방세법 시행령", "37"),
    ("조세특례제한법", "23의2"), ("조세특례제한법", "91의26"), ("조세특례제한법", "91의27"), ("조세특례제한법", "91의28"),
]


# ------------------------------------------------------------------ 1·2. 케이스
def test_case_file_shape():
    ids = [c["case_id"] for c in _CASES]
    assert len(ids) == len(set(ids)) and all(i.startswith("H4R-") for i in ids)
    등록 = 전체()
    for c in _CASES:
        assert c["방식"] in ("노드", "함수") and c["기대"] and c["결론요지"] and c["사건"], c["case_id"]
        assert all(n in 등록 for n in c["노드"]), (c["case_id"], [n for n in c["노드"] if n not in 등록])


@pytest.mark.parametrize("case", _CASES, ids=[c["case_id"] for c in _CASES])
def test_h4r_case(case):
    ok, detail = verify_node_cases.run_case(case)
    assert ok, detail


# ------------------------------------------------------------------ 3. 등록·원문·호목
@pytest.mark.parametrize("법령,조", _대상조문)
def test_target_article_has_node(법령, 조):
    assert any(n.법령 == 법령 and n.조 == 조 for n in 전체().values()), "%s §%s 에 실행 노드가 없다" % (법령, 조)


def test_new_nodes_carry_text_and_current_mst():
    현행 = {"재건축초과이익 환수에 관한 법률": "277019", "재건축초과이익 환수에 관한 법률 시행령": "284841", "소득세법": "280405", "소득세법 시행령": "290841",
          "조세특례제한법": "284389", "조세특례제한법 시행령": "288915", "종합부동산세법": "280417", "종합부동산세법 시행령": "290557",
          "농어촌특별세법": "285905", "지방세법": "282559", "지방세법 시행령": "290815", "법인세법": "280349", "법인세법 시행령": "290843"}
    assert len(_새노드) >= 130
    for nid, n in _새노드.items():
        assert n.원문.strip() and n.제목.strip() and n.산출, nid
        assert n.mst == 현행[n.법령], (nid, n.mst)


def test_no_new_subunit_gap():
    """호 단위로 옮긴 조문(§2·§11①·영 §9①·영 §34·영 §37·§32⑤·§104⑤·영 §167의2①·§20의2①·조특령 §99의2③)에 빠진 형제 호가 없다."""
    subunits = json.loads(node_coverage.SUBUNITS.read_text(encoding="utf-8"))
    dispositions = {k: v for k, v in json.loads(node_coverage.DISPOSITIONS.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    gaps = node_coverage.subunit_gaps(전체(), subunits, dispositions)
    assert [g["표기"] for g in gaps["미처리"]] == []


def test_params_rows_have_source():
    for 키 in ("종부세.납부유예.요건", "종부세.납부유예.이자율", "재건축부담금.감경.다른주택기준", "취득세.신고납부기한",
              "양도세.지정지역.가산세율", "조특.외국자회사수입배당금.익금불산입", "조특.국내시장복귀계좌", "조특.환율변동위험회피상품", "조특.국민성장집합투자증권저축"):
        row = tax_params.get_row(키, 2026)
        assert row["근거"] and row["MST"] and row["검증연도"] == [2026] and row["확인일"] == "2026-11-18", 키
        with pytest.raises(tax_params.ParamNotVerified):
            tax_params.get_param(키, 2025)


def test_corpus_file_cites_new_articles():
    coverage_audit = importlib.import_module("coverage_audit")
    refs = coverage_audit.load_node_refs()["조세특례제한법"]
    assert {(23, 2), (91, 26), (91, 27), (91, 28)} <= refs


# ------------------------------------------------------------------ 4. 연결 전 호출은 그대로
_재건축_새키 = ("개발비용 내역(§11)", "종료시점 다른 주택(§14의2②)", "납부의무자(§6①)", "조합원 2차 납부의무액(§6④)", "감경 후 처분의무(§14의2③)",
           "납부유예 신청기간(영 §13의2①)", "납부유예 취소 시 이자(영 §13의2③)", "단수월 안분율(영 §8④)", "양도세 일 단위 안분(영 §10)")


@pytest.mark.parametrize("개발비용", [0, 5_000_000_000, 11_000_000_000])
@pytest.mark.parametrize("일주택,보유", [(False, None), (True, 5), (True, 12), (True, 25)])
def test_levy_without_new_facts_is_unchanged(개발비용, 일주택, 보유):
    """새 사실(개발비용_항목·세대_다른주택 등)이 없으면 노드 합성과 판정기 결과가 예전과 같고 새 키가 붙지 않는다."""
    kw = dict(종료시점_주택가액=100_000_000_000, 개시시점_주택가액=60_000_000_000, 조합원수=100, 정상상승률=0.2, 개발비용=개발비용,
              종료시점_1세대1주택=일주택)
    if 보유 is not None:
        kw["1세대1주택_보유연수"] = 보유
    r = jaegeonchuk.재건축부담금(**kw)
    assert not any(k in r for k in _재건축_새키)
    assert not any("§11" in a or "10의2" in a for a in r["적용 조문"])
    t = tax_judgment.estimate_reconstruction_levy(100_000_000_000, 60_000_000_000, 100, 0.2, 개발비용,
                                                  one_home_holding_years=보유, is_one_home_at_end=일주택)
    assert "개발비용_내역" not in t
    assert r["부담금추정"] == t["부담금추정"] and r["감경률"] == t["감경률"]


def test_levy_explicit_one_home_fact_wins_over_other_homes():
    """호출자가 '종료시점_1세대1주택'을 주면 세대_다른주택 판정보다 먼저다."""
    kw = dict(종료시점_주택가액=100_000_000_000, 개시시점_주택가액=60_000_000_000, 조합원수=100, 정상상승률=0.2, 부과종료일="2026-06-30",
              세대_다른주택=[{"라벨": "일반", "유형": "일반", "취득일": "2020-01-01"}], **{"1세대1주택_보유연수": 12})
    assert jaegeonchuk.재건축부담금(**kw)["감경률"] == 0.0
    assert jaegeonchuk.재건축부담금(종료시점_1세대1주택=True, **kw)["감경률"] == 0.5


@pytest.mark.parametrize("공시가격", [1_500_000_000, 2_500_000_000, 5_000_000_000])
@pytest.mark.parametrize("보유", [0, 4, 5, 12, 18])
def test_jongbu_without_new_facts_is_unchanged(공시가격, 보유):
    r = jongbu.종부세_주택(공시가격, 2026, 일세대일주택자=True, 연령=62, 보유연수=보유)
    assert not any(k in r for k in ("납부유예(§20의2①)", "납부유예 취소 시 징수(§20의2⑤)", "보유기간(영 §4의5)"))
    assert not any("§20의2" in a or "§4의5" in a for a in r["적용 조문"])


# ------------------------------------------------------------------ 5. 두 구현의 대조
def _통산_입력(seed: int):
    rng = random.Random(seed)
    구분들 = ["기본", "단기50", "단기60", "비사업용", "중과20"]
    out = []
    for i in range(rng.randint(2, 6)):
        out.append({"자산": "자산%d" % i, "호": rng.choice([1, 1, 1, 2]), "세율구분": rng.choice(구분들),
                    "양도소득금액": rng.randrange(-200, 300) * 1_000_000, "양도일": "2026-%02d-%02d" % (rng.randint(1, 12), rng.randint(1, 28))})
    return out


@pytest.mark.parametrize("seed", range(60))
def test_tongsan_matches_law_102_2_node(seed):
    """영 §167의2① 호별 노드(yangdo_tongsan)와 법 §102② 노드(yangdo_gigan)가 같은 통산 결과를 낸다 — 손실 자산이 하나인 사안과
    세율 묶음이 겹치지 않는 사안에서. 손실 자산이 여럿이면 처리 순서가 달라 자산별 금액이 갈릴 수 있어 호별 합계만 본다."""
    목록 = _통산_입력(seed)
    ctx = 실행({"양도자산목록": 목록}, 2026, 세목="양도세")
    새 = ctx.값("통산후_자산별")
    옛 = ctx.값("양도차손통산")
    for 호 in {a["호"] for a in 목록}:
        합 = sum(새[a["자산"]] for a in 목록 if a["호"] == 호)
        assert abs(합 - 옛["호별"][str(호)]) <= len(목록), (호, 합, 옛["호별"])
        익 = sum(a["양도소득금액"] for a in 목록 if a["호"] == 호 and a["양도소득금액"] > 0)
        손 = -sum(a["양도소득금액"] for a in 목록 if a["호"] == 호 and a["양도소득금액"] < 0)
        assert abs(합 - max(익 - 손, 0)) <= len(목록)      # 호 안에서만 통산, 남은 차손은 소멸
    assert all(v >= 0 for v in 새.values())


@pytest.mark.parametrize("seed", range(30))
def test_multi_sale_tax_invariants(seed):
    목록 = [a for a in _통산_입력(seed) if a["호"] == 1] or [{"자산": "x", "양도소득금액": 50_000_000}]
    r = yangdo_tongsan.양도세_여러건(목록, 2026)
    배분 = r["기본공제 배분(§103②)"]
    assert 0 <= sum(배분.values()) <= 2_500_000                      # §103① — 호별 연 250만원
    assert all(0 <= 배분[k] <= r["통산후_양도소득금액"][k] for k in 배분)
    합2 = sum(v["세액"] for v in r["세율구분별 세액(§104⑤2호)"].values())
    합1 = (r["과세표준 합계 × 기본세율(§104⑤1호)"] or {}).get("세액", 0)
    assert r["양도소득세"] == max(합1, 합2)                           # §104⑤ — 큰 것
    assert r["총납부세액"] == r["양도소득세"] + r["지방소득세(10%)"]


def test_single_sale_through_multi_composer_equals_single_calc():
    """한 건만 넣으면 한 건 계산(양도세_부동산)과 같은 세액 — 통산·§104⑤ 비교가 끼어들지 않는다."""
    from tax_nodes.yangdo import 양도세_부동산
    for 종류, 보유 in itertools.product(("토지", "비사업용토지"), (2.5, 5, 12)):
        kw = dict(양도가액=700_000_000, 취득가액=300_000_000, 필요경비=10_000_000, 보유연수=보유, 자산종류=종류, 양도일="2026-05-01")
        한건 = 양도세_부동산(연도=2026, **kw)["양도소득세"]
        여러 = yangdo_tongsan.양도세_여러건([{"자산": "A", "양도일": "2026-05-01", "계산": kw}], 2026)
        assert 여러["양도소득세"] == 한건, (종류, 보유)


@pytest.mark.parametrize("현황,공부", [("전", None), ("답", "임야"), ("과수원", "대"), ("임야", "전"), ("목장용지", None), ("대", None), ("잡종지", "전"),
                                     (None, "임야"), (None, "전"), (None, "공장용지")])
def test_land_category_matches_corporate_node(현황, 공부):
    """소득세법 시행령 §168의7 과 법인세법 시행령 §92의4 는 같은 문언이다 — 같은 입력에 같은 토지종류."""
    f = {k: v for k, v in (("사실상_현황", 현황), ("공부상_지목", 공부)) if v}
    assert 실행(f, 2026, 세목="양도세").값("토지종류_판정") == 실행(f, 2026, 세목="법인세").값("판정지목")


def test_explicit_land_type_wins_over_category_node():
    r = yangdo_bisaeop.비사업용토지_판정("임야", "2026-05-01", "2015-01-01", 사실상_현황="전", 임야소재지_거주=True)
    assert not any("168의7" in a for a in r["적용 조문"])


@pytest.mark.parametrize("항목", [
    {"공사비": 10_000_000_000}, {"공사비": 9_000_000_000, "설계감리비": 400_000_000, "부대비용": 300_000_000, "그밖의경비": 300_000_000},
    {"공사비": 9_000_000_000, "세금공과금": 500_000_000, "기부채납가액": 500_000_000}, {"조합운영경비": 2_000_000_000, "임대주택건설비용": 8_000_000_000},
])
def test_itemized_cost_equals_lump_sum(항목):
    """항목 합계가 100억이면 총액 100억을 넣은 것과 같은 부담금."""
    assert sum(항목.values()) == 10_000_000_000
    base = dict(종료시점_주택가액=100_000_000_000, 개시시점_주택가액=60_000_000_000, 조합원수=100, 정상상승률=0.2)
    assert jaegeonchuk.재건축부담금(개발비용_항목=항목, **base)["부담금추정"] == jaegeonchuk.재건축부담금(개발비용=10_000_000_000, **base)["부담금추정"]


@pytest.mark.parametrize("취득일,연수", [("2021-06-01", 5), ("2021-06-02", 4), ("2016-06-01", 10), ("2011-01-15", 15), ("2026-06-01", 0)])
def test_holding_years_from_date_equals_explicit(취득일, 연수):
    a = jongbu.종부세_주택(2_500_000_000, 2026, 일세대일주택자=True, 연령=62, 주택취득일=취득일)
    b = jongbu.종부세_주택(2_500_000_000, 2026, 일세대일주택자=True, 연령=62, 보유연수=연수)
    assert a["종합부동산세"] == b["종합부동산세"]


def test_jongbu_credit_is_not_truncated_by_float():
    """findings 210 — 연령 20% + 보유 50% = 70%: 5,400,000 × 70% = 3,780,000(3,779,999 가 아니다)."""
    r = jongbu.종부세_주택(2_500_000_000, 2026, 일세대일주택자=True, 연령=62, 보유연수=18)
    assert (r["산출세액"], r["1세대1주택자 세액공제액"], r["종합부동산세"]) == (5_400_000, 3_780_000, 1_620_000)


def test_acquisition_deadline_feeds_penalty_node():
    """지방세법 §20①·④ 기한이 납부지연가산세 기산(법정납부기한)으로 들어간다 — '납부기한'을 주지 않아도 취득일·취득원인으로."""
    from tax_nodes.chwideuk_gasanse import 취득세_가산세
    공통 = dict(취득일="2026-03-10", 신고하여야할_납부세액=10_000_000, 신고세액=10_000_000, 납부세액=0, 납부일="2026-06-08")
    자동 = 취득세_가산세(취득원인="주택유상", **공통)
    직접 = 취득세_가산세(납부기한="2026-05-09", **공통)
    assert 자동["납부지연가산세"] == 직접["납부지연가산세"] and 직접["납부지연가산세"] > 0
