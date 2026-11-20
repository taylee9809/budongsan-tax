"""건축물분 재산세 — 조문표 대조(지방세법 §110①·§111①2호·§111②③·§112·§122·§151①6호, 시행령 §109①1호·§110·§118, 시행규칙 §55·§56).

기대값은 코드가 아니라 법제처 원문(2026-11-17 대조)에 적힌 세율·비율에서 손으로 계산한 것이다.
기준 사안: 시가표준액 10억원 → 과세표준 7억원(100분의 70).
"""
import pytest

import tax_params
from building_property_tax import NOT_COVERED, TOOLS, calc_building_property_tax as calc

V = 1_000_000_000          # 시가표준액
BASE = 700_000_000         # × 100분의 70

RESIDENTIAL = {"연면적": 800, "별표2업종": True, "시지역": True, "주거지역등": True}


def _overcrowded(**kw):
    return dict({"연면적": 800, "별표2업종": True, "과밀억제권역": True, "신설증설": "신설", "기산일": "2024-03-01"}, **kw)


def test_taxable_base_is_70_percent():
    r = calc(2026, V)
    assert r["공정시장가액비율"] == 0.7 and r["과세표준"] == BASE
    assert "지방세법 시행령 §109①1호" in r["적용 조문"] and "지방세법 §110①" in r["적용 조문"]


# §111①2호 — 가목 1천분의 40, 나목 1천분의 5, 다목 1천분의 2.5
@pytest.mark.parametrize("use,factory,label,tax,article", [
    ("일반", None, "다목", 1_750_000, "지방세법 §111①2호다목"),
    ("골프장", None, "가목", 28_000_000, "지방세법 §111①2호가목"),
    ("고급오락장", None, "가목", 28_000_000, "지방세법 §111①2호가목"),
    ("공장", RESIDENTIAL, "나목", 3_500_000, "지방세법 §111①2호나목"),
    ("공장", {"연면적": 800, "별표2업종": True}, "다목", 1_750_000, "지방세법 §111①2호다목"),
    ("공장", None, "다목", 1_750_000, "지방세법 §111①2호다목"),
])
def test_three_rate_classes(use, factory, label, tax, article):
    r = calc(2026, V, use=use, factory=factory)
    assert (r["세율구분"], r["재산세 본세"]) == (label, tax)
    assert article in r["적용 조문"]


def test_factory_is_never_item_ga():
    # findings 42 — 공장을 '가목'으로 인용한 오류. 가목은 골프장·고급오락장용 건축물뿐이다.
    for factory in (None, RESIDENTIAL, _overcrowded()):
        r = calc(2026, V, use="공장", factory=factory)
        assert r["세율구분"] != "가목" and "지방세법 §111①2호가목" not in r["적용 조문"]
    r = calc(2026, V, use="공장")
    assert any(m["표기"] == "지방세법 §111①2호가목" for m in r["미적용 조문"])
    assert any("다목 1천분의 2.5로 계산했다" in n for n in r["주의"])


# 나목 요건: 시 지역 + 주거지역 등 + 별표 2 업종 + 연면적 500제곱미터 이상(시행규칙 §55)
@pytest.mark.parametrize("change,tax", [
    ({}, 3_500_000),
    ({"연면적": 500}, 3_500_000),            # '500제곱미터 이상'
    ({"연면적": 499}, 1_750_000),
    ({"별표2업종": False}, 1_750_000),
    ({"시지역": False}, 1_750_000),          # 읍·면·군 지역
    ({"주거지역등": False}, 1_750_000),
    ({"도시형공장": True}, 3_500_000),       # 도시형 공장 제외는 §111②(§7①) 쪽에만 있다
])
def test_residential_zone_factory_requirements(change, tax):
    assert calc(2026, V, use="공장", factory=dict(RESIDENTIAL, **change))["재산세 본세"] == tax


# §111② — 과밀억제권역 공장 신설·증설: 최초의 과세기준일부터 5년간 1천분의 2.5 × 100분의 500 = 1천분의 12.5
@pytest.mark.parametrize("change,tax", [
    ({}, 8_750_000),
    ({"신설증설": "증설"}, 8_750_000),
    ({"과밀억제권역": False}, 1_750_000),
    ({"산업단지등": True}, 1_750_000),       # 괄호 — 산업단지·유치지역·공업지역 제외
    ({"신설증설": None}, 1_750_000),
    ({"도시형공장": True}, 1_750_000),       # 시행규칙 §7① 괄호
    ({"연면적": 499}, 1_750_000),
    ({"별표2업종": False}, 1_750_000),
    ({"중과제외목": "가"}, 1_750_000),       # 시행규칙 §7②2호 각 목
    ({"중과제외목": "바"}, 1_750_000),
    ({"기산일": None}, 1_750_000),           # 최초의 과세기준일을 정할 수 없다
])
def test_overcrowded_zone_factory_five_times(change, tax):
    r = calc(2026, V, use="공장", factory=_overcrowded(**change))
    assert r["재산세 본세"] == tax
    assert (r["세율구분"] == "§111②") == (tax == 8_750_000)


