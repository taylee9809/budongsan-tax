"""법인 명의 — 주택분 종합부동산세와 취득세(대도시 중과). 조문표 대조.

기대값은 코드가 아니라 법제처 원문(2026-11-17 대조)의 세율·기준액에서 손으로 계산한 것이다.
  종합부동산세법 §8①2호(공제 0원) · §9②3호(1천분의 27 · 1천분의 50) · §10 단서(세 부담 상한 제외) · 시행령 §2의4①(60%)
  지방세법 §11①7호(4%·농지 3%) · §13②(표준세율×300% − 중과기준세율×200%) · §13의2①1호(4% + 2%×400%)
  지방세법 §151①1호 본문·가목·나목 · 농어촌특별세법 §5①6호·8호 · 지방세법 시행령 §27③ · §28의2 1호
"""
import pytest

import tax_server
from corporate_tax import (ACQUISITION_NOT_COVERED, JONGBU_NOT_COVERED, TOOLS, calc_corporate_acquisition_tax as acq,
                           calc_corporate_jongbu_tax as jongbu)


def test_new_tools_are_declared():
    assert {"calc_corporate_jongbu_tax", "calc_corporate_acquisition_tax"} <= set(TOOLS)


# ── 종합부동산세 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("price,homes,rate", [
    (100_000_000, 1, 0.027), (600_000_000, 2, 0.027), (600_000_000, 3, 0.050), (2_500_000_000, 7, 0.050),
])
def test_general_corporation_flat_rate_no_deduction(price, homes, rate):
    r = jongbu(2026, price, homes)
    base = int(price * 0.6)                       # 공제 0원, 공정시장가액비율 60%
    assert r["공제금액"] == 0 and r["과세표준"] == base
    assert r["산출세액"] == int(base * rate)
    assert r["종합부동산세"] == int(base * rate)           # 직전 연도 가격이 없으면 재산세액 공제 없음
    assert r["농어촌특별세"] == int(int(base * rate) * 0.2)
    assert r["세부담상한 적용여부"] is False


def test_property_tax_credit_hand_computed():
    """공시가격 6억(직전 5.8억), 1주택. 재산세 과세표준 3.6억 → 57만 + 6천만×0.4% = 81만.
    공제 = 81만 × [(3.6억×60%=2.16억)에 대한 재산세 19.5만 + 6,600만×0.25% = 36만] ÷ 81만 = 36만."""
    r = jongbu(2026, 600_000_000, 1, prev_year_official_price=580_000_000)
    assert r["산출세액"] == 9_720_000
    assert r["당해 재산세 본세"] == 810_000
    assert r["재산세액 공제"] == 360_000
    assert r["종합부동산세"] == 9_360_000
    assert r["농어촌특별세"] == 1_872_000
    assert r["총납부세액"] == 11_232_000


def test_no_burden_cap_even_when_price_doubles():
    """§10 단서 — 직전 연도 대비 급등해도 상한이 없다. 개인이면 150% 상한이 걸리는 입력이다."""
    r = jongbu(2026, 600_000_000, 1, prev_year_official_price=300_000_000)
    assert r["세부담상한 적용여부"] is False
    assert r["종합부동산세"] == r["산출세액"] - r["재산세액 공제"]
    assert "직전연도 총세액상당액" not in r
    assert "종합부동산세법 §9②" in r["적용 조문"] and "종합부동산세법 §9⑤" not in r["적용 조문"]


def test_generated_tool_cannot_express_corporation_deduction():
    """구멍의 기록(finding 95): 생성 도구 calc_jongbu_tax 는 basic_deduction=0 을 '미지정'으로 읽어 9억원을 공제한다."""
    r = tax_server.calc_jongbu_tax(600_000_000, 2026, basic_deduction=0,
                                   tax_brackets=[{"upto": None, "rate": 0.027, "deduction": 0}])
    assert r["공제금액"] == 900_000_000 and r["과세표준"] == 0
    assert jongbu(2026, 600_000_000, 1)["종합부동산세"] == 9_720_000


