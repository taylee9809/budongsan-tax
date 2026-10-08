# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_inherited_house_priority / judge_co_inherited_owner (run#20·21 재현용).

결함: §155③ 선순위 한정(2017-02-03 영 27829호)과 양도일 경계가 없고, 소수지분 불산입을
무조건으로 플래그했다. 멸실·협의지정·상속개시일 기준시점 입력도 받지 않았다.
"""


def _cite(rule, basis, grade="B"):
    return {"규칙": rule, "근거": basis, "등급": grade}


_INHERIT_PRIORITY_RULES = [
    ("1호", "피상속인이 소유한 기간이 가장 긴 1주택"),
    ("2호", "소유기간이 같으면 피상속인이 거주한 기간이 가장 긴 1주택"),
    ("3호", "소유·거주기간이 모두 같으면 피상속인이 상속개시 당시 거주한 1주택"),
    ("4호", "거주사실이 없고 소유기간이 같으면 기준시가가 가장 높은 1주택(기준시가도 같으면 상속인 선택)"),
]


def judge_inherited_house_priority(houses):
    if not houses:
        return {"오류": "houses가 비어 있음"}
    if len(houses) == 1:
        h = houses[0]
        return {"선순위주택": h.get("라벨") or "상속주택1", "적용호": "해당없음(단일)",
                "순위표": [], "동률잔존": False,
                "근거": [_cite("상속주택이 1개면 순위규정 불요", "영 §155② 본문", "A")],
                "플래그": []}

    def _label(h, i):
        return h.get("라벨") or f"상속주택{i + 1}"

    pool = [(i, h) for i, h in enumerate(houses)]
    flags, trace = [], []
    applied = None

    top = max(float(h.get("피상속인_소유기간_년", 0)) for _, h in pool)
    cand = [(i, h) for i, h in pool if float(h.get("피상속인_소유기간_년", 0)) == top]
    trace.append({"호": "1호", "기준": f"소유기간 최장 {top}년", "잔존": [_label(h, i) for i, h in cand]})
    if len(cand) == 1:
        applied = "1호"
    else:
        pool = cand
        top = max(float(h.get("피상속인_거주기간_년", 0)) for _, h in pool)
        cand = [(i, h) for i, h in pool if float(h.get("피상속인_거주기간_년", 0)) == top]
        trace.append({"호": "2호", "기준": f"거주기간 최장 {top}년", "잔존": [_label(h, i) for i, h in cand]})
        if len(cand) == 1:
            applied = "2호"
        else:
            pool = cand
            cand3 = [(i, h) for i, h in pool if bool(h.get("상속개시당시_거주"))]
            trace.append({"호": "3호", "기준": "상속개시 당시 거주",
                          "잔존": [_label(h, i) for i, h in cand3]})
            if len(cand3) == 1:
                cand, applied = cand3, "3호"
            elif len(cand3) > 1:
                cand, pool = cand3, cand3
                applied = None
            if applied is None:
                pool = cand if cand else pool
                top = max(int(h.get("기준시가", 0)) for _, h in pool)
                cand = [(i, h) for i, h in pool if int(h.get("기준시가", 0)) == top]
                trace.append({"호": "4호", "기준": f"기준시가 최고 {top:,}원",
                              "잔존": [_label(h, i) for i, h in cand]})
                applied = "4호"

    tie = len(cand) > 1
    if tie:
        flags.append("4호까지 적용해도 동률 — 기준시가가 같은 경우 상속인이 선택한다(영 §155②4호 괄호). "
                     "선택지별 시나리오 비교 대상")
    if not any(bool(h.get("상속개시당시_거주")) for h in houses):
        flags.append("피상속인 거주사실이 어느 주택에도 없음 — 4호(기준시가 최고)가 실질 기준")
    flags.append("이 순위는 '피상속인'의 소유·거주기간 기준 — 상속인 기준이 아니다")
    flags.append("선순위 아닌 나머지 상속주택은 일반주택 양도 시 주택수에 그대로 산입 (특례 대상 아님)")

    return {
        "선순위주택": _label(cand[0][1], cand[0][0]),
        "적용호": applied,
        "순위표": trace,
        "동률잔존": tie,
        "후보": [_label(h, i) for i, h in cand],
        "근거": [_cite(f"{no} — {desc}", "소득세법 시행령 §155② (20차 순회)", "A")
                 for no, desc in _INHERIT_PRIORITY_RULES],
        "플래그": flags,
        "연계": "결과를 judge_155_special(kind='상속주택')의 is_first_priority_inherited로 전달",
    }


def judge_co_inherited_owner(shares):
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
    flags.append(f"소유자로 보는 {owner} 외 나머지 공동상속인은 다른 주택 양도 시 이 주택을 주택수에 산입하지 않는다")
    flags.append("세목 분기: 취득세는 최대지분→거주자→연장자(지방세법 영 §28의4⑤), "
                 "종부세는 소액지분(40%↓ 또는 지분공시가 6억·지방3억↓)이면 기간 무관 제외(영 §4의2②) — 결론이 갈릴 수 있음")
    return {
        "소유자귀속": owner,
        "적용기준": applied,
        "불산입_상속인": [s.get("상속인") for s in shares if s.get("상속인") != owner],
        "근거": [
            _cite("공동상속주택은 다른 주택 양도 시 해당 거주자의 주택으로 보지 않음(원칙 불산입)", "영 §155③ 본문", "A"),
            _cite("단서: 상속지분 최대자는 산입, 동률이면 1호 해당 주택 거주자 → 3호 최연장자", "영 §155③ 단서 (2호는 2008 삭제)", "A"),
        ],
        "플래그": flags,
    }
