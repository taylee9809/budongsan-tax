"""명의별 세액 가계산 — 법인 · 부동산매매업자 (2026-09-19 사용자 결정, 노션 결정 DB 같은 날 행).

쓰임
    카드·지도·정렬은 개인 명의 기준이다. 이 모듈의 결과는 고객이 개인정보에서
    '법인 있음/관심 있음' 또는 '매매사업자 있음/관심 있음'을 고른 경우에만 채팅으로 전달한다.
    calc_layer.evaluate(v, c, entity=...)와 calc_layer.entity_comparison()이 부른다.

법문 (현행 2026-07-01 시행본, 원문 덤프 data/legal_nodes)
    법인세법 §55①1호          10 / 20 / 22 / 25%  (2025-12-23 개정)               corp_art55_55_2.txt
    법인세법 §55의2①2·3호     주택·별장 +20%, 비사업용 토지 +10% (양도금액 − 장부가액)
    법인세법 시행령 §92의2②   추가과세 제외 주택 목록에 매매용 주택 없음              corpd_art92_2_97_4.txt
    법인세법 §55①2호·영 §42②  임대·이자·배당이 매출 50% 이상 + 지배주주 50% 초과 + 상시근로자 5명 미만
                              → 200억 이하 20% 단일. 매매가 주업이면 해당 없음(영 §42③ 수입금액 큰 사업) corpd_art42.txt
    지방세법 §103의20·§103의31 법인지방소득세 = 법인세의 10%, 추가과세분도 2%·1%      lt_art103_20.txt · lt_art151_103_31.txt
    지방세법 §13의2①1호        법인 주택 유상취득 12% (주택 수 무관)                   lt_art13_13_2.txt
    지방세법 §13②1호·영 §27③  대도시 설립·전입 후 5년 이내 대도시 부동산 취득 = 표준×3 − 2%×2   ltd_art27.txt
    지방세법 §151①1호 가·나목  지방교육세: §13② 중과는 본문 세액의 3배, §13의2는 (4%−2%)×20%
    소득세법 §64①             비교과세 대상 = §104①1호(분양권)·8호·10호·⑦. 단기세율(2·3호)은 대상 아님   it_art64.txt
    소득세법 §69③ 단서        매매업자 예정신고는 2년 미만이어도 기본세율
    소득세법 §47·§55          근로소득공제 · 기본세율                                 it_art47_55.txt
    소득세법 §17③·§56·§129    배당 Gross-up 10% · 배당세액공제 · 원천징수 14%          it_art17_56_129.txt

넣지 않은 것 (메모로만 남긴다)
    부가가치세 — 법인·매매업자가 85㎡ 초과 주택이나 상가를 팔면 건물분 10% (토지·건물 안분 필요)
    건강보험료 — 매매업자 사업소득에 따른 지역·소득월액 보험료
    법인 종부세 — 6월 1일 보유 시 2.7%/5%, 기본공제 0원 (종부세법 §8①2호·§9②3호)
    배당 단계 — 법인 열은 법인 유보 기준. 개인 인출 시 배당소득세는 dividend_tax_on_withdrawal()로 따로 낸다
"""
from __future__ import annotations

import math
from typing import Optional

REVISION_WATCH = {
    "법인세율": {"값": "2억 이하 10% / 200억 이하 20% / 3천억 이하 22% / 초과 25%",
              "근거": "법인세법 §55①1호 (2025-12-23 개정)", "확인": "2026-09-19"},
    "토지등양도소득_추가과세": {"값": "주택·별장 20% / 비사업용 토지 10% / 입주권·분양권 20% / 미등기 40%",
                      "근거": "법인세법 §55의2①", "확인": "2026-09-19"},
    "법인_주택취득세": {"값": "12% + 지방교육세 0.4% + 농특세(85㎡ 초과 1.0%)",
                 "근거": "지방세법 §13의2①1호·§151①1호나목", "확인": "2026-09-19"},
    "대도시_법인중과": {"값": "설립·전입 후 5년 이내 대도시 부동산 취득, 표준세율×3 − 중과기준세율×2",
                 "근거": "지방세법 §13②1호·시행령 §27③", "확인": "2026-09-19"},
    "배당_GrossUp": {"값": "10%", "근거": "소득세법 §17③ (2024-12-31 개정)", "확인": "2026-09-19"},
}

