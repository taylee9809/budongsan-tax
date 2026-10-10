# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_156_3_special (영 §156의3, 24차 순회 최초 구현).

결함: 양도 당시 '정확히 1주택 + 1분양권'을 암묵 전제하고 그 사실을 입력으로 받지도,
경고하지도 않았다. 실제로는 다른 주택이 있어도 주택수 제외 특례를 거치면 §156의3②이
적용되고(농어촌주택 서면-2022-부동산-4530 / 인구감소지역주택 사전-2026-법규재산-0248 /
동거봉양 합가 서면-2021-부동산-5364), 반대로 분양권이 이미 완공돼 2주택이 된 상태면
적용되지 않는다(서면-2022-부동산-3247). 같은 계열의 judge_155_special은 excluded_homes_*
입력을 갖고 있어 계열 내 비일관이기도 했다.
"""
from tax_judgment import *          # noqa: F401,F403
from tax_judgment import _cite, _b3_years_between, _b3_add_years  # noqa: F401
from tax_judgment import (_B3_APPLIES_FROM, _B3_MOVE_3Y_FROM, _B3_1Y_RULE_FROM,
                          _B3_1Y_WAIVERS, _B3_DELAY_REASONS,
                          _B3_PARTIAL_MOVE_REASONS)  # noqa: F401
from datetime import date           # noqa: F401


def judge_156_3_special(
    prior_home_acquired: str,
    bunyang_acquired: str,
    sale_date: str,
    new_home_completed: str = "",
    moved_in_date: str = "",
    continuous_residence_years: float = 0.0,
    holding_waiver_reason: str = "",
    sale_delay_reason: str = "",
    delay_state_at_3y: bool = False,
    sold_by_that_method: bool = False,
    partial_move_reason: str = "",
) -> dict:
    """주택과 분양권을 소유한 경우 1세대1주택 특례 판정 (영 §156의3②③, 규칙 §75·§75의2).

    **판정범위는 ②③항(일시적 1주택+1분양권)뿐이다.** ④⑤항(상속분양권)·⑥항(동거봉양·
    혼인 조합 — §156의2⑧⑨ 준용)·⑦⑧항(문화재·이농주택 조합)은 미구현이며, 반환의
    '판정범위' 필드와 플래그로 항상 알린다. 상속·합가·혼인이 얽힌 분양권 상담에
    이 툴의 결론을 그대로 쓰면 안 된다(N영156의3-10).

    ②항(3년 내 양도)을 먼저 보고, 안 되면 ③항(신축주택 실입주)으로 넘어간다.

    holding_waiver_reason: judge_exemption_requirements의 waiver_reason과 같은 어휘를 쓴다
      (""|건설임대5년거주|수용|해외이주2년|취학근무국외|부득이1년거주). 이 중 ②항 후단이
      1년 요건을 면제하는 것은 **건설임대5년거주·수용·부득이1년거주 셋뿐**이다 —
      해외이주2년·취학근무국외는 §154①제2호 나목·다목이라 인용 대상이 아니다(N영156의3-2).
    sale_delay_reason: 캠코매각의뢰|법원경매신청|공매진행 (규칙 §75① 열거 3가지).
      delay_state_at_3y는 '분양권 취득일부터 3년이 되는 날 현재' 그 상태였는지,
      sold_by_that_method는 실제로 그 방법으로 양도됐는지 — 둘 다 참이어야 한다.
    partial_move_reason: 세대 구성원 중 일부가 못 옮긴 사유 (취학|근무|질병|학교폭력).
      세대전원이 안 옮긴 경우를 봐주는 규정이 아니다(N규칙75의2-1).

    ③항은 조건부다 — 1년 계속거주를 못 채우면 사유 발생일 말일부터 2개월 내
    신고·납부해야 한다(⑩항). 반환의 '사후관리'에 그 사실을 담는다.
    """
    scope_note = ("이 판정은 ②③항(일시적 1주택+1분양권)에 한정된다 — 상속분양권(④⑤)·"
                  "동거봉양/혼인 조합(⑥, §156의2⑧⑨ 준용)·문화재/이농주택 조합(⑦⑧)은 "
                  "미구현이므로 해당 사실관계가 있으면 원문으로 판정할 것")
    flags, citations = [scope_note], []
    try:
        ph = date.fromisoformat(prior_home_acquired)
        bg = date.fromisoformat(bunyang_acquired)
        sd = date.fromisoformat(sale_date)
    except ValueError:
        return {"오류": "prior_home_acquired·bunyang_acquired·sale_date는 YYYY-MM-DD"}

    # 0. 적용 개시 게이트 — '탈락'이 아니라 '특례 불필요'다
    if bg < _B3_APPLIES_FROM:
        return {
            "판정범위": "②③항 한정(④~⑧ 미구현)",
            "특례적용": True,
            "판정근거항": "해당없음",
            "사유": "2021-01-01 전에 취득한 분양권은 주택수에 산입되지 않는다 — "
                  "§156의3 특례를 볼 필요 없이 종전주택이 1주택이다",
            "근거": [_cite("2021년 1월 1일 이후 취득한 분양권부터 적용",
                          "소득세법 시행령 부칙(2021.2.17) §10① (N영156의3-0)", "A")],
            "플래그": ["분양권 취득일이 기준이다 — 계약일이 아니라 취득일로 확인할 것"],
        }
    if sd < _B3_APPLIES_FROM:
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": True, "판정근거항": "해당없음",
                "사유": "2021-01-01 전 양도분은 이 특례의 적용 대상 기간이 아니다",
                "근거": [_cite("2021년 1월 1일 이후 양도분부터 적용",
                              "소득세법 시행령 부칙(2021.2.17) §10② (N영156의3-0)", "A")],
                "플래그": []}

    gap_1y = _b3_years_between(ph, bg)
    gap_3y = _b3_years_between(bg, sd)
    waived = holding_waiver_reason in _B3_1Y_WAIVERS
    if holding_waiver_reason and not waived:
        flags.append(
            f"'{holding_waiver_reason}'은 §154①제2호 나목·다목이라 ②항 후단의 인용 대상이 "
            "아니다 — 1년 요건은 그대로 적용된다(N영156의3-2)")

    # 1. ②항 — 분양권 취득일부터 3년 이내 양도
    if sd <= _b3_add_years(bg, 3):
        ok_1y = bg >= _b3_add_years(ph, 1) or waived
        if ok_1y:
            citations.append(_cite(
                f"종전주택 취득 후 {gap_1y:.1f}년 뒤 분양권 취득, 분양권 취득 후 "
                f"{gap_3y:.1f}년 만에 양도 — ②항 충족",
                "소득세법 시행령 §156의3② (N영156의3-1)", "A"))
            if waived:
                citations.append(_cite(
                    f"'{holding_waiver_reason}' 해당 — 1년 경과 요건 배제",
                    "소득세법 시행령 §156의3② 후단 (N영156의3-2)", "A"))
            return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": True, "판정근거항": "②",
                    "사유": "일시적 1주택+1분양권 — 3년 내 종전주택 양도",
                    "근거": citations, "플래그": flags, "사후관리": ""}
        flags.append(f"종전주택 취득({prior_home_acquired}) 후 1년이 지나지 않아 분양권을 "
                     f"취득했다 — {_b3_add_years(ph, 1).isoformat()} 이후 취득분이어야 한다")
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": False, "판정근거항": "②",
                "사유": "종전주택 취득일부터 1년 이상 지난 후 분양권을 취득해야 한다",
                "근거": citations + [_cite(
                    "종전주택 취득 후 1년 경과 후 분양권 취득 요건",
                    "소득세법 시행령 §156의3② (N영156의3-1)", "A")],
                "플래그": flags}

    # 2. ②항 괄호 — 3년을 넘겼어도 규칙 §75① 사유면 ②항 유지
    if sale_delay_reason:
        if sale_delay_reason not in _B3_DELAY_REASONS:
            flags.append(
                f"'{sale_delay_reason}'은 규칙 §75① 열거(캠코매각의뢰·법원경매신청·공매진행)에 "
                "없다 — 시장에서 안 팔린 사정은 부득이한 사유가 아니다(N규칙75-1)")
        elif not (delay_state_at_3y and sold_by_that_method):
            missing = []
            if not delay_state_at_3y:
                missing.append("분양권 취득일부터 3년이 되는 날 현재 그 상태일 것")
            if not sold_by_that_method:
                missing.append("실제로 그 방법에 따라 양도될 것")
            flags.append("규칙 §75① 부수요건 미충족 — " + " / ".join(missing))
        else:
            ok_1y = bg >= _b3_add_years(ph, 1) or waived
            if ok_1y:
                citations.append(_cite(
                    f"3년 경과({gap_3y:.1f}년)했으나 '{sale_delay_reason}' 해당 — ②항 유지",
                    "소득세법 시행령 §156의3② 괄호 · 시행규칙 §75① "
                    "(N영156의3-3·N규칙75-1)", "A"))
                return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": True, "판정근거항": "②(부득이)",
                        "사유": "3년 내 양도하지 못했으나 규칙 §75① 사유에 해당",
                        "근거": citations, "플래그": flags, "사후관리": ""}
            flags.append(f"1년 요건 미달({gap_1y:.1f}년) — 부득이한 사유와 무관하게 탈락")

    # 3. ③항 — 3년 경과 양도, 신축주택 실입주 요건
    # 1년 요건은 2022-02-15 이후 '취득한 분양권'부터. 취득일 기준이지 양도일이 아니다.
    need_1y = bg >= _B3_1Y_RULE_FROM
    if not need_1y:
        citations.append(_cite(
            "2022-02-15 전에 취득한 분양권 — ③항의 1년 경과 요건은 종전 규정에 따라 미적용",
            "소득세법 시행령 부칙(2022.2.15) §12 (N영156의3-7)", "A"))
    elif not (bg >= _b3_add_years(ph, 1) or waived):
        flags.append(f"③항 1년 요건 미달 — 분양권을 {_b3_add_years(ph, 1).isoformat()} "
                     f"이후에 취득했어야 한다(취득일 {bunyang_acquired})")
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": False, "판정근거항": "③",
                "사유": "2022-02-15 이후 취득 분양권은 종전주택 취득 1년 경과 후 취득해야 한다",
                "근거": citations + [_cite(
                    "③항 1년 요건 신설", "소득세법 시행령 §156의3③ (2022.2.15 개정, "
                    "N영156의3-4·N영156의3-7)", "A")],
                "플래그": flags}

    if not new_home_completed:
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": False, "판정근거항": "③",
                "사유": f"분양권 취득 후 {gap_3y:.1f}년 만의 양도라 ③항 판정이 필요하다 — "
                      "신축주택 완성일(new_home_completed)이 있어야 한다",
                "근거": citations, "플래그": flags + ["완성일·이사일·거주기간을 받아 재판정할 것"]}

    nc = date.fromisoformat(new_home_completed)
    # 2년 구간은 분양권에서는 실제로 도달하지 않는다 — ③항은 분양권 취득 + 3년을
    # 지난 양도에만 열리고 분양권은 2021-01-01 이후 취득분만 대상이라, 양도일이
    # 항상 2024-01-01을 넘는다(N영156의3-9). 법문상 존재하는 구간이라 지우지 않는다.
    limit_years = 3 if sd >= _B3_MOVE_3Y_FROM else 2
    citations.append(_cite(
        f"완성 후 {limit_years}년 기준 적용 — 양도일 {sale_date}",
        "소득세법 시행령 §156의3③1·2호 · 부칙(2023.2.28) §8 "
        "(N영156의3-5·N영156의3-6)", "A"))
    if limit_years == 2:
        flags.append("2023-01-12 전 양도분이라 종전 규정(2년)이다 — 시행일(2023-02-28)이 "
                     "아니라 양도일 2023-01-12가 기준이다")

    deadline_years = limit_years

    # 제2호 — 완성 전 또는 완성 후 N년 이내 종전주택 양도
    sold_gap = _b3_years_between(nc, sd)
    ok_sale = sd < nc or sd <= _b3_add_years(nc, deadline_years)
    if not ok_sale:
        flags.append(f"신축주택 완성 후 {sold_gap:.1f}년 만에 종전주택 양도 — "
                     f"{deadline_years}년 초과")

    # 제1호 — 완성 후 N년 이내 세대전원 이사 + 1년 이상 계속 거주
    ok_move, move_gap = False, None
    if moved_in_date:
        md = date.fromisoformat(moved_in_date)
        move_gap = _b3_years_between(nc, md)
        ok_move = md <= _b3_add_years(nc, deadline_years)
        if not ok_move:
            flags.append(f"완성 후 {move_gap:.1f}년 만에 이사 — {deadline_years}년 초과")
    else:
        flags.append("세대전원 이사일(moved_in_date)이 없다 — ③항 제1호는 실입주가 요건이다")

    if partial_move_reason:
        if partial_move_reason in _B3_PARTIAL_MOVE_REASONS:
            citations.append(_cite(
                f"세대 구성원 중 일부가 '{partial_move_reason}'으로 이전하지 못한 경우 포함 — "
                "다른 시·군 이전이 전제이고 재학·재직·요양증명서로 확인",
                "소득세법 시행규칙 §75의2① · §71③ (N규칙75의2-1·N규칙71-3)", "A"))
        else:
            flags.append(
                f"'{partial_move_reason}'은 규칙 §71③ 열거(취학·근무·질병·학교폭력)에 없다. "
                "취학은 초·중학교를 제외한다(N규칙71-3)")

    ok_reside = continuous_residence_years >= 1.0
    if not ok_reside:
        flags.append(f"신축주택 계속거주 {continuous_residence_years:.1f}년 — 1년 미달")

    ok = ok_sale and ok_move and ok_reside
    aftercare = ("③항은 조건부다 — 신축주택에서 1년 이상 계속 거주하지 못하게 되면 그 사유가 "
                 "발생한 날이 속하는 달의 말일부터 2개월 이내에 ③항을 적용받지 않았을 경우의 "
                 "세액을 신고·납부해야 한다(영 §156의3⑩, N영156의3-8)")
    citations.append(_cite(
        "완성 후 기한 내 세대전원 이사 + 1년 이상 계속 거주 + 완성 전이나 기한 내 종전주택 양도",
        "소득세법 시행령 §156의3③1·2호 (N영156의3-4)", "A"))
    return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": ok, "판정근거항": "③",
            "사유": ("신축주택 실입주 요건 충족" if ok else "③항 요건 미충족 — 플래그 참조"),
            "근거": citations, "플래그": flags,
            "사후관리": aftercare if ok else ""}
