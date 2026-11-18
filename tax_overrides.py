# -*- coding: utf-8 -*-
"""생성 서버(tax_server.py) 도구의 고친 판 — 같은 이름으로 대체한다.

tax_server.py 는 비공개 생성기(server.py → scripts/extract_tax_server.py)가 만드는 파일이라 이 저장소에서 손으로 고치지
않는다. 2026-11-18 에 원본을 고쳐 다시 생성하면서 결함 95·97·98(종부세 공제 0원, 법인 취득세)과 래퍼가 떨어뜨리던 판정기
인자 31개(findings 120)는 생성 파일 쪽에서 해소됐다. 여기 남은 대체는 공개 저장소의 판정기·조문 노드가 원본보다 앞서 있어서
(공개판에만 있는 인자) 생성 래퍼가 아직 넘기지 못하는 도구다. 계산은 여기서 새로 짜지 않는다 — 판정기·노드를 그대로 부른다.

  judge_transfer_reliefs            한시 배제 나목 인자(토지거래허가·6개월 지역·소재지)와 보유 목록(holdings)을 넘긴다.
  count_heavy_homes                 양도 주택을 지정하면 주택 목록으로 중과 대상·가산세율까지 본다(조문 노드 중과세율_판정).
  judge_temporary_two_homes         조정대상지역 공고일(영 §155①1호 대괄호, 2026-09-30 개정).
  judge_acquisition_homes_and_rate  종전 주택등의 조정대상지역 여부·신규 주택 계약일·계약금 지급일(영 §28의5①, 2026-09-30 개정).
  judge_155_special                 양도일 현재 세대 주택 수(homes_at_sale).
  judge_156_3_from_portfolio        분양권 완공 여부·그 밖의 주택 수 직접 지정(판정기가 **kw 로 받는 인자).
  calc_attached_land_limit          멸실된 상속주택의 정착면적·양도일(조문 노드 소득세법시행령-155-2-멸실신축-b).
  calc_property_tax                 지방세특례제한법 경감과의 비교(조문 노드 지방세법-111의2-4) — 감면유형을 주면 노드 합성(재산세_주택)의 결과.

대체로 메운 인자는 docs/WRAPPER_GAPS.md(scripts/wrapper_gaps.py 가 만든다)에 "원본 래퍼에 되돌릴 목록"으로 적혀 있다.
원본(server.py)을 고쳐 다시 생성하면 그 도구의 대체를 여기서 걷어낸다.

대체 목록은 OVERRIDES 한 곳이다. 호스팅 서버(tax_http.make_server), stdio 진입점(tax_full), 케이스 실행기
(scripts/verify_tool_cases.py)가 이 표를 읽는다. 대체 도구의 인자가 원래 도구 인자의 상위집합인지는
tests/test_tax_overrides.py 가 지킨다 — 생성기가 인자를 바꾸면 깨진다.
"""
from __future__ import annotations

import types

import tax_judgment as _tj
import tax_params
import tax_server as _ts

#: 원래 도구와 기본값이 달라진 인자. 그 밖의 기존 인자는 이름·순서·기본값이 원래 도구와 같아야 한다(테스트가 대조).
CHANGED_DEFAULTS: dict = {
    # 조정대상지역 여부 — 미입력(None)과 '아님'(False)을 가른다(findings 290). 생성 도구는 False 가 기본이라 3년으로 확정한다.
    "judge_temporary_two_homes": {"prev_in_adjusted_area": None, "new_in_adjusted_area": None},
}


def _거부(사유: str, 근거: str, **더) -> dict:
    """계산하지 않았다는 결과. 금액 키를 넣지 않는다 — 금액처럼 읽힐 값이 없어야 한다."""
    return dict({"계산불가": True, "사유": 사유, "근거": 근거}, **더)


