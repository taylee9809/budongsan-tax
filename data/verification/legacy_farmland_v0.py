# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_farmland_reduction / judge_farmland_daeto (농지 계열 run 재현용).

결함: 영 §66⑭ 1호 후단(사업소득 음수는 0)·2호(총수입금액 기준, 2020-02-11 신설) 미반영,
§66⑪⑫ 상속농지 경작기간 통산 입력 부재, 대토 §67⑥(§66⑭ 준용 + 합산 8년 전 소득초과 시
미경작 간주) 미반영.
"""
from datetime import date


def _cite(rule, basis, grade="B"):
    return {"규칙": rule, "근거": basis, "등급": grade}


FARMLAND_INCOME_EXCLUSION = 37_000_000
FARMLAND_ZONE_GRACE_YEARS = 3
DAETO_RESIDE_YEARS = 4
DAETO_TOTAL_FARMING_YEARS = 8
DAETO_AREA_RATIO = 2 / 3
DAETO_PRICE_RATIO = 1 / 2


def judge_farmland_reduction(farming_years_claimed, resides_within_scope, direct_farming,
                             yearly_incomes=None, zone_converted_date="", transfer_date="",
                             estimated_tax=0):
    flags, fails = [], []
    excluded_years = []
    effective_years = float(farming_years_claimed or 0)
    if yearly_incomes:
        for row in yearly_incomes:
            total = int(row.get("사업소득금액", 0) or 0) + int(row.get("총급여액", 0) or 0)
            if total >= FARMLAND_INCOME_EXCLUSION:
                excluded_years.append({"연도": row.get("연도"), "합계소득": total})
        effective_years = max(0.0, effective_years - len(excluded_years))
    else:
        flags.append("연도별 소득자료 미입력 — 영 §66⑭(사업소득금액+총급여 3,700만원 이상 과세기간은 경작기간에서 "
                     "제외)를 검증하지 못함. 겸업 농민은 달력상 8년을 채워도 탈락하는 실질 관문이므로 "
                     "소득금액증명·원천징수영수증으로 확인 필요")

    if not resides_within_scope:
        fails.append("재촌 요건 미충족 — 농지 소재 시·군·구, 연접 시·군·구, 직선거리 30km 이내 거주 아님 (영 §66①)")
    if not direct_farming:
        fails.append("직접 경작 아님 — 상시 종사 또는 농작업 1/2 이상 자기 노동력 필요, 위탁영농 불인정 (영 §66⑬)")
    if effective_years < 8:
        fails.append(f"경작기간 {effective_years:.1f}년 < 8년"
                     + (f" (주장 {farming_years_claimed}년 중 소득초과 {len(excluded_years)}개 과세기간 제외)"
                        if excluded_years else ""))

    if zone_converted_date and transfer_date:
        try:
            conv = date.fromisoformat(zone_converted_date)
            trans = date.fromisoformat(transfer_date)
            if (trans - conv).days > FARMLAND_ZONE_GRACE_YEARS * 365:
                fails.append(f"주거·상업·공업지역 편입({zone_converted_date}) 후 3년 경과 — 감면 배제 (영 §66④1호). "
                             "대규모개발사업 지연·공공기관 시행 등 예외 3종 해당 여부 별도 확인")
            else:
                flags.append(f"용도지역 편입 후 3년 이내({zone_converted_date}) — 감면 유지되나 편입일까지 발생한 "
                             "소득만 감면 대상(§69① 단서). 3년 경과 전 양도가 유리")
        except ValueError:
            flags.append("편입일·양도일 형식 오류(YYYY-MM-DD) — 3년 경과 판정 생략")

    if fails:
        return {"감면가능": False, "감면율": 0, "감면세액": 0, "유효경작기간": round(effective_years, 1),
                "제외과세기간": excluded_years, "미충족요건": fails,
                "근거": [_cite("자경농지 8년 100% 감면", "조세특례제한법 §69①·시행령 §66 (N조특69-1)", "A")],
                "플래그": flags}

    flags.append("감면율은 100%지만 §133① 한도(과세기간 1억·5개 과세기간 2억)로 잘린다 — "
                 "judge_transfer_reduction_limit에 넘겨 최종 감면세액을 확정할 것. '전액 비과세' 안내 금지")
    return {
        "감면가능": True, "감면율": 1.0, "감면세액": int(estimated_tax or 0),
        "유효경작기간": round(effective_years, 1), "제외과세기간": excluded_years,
        "판정": f"자경농지 요건 충족(유효 경작 {effective_years:.1f}년) — 양도세 100% 감면 대상, 한도 컷 전",
        "근거": [], "플래그": flags,
    }


def judge_farmland_daeto(prior_reside_years, transfer_date, new_acquire_date,
                         farming_start_date="", total_farming_years=None,
                         new_area_ratio=None, new_price_ratio=None,
                         is_expropriation=False, estimated_tax=0):
    fails, flags = [], []
    if float(prior_reside_years or 0) < DAETO_RESIDE_YEARS:
        fails.append(f"종전 농지 재촌·경작 {prior_reside_years}년 < 4년 (영 §67①③1호)")
    try:
        td = date.fromisoformat(transfer_date)
        nd = date.fromisoformat(new_acquire_date)
        limit_days = (24 if is_expropriation else 12) * 30.44
        gap_days = abs((nd - td).days)
        if gap_days > limit_days:
            fails.append(f"양도일↔신규 취득일 간격 {gap_days // 30}개월 > "
                         f"{'2년(수용)' if is_expropriation else '1년'} (영 §67③1·2호)")
        if farming_start_date:
            fs = date.fromisoformat(farming_start_date)
            if (fs - nd).days > 366:
                fails.append("신규 농지 취득일부터 1년 내 경작 미개시 (영 §67③1호)")
    except (ValueError, TypeError):
        flags.append("날짜 형식 오류(YYYY-MM-DD) — 기한 요건 판정 생략")

    if total_farming_years is not None and total_farming_years < DAETO_TOTAL_FARMING_YEARS:
        fails.append(f"종전+신규 합산 경작 {total_farming_years}년 < 8년 — 미달 시 감면 배제 또는 추징 (영 §67③1호 단서)")
    elif total_farming_years is None:
        flags.append("합산 경작기간 미입력 — 8년 요건은 사후 충족도 인정되나 미달 시 2개월 내 추징+이자 (§70④⑤)")

    scale_ok = ((new_area_ratio is not None and new_area_ratio >= DAETO_AREA_RATIO)
                or (new_price_ratio is not None and new_price_ratio >= DAETO_PRICE_RATIO))
    if new_area_ratio is None and new_price_ratio is None:
        flags.append("신규 농지 면적비·가액비 미입력 — 면적 2/3 이상 또는 가액 1/2 이상 요건 미검증")
    elif not scale_ok:
        fails.append(f"규모 요건 미충족 — 면적비 {new_area_ratio}·가액비 {new_price_ratio} "
                     "(면적 2/3 이상 또는 가액 1/2 이상 중 하나 필요, 영 §67③1호 가·나목)")

    if fails:
        return {"감면가능": False, "감면율": 0, "감면세액": 0, "미충족요건": fails,
                "근거": [_cite("농지대토 감면", "조세특례제한법 §70·시행령 §67 (N조특70-1·N조특령67-1)", "A")],
                "플래그": flags}

    flags.append("§133①2호가목에 따라 §70 단독으로는 5개 과세기간 1억원 한도가 별도로 걸린다 — "
                 "judge_transfer_reduction_limit에 넘겨 최종 감면세액 확정")
    flags.append("재촌 요건 기간이 자경농지(§69, 8년)와 달리 4년 — 두 감면을 혼동하지 말 것")
    return {"감면가능": True, "감면율": 1.0, "감면세액": int(estimated_tax or 0),
            "판정": "농지대토 요건 충족 — 양도세 100% 감면 대상(한도 컷 전)",
            "근거": [], "플래그": flags}
