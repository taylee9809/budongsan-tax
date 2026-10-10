# -*- coding: utf-8 -*-
"""세대 판정·비과세 주택수 수정 전(v0) 스냅샷 — run#10·11(수정 전) 재현 전용.

2026-08-24 앞단 관문 회귀 검증에서 폐기된 구현. 없는 것:
  ① 소법 §88 6호 괄호 — 법률상 이혼했으나 사실상 이혼으로 보기 어려운 관계(위장이혼)
  ② 취득세 세대의 세목 분기 — 사실혼 제외, 미혼 30세 미만 자녀 분리거주 무효,
     소득요건 직전 12개월, 동거봉양 존속 65세(양도세는 60세)
  ③ 영 §155⑮ 다가구주택 — 구획별 각각 1주택 / 일괄양도 시 전체 1주택
  ④ 영 §154③ 겸용주택 — 주택 연면적이 더 크면 전부 주택
런타임에서 import 하지 말 것. 러너가 `--impl legacy_gate_v0`일 때만 로드한다.
"""
from datetime import date

from tax_judgment import FAMILY_SCOPE, RIGHT_COUNT_FROM, _cite


def judge_same_household(relationship: str, lives_together: bool = True,
                         shares_livelihood: bool = True, age: int | None = None,
                         is_married_or_was: bool = False,
                         income_over_40pct_median: bool = False,
                         is_minor: bool = False, tax_kind: str = "양도세") -> dict:
    """트리① — 본인과 특정인이 같은 1세대인지 판정 (소법 §88 6호·영 §152의3 / 지방령 §28의3 / 종부령 §1의2).

    relationship: 배우자|직계존속|직계비속|직계존비속의 배우자|형제자매|기타(이모·조카·사돈 등)
    tax_kind: 양도세(실질 기준)|취득세(주민등록 기준)|종부세
    반환: 동일세대 여부 + 분리 가능 조건 + 근거·플래그.
    """
    flags, citations = [], []

    # 1) 가족 범위 밖 = 세목 불문 별도 세대 (사례⑭ 이모-조카)
    if relationship == "배우자":
        citations.append(_cite("배우자는 주소·생계 불문 동일 세대(법률혼 기준)",
                               "소법 §88 6호 본문 / 지방령 §28의3①(분리해도 같은 세대) / 종부령 §1의2①", "A"))
        flags.append("종부세는 혼인일부터 10년간 각자 별도 세대 간주(종부령 §1의2④) — 세목 분기 주의")
        return {"동일세대": True, "분리가능": False, "근거": citations, "플래그": flags}
    if relationship not in FAMILY_SCOPE:
        citations.append(_cite("가족 범위(배우자·직계존비속과 그 배우자·형제자매) 밖 — 동거해도 별도 1세대",
                               "소법 §88 6호·종부령 §1의2②·지방령 §28의3 (3세목 공통)", "A"))
        return {"동일세대": False, "분리가능": True, "근거": citations, "플래그": flags}

    # 2) 가족이면서 동거·생계동일이 아니면 별도 (양도세 실질 기준)
    if tax_kind == "양도세" and not (lives_together and shares_livelihood):
        citations.append(_cite("동일 주소에서 생계를 같이하지 않는 가족 — 별도 세대 (취학·요양·근무상 일시퇴거는 포함이므로 확인)",
                               "소법 §88 6호", "A"))
        flags.append("'생계를 같이' 판단은 실질 — 분쟁 최다 지점(해석례 1,376건). 별도 세대 주장 시 독립 생계 증빙 권장")
        return {"동일세대": False, "분리가능": True, "근거": citations, "플래그": flags}
    if tax_kind == "취득세":
        citations.append(_cite("취득세 세대 = 주민등록표 기재 기준. 배우자·미혼 30세 미만 자녀는 분리 거주해도 같은 세대",
                               "지방세법 시행령 §28의3", "B"))

    # 3) 동거 중인 가족의 세대분리 가능성 (영 §152의3)
    can_separate, why = False, None
    if is_minor:
        why = "미성년자 — 결혼·가족 사망 등 불가피 사유 외 분리 불가"
    elif age is not None and age >= 30:
        can_separate, why = True, "30세 이상 — 분리 가능 (영 §152의3 1호)"
    elif is_married_or_was:
        can_separate, why = True, "혼인(또는 이혼·사별) — 분리 가능 (영 §152의3 2호)"
    elif income_over_40pct_median:
        can_separate, why = True, "기준 중위소득 40% 이상 + 독립 생계·주거 유지 — 분리 가능 (영 §152의3 3호)"
        flags.append("소득 측정기간은 법령 명문 없음 — 직전 확정 과세기간을 프록시로 쓰는 실무관행(F급). 취득세는 '직전 12개월' 명문 — 세목 분기")
    else:
        why = "30세 미만·미혼·소득요건 미충족 — 주소 분리해도 동일 세대로 봄"
    citations.append(_cite(why, "소득세법 시행령 §152의3", "B"))
    return {"동일세대": True, "분리가능": can_separate, "분리조건": why, "근거": citations, "플래그": flags}