# 시행규칙 §56② — 취득일(또는 설치 시작일) 이후 최초로 도래하는 과세기준일부터 5년간
@pytest.mark.parametrize("start,year,first,heavy", [
    ("2022-03-01", 2026, "20220601", True),     # 2022·23·24·25·26 — 다섯 번째
    ("2021-03-01", 2026, "20210601", False),    # 2021~2025 — 2026년분은 기간 밖
    ("2021-06-01", 2026, "20210601", False),    # 과세기준일 당일 취득 — 그날이 최초
    ("2021-06-02", 2026, "20220601", True),     # 과세기준일 다음 날 취득 — 이듬해가 최초
    ("2026-06-01", 2026, "20260601", True),
    ("2026-06-02", 2026, "20270601", False),    # 아직 최초의 과세기준일이 오지 않았다
])
def test_first_assessment_date_and_five_year_window(start, year, first, heavy):
    r = calc(year, V, use="공장", factory=_overcrowded(기산일=start))
    assert r["최초과세기준일"] == first
    assert r["재산세 본세"] == (8_750_000 if heavy else 1_750_000)


def test_residential_rate_does_not_beat_overcrowded_rate():
    # §111② "그 건축물에 대한 재산세의 세율은 … 세율로 한다" — 나목 요건을 함께 갖춰도 1천분의 12.5
    r = calc(2026, V, use="공장", factory=dict(RESIDENTIAL, **_overcrowded()))
    assert r["세율구분"] == "§111②" and r["재산세 본세"] == 8_750_000


def test_urban_area_levy_and_education_tax():
    r = calc(2026, V)
    assert r["도시지역분"] == 980_000                  # 7억 × 1천분의 1.4 (§112①2호)
    assert r["지방교육세"] == 350_000                  # 본세 175만 × 100분의 20 — 도시지역분 제외 (§151①6호)
    assert r["총납부세액"] == 1_750_000 + 980_000 + 350_000
    r = calc(2026, V, urban_area=False)
    assert r["도시지역분"] == 0 and r["지방교육세"] == 350_000 and r["총납부세액"] == 2_100_000
    assert any(m["표기"] == "지방세법 §112①2호" for m in r["미적용 조문"])
    r = calc(2026, V, urban_area_rate=0.0023)          # §112② 조례 상한
    assert r["도시지역분"] == 1_610_000 and r["지방교육세"] == 350_000


def test_education_tax_follows_the_rate_class():
    assert calc(2026, V, use="골프장")["지방교육세"] == 5_600_000                              # 2,800만 × 20%
    assert calc(2026, V, use="공장", factory=_overcrowded())["지방교육세"] == 1_750_000       # 875만 × 20%


# §122 — 직전 연도 재산세액 상당액의 100분의 150을 '초과하는 경우'
@pytest.mark.parametrize("prior,expected,capped", [
    (1_000_000, 1_500_000, True),
    (1_166_666, 1_749_999, True),      # × 1.5 = 1,749,999 < 1,750,000
    (1_166_667, 1_750_000, False),     # × 1.5 = 1,750,000.5 — 초과하지 않는다
    (2_000_000, 1_750_000, False),
])
def test_tax_burden_cap_boundary(prior, expected, capped):
    r = calc(2026, V, prior_year_tax=prior)
    assert r["재산세 본세"] == expected
    assert r["세부담상한"]["제1호"]["상한적용"] is capped
    assert r["재산세 본세(산출세액)"] == 1_750_000
    assert r["지방교육세"] == expected * 20 // 100       # 납부하여야 할 재산세액 기준
    assert "지방세법 §122" in r["적용 조문"] and "지방세법 시행령 §118" in r["적용 조문"]


def test_cap_applies_to_each_levy_separately():
    # §122 괄호 "제112조제1항 각 호 … 각각의 세액"
    r = calc(2026, V, prior_year_tax=2_000_000, prior_year_urban_tax=600_000)
    assert (r["재산세 본세"], r["도시지역분"]) == (1_750_000, 900_000)
    assert r["총납부세액"] == 1_750_000 + 900_000 + 350_000
    r = calc(2026, V, prior_year_tax=1_000_000)          # 도시지역분 직전 세액이 없으면 그쪽은 상한을 걸지 않고 알린다
    assert (r["재산세 본세"], r["도시지역분"]) == (1_500_000, 980_000)
    assert any("prior_year_urban_tax" in n for n in r["주의"])


def test_no_prior_year_tax_is_flagged_not_silently_skipped():
    r = calc(2026, V)
    assert r["세부담상한"] is None
    assert any(m["표기"] == "지방세법 §122" for m in r["미적용 조문"])
    assert any("세 부담 상한" in n for n in r["주의"])


