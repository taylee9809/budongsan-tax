# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_jongbu_one_home_status (run#25 재현용).

결함: 일시적 2주택 3년(2023-02-28 개정 전 2년)·지방저가 4억(2025-02-28 개정 전 3억)을
현행 숫자로 하드코딩 — base_date(과세기준일)가 있는데도 경과규정 분기가 없었다.
"""
from datetime import date


def _cite(rule, basis, grade="B"):
    return {"규칙": rule, "근거": basis, "등급": grade}


def _add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


JB_INHERIT_SHARE_LIMIT = 0.40
JB_INHERIT_PRICE_CAP = 600_000_000
JB_INHERIT_PRICE_NONCAP = 300_000_000
JB_LOW_PRICE_LIMIT = 400_000_000


def judge_jongbu_one_home_status(other_homes, base_date=""):
    ok_all, details, flags = True, [], []
    bd = date.fromisoformat(base_date) if base_date else None
    for it in other_homes:
        t, label = it.get("유형", "일반"), it.get("라벨") or it.get("유형", "일반")
        good, why = False, None
        if t == "부속토지":
            good, why = True, "다른 주택의 부속토지만 보유 — 간주 1유형 (법 §8④1호)"
        elif t == "일시적신규":
            if bd and it.get("신규취득일"):
                good = bd <= _add_years(date.fromisoformat(it["신규취득일"]), 3)
                why = f"신규주택 취득 3년 {'미경과 — 간주' if good else '경과 — 탈락'} (영 §4의2①)"
            else:
                good, why = True, "일시적 2주택 — 과세기준일 현재 신규취득 3년 미경과 요건 확인 필요 (영 §4의2①)"
        elif t == "상속":
            share_ok = float(it.get("지분율", 1.0)) <= JB_INHERIT_SHARE_LIMIT
            cap = JB_INHERIT_PRICE_CAP if it.get("수도권", True) else JB_INHERIT_PRICE_NONCAP
            price_ok = 0 < int(it.get("지분공시가", 0)) <= cap
            time_ok = None
            if bd and it.get("상속개시일"):
                time_ok = bd <= _add_years(date.fromisoformat(it["상속개시일"]), 5)
            good = bool(share_ok or price_ok or time_ok)
            why = (f"상속주택 — 지분 40%↓:{share_ok} / 지분공시가 {cap//100_000_000}억↓:{price_ok}"
                   f" / 5년 미경과:{time_ok} (지분·저가 요건은 기간 무제한, 영 §4의2②)")
        elif t == "지방저가":
            good = int(it.get("공시가격", 0)) <= JB_LOW_PRICE_LIMIT and bool(it.get("소재요건충족"))
            why = f"지방 저가주택 — 공시 4억↓ + 소재요건(비수도권 비광역시 등): {'충족' if good else '미충족'} (영 §4의2③, 2026 개정 3억→4억)"
        else:
            why = "일반 주택 — 간주 유형 아님 → 1세대1주택자 탈락"
        ok_all = ok_all and good
        details.append({"항목": label, "간주인정": good, "사유": why})
    if ok_all and other_homes:
        flags.append("간주 인정돼도 그 주택 공시가는 과세표준에 합산 유지 — 12억 공제·연령/보유 세액공제만 1주택자 대우 (법 §8④ 후단)")
        flags.append("신청제: 9/16~9/30 관할세무서장 신청(최초 1회, 변동 없으면 생략 가능 — 법 §8⑤·영 §4의2④⑤)")
        flags.append("세액공제 안분: 간주분(부속토지·일시적·상속·지방저가)은 공제율 적용에서 안분 제외 (법 §9⑦⑨ — calc_jongbu_tax 미지원 명시)")
    return {"1세대1주택자_간주": ok_all if other_homes else True, "항목별": details, "플래그": flags,
            "근거": [_cite("간주 4유형: 부속토지·일시적 2주택 3년·상속(5년/지분40%/6억·3억)·지방저가 4억", "종부세법 §8④·영 §4의2", "B")]}
