"""법인의 비사업용 토지 판정 — 조문 경계 대조(법인세법 §55의2②③⑤, 시행령 §92의2⑤·§92의3~§92의11, 시행규칙 §46·§46의2).

기대값은 코드가 아니라 법제처 원문(2026-11-17 대조)의 요건·수치에서 손으로 정한 것이다. 일수는 주석에 계산을 적었다.
"""
import json
import pathlib

import pytest

import corporate_tax
import tax_params
from corporate_tax import judge_corporate_non_business_land as judge

ROOT = pathlib.Path(__file__).resolve().parents[1]
SALE, BOUGHT = "2026-09-01", "2020-01-01"      # 소유 2020-01-02~2026-09-01 = 2,192 + 243 = 2,435일(5년 이상)


def _j(kind, facts=None, sale=SALE, bought=BOUGHT):
    return judge(kind, sale, bought, facts or {})


# ---------------------------------------------------------------- 농지 (§55의2②1호, 영 §92의5)
@pytest.mark.parametrize("facts,expected", [
    ({"농업_주업": False}, True),                                             # 가목 — 농업 주업이 아닌 법인
    ({"농업_주업": True, "시지역_도시지역": False}, False),
    ({"사업별_수입금액": {"농업": 4, "제조업": 6}}, True),                     # 영 §92의5②1호 — 사업수입금액이 큰 사업
    ({"사업별_수입금액": {"농업": 6, "제조업": 4}, "시지역_도시지역": False}, False),
    ({"농업_주업": False, "농지_예외호": 2, "시지역_도시지역": False}, False),   # ③2호 농지전용허가 농지
    ({"농업_주업": False, "농지_예외호": 5, "시지역_도시지역": False}, False),   # ③5호 비영리사업자 직접 사용
    ({"농업_주업": False, "농지_예외호": 6, "시지역_도시지역": False}, True),    # ③6호 — 시행규칙에 정한 농지가 없다
    ({"농업_주업": False, "농지_예외호": 4, "시지역_도시지역": False}, False),   # ③4호 종중(취득 2005-12-31 이전)
])
def test_farmland_item_ga(facts, expected):
    bought = "2005-12-31" if facts.get("농지_예외호") == 4 else BOUGHT
    assert _j("농지", facts, bought=bought)["비사업용토지"] is expected


def test_farmland_clan_after_2005_is_not_excepted():
    assert _j("농지", {"농업_주업": False, "농지_예외호": 4, "시지역_도시지역": False}, bought="2006-01-01")["비사업용토지"] is True


def test_farmland_urban_area_item_na_and_three_year_grace():
    base = {"농업_주업": True, "시지역_도시지역": True}
    # 편입일을 모르면 소유기간 내내 도시지역으로 본다
    r = _j("농지", base)
    assert r["비사업용토지"] is True and r["해당호"] == "§55의2②1호나목"
    # 녹지지역·개발제한구역은 도시지역에서 제외(영 §92의5④)
    assert _j("농지", dict(base, 녹지지역_또는_GB=True))["비사업용토지"] is False
    # 편입일부터 3년이 지나지 않았다(영 §92의5⑤) — 법인은 재촌·자경 요건이 없다
    r = _j("농지", dict(base, 도시지역_편입일="2024-01-10"), bought="2015-01-01")
    assert r["비사업용토지"] is False and "3년이 지나지 않았다" in r["사유"]


def test_farmland_urban_area_counts_only_days_after_grace():
    base = {"농업_주업": True, "시지역_도시지역": True}
    # 편입 2022-06-01 → 2025-06-02부터 나목. 2025-06-02~2026-09-01 = 365 + 92 = 457일 ≤ 730일 → 1호 가목 미충족
    r = _j("농지", dict(base, 도시지역_편입일="2022-06-01"), bought="2015-01-01")
    assert r["비사업용토지"] is False and r["기간기준"]["비사업용일수"] == 457
    assert r["비사업용_시작일"] == "2025-06-02"
    # 편입 2020-06-01 → 1,096 + 92 = 1,188일. 소유 4,018 + 243 = 4,261일의 40% = 1,704.4일을 넘지 않는다
    r = _j("농지", dict(base, 도시지역_편입일="2020-06-01"), bought="2015-01-01")
    assert (r["기간기준"]["비사업용일수"], r["기간기준"]["소유일수"]) == (1188, 4261)
    assert r["기간기준"]["조건"] == {"가 양도일 직전 5년 중 2년 초과": True, "나 양도일 직전 3년 중 1년 초과": True,
                                  "다 소유기간의 100분의 40 초과": False}
    assert r["비사업용토지"] is False