# ──────────────────────────────────────────────── 종합부동산세·취득세 (원본에서 고침)
# calc_jongbu_tax(공제 0원·법인 거부, findings 95)와 calc_acquisition_tax(§13의2는 주택 유상취득만·가산세율 경고,
# findings 97·98)는 2026-11-18 생성기 원본(server.py)에서 고쳐 tax_server.py 를 다시 만들었다. 여기서 대체하지 않는다.
# 이름은 남겨 둔다 — 이 모듈을 통해 부르던 코드와 테스트가 같은 함수를 받는다.
calc_jongbu_tax = _ts.calc_jongbu_tax
calc_acquisition_tax = _ts.calc_acquisition_tax


# ───────────────────────────────────────────────────────────── 양도소득세
def judge_transfer_reliefs(
    is_one_household_one_home: bool,
    holding_years: float,
    residing_years: float,
    sale_price: int,
    adjusted_at_sale: bool = False,
    heavy_home_count: int = 1,
    sale_date: str = "",
    meets_exemption_requirements: bool = True,
    contract_date: str = "",
    deposit_received: bool = False,
    contract_months_limit: int = 4,
    land_permit_target: bool | None = None,
    land_permit_applied_date: str = "",
    land_permit_granted: bool = False,
    six_month_region: bool | None = None,
    location: str = "",
    holdings: list[dict] | None = None,
    sale_home: dict | None = None,
    heavy_facts: dict | None = None,
) -> dict:
    """양도세 비과세·중과·장특공·고가주택 안분. 설명은 hosted_descriptions.DESCRIPTIONS["judge_transfer_reliefs"]."""
    return _tj.judge_transfer_reliefs(
        is_one_household_one_home, holding_years, residing_years, sale_price,
        adjusted_at_sale, heavy_home_count, sale_date, meets_exemption_requirements,
        contract_date, deposit_received, contract_months_limit,
        land_permit_target=land_permit_target, land_permit_applied_date=land_permit_applied_date,
        land_permit_granted=land_permit_granted, six_month_region=six_month_region, location=location,
        holdings=holdings, sale_home=sale_home, heavy_facts=heavy_facts)


def count_heavy_homes(
    items: list[dict],
    heavy_tier: int = 3,
    sale_label: str = "",
    sale_date: str = "",
    adjusted_at_sale: bool | None = None,
    holding_years: float | None = None,
    contract_date: str = "",
    deposit_received: bool = False,
    land_permit_target: bool | None = None,
    land_permit_applied_date: str = "",
    land_permit_granted: bool = False,
    six_month_region: bool | None = None,
    location: str = "",
    household_facts: dict | None = None,
) -> dict:
    """양도세 중과 판정용 주택 수. 설명은 hosted_descriptions.DESCRIPTIONS["count_heavy_homes"]."""
    r = _tj.count_heavy_homes(items, heavy_tier)
    if not sale_label:
        return r        # 양도 주택을 지정하지 않으면 원래 도구와 결과가 같다
    대상 = [it for it in items if (it.get("라벨") or it.get("종류", "주택")) == sale_label]
    if len(대상) != 1:
        r["양도주택_중과판정"] = {
            "판정불가": True,
            "사유": "sale_label=%r 인 항목이 items 에 %d개다 — 양도하는 주택 하나에만 그 \"라벨\"을 붙인다" % (sale_label, len(대상))}
        return r
    from tax_nodes.yangdo_jungkwa_ho import 중과세율_판정
    h = dict(대상[0])
    # 한시 배제(영 §167의3①12호의2 등)는 양도 주택 항목의 사실로 읽는다 — 인자로 준 것만 덮어쓴다.
    for 키, 값, 준것 in (("보유연수", holding_years, holding_years is not None),
                      ("매매계약일", contract_date, bool(contract_date)),
                      ("계약금_수령", deposit_received, bool(deposit_received)),
                      ("토지거래허가_대상", land_permit_target, land_permit_target is not None),
                      ("토허_신청일", land_permit_applied_date, bool(land_permit_applied_date)),
                      ("토허_허가", land_permit_granted, bool(land_permit_granted)),
                      ("6개월_지역", six_month_region, six_month_region is not None),
                      ("소재지", location, bool(location))):
        if 준것:
            h[키] = 값
    사실 = {k: v for k, v in (household_facts or {}).items() if k not in ("양도주택", "보유목록", "양도일", "양도당시_조정대상지역")}
    p = 중과세율_판정(h, items, sale_date, adjusted_at_sale, **사실)
    r["양도주택_중과판정"] = p
    if p.get("가산_주택수") and p["가산_주택수"] != heavy_tier:
        r.setdefault("플래그", []).append(
            "양도주택_중과판정은 주택 목록에서 계열을 스스로 정한다(가산_주택수 %s) — heavy_tier=%s 로 센 '중과판정_주택수'와 계열이 다르다"
            % (p["가산_주택수"], heavy_tier))
    return r


