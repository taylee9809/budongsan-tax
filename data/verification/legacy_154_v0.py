# -*- coding: utf-8 -*-
"""judge_exemption_requirements 수정 전(v0) 스냅샷 — run#3(수정 전 상태) 재현 전용.

2026-08-24 트리④ 예규 회귀 검증에서 폐기된 구현. 없는 것:
  ① §154①5호를 pre_announce_contract_no_home 단일 boolean으로만 받아
     계약금 전액 지급·계약 당시 무주택 여부를 구분하지 못함
  ② 동일세대원 간 증여·상속의 지위 승계(원 계약자 지위 유지)
  ③ 자가건설·조합가입이 '매매계약'이 아니라는 구분
  ④ 비거주자가 체결한 상생임대차계약의 특례 배제
런타임에서 import 하지 말 것. 러너가 `--impl legacy_154_v0`일 때만 로드한다.
"""
from tax_judgment import HIGH_PRICE_HOME, _cite


def judge_exemption_requirements(
    is_one_household_one_home: bool,
    holding_years: float,
    residing_years: float,
    acquired_in_adjusted_area: bool,
    sale_price: int = 0,
    waiver_reason: str = "",
    sangsaeng_rental_ok: bool = False,
    pre_announce_contract_no_home: bool = False,
    acquisition_cause: str = "매매",
    is_usage_converted_after_contract: bool = False,
) -> dict:
    """트리④ — 1세대1주택 비과세 요건 판정 (소법 §89①3호·영 §154, 노드 N154 계열).

    입력은 트리①(세대)·트리②(주택수)의 출력을 전제: is_one_household_one_home.
    holding_years는 비과세용 보유기간(§95④ 준용 기산 — 장특공·세율 기산과 별개, B5).
    acquired_in_adjusted_area: '취득 당시' 조정대상지역 여부 — 현재 지정현황이 아니라
    취득시점 지정이력 기준(B2). 입주권·분양권 승계취득은 사용승인일 기준(대조 143346).
    waiver_reason: ""|건설임대5년거주|수용|해외이주2년|취학근무국외|부득이1년거주 (§154①1~3호).
    sangsaeng_rental_ok: 상생임대 3요건 충족(§155의3 — 거주요건만 배제, N155의3-1).
    pre_announce_contract_no_home: 조정 공고 전 매매계약+계약금+무주택(§154①5호 — 거주요건만 배제).
    acquisition_cause: 매매|증여|조합가입 — 5호는 '매매계약' 엄격해석(증여분양권·조합가입 배제, N154-1-5-문언).
    결과의 meets_exemption_requirements·과세대상비율을 judge_transfer_reliefs로 연결.
    """
    citations, flags = [], []
    if not is_one_household_one_home:
        return {"비과세성립": False, "사유": "양도일 현재 1세대1주택 아님(특례 간주 포함 판정은 count_transfer_homes 선행)",
                "근거": [_cite("1세대 1주택 + 보유 2년(취득당시 조정 시 거주 2년)", "소법 §89①3호·영 §154①", "A")],
                "플래그": ["다주택이면 중과 판정(count_heavy_homes)으로 분기"], "과세대상비율": 1.0}

    if is_usage_converted_after_contract:
        flags.append("B1: 매매계약 후 용도변경 양도 — 판정시점이 양도일이 아니라 매매계약일(N154-1-1), 시나리오 2개 검토")

    waivers = {"건설임대5년거주": "§154①1호(건설임대 임차일~양도일 세대전원 거주 5년↑)",
               "수용": "§154①2호가(사업인정고시 전 취득분 수용)",
               "해외이주2년": "§154①2호나(해외이주 — 출국 2년 내 양도)",
               "취학근무국외": "§154①2호다(취학·근무 1년↑ 국외거주 — 출국 2년 내)",
               "부득이1년거주": "§154①3호(1년↑ 거주 + 취학·근무·질병 부득이 사유)"}
    if waiver_reason:
        basis = waivers.get(waiver_reason)
        if not basis:
            return {"오류": f"waiver_reason 선택지: {list(waivers)}"}
        citations.append(_cite(f"보유·거주요건 배제 — {basis}", "영 §154① 단서", "B"))
        flags.append("배제사유 증빙(사업인정고시·이주신고·재학/재직증명 등)은 문서 정본 요구")
        hold_ok = reside_ok = True
    else:
        hold_ok = holding_years >= 2.0
        citations.append(_cite(f"보유 {holding_years}년(2년↑: {hold_ok}) — 기산 §95④ 준용, 멸실 재건축·동일세대 상속 통산(N154-8)", "영 §154①·⑤", "B"))
        if not hold_ok:
            flags.append("보유 2년 미만 — 단기세율 구간(1년↑2년 미만 주택 60%) 경고")
        reside_ok = True
        if acquired_in_adjusted_area:
            if sangsaeng_rental_ok:
                citations.append(_cite("상생임대주택 — 직전임대 1년6개월↑+5%↓ 인상 계약(2021-12-20~2026-12-31 체결)+임대 2년↑ → 거주기간 제한 배제", "영 §155의3①", "B"))
                flags.append("상생임대 특례적용신고서+계약서 2건 제출 요건(§155의3⑤) — 일몰 2026-12-31 감시")
            elif pre_announce_contract_no_home:
                if acquisition_cause != "매매":
                    reside_ok = residing_years >= 2.0
                    citations.append(_cite(f"§154①5호는 '매매계약' 한정 — {acquisition_cause}는 배제 불가(기재부 조세법령운용과-988·법규재산-2823), 거주 {residing_years}년(2년↑: {reside_ok})", "영 §154①5호 + 해석례", "D"))
                else:
                    citations.append(_cite("조정 공고 전 매매계약+계약금 지급+계약금지급일 무주택 — 거주요건 배제", "영 §154①5호", "B"))
            else:
                reside_ok = residing_years >= 2.0
                citations.append(_cite(f"취득 당시 조정대상지역 — 거주 {residing_years}년(2년↑: {reside_ok}, 주민등록표 기준·공동상속은 최장 상속인 기준)", "영 §154①·N154-6·N154-12", "B"))
                if not reside_ok:
                    flags.append("거주요건 대체 경로 검토: 상생임대(§155의3)·집행기준 89-154-3(세대원 일부 부득이 미거주 — D급)")
        else:
            citations.append(_cite("취득 당시 비조정대상지역 — 거주요건 없음(보유 2년만)", "영 §154①", "B"))
        flags.append("B2: '취득 당시' 지정 여부는 지정이력 기준 — 현재 지정현황으로 판정 금지, 승계 입주권·분양권은 사용승인일 기준(대조 143346)")

    qualifies = hold_ok and reside_ok
    ratio, table = 1.0, "표1"
    if qualifies:
        if sale_price > HIGH_PRICE_HOME:
            ratio = round((sale_price - HIGH_PRICE_HOME) / sale_price, 4)
            citations.append(_cite(f"고가주택(양도가 {sale_price:,} > 12억) — 과세대상 양도차익 비율 {ratio}", "소법 §89①3호·영 §160 (N95-3-1)", "A"))
        else:
            ratio = 0.0
        table = "표2" if residing_years >= 2.0 else "표1"
        if table == "표1":
            flags.append("거주 2년 미만이라 장특공 표2 불가(§159의4 입구) — 표1 최대 30%")
    flags.append("B5: 보유기간 3종 병존 — 비과세(§154)·장특공(§95④)·세율(§104②) 기산이 각각 다름, 단일 변수 사용 금지")

    return {"비과세성립": qualifies, "과세대상비율": ratio if qualifies else 1.0,
            "장특공표": table, "meets_exemption_requirements": qualifies,
            "근거": citations, "플래그": flags,
            "연계": "judge_transfer_reliefs(is_one_household_one_home=True, meets_exemption_requirements=비과세성립, ...) → calc_transfer_tax. 재건축 물건이면 트리③(judge_reconstruction_membership_transfer) 선행"}