def test_farmland_excepted_under_ga_can_still_fall_under_na():
    facts = {"농업_주업": False, "농지_예외호": 2, "시지역_도시지역": True, "도시지역_편입일": "2010-01-01"}
    r = _j("농지", facts, bought="2018-01-01")
    assert r["비사업용토지"] is True and r["해당호"] == "§55의2②1호나목"


def test_farmland_own_raw_material_rule():
    # 영 §92의5②2호 후단 — 사용비율 30% < 50%: 면적 × 0.3 × 2 = 6,000㎡까지만 농업 주업
    r = _j("농지", {"농산물_자사원료_구분경리": True, "원료_사용비율": 0.3, "면적": 10000, "시지역_도시지역": False})
    assert r["비사업용토지"] is True and r["비사업용_면적"] == 4000.0
    r = _j("농지", {"농산물_자사원료_구분경리": True, "원료_사용비율": 0.5, "면적": 10000, "시지역_도시지역": False})
    assert r["비사업용토지"] is False


# ---------------------------------------------------------------- 임야 (§55의2②2호, 영 §92의6)
@pytest.mark.parametrize("facts,bought,expected", [
    ({}, BOUGHT, True),
    ({"임야_공익호": 1}, BOUGHT, False),
    ({"임야_공익호": 12}, BOUGHT, False),
    ({"임야_공익호": 13}, BOUGHT, True),                                       # 13호 — 시행규칙에 정한 임야가 없다
    ({"임야_공익호": 14}, BOUGHT, True),                                       # 소득세법 시행령 §168의9①은 14호까지, 법인은 13호까지
    ({"임업_주업": True, "임야_임업호": 1, "산지_안": True}, BOUGHT, False),
    ({"임업_주업": False, "임야_임업호": 1, "산지_안": True}, BOUGHT, True),      # 나목은 임업 주업 법인·독림가여야 한다
    ({"독림가": True, "임야_임업호": 2, "산지_안": True}, BOUGHT, False),
    ({"임업_주업": True, "임야_임업호": 1, "산지_안": False}, BOUGHT, True),      # 산지 안의 임야가 아니다
    ({"사업별_자산가액": {"임업": 70, "제조업": 30}, "임야_임업호": 2, "산지_안": True}, BOUGHT, False),   # 영 §92의6② 자산가액 기준
    ({"사업별_자산가액": {"임업": 30, "제조업": 70}, "임야_임업호": 2, "산지_안": True}, BOUGHT, True),
    ({"임야_사업호": 2}, BOUGHT, False),                                       # 자연휴양림
    ({"임야_사업호": 6}, "2005-12-31", False),                                 # 종중 임야 — 2005-12-31 이전 취득
    ({"임야_사업호": 6}, "2006-01-01", True),
    ({"임야_사업호": 7}, BOUGHT, True),                                        # 7호 — 시행규칙에 정한 임야가 없다
])
def test_forest(facts, bought, expected):
    assert _j("임야", facts, bought=bought)["비사업용토지"] is expected


def test_forest_in_urban_area_loses_item_na_after_three_years():
    base = {"임업_주업": True, "임야_임업호": 1, "산지_안": True, "도시지역": True}
    assert _j("임야", dict(base, 도시지역_편입일="2024-01-10"))["비사업용토지"] is False        # 3년 미경과
    # 편입 2020-06-01 → 2023-06-02부터 1,096 + 92 = 1,188일 > 2,435일의 40%(974일)
    r = _j("임야", dict(base, 도시지역_편입일="2020-06-01"))
    assert r["비사업용토지"] is True and r["기간기준"]["비사업용일수"] == 1188
    # 편입 2021-01-10 → 2024-01-11부터 366 + 365 + 234 = 965일은 974일을 넘지 않는다(1호다목)
    assert _j("임야", dict(base, 도시지역_편입일="2021-01-10"))["비사업용토지"] is False
    assert _j("임야", dict(base, 도시지역_편입일="2020-06-01", 보전녹지지역=True))["비사업용토지"] is False   # 보전녹지지역은 단서의 도시지역이 아니다