def judge_temporary_two_homes(
    prev_acquired: str,
    new_acquired: str,
    prev_sale_date: str | None = None,
    prev_meets_exemption: bool = True,
    one_year_rule_waived: bool = False,
    prev_in_adjusted_area: bool | None = None,
    new_in_adjusted_area: bool | None = None,
    moved_in_within_1y: bool | None = None,
    moved_in_date: str | None = None,
    new_home_tenant_lease_end: str | None = None,
    new_contract_date: str | None = None,
    other_homes_at_acquisition: int = 0,
    prev_adjusted_after_new_contract: bool = False,
    merged_homes_at_acquisition: int = 0,
    merge_kind: str | None = None,
    merge_date: str | None = None,
    other_homes_at_sale: int = 0,
    new_right_acquired: str | None = None,
    adjusted_area_notice_date: str | None = None,
) -> dict:
    """영 §155① 일시적 2주택. 설명은 hosted_descriptions.DESCRIPTIONS["judge_temporary_two_homes"]."""
    return _tj.judge_temporary_two_homes(
        prev_acquired, new_acquired, prev_sale_date, prev_meets_exemption, one_year_rule_waived,
        prev_in_adjusted_area, new_in_adjusted_area, moved_in_within_1y, moved_in_date,
        new_home_tenant_lease_end, new_contract_date,
        other_homes_at_acquisition=other_homes_at_acquisition,
        prev_adjusted_after_new_contract=prev_adjusted_after_new_contract,
        merged_homes_at_acquisition=merged_homes_at_acquisition, merge_kind=merge_kind, merge_date=merge_date,
        other_homes_at_sale=other_homes_at_sale, new_right_acquired=new_right_acquired,
        adjusted_area_notice_date=adjusted_area_notice_date)


def judge_155_special(
    kind: str,
    event_date: str = "",
    sale_date: str = "",
    homes_mine: int = 1,
    homes_spouse_or_parent: int = 1,
    parent_max_age_at_merge: int | None = None,
    separate_household_at_inheritance: bool = True,
    general_home_acquired_before_inheritance: bool = True,
    is_first_priority_inherited: bool = True,
    gifted_within_2y_before_inheritance: bool = False,
    rental_registered: bool = False,
    residence_years_in_home: float = 0.0,
    first_time_use: bool = True,
    excluded_homes_mine: int = 0,
    excluded_homes_spouse_or_parent: int = 0,
    parent_is_female: bool = False,
    merged_for_parent_care: bool = False,
    held_before_merge: bool = True,
    designated_by_agreement: bool = False,
    homes_at_sale: int | None = None,
) -> dict:
    """영 §155 특례(혼인·동거봉양·상속주택·거주주택). 설명은 hosted_descriptions.DESCRIPTIONS["judge_155_special"]."""
    return _tj.judge_155_special(
        kind, event_date, sale_date, homes_mine, homes_spouse_or_parent, parent_max_age_at_merge,
        separate_household_at_inheritance, general_home_acquired_before_inheritance, is_first_priority_inherited,
        gifted_within_2y_before_inheritance, rental_registered, residence_years_in_home, first_time_use,
        excluded_homes_mine, excluded_homes_spouse_or_parent, parent_is_female, merged_for_parent_care,
        held_before_merge, designated_by_agreement, homes_at_sale=homes_at_sale)