def test_recomputed_prior_year_amount_is_labelled():
    r = calc(2026, V, use="골프장", prior_year_tax=10_000_000, prior_year_recomputed=True)
    assert r["재산세 본세"] == 15_000_000


# §111③ — 표준세율의 100분의 50 범위
def test_ordinance_rate_within_half_range():
    assert calc(2026, V, ordinance_rate=0.00375)["재산세 본세"] == 2_625_000
    r = calc(2026, V, ordinance_rate=0.00125)
    assert r["재산세 본세"] == 875_000 and r["조례가감 적용여부"] and "지방세법 §111③" in r["적용 조문"]
    for bad in (0.001, 0.004):
        with pytest.raises(ValueError):
            calc(2026, V, ordinance_rate=bad)
    r = calc(2026, V, use="공장", factory=_overcrowded(), ordinance_rate=0.003)
    assert r["재산세 본세"] == 8_750_000 and not r["조례가감 적용여부"]
    assert any("ordinance_rate 를 적용하지 않았다" in n for n in r["주의"])


def test_amounts_are_truncated_below_one_won_without_float_drift():
    r = calc(2026, 123_456_789)
    assert r["과세표준"] == 86_419_752              # 86,419,752.3
    assert r["재산세 본세"] == 216_049              # 216,049.38
    assert r["도시지역분"] == 120_987               # 120,987.6528
    assert r["지방교육세"] == 43_209                # 43,209.8
    # 1천분의 2.5·1천분의 1.4는 이진 부동소수로 딱 떨어지지 않는다 — 정수로 나누어떨어지는 값은 그대로 나와야 한다
    for v in (4_000_000, 20_000_000, 2_860_000_000, 9_999_600_000):
        r = calc(2026, v)
        base = v * 7 // 10
        assert (r["과세표준"], r["재산세 본세"], r["도시지역분"]) == (base, base * 25 // 10_000, base * 14 // 10_000)


def test_housing_only_articles_are_reported_as_not_applied():
    r = calc(2026, V)
    labels = {m["표기"] for m in r["미적용 조문"]}
    assert {"지방세법 §110③", "지방세법 §111①3호나목", "지방세법 §111의2①"} <= labels
    assert "지방세법 시행령 §109①2호" not in r["적용 조문"]


def test_housing_result_is_unchanged_by_building_branches():
    # 주택분은 종전 산식 그대로 — 공시가격 9억, 직전 8억, 1세대1주택 아님
    import tax_nodes.jaesan_geonchuk  # noqa: F401
    from tax_nodes.jaesan import 재산세_주택
    r = 재산세_주택(900_000_000, 2026, 직전연도_시가표준액=800_000_000)
    assert r["과세표준"] == 507_000_000              # 상한액 = 8억×60% + 9억×60%×5% = 5억700만 < 5억4천만
    assert r["재산세 본세"] == 507_000_000 * 4 // 1000 - 630_000
    assert not any("§111①2호" in a or "§111②" in a or "§111③" in a for a in r["적용 조문"])
    assert not any("§111①2호" in m["표기"] or m["표기"] in ("지방세법 §111②", "지방세법 §111③") for m in r["미적용 조문"])


def test_unverified_year_is_refused():
    with pytest.raises(tax_params.ParamNotVerified):
        calc(2025, V)


def test_future_year_is_marked_as_estimate():
    r = calc(2027, V)
    assert "추정" in r["값 출처"]["건축물 세율(다목)"]


@pytest.mark.parametrize("kw", [
    {"standard_value": 0},
    {"standard_value": V, "use": "상가"},
    {"standard_value": V, "factory": {"연면적": 800}},                       # 공장이 아닌데 factory
    {"standard_value": V, "use": "공장", "factory": {"면적": 800}},
    {"standard_value": V, "use": "공장", "factory": _overcrowded(신설증설="이전")},
    {"standard_value": V, "use": "공장", "factory": _overcrowded(중과제외목="사")},   # 사목은 차량·기계장비
    {"standard_value": V, "prior_year_tax": 0},
    {"standard_value": V, "urban_area_rate": 0.003},                         # §112② 1천분의 2.3 초과
    {"standard_value": V, "urban_area": False, "urban_area_rate": 0.0014},
])
def test_invalid_input_raises(kw):
    with pytest.raises(ValueError):
        calc(2026, **kw)


def test_scope_notice_and_tool_export():
    r = calc(2026, V)
    assert r["다루지 않는 것"] == NOT_COVERED
    assert any("지역자원시설세" in s for s in NOT_COVERED) and any("부속토지" in s for s in NOT_COVERED)
    assert TOOLS == ("calc_building_property_tax",)
    assert calc.__doc__.splitlines()[0].startswith("Korea property tax")
    assert "근거표" not in r
