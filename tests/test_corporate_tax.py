"""법인의 부동산 양도 세액 — 조문표 대조(법인세법 §55·§55의2, 시행령 §92의2, 지방세법 §103의20·§103의31).

기대값은 코드가 아니라 법제처 원문(2026-11-17 대조)에 적힌 기준액·세율에서 손으로 계산한 것이다.
"""
import pytest

import tax_http
import tax_params
from corporate_tax import NOT_COVERED, calc_corporate_property_sale_tax as calc


def _house(**kw):
    return dict({"라벨": "A", "종류": "주택", "양도금액": 500_000_000, "장부가액": 400_000_000}, **kw)


# 원문 세율표의 구간 끝 기준액: "2천만원 + …", "39억8천만원 + …", "655억8천만원 + …"
@pytest.mark.parametrize("base,expected", [
    (100_000_000, 10_000_000), (200_000_000, 20_000_000), (300_000_000, 40_000_000),
    (20_000_000_000, 3_980_000_000), (300_000_000_000, 65_580_000_000),
    (400_000_000_000, 65_580_000_000 + 25_000_000_000),
])
def test_general_brackets_match_statute_table(base, expected):
    assert calc(2026, [], taxable_base=base)["법인세_각사업연도소득"] == expected


# §55①2호: "200억원 이하 100분의 20", "40억원 + …", "656억원 + …"
@pytest.mark.parametrize("base,expected", [
    (100_000_000, 20_000_000), (20_000_000_000, 4_000_000_000), (300_000_000_000, 65_600_000_000),
])
def test_small_rental_corporation_brackets(base, expected):
    r = calc(2026, [], taxable_base=base, small_rental_corporation=True)
    assert r["법인세_각사업연도소득"] == expected
    assert r["적용세율표"] == "§55①2호"


# 지방세법 §103의20①: "200만원 + …", "3억9천800만원 + …", "65억5천800만원 + …" / 2호 "4억원 + …", "65억6천만원 + …"
@pytest.mark.parametrize("base,small,expected", [
    (200_000_000, False, 2_000_000), (20_000_000_000, False, 398_000_000), (300_000_000_000, False, 6_558_000_000),
    (20_000_000_000, True, 400_000_000), (300_000_000_000, True, 6_560_000_000),
])
def test_local_income_tax_brackets(base, small, expected):
    r = calc(2026, [], taxable_base=base, small_rental_corporation=small)
    assert r["법인지방소득세_각사업연도소득"] == expected


@pytest.mark.parametrize("kind,unregistered,rate,local", [
    ("주택", False, 0.20, 0.020), ("별장", False, 0.20, 0.020), ("비사업용토지", False, 0.10, 0.010),
    ("조합원입주권", False, 0.20, 0.020), ("분양권", False, 0.20, 0.020),
    ("주택", True, 0.40, 0.040), ("비사업용토지", True, 0.40, 0.040),
    ("분양권", True, 0.20, 0.020),      # 4호에는 미등기 세율이 없다
    ("그밖", False, 0.0, 0.0),
])
def test_additional_tax_rate_by_asset(kind, unregistered, rate, local):
    r = calc(2026, [_house(종류=kind, 미등기=unregistered)])
    assert r["토지등양도소득_법인세"] == int(100_000_000 * rate)
    assert r["법인지방소득세_토지등양도"] == int(100_000_000 * local)
    assert r["자산별"][0]["세율"] == rate


def test_additional_tax_is_on_top_of_regular_tax():
    r = calc(2026, [_house()], taxable_base=100_000_000)
    assert (r["법인세_각사업연도소득"], r["토지등양도소득_법인세"], r["법인세_산출세액"]) == (10_000_000, 20_000_000, 30_000_000)
    assert r["세액합계"] == 33_000_000
    assert "법인세법 §55의2①2호" in r["적용 조문"] and "지방세법 §103의31①1호" in r["적용 조문"]


