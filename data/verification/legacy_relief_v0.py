# -*- coding: utf-8 -*-
"""중과·장특공 판정과 중과판정 주택수 수정 전(v0) 스냅샷 — run#14·15 재현 전용.

2026-08-24 종착점 회귀 검증에서 폐기된 구현. 없는 것:
  ① 중과세율 20/30%p의 시행일 — 법 17477호 부칙 §3으로 2021-06-01 이후 양도분부터고
     그 전은 10/20%p인데 현행 수치를 고정
  ② 한시배제(영 §167의3①12호의2)의 '보유 2년 이상' 전제 — 보유기간을 보지 않고 배제
  ③ 한시배제 나·다목(2026-05-09까지 계약+계약금, 4개월 내 양도)
  ④ 영 §167의3①12호 소형 신축주택 세부요건 — boolean 하나로만 받음
  ⑤ 2주택 전용 완화(영 §167의10①9호 기준시가 1억 이하) — 계열 구분 없음
런타임에서 import 하지 말 것. 러너가 `--impl legacy_relief_v0`일 때만 로드한다.
"""
from tax_judgment import (HEAVY_LOCAL_PRICE_LIMIT, HIGH_PRICE_HOME,
                          TEMP_EXCLUSION_SALE_DEADLINE, _cite)


def _table1_rate(holding_years: float) -> float:
    if holding_years < 3:
        return 0.0
    return min(0.30, 0.02 * int(holding_years))


def _table2_rate(holding_years: float, residing_years: float) -> float:
    hold = 0.0 if holding_years < 3 else min(0.40, 0.04 * int(holding_years))
    if residing_years >= 3:
        res = min(0.40, 0.04 * int(residing_years))
    elif residing_years >= 2 and holding_years >= 3:
        res = 0.08
    else:
        res = 0.0
    return hold + res


def judge_transfer_reliefs(is_one_household_one_home: bool, holding_years: float,
                           residing_years: float, sale_price: int,
                           adjusted_at_sale: bool = False, heavy_home_count: int = 1,
                           sale_date: str = "", meets_exemption_requirements: bool = True) -> dict:
    """양도세 특례 판정 오케스트레이터 (노드 N95-2-1·N95-2-2·N159의4-1·N104-7-1·N160-1).

    반환값을 calc_transfer_tax 인자(long_term_deduction_rate·surcharge_rate)로 연결.
    - is_one_household_one_home: 트리①·②의 출력(비과세 특례 간주 포함)
    - heavy_home_count: 중과판정 주택수 (영 §167의3~11 제외 적용 후)
    - meets_exemption_requirements: 보유 2년(+취득당시 조정이면 거주 2년) 충족 여부
    """
    flags, citations = [], []
    surcharge = 0.0
    heavy = False

    if adjusted_at_sale and heavy_home_count >= 2 and not is_one_household_one_home:
        heavy = True
        surcharge = 0.2 if heavy_home_count == 2 else 0.3
        citations.append(_cite(f"조정지역 {heavy_home_count}주택 중과 +{int(surcharge*100)}%p", "소득세법 §104⑦", "A"))
        if sale_date and sale_date <= TEMP_EXCLUSION_SALE_DEADLINE:
            heavy, surcharge = False, 0.0
            flags.append(f"한시배제: {sale_date} ≤ {TEMP_EXCLUSION_SALE_DEADLINE} 양도 — 중과 제외(보유 2년↑ 전제, 영 §167의3①12호의2 가목). 계약분 유예·연장지역은 나·다목 별도 확인")

    exempt, taxable_ratio = False, 1.0
    if is_one_household_one_home and meets_exemption_requirements:
        if sale_price <= HIGH_PRICE_HOME:
            exempt = True
            citations.append(_cite("1세대1주택 비과세 (12억 이하)", "소득세법 §89①3호", "A"))
        else:
            taxable_ratio = (sale_price - HIGH_PRICE_HOME) / sale_price
            citations.append(_cite(f"고가주택 안분: 과세 양도차익 = 전체차익 × {taxable_ratio:.4f}", "영 §160 (양도가액−12억)/양도가액", "B"))

    if heavy:
        ltsd = 0.0
        citations.append(_cite("중과대상 = 장특공 원천 배제", "소득세법 §95② (§104⑦ 자산 제외 — 미등기와 동급)", "A"))
    elif is_one_household_one_home and residing_years >= 2:
        ltsd = _table2_rate(holding_years, residing_years)
        citations.append(_cite(f"표2 장특공 {ltsd:.0%} (보유+거주, 최대 80%)", "소득세법 §95② 표2·영 §159의4 (거주 2년↑ 입구)", "A"))
    else:
        ltsd = _table1_rate(holding_years)
        if is_one_household_one_home and residing_years < 2:
            flags.append("거주 2년 미만 — 고가 1주택이라도 표2 불가, 표1(최대 30%)로 강등 (영 §159의4)")
        citations.append(_cite(f"표1 장특공 {ltsd:.0%} (보유 3년↑, 최대 30%)", "소득세법 §95② 표1", "A"))

    if holding_years < 2 and not exempt:
        flags.append("보유 2년 미만 — 단기세율(주택 70%/60%)과 비교과세: calc_transfer_tax를 두 번 호출해 큰 세액 채택 (§104① 후단·⑦ 후단)")

    return {
        "비과세": exempt,
        "과세대상_양도차익_비율": round(taxable_ratio, 6),
        "중과여부": heavy,
        "surcharge_rate": surcharge,
        "long_term_deduction_rate": round(ltsd, 4),
        "플래그": flags,
        "근거": citations,
        "주의": "세대·주택수 판정(트리①②)은 이 함수의 입력 — 여기서 판정하지 않음. 보유기간은 용도별 상이(비과세·장특공·세율) — N95-4-1",
    }


