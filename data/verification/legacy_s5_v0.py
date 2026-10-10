# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — S5 대법원 판례 교차검증에서 적발된 두 함수.

결함: ①judge_temporary_two_homes — §155①이 '1주택자가 신규주택을 취득해 2주택'이 된 경우
전제라는 게이트가 없어, 3주택에서 1채를 처분해 2주택을 만든 사안도 특례 가능으로 오판
(대법원 2024두55426). ②judge_co_inherited_owner — §155③은 상속개시 당시 상속인·피상속인이
별도세대임을 전제(동거봉양 합가 예외 제외)라는 게이트가 없어 동일세대원 공동상속 지분도
불산입으로 오판(대법원 2023두53799).
"""
from tax_judgment import *          # noqa: F401,F403
from tax_judgment import (  # noqa: F401 — 변경 없는 프라이빗 헬퍼 일괄
    _cite, _add_months, _add_years, _CO_INHERIT_PRIORITY_FROM, _r155_regime)
from datetime import date           # noqa: F401


def judge_temporary_two_homes(prev_acquired: str, new_acquired: str,
                              prev_sale_date: str | None = None,
                              prev_meets_exemption: bool = True,
                              one_year_rule_waived: bool = False,
                              prev_in_adjusted_area: bool = False,
                              new_in_adjusted_area: bool = False,
                              moved_in_within_1y: bool | None = None,
                              moved_in_date: str | None = None,
                              new_home_tenant_lease_end: str | None = None,
                              new_contract_date: str | None = None) -> dict:
    """§155① 일시적 2주택 특례 판정 (노드 §155 계열·사례③, 심판례 회귀셋 cases_155_1.json).

    요건: ①종전주택 취득 1년 경과 후 신규 취득(§154①1~3호 해당 시 면제 — 공공임대 5년 거주 등)
    ②신규 취득일부터 법정기한 내 종전 양도 ③종전주택 자체가 비과세 요건 충족
    ④(구법·조정→조정) 신규주택 취득일부터 1년 내 세대전원 이사·전입신고.

    양도기한은 양도일에 따라 3년/2년/1년으로 갈린다(부칙 모두 "양도하는 경우부터 적용"):
    2023.1.12 이후 양도=3년 단일, 2022.5.10~2023.1.11=조정→조정 2년, 그 전=신규취득일 구간별
    3년/2년/1년+전입요건. 2026-08-23 심판례 17건 회귀 검증에서 이 구법 분기 누락이 확인되어 신설.

    전입·양도 기한은 신규주택에 전소유자와의 임대차가 남아 있고 그 종료일이 취득일+1년 후이면
    임대차 종료일까지 연장(취득일부터 최대 2년, 취득 후 갱신계약은 불인정 — 구 §155①2호 단서).
    날짜는 YYYY-MM-DD. prev_sale_date 미정이면 현행법(3년) 기준 데드라인만 계산.
    """
    p, n = date.fromisoformat(prev_acquired), date.fromisoformat(new_acquired)
    s = date.fromisoformat(prev_sale_date) if prev_sale_date else None
    citations, flags = [], []

    p_anniv = date(p.year + 1, p.month, p.day) if not (p.month == 2 and p.day == 29) else date(p.year + 1, 3, 1)
    one_year_ok = n >= p_anniv or one_year_rule_waived
    if one_year_rule_waived:
        citations.append(_cite("1년 경과 요건 면제 — §154①1~3호 해당(건설임대 5년 거주·수용·출국 등)",
                               "영 §155① 후단 (사례③ 확정 명문)", "B"))
    else:
        citations.append(_cite(f"종전 취득 {prev_acquired} + 1년 ≤ 신규 취득 {new_acquired}: {'충족' if one_year_ok else '미충족'}",
                               "영 §155① (1년 이상 지난 후 신규 취득)", "B"))

    years, needs_move_in, regime = _r155_regime(
        n, s, prev_in_adjusted_area, new_in_adjusted_area,
        date.fromisoformat(new_contract_date) if new_contract_date else None)
    citations.append(_cite(regime, "영 §155① 및 부칙(29242·30395·32654·33267호)", "A"))

    deadline = _add_years(n, years)
    cap2y = _add_years(n, 2)
    lease_end = date.fromisoformat(new_home_tenant_lease_end) if new_home_tenant_lease_end else None
    extended = None
    if lease_end and years == 1 and lease_end > _add_years(n, 1):
        extended = min(lease_end, cap2y)
        deadline = extended
        citations.append(_cite(
            f"전소유자 임대차 종료일 {lease_end.isoformat()} → 양도·전입 기한 {extended.isoformat()}로 연장(취득일+2년 한도)",
            "구 영 §155①2호 단서", "B"))

    sale_ok, sale_note = None, f"양도 데드라인 = {deadline.isoformat()} (신규 취득 + {years}년)"
    if s:
        sale_ok = s <= deadline
        sale_note = (f"양도(예정)일 {prev_sale_date} — 데드라인 {deadline.isoformat()} "
                     f"{'이내 충족' if sale_ok else '경과·미충족'} (잔여 {(deadline - s).days}일)")
    citations.append(_cite(sale_note, f"영 §155① (신규 취득일부터 {years}년 이내 종전주택 양도)", "B"))

    # ── 전입요건 (구법·조정→조정 1년 구간만) ──
    move_in_ok: bool | None = None
    gray = False
    if needs_move_in:
        mdate = date.fromisoformat(moved_in_date) if moved_in_date else None
        if mdate:
            move_in_ok = mdate <= deadline
            delay = (mdate - deadline).days
            if not move_in_ok and 0 < delay <= 30:
                gray = True
                flags.append(f"전입 지연 {delay}일 — 임차인 잔존 등 사정 시 '사회통념상 일시적'으로 특례를 인정한 "
                             f"선례 있음(조심 2023서6773, 15일 지연 인용). 법문상은 미충족 — 전문가 확인 필요(등급 c)")
            citations.append(_cite(
                f"세대전원 전입완료 {moved_in_date} vs 전입기한 {deadline.isoformat()}: {'충족' if move_in_ok else '미충족'}",
                "구 영 §155①2호 가목", "A"))
        elif moved_in_within_1y is not None:
            move_in_ok = bool(moved_in_within_1y)
            citations.append(_cite(
                f"신규주택 취득일부터 1년 내 세대전원 이사·전입신고: {'충족' if move_in_ok else '미충족'}",
                "구 영 §155①2호 가목", "A"))
        else:
            flags.append("구법 전입요건 적용 구간인데 전입 여부 미입력 — 판정 보류. "
                         "세대 '전원'(일부 전입은 미충족) 기준으로 확인 필요")
            citations.append(_cite("전입요건 적용 구간 — 입력 없음, 판정 보류", "구 영 §155①2호 가목", "A"))
        flags.append("전입요건은 세대 전원 기준. 취학·근무상 형편·질병 요양(규칙 §72⑦)만 일부 미이사 허용 — "
                     "임차인 잔존·인테리어 공사·전소유자 임차는 법정 예외 아님(심판례 다수 기각)")

    if not prev_meets_exemption:
        flags.append("종전주택 자체 비과세 요건(보유 2년·취득당시 조정 시 거주 2년) 미충족 — 특례 무의미")
    flags.append("취득세 일시적 2주택(영 §28의5)은 별개: 1년 경과 요건 없음·종전에 오피스텔 포함 — 세목 분기")
    flags.append("종전주택 취득시기 자체가 갈리는 유형(분양전환임대 등)은 취득시기 판정 선행 — 사례③ 쟁점. "
                 "대금청산 전 소유권이전등기를 한 경우 취득시기는 등기접수일(영 §162①2호)")

    if needs_move_in and move_in_ok is None:
        qualifies = None
    else:
        qualifies = one_year_ok and (sale_ok is not False) and prev_meets_exemption and (move_in_ok is not False)
        if not prev_sale_date:
            qualifies = one_year_ok and prev_meets_exemption and (move_in_ok is not False)

    return {
        "특례충족": qualifies,
        "1년경과요건": one_year_ok,
        "적용법령": regime,
        "양도기한연수": years,
        "양도데드라인": deadline.isoformat(),
        "임대차연장": extended.isoformat() if extended else None,
        "양도기한내": sale_ok,
        "전입요건적용": needs_move_in,
        "전입요건충족": move_in_ok,
        "회색지대": gray,
        "근거": citations,
        "플래그": flags,
    }


def judge_co_inherited_owner(shares: list[dict], is_first_priority: bool | None = None,
                             sale_date: str = "",
                             shares_changed_after_inheritance: bool = False) -> dict:
    """공동상속주택의 소유자 귀속 + 소수지분 불산입 적용 판정 (영 §155③).

    원칙: 공동상속주택은 다른 주택 양도 시 '해당 거주자의 주택으로 보지 아니한다'(불산입).
    단 상속지분 최대자는 산입하며, 최대자가 2명 이상이면 ①해당 주택 거주자 ②최연장자 순.
    (2호는 2008-02-22 삭제 — 현행은 1호·3호만)

    ⚠️피상속인이 상속개시 당시 2주택 이상이면 §155③의 공동상속주택은 '§155② 각 호 순위에 따른
    1주택(선순위)'만을 말한다 — 이 괄호는 2017-02-03(영 27829호, 공포일 시행) 신설이고 기준일은
    양도일이다. 구법 양도분은 선순위 불문 전부 불산입(조심 2017서3603), 현행 양도분은 선순위만
    불산입·나머지 소수지분은 주택수 산입(조심 2018중0793).

    shares 원소: {"상속인": str, "지분율": float, "해당주택_거주": bool, "나이": int}
      — 지분율은 '상속개시일 현재' 기준. 이후 증여·경정등기로 변경돼도 상속개시일 기준으로
        판정한다(서면-2025-법규재산-2004).
    is_first_priority: 이 주택이 §155② 선순위 상속주택인지 (피상속인 다주택일 때만 의미,
      judge_inherited_house_priority로 산출). None이면 확인 플래그만 세운다.
    sale_date: 일반주택 양도일 YYYY-MM-DD — 2017-02-03 경계 판정용. 비우면 현행법 가정.
    """
    if not shares:
        return {"오류": "shares가 비어 있음"}
    top = max(float(s.get("지분율", 0)) for s in shares)
    cand = [s for s in shares if float(s.get("지분율", 0)) == top]
    applied, flags = "최대지분", []
    if len(cand) > 1:
        resid = [s for s in cand if bool(s.get("해당주택_거주"))]
        if len(resid) == 1:
            cand, applied = resid, "동률 → 1호(해당 주택 거주자)"
        else:
            base = resid if resid else cand
            oldest = max(int(s.get("나이", 0)) for s in base)
            cand = [s for s in base if int(s.get("나이", 0)) == oldest]
            applied = "동률 → 3호(최연장자)"
            if len(cand) > 1:
                flags.append("최연장자도 동률 — 조문상 추가 기준 없음, 사실관계 확인 필요(쟁점플래그)")
    owner = cand[0].get("상속인", "미상")

    # 소수지분 불산입이 이 주택에 적용되는지 — 선순위 한정(2017-02-03~) 경계
    old_law = bool(sale_date) and date.fromisoformat(sale_date) < _CO_INHERIT_PRIORITY_FROM
    if old_law:
        exempt = True
        flags.append("양도일이 2017-02-03(영 27829호) 전 — 선순위 한정 괄호가 없던 구법이라 소수지분 "
                     "공동상속주택은 선순위 불문 전부 불산입(조심 2017서3603·2015중2794)")
    elif is_first_priority is False:
        exempt = False
        flags.append("선순위 아닌 공동상속주택 — 2017-02-03 이후 양도분은 §155③ 대상이 아니어서 "
                     "소수지분이라도 주택수에 산입한다(조심 2018중0793·2020전8566·2021서2745)")
    else:
        exempt = True
        if is_first_priority is None:
            flags.append("피상속인이 상속개시 당시 2주택 이상이었다면 선순위 여부 확인 필수 — "
                         "judge_inherited_house_priority로 판정 후 is_first_priority로 전달"
                         " (선순위 아니면 불산입 배제)")
    if exempt:
        flags.append(f"소유자로 보는 {owner} 외 나머지 공동상속인은 다른 주택 양도 시 이 주택을 "
                     "주택수에 산입하지 않는다")
    if shares_changed_after_inheritance:
        flags.append("상속개시일 이후 지분 변경(증여·경정등기 등)은 판정에 반영하지 않는다 — "
                     "소유자 판정은 상속개시일 기준(서면-2025-법규재산-2004)")
    flags.append("세목 분기: 취득세는 최대지분→거주자→연장자(지방세법 영 §28의4⑤), "
                 "종부세는 소액지분(40%↓ 또는 지분공시가 6억·지방3억↓)이면 기간 무관 제외(영 §4의2②) — 결론이 갈릴 수 있음")
    return {
        "소유자귀속": owner,
        "적용기준": applied,
        "소수지분_불산입적용": exempt,
        "불산입_상속인": ([s.get("상속인") for s in shares if s.get("상속인") != owner]
                     if exempt else []),
        "근거": [
            _cite("공동상속주택은 다른 주택 양도 시 해당 거주자의 주택으로 보지 않음(원칙 불산입)", "영 §155③ 본문", "A"),
            _cite("단서: 상속지분 최대자는 산입, 동률이면 1호 해당 주택 거주자 → 3호 최연장자", "영 §155③ 단서 (2호는 2008 삭제)", "A"),
            _cite("피상속인 다주택 시 공동상속주택 = §155② 순위의 선순위 1주택 한정 — 2017-02-03 공포일 "
                  "시행, 양도일 기준", "영 §155③ 괄호 · 영 27829호 부칙 §1", "A"),
        ],
        "플래그": flags,
    }
