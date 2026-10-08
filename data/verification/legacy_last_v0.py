# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_business_dealer_status / judge_reconstruction_membership_transfer.

결함: ①재개발 관리처분 제한(§39②)의 경과규정 부재 — 법 14943호 부칙 §1·§2로 2018-01-24
시행 + '시행 후 최초로 사업시행인가를 신청하는 경우부터'인데 신청일 입력이 없어 구법 구역
(2018-01-24 전 신청)도 봉쇄로 오판 ②자영건설 판매를 일률 '양도소득'으로 안내 — 비주거
자영건설 판매는 영 §122① 명문의 부동산매매업, 주거 신축분양은 건설업(양도소득 아님).
"""
from tax_judgment import *          # noqa: F401,F403
from tax_judgment import _cite, _TRANSFEROR_EXCEPTIONS  # noqa: F401


def judge_business_dealer_status(
    acquisitions_in_period: int = 0,
    sales_in_period: int = 0,
    has_business_registration: bool = False,
    business_purpose_advertised: bool = False,
    is_self_built_sale: bool = False,
    is_residential_resale: bool = False,
) -> dict:
    """사업자성 스크리닝 — 부동산매매업(사업소득)인지 양도소득인지 (P0 Q0 축).

    acquisitions_in_period·sales_in_period: **1과세기간(부가세법상 6개월)** 중 취득·판매 건수.
    법문에 소득세법상 임계값이 없으므로 부가규칙 §2②2호(1회 이상 취득 + 2회 이상 판매)를
    스크리닝 기준으로만 쓰고, 최종 판단은 계속성·반복성 사실판단(판례)으로 남긴다.
    """
    hits, flags = [], []
    threshold_met = (acquisitions_in_period >= VAT_DEALER_ACQUIRE and sales_in_period >= VAT_DEALER_SELL)
    if threshold_met:
        hits.append(f"1과세기간 중 취득 {acquisitions_in_period}회 + 판매 {sales_in_period}회 — "
                    "부가규칙 §2②2호 기준 충족(1회 이상 취득·2회 이상 판매)")
    if business_purpose_advertised:
        hits.append("부동산 매매·중개를 사업목적으로 표방 — 부가규칙 §2②1호")
    if has_business_registration:
        hits.append("부동산매매업 사업자등록 보유")
    if is_self_built_sale:
        flags.append("자영건설 판매 — 비주거용은 부동산매매업(영 §122①), 주거용 신축분양은 "
                     "주거용 건물 개발·공급업으로 §64 비교과세 대상에서 제외")
    if is_residential_resale:
        hits.append("구입한 주거용 건물의 재판매 — 영 §122① 단서 괄호로 부동산매매업에 포함")

    if hits:
        verdict = "사업소득(부동산매매업) 가능성 높음"
        grade = "c(회색지대 — 사실판단 영역)"
    else:
        verdict = "양도소득으로 판단(스크리닝 기준 미충족)"
        grade = "c(회색지대 — 사실판단 영역)"

    flags.append("⚠️소득세법에는 계속성·반복성의 임계값이 없다 — 위 기준은 부가가치세법 시행규칙 근거의 "
                 "**스크리닝 전용**이며 소득세 과세 판정을 단정하지 않는다 (N부가규칙2-2)")
    if hits:
        flags.append("사업소득으로 보더라도 §64 비교과세로 중과세율이 살아난다 — calc_dealer_comparative_tax로 "
                     "두 안을 비교할 것 (N법64-1)")
        flags.append("부동산매매업자는 매매일이 속하는 달의 말일부터 2개월 내 토지등 매매차익 예정신고 의무 "
                     "(차손이어도 신고). 보유 2년 미만이면 단기세율 강제 (N법69-1)")
    flags.append("세율 체계가 통째로 갈리므로 출력 규약상 시나리오 2개 병기(양도소득 가정 / 사업소득 가정) + "
                 "차액을 리드스코어로 제시할 것")

    return {
        "판정": verdict,
        "스크리닝충족": bool(hits),
        "충족근거": hits,
        "신뢰등급": grade,
        "근거": [
            _cite("1과세기간 중 1회 이상 취득 + 2회 이상 판매", "부가가치세법 시행규칙 §2②2호 (N부가규칙2-2)", "C"),
            _cite("부동산매매업 정의(구입 주거용 건물 재판매 포함)", "소득세법 시행령 §122① (N영122-1)", "A"),
            _cite("계속성·반복성 종합 사실판단", "종합소득세(부동산) 판례 215건 (N판례-사업자성-1)", "E"),
        ],
        "플래그": flags,
    }


def judge_reconstruction_membership_transfer(
    project_type: str,
    in_speculation_overheated_zone: bool,
    association_established: bool = False,
    management_disposal_approved: bool = False,
    transfer_notice_done: bool = False,
    transferor_reason: str = "",
    owned_years: float = 0.0,
    resided_years: float = 0.0,
    decree_reason: str = "",
    is_partial_share_transfer: bool = False,
    is_one_plus_one_small: bool = False,
) -> dict:
    """트리③ — 재건축·재개발 조합원 지위양도 제한 판정 (도시정비법 §39②③·영 §37①③).

    투기과열지구에서 재건축=조합설립인가 후, 재개발=관리처분계획인가 후 양수자는 조합원 불가
    (§39②본문, '양수'는 매매·증여 포함/상속·이혼 제외). 탈락 시 매수인은 §39③→§73 준용
    손실보상 절차(협의→수용재결/매도청구) 대상. 세액 계산 전 매도가능성 선필터 — 외부대조
    ⑳(방배13 사례)에서 세무사도 놓친 관문.

    transfer_notice_done: 이전고시 완료 여부 — 완료+등기 후엔 완성 부동산 거래라 제한 실효
    (§86②·§88, 보정1). is_one_plus_one_small: 1+1 분양 소형 60㎡↓ 여부 — 이전고시 후에도
    3년 전매금지(§76①7호라목, N76-1-7라). is_partial_share_transfer: 지분 일부 양수 여부(R6).
    transferor_reason: ""|세대이전|상속주택이전|해외이주|지분형주택|공공재개발양도|
    1세대1주택_소유10년_거주5년|시행령예외(→decree_reason).
    """
    citations = [_cite("재건축=조합설립인가 후/재개발=관리처분인가 후 양수자 조합원 불가(증여 포함·상속·이혼 제외), 자격 불취득 시 §73 준용 손실보상", "도시정비법 §39②③", "A")]
    flags: list[str] = []

    if transfer_notice_done:
        flags.append("이전고시일~§88 등기 완료 사이엔 저당권 등 다른 등기 금지(§88③) — 등기 완료 후 거래 가능")
        if is_one_plus_one_small:
            return {"조합원지위승계가능": False,
                    "사유": "1+1 분양 소형(60㎡↓)은 이전고시일 다음 날부터 3년간 전매 금지 — 상속만 제외(이혼도 미제외)",
                    "근거": [_cite("60㎡ 이하로 공급받은 1주택은 이전고시일 다음 날부터 3년 전매·알선 금지", "도시정비법 §76①7호라목", "A")],
                    "플래그": flags + ["3년 경과 후 일반 매매 가능 — 이전고시일 확인해 데드라인 역산"]}
        return {"조합원지위승계가능": True,
                "사유": "이전고시 후 — 분양받을 자가 소유권 취득(§86②)해 완성 부동산 거래, 조합원 자격 무의미(제한 실효)",
                "근거": citations + [_cite("이전고시 다음 날 소유권 취득 → 등기 촉탁", "도시정비법 §86②·§88①", "A")], "플래그": flags}

    if not in_speculation_overheated_zone:
        return {"조합원지위승계가능": True, "사유": "투기과열지구 아님 — §39② 미적용",
                "근거": citations, "플래그": ["투기과열지구 지정은 상시 변동 — search_law(admrul)로 거래 시점 재확인 필수"]}

    if project_type == "재건축":
        trigger, basis = association_established, "§39②본문(재건축=조합설립인가 후)"
    elif project_type == "재개발":
        trigger, basis = management_disposal_approved, "§39②본문(재개발=관리처분계획인가 후)"
    else:
        return {"오류": f"project_type은 '재건축'|'재개발'만 지원: {project_type}"}
    if not trigger:
        return {"조합원지위승계가능": True, "사유": f"제한 미발동({basis} — 인가 전 자유 양도)",
                "근거": citations, "플래그": ["인가 절차 진행 중이면 창이 급격히 닫힘(P1) — 오금현대는 신청→인가 16일"]}
    citations.append(_cite("제한 발동", basis, "A"))

    def _fail() -> dict:
        f = list(flags)
        f.append("매수인은 조합원 자격 불가 → §39③에 따라 §73 준용 손실보상 절차(관리처분인가 후 협의 90일→수용재결/매도청구) 대상 — 모르고 매수하면 치명적 손실")
        f.append("대안 경로: 예외사유 개방 시점 역산(영 §37③ 데드라인) 또는 이전고시·등기 후 매도 대기(취득세 1회 추가·시세변동 트레이드오프)")
        if is_partial_share_transfer:
            f.append("R6: 지분 일부 양수 — §39③ 문언상 손실보상 대상이나(예외 없음) 기존 조합원 유지 구조에선 실무·전문가 판단 갈림 관찰(외부대조 ⑱, 판례·유권해석 미확보 D-) — 전문가 확인 권장")
        f.append("R5: 인가 후 지분 양수는 §39①3호 대표조합원 1명 강제 — 지분을 사도 입주권이 늘지 않음")
        return {"조합원지위승계가능": False, "사유": "예외사유 없음 — 매수인 조합원 자격 불가",
                "근거": citations, "플래그": f}

    if transferor_reason == "1세대1주택_소유10년_거주5년":
        own_ok, reside_ok = owned_years >= RECON_OWN_YEARS, resided_years >= RECON_RESIDE_YEARS
        citations.append(_cite(
            f"소유 {owned_years}년(10년↑:{own_ok}) · 거주 {resided_years}년(5년↑:{reside_ok} — 주민등록표 기준, 배우자·직계존비속 거주 합산·상속 시 피상속인 기간 합산)",
            "영 §37①", "B"))
        flags.append("전제 '1세대1주택자'의 세대는 §39①2호 자체 정의(법률혼+주민등록표 한정·사실혼 배제, 인가 후 세대분리 봉쇄) — 소법 §88과 다른 기준, judge_same_household로 세대주택수 선확정")
        if own_ok and reside_ok:
            return {"조합원지위승계가능": True, "사유": "1세대1주택 + 소유10년·거주5년 충족 (§39②4호)", "근거": citations, "플래그": flags}
        return _fail()

    if transferor_reason == "시행령예외":
        text = _DECREE_37_3.get(decree_reason)
        if not text:
            return {"오류": f"decree_reason 선택지: {list(_DECREE_37_3)}"}
        citations.append(_cite(text, "영 §37③", "B"))
        flags.append("사업지연 3종은 지연 3년+계속소유 3년 이중요건 — 각각 별개 충족 확인 (외부대조 ⑰ 검증)")
        flags.append("5호 경매 예외는 국가·지자체·금융기관 채무 한정 — 사인 간 강제경매는 문언상 불포함(쟁점플래그)")
        return {"조합원지위승계가능": True, "사유": text, "근거": citations, "플래그": flags}

    if transferor_reason in _TRANSFEROR_EXCEPTIONS:
        text, ho = _TRANSFEROR_EXCEPTIONS[transferor_reason]
        citations.append(_cite(text, f"도시정비법 §39②{ho}", "A"))
        flags.append("1~3호는 '세대원 전원' 요건 — 일부만 이전하면 탈락, 증빙(의료기관장 인정서·이주신고 등)은 문서 정본 요구")
        return {"조합원지위승계가능": True, "사유": text, "근거": citations, "플래그": flags}

    return _fail()