# ---------------------------------------------------------------- 목장용지 (§55의2②3호, 영 §92의7)
def test_pasture():
    r = _j("목장용지", {"축산업_주업": False})
    assert r["비사업용토지"] is True and r["해당호"] == "§55의2②3호나목"
    base = {"축산업_주업": True, "축산_기준면적": 10000, "시지역_도시지역": False}
    r = _j("목장용지", dict(base, 면적=12000))
    assert r["비사업용토지"] is True and r["비사업용_면적"] == 2000.0
    assert _j("목장용지", dict(base, 면적=10000))["비사업용토지"] is False                    # 기준면적 '초과'가 아니다
    # 영 §92의7③1호 단서 — 농업협동조합은 축산업 주업 법인으로 본다
    assert _j("목장용지", {"농업협동조합": True, "축산_기준면적": 10000, "면적": 9000, "시지역_도시지역": False})["비사업용토지"] is False
    # 도시지역 편입 3년 유예(영 §92의7⑥)
    city = dict(base, 면적=9000, 시지역_도시지역=True)
    assert _j("목장용지", dict(city, 도시지역_편입일="2024-01-10"))["비사업용토지"] is False
    assert _j("목장용지", city)["비사업용토지"] is True
    # 영 §92의7② — 종중(1호), 학교·가축개량기관 시험·연구·실습지(2호)
    assert _j("목장용지", {"축산업_주업": False, "목장용지_예외호": 2})["비사업용토지"] is False
    assert _j("목장용지", {"축산업_주업": False, "목장용지_예외호": 1}, bought="2006-01-01")["비사업용토지"] is True


# ---------------------------------------------------------------- 그 밖의 토지 (§55의2②4호, 영 §92의8, 규칙 §46)
@pytest.mark.parametrize("facts,expected", [
    ({"재산세_토지구분": "종합합산"}, True),
    ({"재산세_토지구분": "별도합산"}, False),
    ({"재산세_토지구분": "분리과세"}, False),
    ({"재산세_비과세면제": True}, False),
    ({"재산세_토지구분": "종합합산", "기타토지_사업호": 8}, False),               # 골재채취장용 토지
    ({"재산세_토지구분": "종합합산", "기타토지_사업호": 8, "기준면적내": False}, True),
    ({"재산세_토지구분": "종합합산", "기타토지_사업호": 13}, True),              # 13호 — 시행규칙에 정한 토지가 없다
])
def test_other_land(facts, expected):
    assert _j("기타", facts)["비사업용토지"] is expected


# 수입금액비율 기준 — 규칙 §46⑥ 100분의 3 · ⑬ 100분의 4 · ⑮ 100분의 20·7·10·7·10. '이상'이면 충족.
@pytest.mark.parametrize("extra,income,expected", [
    ({"기타토지_사업호": 2, "주차장운영업": True}, 30_000_000, False),
    ({"기타토지_사업호": 2, "주차장운영업": True}, 29_999_999, True),
    ({"기타토지_사업호": 10}, 40_000_000, False),
    ({"기타토지_사업호": 10}, 39_000_000, True),
    ({"기타토지_사업호": 11, "양어장_다목": True}, 39_000_000, True),
    ({"기타토지_사업호": 11}, 0, False),                                       # 가·나목(허가·면허 어업)은 수입금액 요건이 없다
    ({"기타토지_사업호": 12, "기타토지_12호_업종": "블록석물토관제조업"}, 200_000_000, False),
    ({"기타토지_사업호": 12, "기타토지_12호_업종": "블록석물토관제조업"}, 190_000_000, True),
    ({"기타토지_사업호": 12, "기타토지_12호_업종": "조경작물식재업"}, 70_000_000, False),
    ({"기타토지_사업호": 12, "기타토지_12호_업종": "화훼판매시설업"}, 60_000_000, True),
    ({"기타토지_사업호": 12, "기타토지_12호_업종": "정비운전학원"}, 100_000_000, False),
    ({"기타토지_사업호": 12, "기타토지_12호_업종": "농업학원"}, 69_000_000, True),
    ({"기타토지_사업호": 12, "기타토지_12호_업종": "도소매업용"}, 99_000_000, True),
    ({"기타토지_사업호": 12}, 500_000_000, True),                              # 업종을 모르면 율을 못 골라 예외로 보지 않는다
])
def test_other_land_income_ratio(extra, income, expected):
    facts = dict({"재산세_토지구분": "종합합산", "연간수입금액": income, "토지가액": 1_000_000_000}, **extra)
    assert _j("기타", facts)["비사업용토지"] is expected


