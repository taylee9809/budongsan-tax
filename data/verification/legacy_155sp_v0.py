# -*- coding: utf-8 -*-
"""judge_155_special 수정 전(v0) 스냅샷 — run#5(수정 전 상태) 재현 전용.

2026-08-24 §155 특례군 회귀 검증에서 폐기된 구현. 없는 것:
  ① 혼인·동거봉양 특례기간의 양도일 기준 경과규정 — 둘 다 10년 고정이라
     구법 5년 구간(혼인 2024-11-12 전 / 동거봉양 2018-02-13 전 양도)을 오인정
  ② 다른 특례로 주택수에서 빠지는 주택(공동상속·농어촌 등)의 차감
  ③ 2009-02-04 전 합가의 여성 직계존속 55세 기준
  ④ 동거봉양 합가로 동일세대가 된 경우 '합치기 이전부터 보유한 주택'의 상속주택 인정
런타임에서 import 하지 말 것. 러너가 `--impl legacy_155sp_v0`일 때만 로드한다.
"""
from datetime import date

from tax_judgment import _add_years, _cite


def judge_155_special(kind: str, event_date: str = "", sale_date: str = "",
                      homes_mine: int = 1, homes_spouse_or_parent: int = 1,
                      parent_max_age_at_merge: int | None = None,
                      separate_household_at_inheritance: bool = True,
                      general_home_acquired_before_inheritance: bool = True,
                      is_first_priority_inherited: bool = True,
                      gifted_within_2y_before_inheritance: bool = False,
                      rental_registered: bool = False,
                      residence_years_in_home: float = 0.0,
                      first_time_use: bool = True) -> dict:
    """§155 특례 판정 디스패처 (kind: 혼인|동거봉양|상속주택|거주주택).

    - 혼인(§155⑤): 각 1주택끼리 혼인 → 혼인일부터 10년 내 먼저 양도분 비과세. 1+1 한정(사례⑩).
    - 동거봉양(§155④): 60세↑ 직계존속(한쪽만 60↑ 포함) 합가 → 합가일부터 10년 내 먼저 양도분.
    - 상속주택(§155②): 별도세대 피상속인의 선순위 상속주택 → 일반주택 양도 시 없는 것으로 간주.
    - 거주주택(§155⑳): 장기임대 등록 + 거주주택 2년 거주 → 생애 1회 비과세(사후관리부).
    event_date = 혼인일/합가일 (YYYY-MM-DD).
    """
    flags, citations = [], []
    if kind == "혼인":
        if homes_mine != 1 or homes_spouse_or_parent != 1:
            return {"특례적용": False, "사유": f"1주택+1주택 결합만 가능 — {homes_mine}+{homes_spouse_or_parent}는 탈락 (사례⑩: 2+1 불가)",
                    "근거": [_cite("혼인 합가 특례는 각 1주택 한정", "영 §155⑤ 문언", "B")], "플래그": flags}
        dl = _add_years(date.fromisoformat(event_date), 10)
        ok = (date.fromisoformat(sale_date) <= dl) if sale_date else None
        citations.append(_cite(f"혼인일 {event_date} + 10년 = {dl.isoformat()} 내 먼저 양도분 비과세", "영 §155⑤", "B"))
        flags.append("먼저 양도하는 주택에만 적용 — 양도 순서 선택권이 절세 레버. 각 주택 자체 비과세 요건 충족 전제")
        flags.append("세목 분기: 종부세는 세대 자체 10년 분리(종부령 §1의2④), 취득세 완충은 혼전 분양권 케이스만")
        return {"특례적용": ok if sale_date else True, "데드라인": dl.isoformat(), "근거": citations, "플래그": flags}

    if kind == "동거봉양":
        if parent_max_age_at_merge is not None and parent_max_age_at_merge < 60:
            flags.append("직계존속 모두 60세 미만 — 원칙 불가. 단 요양 필요 등 예외 3호(§155④ 단서) 확인")
            return {"특례적용": False, "사유": "합가 당시 60세 이상 직계존속 요건 미충족", "근거": [_cite("60세 이상 직계존속 동거봉양", "영 §155④", "B")], "플래그": flags}
        if homes_mine != 1 or homes_spouse_or_parent != 1:
            return {"특례적용": False, "사유": "각 1주택 세대끼리의 합가만 가능", "근거": [_cite("1주택+1주택 합가", "영 §155④", "B")], "플래그": flags}
        dl = _add_years(date.fromisoformat(event_date), 10)
        ok = (date.fromisoformat(sale_date) <= dl) if sale_date else None
        citations.append(_cite(f"합가일 {event_date} + 10년 = {dl.isoformat()} 내 먼저 양도분 비과세 (한쪽 존속만 60세↑여도 가능)", "영 §155④", "B"))
        flags.append("종부세 동거봉양은 세대 분리 간주 10년(종부령 §1의2⑤ — 60세 도달 규칙 별도)·상속공제 동거주택 판정에도 합가 예외 있음(상증령 §20의2①6호)")
        return {"특례적용": ok if sale_date else True, "데드라인": dl.isoformat(), "근거": citations, "플래그": flags}

    if kind == "상속주택":
        ok = (separate_household_at_inheritance and general_home_acquired_before_inheritance
              and is_first_priority_inherited and not gifted_within_2y_before_inheritance)
        if not separate_household_at_inheritance:
            flags.append("상속개시 당시 동일세대 — 특례 배제. 단 동거봉양 합가로 동일세대가 된 경우 예외(§155② 괄호) 확인")
        if gifted_within_2y_before_inheritance:
            flags.append("상속개시 전 2년 내 피상속인으로부터 증여받은 주택 — 일반주택 범위에서 제외")
        if not is_first_priority_inherited:
            flags.append("피상속인 다주택 시 선순위(보유기간 최장→거주기간 최장→상속개시 당시 거주→기준시가 최고) 1개만 특례")
        citations.append(_cite("선순위 상속주택은 일반주택 비과세 판정 시 없는 것으로 간주", "영 §155②", "B"))
        return {"특례적용": ok, "근거": citations, "플래그": flags,
                "연계": "충족 시 count_transfer_homes의 상속특례주택=True로 전달"}

    if kind == "거주주택":
        ok = rental_registered and residence_years_in_home >= 2 and first_time_use
        if not first_time_use:
            flags.append("거주주택 특례는 생애 1회 한정(2019-02-12 이후 취득분)")
        if rental_registered and ok:
            flags.append("사후관리: 임대 등록 유지·임대료 5% 상한 위반 시 추징 — D급 확인 권장")
        citations.append(_cite("장기임대 등록 + 거주주택 2년 이상 거주 시 거주주택 비과세", "영 §155⑳", "B"))
        return {"특례적용": ok, "근거": citations, "플래그": flags,
                "연계": "충족 시 count_transfer_homes의 등록임대_거주주택특례=True로 전달"}

    return {"오류": f"지원하지 않는 kind: {kind} (혼인|동거봉양|상속주택|거주주택)"}