# ── 3. 가족 간 차용 / 무상대출 스크리닝 ──────────────────────────────────────


def count_heavy_homes(items: list[dict]) -> dict:
    """양도세 중과판정 주택수 산정 (영 §167의3②·167의4②·167의11② 불산입 자동 적용).

    items 원소: {"종류": 주택|조합원입주권|분양권, "기준시가": 원(입주권=종전주택가·분양권=공급가),
    "지방소재": bool(수도권·광역시·특별자치시 밖 — 군·읍·면 포함), "인구감소등_12호": bool,
    "라벨": str}. 반환 주택수를 judge_transfer_reliefs의 heavy_home_count로 연결.
    """
    counted, details = 0, []
    for it in items:
        label = it.get("라벨") or it.get("종류", "주택")
        inc, why = True, "산입"
        if it.get("인구감소등_12호"):
            inc, why = False, "§167의3①12호(소형신축·인구감소지역 등) — 불산입"
        elif it.get("지방소재") and int(it.get("기준시가", 0)) <= HEAVY_LOCAL_PRICE_LIMIT:
            inc, why = False, "지방(수도권·광역시·특자시 밖) + 기준시가 3억 이하 — 불산입 (영 §167의3①1호·167의4②·167의11②)"
        if inc:
            counted += 1
        details.append({"항목": label, "산입": inc, "사유": why})
    flags = ["2주택 중과 판정이면 추가 완화 별도 확인: 기준시가 1억 이하(정비구역 제외)·부득이 사유 이전용 3억 이하 (영 §167의10①3·9호 — 3주택엔 없음)",
             "양도 주택 자체의 중과 제외(장기임대·상속 5년·한시배제·비과세특례 주택 등)는 judge_transfer_reliefs의 sale_date·별도 확인",
             "혼인 5년 완충(§167의3⑨·167의4⑤)은 3주택 계열만 — 해당 시 배우자 보유분 차감"]
    return {"중과판정_주택수": counted, "항목별": details, "플래그": flags,
            "주의": "비과세 판정용 주택수(count_transfer_homes)와 별개 — 같은 세대가 두 값이 다를 수 있음"}