def test_income_ratio_takes_larger_of_one_and_two_year_ratio():
    facts = {"재산세_토지구분": "종합합산", "기타토지_사업호": 12, "기타토지_12호_업종": "조경작물식재업",
             "연간수입금액": 60_000_000, "토지가액": 1_000_000_000}
    assert _j("기타", facts)["비사업용토지"] is True                             # 6% < 7%
    # 영 §92의8②2호 — (6천만 + 9천만) ÷ (10억 + 10억) = 7.5%
    assert _j("기타", dict(facts, 직전_연간수입금액=90_000_000, 직전_토지가액=1_000_000_000))["비사업용토지"] is False
    # 영 §92의8③3호 — 사업 영위 기간 182일의 수입 3천5백만 → 1년 환산 약 7.02%
    assert _j("기타", dict(facts, 연간수입금액=35_000_000, 사업영위일수=182))["비사업용토지"] is False


def test_other_land_area_limits():
    base = {"재산세_토지구분": "종합합산"}
    # 영 §92의8①7호 — 최대 사용면적의 100분의 120
    r = _j("기타", dict(base, 기타토지_사업호=7, 최대사용면적=1000, 면적=1300))
    assert r["비사업용토지"] is True and r["비사업용_면적"] == 100.0
    assert _j("기타", dict(base, 기타토지_사업호=7, 최대사용면적=1000, 면적=1200))["비사업용토지"] is False
    # 영 §92의8①4호·규칙 §46⑧ — 수용정원 × 200㎡
    r = _j("기타", dict(base, 기타토지_사업호=4, 수용정원=50, 면적=10500))
    assert r["비사업용토지"] is True and r["비사업용_면적"] == 500.0


def test_developed_land_two_years_after_completion():
    base = {"재산세_토지구분": "종합합산", "기타토지_사업호": 3}
    assert _j("기타", dict(base, 조성완료일="2025-01-10"))["비사업용토지"] is False
    # 완료 2021-06-01 → 2023-06-02부터 1,188일. 2,435일의 40% = 974일 초과
    r = _j("기타", dict(base, 조성완료일="2021-06-01"))
    assert r["비사업용토지"] is True and r["기간기준"]["비사업용일수"] == 1188


# ---------------------------------------------------------------- 주택 부속토지·별장 (§55의2②5호·6호, 영 §92의9·§92의10)
def test_house_attached_land_multiplier_has_no_capital_area_tier():
    r = _j("주택부수토지", {"주택_정착면적": 100, "면적": 600, "도시지역": True})
    assert r["비사업용토지"] is True and r["비사업용_면적"] == 100.0           # 5배 = 500㎡ (소득세법의 수도권 3배가 아니다)
    assert _j("주택부수토지", {"주택_정착면적": 100, "면적": 500, "도시지역": True})["비사업용토지"] is False
    assert _j("주택부수토지", {"주택_정착면적": 100, "면적": 1000, "도시지역": False})["비사업용토지"] is False   # 10배
    assert _j("주택부수토지", {"주택_정착면적": 100, "면적": 1001, "도시지역": False})["비사업용_면적"] == 1.0


def test_villa_land_and_rural_house_scope():
    r = _j("별장부속토지", {"별장_경계불명확": True, "건축물_바닥면적": 80})
    assert r["비사업용토지"] is True and r["해당호"] == "§55의2②6호" and r["비사업용_면적"] == 800.0
    rural = {"읍면_소재": True, "건물_연면적": 150, "면적": 660, "기준시가": 200_000_000, "조특법99의4_제외지역": False}
    r = _j("별장부속토지", rural)
    # ②6호에는 농어촌주택 제외 단서가 없다 — 범위·기준(영 §92의10)은 ①2호 단서용으로만 알려 준다
    assert r["비사업용토지"] is True and r["농어촌주택_범위기준"] is True and r["농어촌주택_①2호단서"] is True
    assert any("농어촌주택 제외 단서가 없다" in n for n in r["주의"])
    for k, v in (("건물_연면적", 150.1), ("면적", 660.1), ("기준시가", 200_000_001), ("조특법99의4_제외지역", True)):
        assert _j("별장부속토지", dict(rural, **{k: v}))["농어촌주택_범위기준"] is False