def judge_156_3_from_portfolio(
    items: list[dict],
    sale_date: str,
    new_home_completed: str = "",
    moved_in_date: str = "",
    continuous_residence_years: float = 0.0,
    holding_waiver_reason: str = "",
    sale_delay_reason: str = "",
    delay_state_at_3y: bool = False,
    sold_by_that_method: bool = False,
    partial_move_reason: str = "",
    bunyang_already_completed: bool = False,
    other_homes: int | None = None,
    excluded_homes: int | None = None,
) -> dict:
    """보유 목록으로 영 §156의3 판정. 설명은 hosted_descriptions.DESCRIPTIONS["judge_156_3_from_portfolio"]."""
    kw = dict(new_home_completed=new_home_completed, moved_in_date=moved_in_date,
              continuous_residence_years=continuous_residence_years, holding_waiver_reason=holding_waiver_reason,
              sale_delay_reason=sale_delay_reason, delay_state_at_3y=delay_state_at_3y,
              sold_by_that_method=sold_by_that_method, partial_move_reason=partial_move_reason)
    if bunyang_already_completed:
        kw["bunyang_already_completed"] = True
    # 주택 수는 판정기가 목록에서 센다 — 직접 준 값(None 이 아닌 것)만 그 산정을 덮어쓴다.
    if other_homes is not None:
        kw["other_homes"] = other_homes
    if excluded_homes is not None:
        kw["excluded_homes"] = excluded_homes
    return _tj.judge_156_3_from_portfolio(items, sale_date, **kw)


def calc_attached_land_limit(
    building_footprint_m2: float,
    land_area_m2: float,
    is_urban_area: bool = True,
    is_capital_region: bool = True,
    urban_zone: str = "주거상업공업",
    demolished_inherited_footprint_m2: float | None = None,
    sale_date: str = "",
) -> dict:
    """주택 부수토지 비과세 한도. 설명은 hosted_descriptions.DESCRIPTIONS["calc_attached_land_limit"]."""
    return _tj.calc_attached_land_limit(
        building_footprint_m2, land_area_m2, is_urban_area, is_capital_region, urban_zone,
        demolished_inherited_footprint_m2=demolished_inherited_footprint_m2, sale_date=sale_date)


# ───────────────────────────────────────────────────────────────── 취득세
def judge_acquisition_homes_and_rate(
    homes: list[dict],
    in_adjusted_area: bool,
    is_corporation: bool = False,
    exclusive_area_m2: float | None = None,
    acquire_date: str | None = None,
    prev_disposal_date: str | None = None,
    prev_disposal_kind: str = "매각",
    disposal_to_same_household: bool = False,
    new_home_for_rental: bool = False,
    is_gift: bool = False,
    gift_std_value: int = 0,
    gift_from_one_home_household_to_family: bool = False,
    prev_home_in_adjusted_area: bool | None = None,
    new_contract_date: str | None = None,
    new_deposit_paid_date: str | None = None,
) -> dict:
    """취득세 주택 수·일시적 2주택·세율. 설명은 hosted_descriptions.DESCRIPTIONS["judge_acquisition_homes_and_rate"]."""
    return _tj.judge_acquisition_homes_and_rate(
        homes, in_adjusted_area, is_corporation, exclusive_area_m2, acquire_date, prev_disposal_date,
        prev_disposal_kind, disposal_to_same_household, new_home_for_rental, is_gift, gift_std_value,
        gift_from_one_home_household_to_family,
        prev_home_in_adjusted_area=prev_home_in_adjusted_area, new_contract_date=new_contract_date,
        new_deposit_paid_date=new_deposit_paid_date)