@pytest.mark.parametrize("extra,expected", [
    ({"적용제외호": "1"}, 0),                      # §55의2④1호 파산
    ({"적용제외호": "3"}, 0),                      # ④3호 환지처분 등
    ({"적용제외호": "1", "미등기": True}, 40_000_000),   # ④ 단서 — 미등기는 제외하지 않는다
    ({"제외주택호": "3"}, 0),                      # 영 §92의2②3호
    ({"국외": True}, 0),                           # 영 §92의2② 본문 — 국내 소재 주택
    ({"농어촌주택": True}, 0),                     # §55의2①2호 단서
    ({"양도일": "2012-12-31"}, 0),                 # §55의2⑧
    ({"양도일": "2013-01-01"}, 20_000_000),
])
def test_exclusions(extra, expected):
    assert calc(2026, [_house(**extra)])["토지등양도소득_법인세"] == expected


def test_loss_offsets_same_rate_first_then_other_rate():
    # 영 §92의2⑨1호 — 같은 세율 자산끼리
    r = calc(2026, [_house(라벨="차익"), _house(라벨="차손", 양도금액=370_000_000)])
    assert r["토지등양도소득_법인세"] == int(70_000_000 * 0.20)
    # ⑨2호 — 남은 차손은 다른 세율 자산의 양도소득에서
    r = calc(2026, [_house(라벨="주택", 양도금액=370_000_000), _house(라벨="나대지", 종류="비사업용토지")])
    assert r["토지등양도소득_법인세"] == int(70_000_000 * 0.10)
    # 차손이 더 크면 0원이고, 음수가 되지 않는다
    r = calc(2026, [_house(라벨="주택", 양도금액=100_000_000), _house(라벨="나대지", 종류="비사업용토지")])
    assert r["토지등양도소득_법인세"] == 0 and r["법인지방소득세_토지등양도"] == 0


def test_loss_on_untaxed_asset_does_not_offset():
    # 상가(추가과세 없음)의 차손은 법 §55의2를 적용받는 토지등이 아니라 통산하지 않는다
    r = calc(2026, [_house(), _house(라벨="상가", 종류="그밖", 양도금액=300_000_000)])
    assert r["토지등양도소득_법인세"] == 20_000_000


def test_ambiguous_offset_order_is_flagged():
    r = calc(2026, [_house(라벨="주택"), _house(라벨="나대지", 종류="비사업용토지"),
                    _house(라벨="미등기", 미등기=True, 양도금액=370_000_000)])
    assert any("차감 순서는 법문에 없어" in n for n in r["주의"])
    assert r["토지등양도소득_법인세"] == int(100_000_000 * 0.20) + int(70_000_000 * 0.10)


def test_short_business_year_is_annualised():
    # §55② — 6천만 ÷ 6 × 12 = 1억2천만 → 10% = 1,200만 → × 6/12
    r = calc(2026, [], taxable_base=60_000_000, business_year_months=6)
    assert r["법인세_각사업연도소득"] == 6_000_000
    assert r["법인지방소득세_각사업연도소득"] is None      # 환산 규정을 옮기지 않아 계산하지 않는다


def test_without_taxable_base_only_additional_tax():
    r = calc(2026, [_house()])
    assert r["법인세_각사업연도소득"] is None and r["법인세_산출세액"] is None
    assert r["세액합계"] == 22_000_000
    assert any("taxable_base 가 없어" in n for n in r["주의"])
    assert r["다루지 않는 것"] == NOT_COVERED


def test_unverified_year_is_refused():
    # 2025년 이전 개시 사업연도는 종전 세율이다(부칙 §5) — 대조하지 않은 표로 계산하지 않는다
    with pytest.raises(tax_params.ParamNotVerified):
        calc(2025, [_house()], taxable_base=100_000_000)


def test_future_year_is_marked_as_estimate():
    r = calc(2027, [_house()], taxable_base=100_000_000)
    assert "추정" in r["값 출처"]["법인세 세율표"]


@pytest.mark.parametrize("kw", [
    {"sales": [], "taxable_base": None},
    {"sales": [{"종류": "아파트", "양도금액": 1, "장부가액": 1}]},
    {"sales": [{"종류": "주택", "양도금액": 1}]},
    {"sales": [_house(적용제외호="9")]},
    {"sales": [], "taxable_base": -1},
])
def test_invalid_input_raises(kw):
    with pytest.raises(ValueError):
        calc(2026, **kw)


def test_registered_on_hosted_server_with_statute_trail():
    tools = {t.name: t for t in tax_http.make_server()._tool_manager.list_tools()}
    t = tools["calc_corporate_property_sale_tax"]
    assert t.annotations.readOnlyHint
    assert "법인세법" in t.description and "business_year" in t.description