def count_transfer_homes(items: list[dict]) -> dict:
    """트리② — 1세대1주택 비과세 판정용 주택수 산정 (소법 §88·§89, 영 §154~156의3 노드).

    items 각 원소: {
      "종류": "주택"|"조합원입주권"|"분양권"|"오피스텔",
      "사실상주거용": bool (오피스텔·겸용 판정 — 양도세는 공부 아닌 현황),
      "취득일": "YYYY-MM-DD" (분양권 2021-01-01 이후 취득분만 산입),
      "상속특례주택": bool (§155② 선순위 상속주택 — 별도세대 피상속인),
      "공동상속_소수지분": bool (§155③),
      "농어촌주택특례": bool (§155⑦),
      "등록임대_거주주택특례": bool (§155⑳ 장기임대 — 거주주택 비과세 판정 시 제외),
      "라벨": str,
    }
    """
    counted, details, flags = 0, [], []
    for it in items:
        kind = it.get("종류", "주택")
        label = it.get("라벨") or kind
        inc, why = True, "산입"
        if kind == "오피스텔" and not it.get("사실상주거용", False):
            inc, why = False, "업무용 오피스텔 — 주택 아님 (양도세는 사실상 용도, §88 정의)"
        elif kind == "주택" and it.get("사실상주거용") is False:
            inc, why = False, "사실상 주거용 아님(용도변경·근생 등) — 양도일 현재 현황 판정 (사례⑫)"
        elif kind == "분양권":
            acq = it.get("취득일")
            if acq and date.fromisoformat(acq) < RIGHT_COUNT_FROM:
                inc, why = False, "2021-01-01 전 취득 분양권 — 주택수 미산입 (소법 §88 10호 경과규정)"
            else:
                why = "분양권 산입 (2021 이후 취득, §88 10호)"
        elif it.get("상속특례주택"):
            inc, why = False, "선순위 상속주택 특례 — 일반주택 비과세 판정 시 제외 (영 §155②, 별도세대 피상속인·동일세대 배제)"
        elif it.get("공동상속_소수지분"):
            inc, why = False, "공동상속 소수지분 — 제외 (영 §155③)"
        elif it.get("농어촌주택특례"):
            inc, why = False, "농어촌주택 특례 — 제외 (영 §155⑦)"
        elif it.get("등록임대_거주주택특례"):
            inc, why = False, "장기임대 등록주택 — 거주주택 비과세 판정 시 제외 (영 §155⑳, 거주 2년 요건·사후관리 플래그)"
            flags.append(f"{label}: 거주주택 특례는 임대요건(등록 유지·5% 상한) 사후관리 위반 시 추징 — D급 확인 권장")
        if inc:
            counted += 1
        details.append({"항목": label, "산입": inc, "사유": why})
    return {
        "비과세판정_주택수": counted,
        "1세대1주택_간주가능": counted == 1,
        "항목별": details,
        "플래그": flags,
        "주의": "이 산정은 비과세(§89) 판정용 — 중과판정 주택수(영 §167의3~11: 지방 3억·기준시가 1억 등 별도 제외)와 다르다. 세목별 주택수 분리 원칙",
    }
