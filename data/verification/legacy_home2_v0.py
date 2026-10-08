# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_second_home_exclusion / judge_first_home_acquisition_relief.

결함: ①농어촌주택 기준시가 3억을 전 양도분에 적용(2022 이전 양도는 2억 — 법 19199호 부칙
§39)·대지 660㎡ 면적요건(2020 이전 양도분) 부재·고향주택 취득기간 시작일(2009-01-01) 미구분
②생애최초 감면을 현행(12억·200/300만)으로만 판정 — 구제도(2020-08-12~2022-06-20: 소득 7천만·
3/4억·100/50% 감면) 부재, 소형 300만의 가액 요건(3억/수도권 6억)·시행시점(2025)·인구감소
300만 시행시점(2026) 전부 누락.
"""
from tax_judgment import *          # noqa: F401,F403
from tax_judgment import _cite      # noqa: F401
from datetime import date           # noqa: F401


def judge_second_home_exclusion(
    kind: str,
    acquired_date: str,
    published_price: int,
    is_hanok: bool = False,
    in_capital_area: bool = False,
    same_or_adjacent_area: bool = False,
    same_sigungu: bool = False,
    holding_years: float | None = None,
    acquired_after_general_home: bool = True,
    exclusive_area_m2: float | None = None,
    acquisition_price: int | None = None,
    first_contract: bool = True,
    seller_is_supplier: bool = True,
) -> dict:
    """주택수 제외 특례 3형제 — 조특법 §99의4(농어촌·고향주택) / §71의2(인구감소지역) / §98의9(준공후미분양).

    kind: "농어촌주택" | "고향주택" | "인구감소지역주택" | "인구감소관심지역주택" | "준공후미분양주택"
    same_or_adjacent_area: (농어촌·고향주택) 일반주택과 같거나 연접한 읍·면·동(고향주택은 시)인지
    same_sigungu: (인구감소지역주택) 종전 보유 주택과 같은 시·군·구인지
    준공후미분양주택은 exclusive_area_m2(85㎡ 이하)·acquisition_price(7억 이하)·in_capital_area(수도권 배제)와
    first_contract(최초 매매계약자)·seller_is_supplier(양도자가 사업주체·분양사업자·시공자)를 함께 넘긴다.
    """
    fails, flags = [], []
    rural = kind in ("농어촌주택", "고향주택")
    unsold = kind == "준공후미분양주택"
    try:
        acq = date.fromisoformat(acquired_date)
    except (ValueError, TypeError):
        return {"주택수제외": False, "판정": "취득일 형식 오류(YYYY-MM-DD)", "근거": [], "플래그": []}

    if rural:
        limit = RURAL_HOUSE_PRICE_HANOK if is_hanok else RURAL_HOUSE_PRICE
        if not (date(2003, 8, 1) <= acq <= date(2028, 12, 31)):
            fails.append(f"취득기간 밖 — 농어촌주택 2003-08-01(고향주택 2009-01-01)~2028-12-31 (§99의4①)")
        if published_price > limit:
            fails.append(f"취득 당시 기준시가 {published_price:,}원 > {limit:,}원{'(한옥)' if is_hanok else ''}")
        if same_or_adjacent_area:
            fails.append("일반주택과 같거나 연접한 읍·면·동(고향주택은 같은·연접 시)에 소재 — 특례 배제 (§99의4③)")
        if holding_years is not None and holding_years < RURAL_HOUSE_HOLD_YEARS:
            flags.append(f"보유 {holding_years}년 — 3년 보유 전에 일반주택을 양도해도 특례는 적용되나(§99의4④), "
                         "이후 3년을 채우지 못하면 2개월 내 추징(§99의4⑥)")
        ground = _cite("농어촌주택등 취득자 양도세 과세특례", "조세특례제한법 §99의4 (N조특99의4-1)", "A")
    elif unsold:
        if not (date(2024, 1, 10) <= acq <= date(2026, 12, 31)):
            fails.append("취득기간 밖 — 2024-01-10~2026-12-31 취득분만 (§98의9①, 2026-12-31 일몰)")
        if in_capital_area:
            fails.append("수도권 소재 — 수도권 밖의 지역이어야 함 (§98의9①1호)")
        if exclusive_area_m2 is not None and exclusive_area_m2 > UNSOLD_HOUSE_AREA_LIMIT:
            fails.append(f"전용면적 {exclusive_area_m2}㎡ > 85㎡ (영 §98의8①1호)")
        elif exclusive_area_m2 is None:
            flags.append("전용면적 미입력 — 85㎡ 이하 요건 미검증")
        if acquisition_price is not None and int(acquisition_price) > UNSOLD_HOUSE_PRICE_LIMIT:
            fails.append(f"취득가액 {int(acquisition_price):,}원 > 7억원 (영 §98의8①2호)")
        elif acquisition_price is None:
            flags.append("취득가액 미입력 — 7억 이하 요건 미검증")
        if not first_contract:
            fails.append("양수자가 최초 매매(공급·분양)계약자가 아님 (영 §98의8①4호)")
        if not seller_is_supplier:
            fails.append("양도자가 사업주체·분양사업자·시공자가 아님 (영 §98의8①3호)")
        flags.append("'준공후미분양' 확인은 시장·군수·구청장의 매매계약서 날인 절차로 증명 (영 §98의8②)")
        flags.append("종부세도 1세대1주택자 간주되나 9월 16~30일 별도 신청 필요 (§98의9②③)")
        ground = _cite("수도권 밖 준공후미분양주택 과세특례",
                       "조세특례제한법 §98의9·시행령 §98의8 (N조특98의9-1·N조특령98의8-1)", "A")
    else:
        limit = DEPOP_HOUSE_PRICE_CAPITAL if (in_capital_area or kind == "인구감소관심지역주택") else DEPOP_HOUSE_PRICE_NONCAPITAL
        if not (date(2024, 1, 4) <= acq <= date(2026, 12, 31)):
            fails.append("취득기간 밖 — 2024-01-04~2026-12-31 취득분만 (§71의2①, 2026-12-31 일몰)")
        if published_price > limit:
            fails.append(f"기준시가 {published_price:,}원 > {limit:,}원 (영 §68의2①)")
        if same_sigungu:
            fails.append("종전 보유 주택과 같은 시·군·구 소재 — 특례 배제 (영 §68의2①1호가목3))")
        flags.append("종부세도 1세대1주택자로 간주되나 별도 신청 필요 — 해당 연도 9월 16일~30일 (§71의2②③)")
        ground = _cite("인구감소지역 주택 양도세·종부세 과세특례",
                       "조세특례제한법 §71의2·시행령 §68의2 (N조특71의2-1)", "A")

    if not acquired_after_general_home:
        fails.append("특례 주택을 종전 주택보다 먼저 취득 — 두 특례 모두 '취득 전부터 보유하던 주택'을 양도하는 "
                     "구조라 취득 순서가 뒤바뀌면 적용 불가")

    if fails:
        return {"주택수제외": False, "판정": " / ".join(fails), "미충족요건": fails,
                "근거": [ground], "플래그": flags}

    flags.append("주택수 제외 특례 3형제(§99의4 농어촌·§71의2 인구감소지역·§98의9 준공후미분양)의 중복 적용 "
                 "가능 여부는 법문에 명시가 없다 — 둘 이상 해당하면 쟁점 플래그(직격 해석례 미발견, D- 유지)")
    if kind in ("인구감소지역주택", "인구감소관심지역주택"):
        flags.append("취득원인·다른 특례와의 중첩은 2026년 해석례가 몰려 나온 쟁점 — 상속(서면-2025-법규재산-1621, "
                     "2026-01-14)·증여 취득(서면-2025-법규재산-2010, 2026-03-25)·분양권 중첩"
                     "(사전-2026-법규재산-0248, 2026-06-11). 본문 미수집이라 결론 미확정, 전문가 검토 유도 (N해석-71의2-1)")
    return {
        "주택수제외": True,
        "판정": f"{kind} — 일반주택 양도 시 소유주택에서 제외(소법 §89①3호 적용)",
        "근거": [ground],
        "플래그": flags,
    }


def judge_first_home_acquisition_relief(
    acquisition_price: int,
    no_home_history: bool = True,
    is_minor: bool = False,
    computed_tax: int = 0,
    exclusive_area_m2: float | None = None,
    house_type: str = "",
    in_depopulation_area: bool = False,
    acquired_date: str = "",
    co_owners: int = 1,
) -> dict:
    """지특법 §36의3 생애최초 주택 구입 취득세 감면.

    house_type: "아파트"|"공동주택"|"도시형생활주택"|"다가구"|"단독주택" 등.
    300만원 한도는 ①전용 60㎡ 이하 공동주택(아파트 제외)·도시형생활주택·구분 다가구 60㎡ 호
    ②인구감소지역 소재 주택. 그 외는 200만원.
    """
    fails, flags = [], []
    if not no_home_history:
        fails.append("본인·배우자에게 주택 소유 이력 있음 — 다만 상속 공유지분 처분, 비도시지역 20년 이상·85㎡ 이하 "
                     "단독주택 후 이주, 전용 20㎡ 이하 주택 등 예외 있음 (§36의3③)")
    if is_minor:
        fails.append("미성년자 취득 — 감면 제외 (§36의3① 단서)")
    if int(acquisition_price or 0) > FIRST_HOME_PRICE_LIMIT:
        fails.append(f"취득당시가액 {int(acquisition_price):,}원 > 12억원 (§36의3①)")
    if acquired_date:
        try:
            if date.fromisoformat(acquired_date) > date(2028, 12, 31):
                fails.append("일몰 — 2028-12-31까지 취득분 (§36의3①)")
        except ValueError:
            flags.append("취득일 형식 오류(YYYY-MM-DD) — 일몰 판정 생략")

    if fails:
        return {"감면가능": False, "감면세액": 0, "미충족요건": fails,
                "근거": [_cite("생애최초 주택 취득세 감면", "지방세특례제한법 §36의3① (N지특36의3-1)", "A")],
                "플래그": flags}

    small = (exclusive_area_m2 is not None and exclusive_area_m2 <= 60
             and house_type in ("공동주택", "도시형생활주택", "다가구"))
    cap = FIRST_HOME_RELIEF_SMALL if (small or in_depopulation_area) else FIRST_HOME_RELIEF_PLAIN
    reason = ("전용 60㎡ 이하 소형주택(아파트 제외)" if small else
              "인구감소지역 소재 주택" if in_depopulation_area else "일반 주택")
    computed = int(computed_tax or 0)
    relief = computed if computed <= cap else cap
    if co_owners > 1:
        flags.append(f"공동취득 {co_owners}인 — 감면 한도 {cap:,}원은 해당 주택 총 감면액 기준 (§36의3②)")
    flags.append("추징: 취득일부터 3개월 내 상시거주 미개시, 또는 거주 시작 후 3년 내 매각·증여·**임대** (§36의3④). "
                 "전세 끼고 사는 경로는 차단된다")
    flags.append("이 감면 적용 시 지방세법 §13의2 다주택 중과세율은 적용하지 않는다 (§36의3① 괄호)")
    flags.append("감면분에 대한 농어촌특별세 과세 여부는 미순회 — 별도 확인 필요")

    return {
        "감면가능": True,
        "감면한도": cap,
        "감면세액": relief,
        "납부세액": max(0, computed - relief),
        "판정": f"{reason} → 한도 {cap:,}원 ({'전액 면제' if computed <= cap else '한도까지 공제'})",
        "근거": [
            _cite("취득당시가액 12억 이하 유상거래·무주택·거주목적, 2028-12-31까지",
                  "지방세특례제한법 §36의3① (N지특36의3-1)", "A"),
            _cite("한도 300만원(소형·인구감소지역)/200만원(그 외)", "지특법 §36의3①1·2호 (2025-12-31 개정)", "A"),
            _cite("추징 요건", "지방세특례제한법 §36의3④ (N지특36의3-2)", "A"),
        ],
        "플래그": flags,
    }