# ---------------------------------------------------------------- 기간기준 (영 §92의3)
@pytest.mark.parametrize("bought,sale,start,end,expected,days", [
    # 3호(3년 미만) — 소유 2024-01-02~2026-07-01 = 731 + 181 = 912일. 가: > 912−730 = 182, 나: > 364.8
    ("2024-01-01", "2026-07-01", "2024-01-02", "2024-12-31", True, 365),
    ("2024-01-01", "2026-07-01", "2024-01-02", "2024-12-30", False, 364),
    # 3호 단서 — 소유 2년 미만(2025-01-02~2026-07-01 = 546일)이면 나목(40% = 218.4일)만 본다
    ("2025-01-01", "2026-07-01", "2025-01-02", "2025-08-08", True, 219),
    ("2025-01-01", "2026-07-01", "2025-01-02", "2025-08-07", False, 218),
    # 2호(3년 이상 5년 미만) — 소유 2022-07-02~2026-07-01 = 1,461일. 가: > 366, 나: 직전 3년 중 > 365, 다: > 584.4
    ("2022-07-01", "2026-07-01", "2024-11-24", "2026-07-01", True, 585),
    ("2022-07-01", "2026-07-01", "2024-11-25", "2026-07-01", False, 584),
    # 2호 나목 — 전체 600일이어도 양도일 직전 3년(2023-07-02~) 안의 비사업용이 365일을 넘지 않으면 사업용
    ("2022-07-01", "2026-07-01", "2022-07-02", "2024-02-21", False, 600),
    # 1호(5년 이상) — 소유 2021-06-02~2026-07-01 = 1,826 + 30 = 1,856일. 다: > 742.4
    ("2021-06-01", "2026-07-01", "2024-06-19", "2026-07-01", True, 743),
    ("2021-06-01", "2026-07-01", "2024-06-20", "2026-07-01", False, 742),
    # 1호 가목 — 전체 2,000일이어도 직전 5년(2021-07-02~) 안이 730일을 넘지 않으면 사업용
    ("2014-01-01", "2026-07-01", "2018-01-10", "2023-07-01", False, 1999),
])
def test_period_test_boundaries(bought, sale, start, end, expected, days):
    r = judge("기타", sale, bought, {"재산세_토지구분": "별도합산", "비사업용_구간": [[start, end]]})
    assert r["기간기준"]["비사업용일수"] == days
    assert r["비사업용토지"] is expected


def test_period_test_with_day_counts_only():
    # 날짜 없이 일수만 — 소유 2,000일(5년 이상), 직전 5년 중 800일·직전 3년 중 400일·전체 801일 > 800일(40%)
    f = {"재산세_토지구분": "종합합산", "소유일수": 2000, "비사업용일수": 801, "직전5년_비사업용일수": 800, "직전3년_비사업용일수": 400}
    assert judge("기타", SALE, None, f)["비사업용토지"] is True
    assert judge("기타", SALE, None, dict(f, 비사업용일수=800))["비사업용토지"] is False
    assert judge("기타", SALE, None, dict(f, 직전3년_비사업용일수=365))["비사업용토지"] is False