# ───────────────────────────────────────────────────────────────── 재산세
def calc_property_tax(
    official_price: int,
    year: int,
    prev_year_official_price: int = 0,
    one_home: bool = False,
    fair_market_ratio: float = 0.0,
    tax_brackets: list[dict] | None = None,
    urban_area_rate: float = -1.0,
    local_education_tax_rate: float = -1.0,
    taxable_base_cap: int = 0,
    jiteuk_relief_type: str = "",
    jiteuk_relief_facts: dict | None = None,
) -> dict:
    """주택분 재산세. 설명은 hosted_descriptions.DESCRIPTIONS["calc_property_tax"]."""
    if not jiteuk_relief_type:
        if jiteuk_relief_facts:
            return _거부("jiteuk_relief_facts 만 주고 jiteuk_relief_type(감면유형)을 주지 않았다 — 어느 경감 규정과 견줄지 알 수 없다",
                       "지방세법 §111의2④")
        return _ts.calc_property_tax(official_price, year, prev_year_official_price, one_home, fair_market_ratio,
                                     tax_brackets, urban_area_rate, local_education_tax_rate, taxable_base_cap)
    직접 = [이름 for 이름, 준것 in (("fair_market_ratio", bool(fair_market_ratio)), ("tax_brackets", tax_brackets is not None),
                               ("urban_area_rate", urban_area_rate >= 0), ("local_education_tax_rate", local_education_tax_rate >= 0),
                               ("taxable_base_cap", taxable_base_cap > 0)) if 준것]
    if 직접:
        return _거부("지방세특례제한법 경감 비교(jiteuk_relief_type)는 상수표의 세율·비율로만 한다 — 직접 지정한 %s 와 함께 쓸 수 없다"
                   % "·".join(직접), "지방세법 §111의2④ (표준세율 세액과 특례세율 세액을 같은 과세표준에서 견준다)")
    if official_price <= 0:
        raise ValueError("official_price는 0보다 커야 합니다")
    from tax_nodes.jaesan import 재산세_주택
    return 재산세_주택(official_price, year, prev_year_official_price, one_home,
                    지방세특례_감면유형=jiteuk_relief_type, 지방세특례_사실=dict(jiteuk_relief_facts or {}))


# ───────────────────────────────────────────────────────────── 재건축부담금
def estimate_reconstruction_levy(
    end_price_total: int,
    start_price_total: int,
    member_count: int,
    normal_rise_rate: float,
    development_cost: int = 0,
    start_date: str = "",
    end_date: str = "",
    management_plan_applied_date: str = "",
    one_home_holding_years: float | None = None,
    is_one_home_at_end: bool = False,
    age_at_end: int | None = None,
    development_cost_items: dict | None = None,
) -> dict:
    """재건축부담금 추정. 설명은 hosted_descriptions.DESCRIPTIONS["estimate_reconstruction_levy"]."""
    return _tj.estimate_reconstruction_levy(
        end_price_total, start_price_total, member_count, normal_rise_rate, development_cost,
        start_date, end_date, management_plan_applied_date, one_home_holding_years,
        is_one_home_at_end, age_at_end, development_cost_items=development_cost_items)


#: 대체 도구 — 이름 → 고친 판 함수. 이름은 생성 서버 도구 이름과 같아야 한다.
OVERRIDES = {f.__name__: f for f in (
    judge_transfer_reliefs, count_heavy_homes, judge_temporary_two_homes, judge_155_special, judge_156_3_from_portfolio,
    calc_attached_land_limit, judge_acquisition_homes_and_rate, calc_property_tax,
    estimate_reconstruction_levy)}


def replace_tools(source_tools: list, descriptions: dict | None = None) -> list:
    """생성 서버 도구 목록에서 OVERRIDES 에 있는 이름을 고친 판으로 바꾼 목록(순서 유지).

    제목·annotations 는 원래 도구 것을 물려받고, 설명은 descriptions[name](없으면 원래 도구의 설명)을 쓴다.
    목록에 없는 이름은 더하지 않는다 — 도구 수는 그대로다.
    """
    from mcp.server.fastmcp.tools import Tool
    out = []
    for t in source_tools:
        fn = OVERRIDES.get(t.name)
        out.append(t if fn is None else Tool.from_function(
            fn, name=t.name, title=t.title, annotations=t.annotations,
            description=(descriptions or {}).get(t.name) or t.description))
    return out