# (과세표준 상한, 세율, 누진공제)
CORP_BRACKETS = [(200_000_000, 0.10, 0), (20_000_000_000, 0.20, 20_000_000),
                 (300_000_000_000, 0.22, 420_000_000), (float("inf"), 0.25, 9_420_000_000)]
INCOME_BRACKETS = [(14_000_000, 0.06, 0), (50_000_000, 0.15, 1_260_000), (88_000_000, 0.24, 5_760_000),
                   (150_000_000, 0.35, 15_440_000), (300_000_000, 0.38, 19_940_000),
                   (500_000_000, 0.40, 25_940_000), (1_000_000_000, 0.42, 35_940_000),
                   (float("inf"), 0.45, 65_940_000)]
LOCAL = 1.1                         # 지방소득세 10%
SURCHARGE_HOUSE, SURCHARGE_NONBIZ_LAND = 0.20, 0.10
HEAVY_ADD = {2: 0.20, 3: 0.30}      # 소법 §104⑦ 조정대상지역 2주택 +20%p · 3주택 이상 +30%p
BASIC_DEDUCTION = 2_500_000         # 양도소득 기본공제 (영 §122② 주택등매매차익 계산에 준용)
PERSONAL_DEDUCTION = 1_500_000      # 본인 기본공제만 가정
DIVIDEND_GROSS_UP, DIVIDEND_WITHHOLD, FIN_INCOME_THRESHOLD = 0.10, 0.14, 20_000_000

# 명의 유지 고정비 — 법정 값이 아니라 시장가 가정. 고객이 값을 주면 그 값으로 바꾼다.
FIXED_COST_ASSUMED = {"법인": 3_000_000, "매매사업자": 1_500_000}   # 연간 기장·조정료 수준


def _progressive(base: float, brackets) -> float:
    if base <= 0:
        return 0.0
    for cap, rate, ded in brackets:
        if base <= cap:
            return max(base * rate - ded, 0.0)
    return 0.0


def corp_income_tax(base: float) -> float:
    return _progressive(base, CORP_BRACKETS)


def income_tax(base: float) -> float:
    return _progressive(base, INCOME_BRACKETS)


def earned_income_deduction(salary: float) -> float:
    """소득세법 §47① 근로소득공제 (한도 2천만원)."""
    if salary <= 5_000_000:
        d = salary * 0.70
    elif salary <= 15_000_000:
        d = 3_500_000 + (salary - 5_000_000) * 0.40
    elif salary <= 45_000_000:
        d = 7_500_000 + (salary - 15_000_000) * 0.15
    elif salary <= 100_000_000:
        d = 12_000_000 + (salary - 45_000_000) * 0.05
    else:
        d = 14_750_000 + (salary - 100_000_000) * 0.02
    return min(d, 20_000_000, salary)


def salary_tax_base(salary: float) -> float:
    """총급여 → 종합소득 과세표준 근사. 근로소득공제와 본인 기본공제만 뺀다(그 밖의 공제는 모름)."""
    return max(salary - earned_income_deduction(salary) - PERSONAL_DEDUCTION, 0.0)


# ── 취득세 ──────────────────────────────────────────────────────────────────
def corp_acq_tax(price: int, kind: str, area_m2: float, metro_heavy: bool) -> tuple[int, str]:
    """법인 취득세. kind는 calc_layer.asset_class 값. metro_heavy = 대도시 설립·전입 5년 이내 법인 × 대도시 물건."""
    if kind == "house":
        rate = 0.134 if area_m2 > 85 else 0.124
        return int(price * rate), (f"법인 주택 12% + 지방교육세 0.4%"
                                   f"{' + 농특세 1.0%' if area_m2 > 85 else ' (85㎡ 이하 농특세 비과세)'}")
    if metro_heavy:
        return int(price * 0.094), "대도시 법인 중과 8%(4%×3 − 2%×2) + 지방교육세 1.2% + 농특세 0.2%"
    return int(price * 0.046), "주택 외 유상취득 4% + 농특세 0.2% + 지방교육세 0.4%"


