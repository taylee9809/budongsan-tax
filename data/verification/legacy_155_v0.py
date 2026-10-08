# -*- coding: utf-8 -*-
"""judge_temporary_two_homes 수정 전(v0) 스냅샷 — run #1(수정 전 상태) 재현 전용.

2026-08-23 심판례 회귀 검증에서 폐기된 구현. 아래 두 가지가 없다:
  ① 양도일 기준 양도기한 분기(3년/2년/1년) — 무조건 신규취득일+3년
  ② 구 영 §155①2호 가목 전입요건
런타임에서 import 하지 말 것. 러너가 `--impl legacy_v0`일 때만 로드한다.
"""
from datetime import date

from tax_judgment import _cite


def judge_temporary_two_homes(prev_acquired: str, new_acquired: str,
                              prev_sale_date: str | None = None,
                              prev_meets_exemption: bool = True,
                              one_year_rule_waived: bool = False) -> dict:
    """§155① 일시적 2주택 특례 날짜 판정 (노드 §155 계열·사례③) — v0 원본."""
    p, n = date.fromisoformat(prev_acquired), date.fromisoformat(new_acquired)
    citations, flags = [], []

    p_anniv = date(p.year + 1, p.month, p.day) if not (p.month == 2 and p.day == 29) else date(p.year + 1, 3, 1)
    one_year_ok = n >= p_anniv or one_year_rule_waived
    if one_year_rule_waived:
        citations.append(_cite("1년 경과 요건 면제 — §154①1~3호 해당(건설임대 5년 거주·수용·출국 등)",
                               "영 §155① 후단 (사례③ 확정 명문)", "B"))
    else:
        citations.append(_cite(f"종전 취득 {prev_acquired} + 1년 ≤ 신규 취득 {new_acquired}: {'충족' if one_year_ok else '미충족'}",
                               "영 §155① (1년 이상 지난 후 신규 취득)", "B"))

    deadline = date(n.year + 3, n.month, n.day) if not (n.month == 2 and n.day == 29) else date(n.year + 3, 2, 28)
    sale_ok, sale_note = None, f"양도 데드라인 = {deadline.isoformat()} (신규 취득 + 3년)"
    if prev_sale_date:
        s = date.fromisoformat(prev_sale_date)
        sale_ok = s <= deadline
        sale_note = f"양도(예정)일 {prev_sale_date} — 데드라인 {deadline.isoformat()} {'이내 충족' if sale_ok else '경과·미충족'} (잔여 {(deadline - s).days}일)"
    citations.append(_cite(sale_note, "영 §155① (신규 취득일부터 3년 이내 종전주택 양도)", "B"))

    qualifies = one_year_ok and (sale_ok is not False) and prev_meets_exemption
    if not prev_meets_exemption:
        flags.append("종전주택 자체 비과세 요건(보유 2년·취득당시 조정 시 거주 2년) 미충족 — 특례 무의미")
    flags.append("취득세 일시적 2주택(영 §28의5)은 별개: 1년 경과 요건 없음·종전에 오피스텔 포함 — 세목 분기")
    flags.append("종전주택 취득시기 자체가 갈리는 유형(분양전환임대 등)은 취득시기 판정 선행 — 사례③ 쟁점")

    return {
        "특례충족": qualifies if prev_sale_date else (one_year_ok and prev_meets_exemption),
        "1년경과요건": one_year_ok,
        "양도데드라인": deadline.isoformat(),
        "양도기한내": sale_ok,
        "근거": citations,
        "플래그": flags,
    }
