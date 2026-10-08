# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_temporary_two_homes (S4 상담사례 교차검증, run 재현용).

결함: 조정→조정 2년 단축 판정이 '신규주택 취득 당시 두 주택 모두 조정'만 보고, 종전주택이
신규주택 취득계약 후에 비로소 조정지정된 경우(고시 불소급)를 구분하지 못해 2년으로 오판.
상담사례 세법상담-500(근거 서면-2020-부동산-3583)이 발견 — 정답은 3년.
"""
from tax_judgment import (  # noqa: F401,F403 — 변경 없는 헬퍼·상수
    _cite, _add_years, _add_months, _R155_REL_3Y, _R155_REL_2Y, _R155_ACQ_2Y, _R155_ACQ_1Y,
    _R155_EFF_29242, _R155_EFF_30395)
from datetime import date  # noqa: F401


def _r155_regime(n: date, sale: date | None, prev_adj: bool, new_adj: bool,
                 new_contract: date | None) -> tuple[int, bool, str]:
    """(양도기한 연수, 전입요건 적용 여부, 적용법령 설명) — 조정→조정만 단축·전입요건 대상."""
    if not (prev_adj and new_adj):
        return 3, False, "영 §155① 본문 — 조정대상지역 상호 요건 미해당 → 3년"
    if sale is None or sale >= _R155_REL_3Y:
        return 3, False, "영 §155①(2023.2.28 개정, 33267호 부칙 §8) — 2023.1.12 이후 양도분 3년 단일·전입요건 폐지"
    if sale >= _R155_REL_2Y:
        return 2, False, "구 영 §155①2호(32654호 부칙 §3) — 2022.5.10~2023.1.11 양도분 2년·전입요건 폐지"
    # 2022.5.10 전 양도 — 신규주택 취득(계약)일로 구간 확정
    gate = new_contract or n
    if gate < _R155_ACQ_2Y or sale < _R155_EFF_29242:
        return 3, False, "구 영 §155①(29242호 부칙 §2② 1·2호) — 2018.9.13 이전 신규취득·계약분은 종전규정 3년"
    if gate < _R155_ACQ_1Y or sale < _R155_EFF_30395:
        return 2, False, "구 영 §155①2호(29242호) — 조정→조정, 2018.9.14~2019.12.16 신규취득분 2년"
    return 1, True, "구 영 §155①2호 가·나목(30395호) — 조정→조정, 2019.12.17 이후 신규취득분: 1년 내 양도 + 1년 내 세대전원 이사·전입신고(둘 다)"


def judge_temporary_two_homes(prev_acquired: str, new_acquired: str,
                              prev_sale_date: str | None = None,
                              prev_meets_exemption: bool = True,
                              one_year_rule_waived: bool = False,
                              prev_in_adjusted_area: bool = False,
                              new_in_adjusted_area: bool = False,
                              moved_in_within_1y: bool | None = None,
                              moved_in_date: str | None = None,
                              new_home_tenant_lease_end: str | None = None,
                              new_contract_date: str | None = None,
                              other_homes_at_acquisition: int = 0) -> dict:
    """§155① 일시적 2주택 특례 판정 (노드 §155 계열·사례③, 심판례 회귀셋 cases_155_1.json).

    other_homes_at_acquisition: 신규주택 취득 당시 종전주택 외 추가 보유 주택수 — §155①은
    '1주택을 소유한 1세대가 신규주택을 취득해 일시적으로 2주택'이 된 경우 전제라, 취득 당시
    2주택 이상(3주택 이상이 됐다가 처분으로 2주택을 만든 사안 포함)이면 특례 배제
    (대법원 2024두55426 — 확장·유추해석 불가).

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

    if int(other_homes_at_acquisition or 0) > 0:
        return {
            "특례충족": False,
            "사유": f"신규주택 취득 당시 종전주택 외 {other_homes_at_acquisition}주택 추가 보유 — "
                  "§155①은 '1주택 세대가 신규취득으로 일시적 2주택'이 된 경우 전제라 3주택 이상이 "
                  "됐다가 처분으로 2주택을 만들어도 특례 불가",
            "근거": [_cite("§155①1호는 1주택 소유 1세대의 신규취득을 전제 — 확장·유추해석 불허",
                         "대법원 2024두55426 (2025-02-13) · 소득세법 시행령 §155①", "A")],
            "플래그": ["처분 순서를 바꿔도 결론 동일 — 신규취득 '당시' 주택수가 기준. "
                     "다른 특례(§155②~ 상속·혼인 등) 중첩 여부는 별도 판정"],
        }

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