# ── 매각 단계 세액 ──────────────────────────────────────────────────────────
def corp_exit_tax(gain: int, kind: str, *, other_corp_base: int = 0,
                  nonbiz_land: bool = False) -> tuple[int, str]:
    """법인 매각 세액 = 각 사업연도 소득 법인세 증분 + 토지등 양도소득 추가과세, 지방소득세 포함.

    gain은 양도금액 − (취득가·취득세·인수액 등)로 넘어온 값을 그대로 쓴다. 추가과세 기준은 법문상
    양도금액 − 장부가액이라 명도비처럼 장부가액에 안 들어가는 비용만큼 작게 잡힌다(근사).
    """
    if gain <= 0:
        return 0, "양도차익 없음"
    base_tax = corp_income_tax(other_corp_base + gain) - corp_income_tax(other_corp_base)
    sur_rate = SURCHARGE_HOUSE if kind == "house" else SURCHARGE_NONBIZ_LAND if nonbiz_land else 0.0
    tax = (base_tax + gain * sur_rate) * LOCAL
    note = f"법인세 {base_tax / gain:.0%}"
    if sur_rate:
        note += f" + {'주택' if kind == 'house' else '비사업용 토지'} 추가과세 {sur_rate:.0%}"
    return int(tax), note + " + 지방소득세"


def dealer_exit_tax(gain: int, salary: int, *, heavy_homes: int = 0) -> tuple[int, str]:
    """부동산매매업자 매각 세액 = 종합소득세 증분(근로소득과 합산), 지방소득세 포함.

    heavy_homes: 양도 시점 조정대상지역 중과 주택 수(2 또는 3+). 0이면 비교과세 없음.
    §64① 비교과세 — 중과 자산이면 (차익 × (기본세율 + 가산)) 과 비교해 큰 쪽.
    """
    if gain <= 0:
        return 0, "매매차익 없음"
    other = salary_tax_base(salary)
    plan_a = income_tax(other + gain) - income_tax(other)
    note = "종합소득세 증분(근로소득 합산)"
    tax = plan_a
    if heavy_homes >= 2:
        add = HEAVY_ADD[3 if heavy_homes >= 3 else 2]
        taxable = max(gain - BASIC_DEDUCTION, 0)
        plan_b = income_tax(taxable) + taxable * add
        if plan_b > plan_a:
            tax, note = plan_b, f"§64 비교과세 — 중과세율(기본 + {add:.0%}p) 적용안"
    return int(tax * LOCAL), note + " + 지방소득세"


def dividend_tax_on_withdrawal(dividend: int, salary: int) -> tuple[int, str]:
    """법인에 남긴 세후 이익을 한 해에 전액 배당으로 꺼낼 때 개인이 더 내는 세액(지방소득세 포함)."""
    if dividend <= 0:
        return 0, "배당 없음"
    if dividend <= FIN_INCOME_THRESHOLD:
        return int(dividend * DIVIDEND_WITHHOLD * LOCAL), "2천만원 이하 — 원천징수 14% 분리과세"
    other = salary_tax_base(salary)
    over = dividend - FIN_INCOME_THRESHOLD
    gross = over * DIVIDEND_GROSS_UP
    total = (income_tax(other + over + gross) - income_tax(other) - gross
             + FIN_INCOME_THRESHOLD * DIVIDEND_WITHHOLD)
    floor = dividend * DIVIDEND_WITHHOLD            # 종합과세해도 원천징수세액보다 작아지지 않는다(§62 비교)
    return int(max(total, floor) * LOCAL), "2천만원 초과분 종합과세(Gross-up 10%·배당세액공제) — 다른 금융소득 없음 가정"


def breakeven_deals(fixed_annual: int, gain_per_deal: int) -> Optional[int]:
    """연간 고정비를 건당 세후 수익 차이(해당 명의 − 개인)로 나눈 손익분기 거래 횟수. 차이가 0 이하면 None."""
    if gain_per_deal <= 0:
        return None
    return max(math.ceil(fixed_annual / gain_per_deal), 1)