def test_node_composition_reads_corporation_without_prior_import():
    """finding 96: jongbu_setdae 가 읽히지 않은 상태에서도 '법인' 사실이 무시되지 않는다."""
    import subprocess
    import sys
    code = ("from tax_nodes import jongbu; r = jongbu.종부세_주택(600000000, 2026, 직전연도_합산공시가격=300000000, 법인=True, 주택수=1); "
            "print(r['공제금액'], r['종합부동산세'], r['세부담상한 적용여부'])")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    assert out == ["0", "9360000", "False"]


@pytest.mark.parametrize("kind,use_only,label", [
    ("종중", False, "1호"), ("공공주택사업자", False, "1호"), ("주택조합", False, "1호"),
    ("공익법인", True, "1호"), ("공익법인", False, "2호"),
])
def test_progressive_rate_corporations_get_individual_rules(kind, use_only, label):
    r = jongbu(2026, 1_500_000_000, 1, corporation_type=kind, public_interest_use_only=use_only)
    assert r["세율구분"].startswith(label)
    assert r["공제금액"] == 900_000_000
    assert r["과세표준"] == 360_000_000
    assert r["산출세액"] == 1_500_000 + int(60_000_000 * 0.007)      # 3억 초과 6억 이하: 150만 + 초과분 1천분의 7


def test_public_interest_corporation_with_three_homes_uses_three_home_table():
    """§9②2호는 '제1항 각 호' — 3주택 이상이면 3주택 표. 12억 초과분부터 갈린다(1천분의 20)."""
    r = jongbu(2026, 3_400_000_000, 3, corporation_type="공익법인")        # 과세표준 (34억−9억)×60% = 15억
    assert r["과세표준"] == 1_500_000_000
    assert r["산출세액"] == 9_600_000 + int(300_000_000 * 0.020)
    r1 = jongbu(2026, 3_400_000_000, 3, corporation_type="종중")           # 1호는 '제1항제1호' — 주택 수와 무관하게 2주택 이하 표
    assert r1["산출세액"] == 9_600_000 + int(300_000_000 * 0.013)


def test_jongbu_rejects_bad_input_and_states_limits():
    for bad in (dict(home_count=0), dict(corporation_type="주식회사"), dict(public_interest_use_only=True)):
        with pytest.raises(ValueError):
            jongbu(2026, 600_000_000, **dict({"home_count": 1}, **bad))
    for y in (2019, 2022, 2024):                 # 검증되지 않은 과거 연도는 거부한다
        with pytest.raises(Exception):
            jongbu(y, 600_000_000, 1)
    assert any("추정" in n for n in jongbu(2031, 600_000_000, 1)["주의"])     # 미래 연도는 추정임을 밝힌다
    r = jongbu(2026, 600_000_000, 1)
    assert r["다루지 않는 것"] is JONGBU_NOT_COVERED
    assert any("토지분" in x for x in r["다루지 않는 것"]) and any("재산세액 공제" in x for x in r["주의"])


# ── 취득세 ──────────────────────────────────────────────────────────────────
METRO = dict(property_in_metro=True, metro_office_date="2023-01-10")


def test_shop_in_metro_within_five_years():
    """상가 10억: 4%×3 − 2%×2 = 8% / 지방교육세 (4%−2%)×20%×300% = 1.2% / 농특세 (2%×3 − 2%×2)×10% = 0.2%."""
    r = acq(1_000_000_000, "2026-03-02", "주택외", **METRO)
    assert r["대도시중과"] is True and r["적용세율"] == 0.08
    assert (r["취득세"], r["지방교육세"], r["농어촌특별세"]) == (80_000_000, 12_000_000, 2_000_000)
    assert "지방세법 §13②" in r["적용 조문"]


@pytest.mark.parametrize("kw,reason", [
    (dict(property_in_metro=False), "밖"),
    (dict(property_in_metro=True, no_metro_office=True), "본점·지점"),
    (dict(property_in_metro=True, metro_office_date="2020-01-10"), "5년이 지났다"),
])
def test_shop_without_metro_surcharge(kw, reason):
    r = acq(1_000_000_000, "2026-03-02", "주택외", **kw)
    assert r["대도시중과"] is False and reason in r["대도시중과_사유"]
    assert (r["적용세율"], r["취득세"], r["지방교육세"], r["농어촌특별세"]) == (0.04, 40_000_000, 4_000_000, 2_000_000)


