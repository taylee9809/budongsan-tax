# -*- coding: utf-8 -*-
"""생성 서버(tax_server.py) 도구의 고친 판 — 같은 이름으로 대체한다.

tax_server.py 는 비공개 생성기(server.py → scripts/extract_tax_server.py)가 만드는 파일이라 이 저장소에서 손으로 고치지
않는다. 2026-11-18 에 원본을 고쳐 다시 생성하면서 결함 95·97·98(종부세 공제 0원, 법인 취득세)과 래퍼가 떨어뜨리던 판정기
인자 31개(findings 120)는 생성 파일 쪽에서 해소됐다. 여기 남은 대체는 공개 저장소의 판정기가 원본보다 앞서 있어서
(공개판에만 있는 인자) 생성 래퍼가 아직 넘기지 못하는 두 도구다.

  judge_transfer_reliefs 판정기가 받는 한시 배제 나목 인자(토지거래허가·6개월 지역·소재지)와 보유 목록(holdings)을 넘긴다.
  count_heavy_homes      양도 주택을 지정하면 주택 목록으로 중과 대상·가산세율까지 본다(조문 노드 중과세율_판정).

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
CHANGED_DEFAULTS: dict = {}


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


#: 대체 도구 — 이름 → 고친 판 함수. 이름은 생성 서버 도구 이름과 같아야 한다.
OVERRIDES = {f.__name__: f for f in (judge_transfer_reliefs, count_heavy_homes)}


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