# ---------------------------------------------------------------- 부득이한 사유 (§55의2③, 영 §92의11, 규칙 §46의2)
def test_unavoidable_cause_periods_count_as_business_use():
    base = {"재산세_토지구분": "종합합산"}
    # 규칙 §46의2①6호 — 취득일부터 2년. 소유 761일 중 남는 31일은 소유기간−2년(31일)을 초과하지 않는다
    assert judge("기타", SALE, "2024-08-01", base)["비사업용토지"] is True
    r = judge("기타", SALE, "2024-08-01", dict(base, 부득이사유호=6))
    assert r["비사업용토지"] is False and r["기간기준"]["비사업용일수"] == 31
    # 영 §92의11①1호 — 법령상 사용 금지 기간. 2,435일 중 2020-01-02~2024-12-31(1,826일)을 빼면 609일 ≤ 730일
    r = _j("기타", dict(base, 사용제한_구간=[["2020-01-02", "2024-12-31"]]))
    assert r["비사업용토지"] is False and r["기간기준"]["비사업용일수"] == 609
    # 규칙 §46의2① 단서 — 부동산매매업자의 매매용부동산에는 1호(건축허가 제한)를 적용하지 않는다
    limited = dict(base, 부득이사유호=1, 부득이_구간=[["2020-01-02", "2024-12-31"]])
    assert _j("기타", limited)["비사업용토지"] is False
    assert _j("기타", dict(limited, 부동산매매업_매매용=True))["비사업용토지"] is True
    # 규칙 §46의2①12호 — 유동화전문회사가 취득한 토지는 3년. 소유 2023-06-02~2026-09-01 = 1,188일, 남는 92일
    r = judge("기타", SALE, "2023-06-01", dict(base, 부득이사유호=12))
    assert r["비사업용토지"] is False and r["기간기준"]["비사업용일수"] == 92


def test_auction_and_public_sale_move_the_reference_date():
    f = {"재산세_토지구분": "종합합산", "비사업용_구간": [["2025-03-02", SALE]]}
    assert _j("기타", f)["기간기준"]["비사업용일수"] == 549
    for key in ("최초경매기일", "공매일", "매각위임일"):
        r = _j("기타", dict(f, **{key: "2025-03-01"}))
        assert r["비사업용토지"] is False and r["기간기준"]["기간판정_양도일"] == "2025-03-01"
    # 규칙 §46의2②3호 — 매각 공고는 요건을 갖췄다는 입력이 있어야 한다
    assert _j("기타", dict(f, 최초매각공고일="2025-03-01"))["기간기준"]["기간판정_양도일"] == SALE
    assert _j("기타", dict(f, 최초매각공고일="2025-03-01", 매각공고_요건충족=True))["기간기준"]["기간판정_양도일"] == "2025-03-01"


@pytest.mark.parametrize("kind,bought,facts,expected", [
    ("임야", "2023-09-01", {"양도사유": "합병"}, False),                        # 영 §92의11③1호 — 취득일부터 3년 이내
    ("임야", "2023-08-30", {"양도사유": "분할"}, True),
    ("임야", "2015-01-01", {"양도사유": "수용", "사업인정고시일": "2006-12-31"}, False),      # ③2호가목
    ("임야", "2017-06-01", {"양도사유": "수용", "사업인정고시일": "2022-06-01"}, False),      # ③2호나목 — 5년 이전
    ("임야", "2017-06-02", {"양도사유": "협의매수", "사업인정고시일": "2022-06-01"}, True),
    ("임야", "2010-01-01", {"양도사유": "수용", "사업인정고시일": "2020-06-01"}, True),       # 2021-05-04 전 고시 — 종전 규정 미수록
    ("임야", BOUGHT, {"학교법인_기부받은토지": True}, False),                    # ③4호
    ("기타", "2008-12-31", {"재산세_토지구분": "종합합산", "부득이_배제호": 14}, False),      # 규칙 §46의2③14호
    ("기타", "2009-01-01", {"재산세_토지구분": "종합합산", "부득이_배제호": 14}, True),       # 2008-12-31 이전 취득 한정
    ("기타", "2005-01-01", {"재산세_토지구분": "종합합산", "부득이_배제호": 9}, True),        # 9호 삭제
])
def test_exclusions(kind, bought, facts, expected):
    assert judge(kind, SALE, bought, facts)["비사업용토지"] is expected


def test_pre_2021_expropriation_is_flagged_not_guessed():
    r = judge("임야", SALE, "2010-01-01", {"양도사유": "수용", "사업인정고시일": "2020-06-01"})
    assert any("종전 규정" in n for n in r["주의"])


def test_clan_farmland_in_urban_area_is_excluded():
    f = {"농업_주업": False, "농지_예외호": 4, "종중소유": True, "시지역_도시지역": True, "도시지역_편입일": "2010-01-01"}
    r = judge("농지", SALE, "2000-01-01", f)
    assert r["비사업용토지"] is False and "§92의11③3호" in r["배제"]