def test_farmland_in_metro():
    """농지 5억: 3%×3 − 4% = 5% / 지방교육세 (3%−2%)×20%×3 = 0.6% / 농특세 0.2%."""
    r = acq(500_000_000, "2026-03-02", "농지", **METRO)
    assert (r["적용세율"], r["취득세"], r["지방교육세"], r["농어촌특별세"]) == (0.05, 25_000_000, 3_000_000, 1_000_000)


def test_excluded_business_gets_standard_rate_with_followup_warning():
    r = acq(1_000_000_000, "2026-03-02", "주택외", excluded_business=True, **METRO)
    assert r["대도시중과"] is True and r["적용세율"] == 0.04
    assert any("§13③" in n for n in r["주의"])


@pytest.mark.parametrize("kw", [dict(), dict(property_in_metro=True)])
def test_unknown_metro_facts_return_both_cases_not_a_guess(kw):
    r = acq(1_000_000_000, "2026-03-02", "주택외", **kw)
    assert r["대도시중과"] is None and r["총납부세액"] is None and r["취득세"] is None
    assert r["경우별_세액"]["대도시 중과 아님"]["총납부세액"] == 46_000_000
    assert r["경우별_세액"]["대도시 중과"]["총납부세액"] == 94_000_000


@pytest.mark.parametrize("area,rural", [(59.0, 0), (85.0, 0), (85.01, 5_000_000), (None, 5_000_000)])
def test_house_twelve_percent_regardless_of_metro(area, rural):
    """주택 5억: 4% + 2%×400% = 12% / 지방교육세 (4%−2%)×20% = 0.4% / 농특세 (2% + 8%)×10% = 1.0%, 85㎡ 이하 비과세."""
    for kw in (dict(), dict(property_in_metro=False), METRO):
        r = acq(500_000_000, "2026-03-02", "주택", exclusive_area=area, **kw)
        assert r["법인주택중과"] is True
        assert (r["적용세율"], r["취득세"], r["지방교육세"], r["농어촌특별세"]) == (0.12, 60_000_000, 2_000_000, rural)


@pytest.mark.parametrize("std,capital,zone,exception", [
    (100_000_000, True, False, True), (100_000_001, True, False, False),
    (200_000_000, False, False, True), (200_000_001, False, False, False),
    (80_000_000, True, True, False),
])
def test_low_value_home_exception(std, capital, zone, exception):
    """시행령 §28의2 1호 — 수도권 1억원·그 밖 2억원 이하, 정비구역 제외. 예외면 §11①8호 6억 이하 1%."""
    r = acq(90_000_000, "2026-03-02", "주택", property_in_metro=False, exclusive_area=59.0,
            standard_value=std, in_capital_area=capital, in_redevelopment_zone=zone)
    assert r["주택중과_예외"]["해당"] is exception
    assert r["적용세율"] == (0.01 if exception else 0.12)
    if exception:
        assert (r["취득세"], r["지방교육세"]) == (900_000, 90_000)      # 1% / 1%×50%×20% = 0.1%


def test_low_value_home_in_metro_is_flagged_not_silently_resolved():
    r = acq(90_000_000, "2026-03-02", "주택", exclusive_area=59.0, standard_value=80_000_000, in_capital_area=True, **METRO)
    assert r["적용세율"] == 0.12 and any("확인하지 못했다" in n for n in r["주의"])


def test_acquisition_rejects_bad_input_and_states_limits():
    with pytest.raises(ValueError):
        acq(1_000_000_000, "2026-03-02", "상가")
    with pytest.raises(ValueError):
        acq(1_000_000_000, "2026-03-02", "주택외", exclusive_area=59.0)
    with pytest.raises(ValueError):
        acq(1_000_000_000, "2026-03-02", "주택", standard_value=90_000_000)
    with pytest.raises(ValueError):
        acq(1_000_000_000, "2026-03-02", "주택외", no_metro_office=True, metro_office_date="2024-01-01")
    r = acq(1_000_000_000, "2026-03-02", "주택외", **METRO)
    assert r["다루지 않는 것"] is ACQUISITION_NOT_COVERED