# ---------------------------------------------------------------- 미등기 (§55의2⑤, 영 §92의2⑤)
@pytest.mark.parametrize("facts,expected", [
    ({"취득등기_없이_양도": True}, True),
    ({"취득등기_없이_양도": False}, False),
    ({"취득등기_없이_양도": True, "장기할부_등기불가": True}, False),
    ({"취득등기_없이_양도": True, "미등기_제외호": 1}, False),
    ({"취득등기_없이_양도": True, "미등기_제외호": 2}, False),
    ({"취득등기_없이_양도": True, "미등기_제외호": 3}, True),                     # 소득세법 시행령 §168①은 7개 호, 법인은 2개 호
    ({}, None),
])
def test_unregistered(facts, expected):
    assert _j("기타", dict({"재산세_토지구분": "종합합산"}, **facts))["미등기"] is expected


# ---------------------------------------------------------------- 도구 입출력
@pytest.mark.parametrize("kind,facts", [
    ("농지", {}), ("농지", {"농업_주업": True}), ("목장용지", {}), ("목장용지", {"축산업_주업": True, "시지역_도시지역": False}),
    ("기타", {}), ("주택부수토지", {"주택_정착면적": 100, "면적": 600}),
])
def test_missing_facts_give_no_verdict(kind, facts):
    r = _j(kind, facts)
    assert r["비사업용토지"] is None and r["calc_입력_종류"] is None and r["판정불가_사유"]
    assert any("판정하지 않았다" in n for n in r["주의"])


def test_result_carries_statute_trail_and_feeds_the_calculator():
    r = _j("임야")
    assert "법인세법 §55의2②2호" in r["적용 조문"] and "법인세법 시행령 §92의3" in r["적용 조문"]
    assert any(m["표기"] == "법인세법 §55의2②7호" for m in r["미적용 조문"])
    assert "MST 290843" in r["값 출처"]["기간기준"]
    assert r["다루지 않는 것"] == corporate_tax.NON_BUSINESS_LAND_NOT_COVERED and "근거표" not in r
    sale = {"라벨": "임야", "종류": r["calc_입력_종류"], "양도금액": 500_000_000, "장부가액": 400_000_000}
    assert corporate_tax.calc_corporate_property_sale_tax(2026, [sale])["토지등양도소득_법인세"] == 10_000_000
    json.dumps(r, ensure_ascii=False)


def test_land_type_from_actual_use_then_register():
    from tax_nodes.beobin_bisaeop import 법인_비사업용토지_판정
    assert 법인_비사업용토지_판정(SALE, BOUGHT, 사실상_현황="답", 공부상_지목="임야", 농업_주업=False)["토지종류"] == "농지"
    assert 법인_비사업용토지_판정(SALE, BOUGHT, 공부상_지목="임야")["토지종류"] == "임야"
    assert 법인_비사업용토지_판정(SALE, BOUGHT, 공부상_지목="잡종지", 재산세_토지구분="종합합산")["토지종류"] == "기타"


@pytest.mark.parametrize("args", [
    ("아파트", SALE, BOUGHT, {}),
    ("임야", SALE, BOUGHT, {"양도일": "2026-01-01"}),
    ("임야", "2026-03-01", "2026-03-01", {}),
    ("기타", SALE, BOUGHT, {"재산세_토지구분": "합산"}),
])
def test_invalid_input_raises(args):
    with pytest.raises(ValueError):
        judge(*args)


def test_unverified_year_is_refused_and_future_year_is_marked():
    with pytest.raises(tax_params.ParamNotVerified):
        judge("임야", "2025-09-01", "2020-01-01", {})
    assert "추정" in judge("임야", "2027-09-01", "2020-01-01", {})["값 출처"]["기간기준"]


def test_tool_is_listed_with_english_first_line():
    assert "judge_corporate_non_business_land" in corporate_tax.TOOLS
    doc = judge.__doc__
    assert doc.splitlines()[0].startswith("Korea Corporate Tax Act") and "법인세법 §55의2②" in doc


def test_registered_cases_pass():
    rows = [json.loads(line) for line in (ROOT / "data/verification/cases.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line)["case_id"].startswith("CN-")]
    assert len(rows) >= 50
    for c in rows:
        got = judge(**json.loads(c["input_json"]))[c["expected_key"]]
        assert got == json.loads(c["expected_json"]), c["case_id"]
