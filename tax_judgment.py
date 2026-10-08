# -*- coding: utf-8 -*-
"""세금 판정 레이어 — 법문 노드(data/legal_nodes/*.json)의 기계판정 가능 규칙을 실행 코드로 연결.

설계 원칙 (⚖️ 법문→알고리즘 원장):
- 계산기(server.py calc_*)는 산식만, 이 모듈은 그 앞단의 판정(세율·공제·특례)을 담당한다.
- 모든 판정 결과에 근거(노드 id + 조문)와 플래그(A~C=결정적 / D~F=쟁점)를 붙인다.
- 법정 상수는 "개정일 감시부 상수"로 둔다 — REVISION_WATCH의 개정일이 바뀌면 재검증.
  (세율 하드코딩 금지 원칙의 절충안 — 🧮 계산기 검증 §5)
"""
from __future__ import annotations

from datetime import date, timedelta

# ── 개정일 감시부 상수 (🔔 검증상수 레지스트리와 동기) ─────────────────────
REVISION_WATCH = {
    "취득세_저가주택": {"값": "수도권 1억 / 비수도권 2억", "근거": "지방세법 시행령 §28의2 1호", "확인": "2026-08-17"},
    "고가주택": {"값": "12억", "근거": "소득세법 §89①3호·영 §160", "확인": "2026-08-17"},
    "한시배제": {"값": "2026-05-09 양도분", "근거": "영 §167의3①12호의2 등 3곳", "확인": "2026-08-17"},
    "적정이자율": {"값": "연 4.6%", "근거": "법인세법 시행규칙 §43②(1,000분의 46)", "확인": "2026-08-17"},
    "자금조달계획서": {"값": "6억/규제지역", "근거": "거래신고령 별표 1 (2025-12-09 개정)", "확인": "2026-08-17"},
    "간주임대료_이자율": {"값": "연 3.1%(1천분의 31) — 2025·2026 귀속. 귀속연도별 이력은 "
                            "DEPOSIT_INTEREST_RATE_BY_YEAR (2024년 3.5%·2023년 2.9%·2021~22년 1.2%)",
                      "근거": "소득세법 시행규칙 §23① (3.1%는 2025-03-21 개정으로 설정. "
                            "2026-01-02 개정은 부처명 변경으로 요율 무변동) + 각 개정 부칙 경과조치",
                      "확인": "2026-08-21"},
    "간주임대료_요건": {"값": "3주택+3억 초과 / 2주택(12억 초과 주택만)+12억 초과는 2026 과세기간부터",
                   "근거": "소법 §25①1·2호·영 §53①, 부칙 제19933호 §1제1호", "확인": "2026-08-20"},
    "주택임대_분리과세": {"값": "수입 2천만 이하·14%·경비 50%(등록 60%)·공제 200만(등록 400만)",
                   "근거": "소법 §14③7호·§64의2①②", "확인": "2026-08-20"},
    "소형주택_주택수제외": {"값": "40㎡ 이하 and 기준시가 2억 이하 — 일몰 2026-12-31",
                    "근거": "소법 §25① 단서", "확인": "2026-08-20"},
    "감면_종합한도": {"값": "일반 과세기간 1억·5년 2억 / 공익수용 과세기간 2억·5년 3억",
               "근거": "조특법 §133①② (②는 2025-03-14 신설)", "확인": "2026-08-20"},
    "소형주택임대_감면율": {"값": "1호 30%(장기일반 75%)·2호↑ 20%(50%), 일몰 2028-12-31",
                  "근거": "조특법 §96① (2025-12-23 개정)", "확인": "2026-08-20"},
    "자경농지_소득제외": {"값": "사업소득금액+총급여 3,700만원 이상 과세기간은 경작기간 제외",
                  "근거": "조특법 시행령 §66⑭", "확인": "2026-08-20"},
    "세컨드홈_특례": {"값": "농어촌주택 3억(한옥 4억)·취득 ~2028-12-31 / 인구감소지역 9억(수도권·관심 4억)·취득 ~2026-12-31",
               "근거": "조특법 §99의4·§71의2·영 §68의2", "확인": "2026-08-20"},
    "생애최초_취득세감면": {"값": "가액 12억 이하, 한도 300만(소형·인구감소지역)/200만, 일몰 2028-12-31",
                   "근거": "지특법 §36의3 (2025-12-31 개정)", "확인": "2026-08-20"},
}

LOW_PRICE_HOME_LIMIT_CAPITAL = 100_000_000       # 취득세 저가주택 수도권 (영 §28의2 1호가목)
LOW_PRICE_HOME_LIMIT_NONCAPITAL = 200_000_000    # 취득세 저가주택 비수도권 (동 나목)
OFFICETEL_COUNT_LIMIT = 100_000_000              # 오피스텔 주택수 산입 기준 (영 §28의4⑥4호)
HIGH_PRICE_HOME = 1_200_000_000                  # 고가주택 (소법 §89①3호)
FAIR_INTEREST_RATE = 0.046                       # 적정이자율 (법인규칙 §43②)
LOAN_GIFT_THRESHOLD = 10_000_000                 # 무상대출 기준금액 (상증령 §31의4②)
FUND_PLAN_PRICE_LIMIT = 600_000_000              # 자금조달계획서 비규제 6억 (별표 1 3호)
TEMP_EXCLUSION_SALE_DEADLINE = "2026-05-09"      # 중과 한시배제 (가목 기준)


def _cite(rule: str, basis: str, grade: str = "B") -> dict:
    return {"규칙": rule, "근거": basis, "등급": grade}


# ── 1. 취득세: 주택수 산정 → 세율·부가세 판정 ──────────────────────────────
# ── 취득세 주택수·중과 경과규정 상수 ────────────────────────────────────────
_ACQ_LOCAL_2E_FROM = date(2025, 1, 2)     # 영 35477호 부칙 §2 — 이후 취득분부터 비수도권 저가 2억
_ACQ_SMALL_OFFI_FROM = date(2024, 1, 10)  # 1.10 대책 소형 오피스텔 특례 시작 (영 §28의4⑥8·9호)
_ACQ_SMALL_OFFI_TO = date(2025, 12, 31)   # 〃 종료
_ACQ_SMALL_OFFI_AREA = 60.0               # 전용 60㎡ 이하
_ACQ_SMALL_OFFI_PRICE_CAPITAL = 600_000_000    # 수도권 6억 이하
_ACQ_SMALL_OFFI_PRICE_LOCAL = 300_000_000      # 비수도권 3억 이하
GIFT_HEAVY_STD_VALUE = 300_000_000        # 무상취득 중과 기준 시가표준액 (영 §28의6①)


def _acq_low_price_limit(is_capital: bool, acquire: date | None) -> tuple[int, str]:
    """저가주택 기준액 — 비수도권은 취득일로 1억/2억이 갈린다."""
    if is_capital:
        return LOW_PRICE_HOME_LIMIT_CAPITAL, "수도권 1억"
    if acquire is None or acquire >= _ACQ_LOCAL_2E_FROM:
        return LOW_PRICE_HOME_LIMIT_NONCAPITAL, "비수도권 2억(2025-01-02 이후 취득분)"
    return LOW_PRICE_HOME_LIMIT_CAPITAL, "비수도권 1억(2025-01-02 전 취득분 — 완화 전)"


def count_acquisition_homes(items: list[dict], acquire_date: str | None = None) -> dict:
    """취득세 세대 주택수 산정 (지방세법 시행령 §28의4, 노드 N28-4-1~6).

    items 각 원소: {
      "종류": "주택"|"조합원입주권"|"주택분양권"|"오피스텔"|"부속토지",
      "시가표준액": int,                  # 지분·부속토지만이면 전체 기준 (영 §28의2 1호)
      "수도권": bool,
      "정비구역": bool,                   # 저가주택 제외의 예외 (재개발 딱지 차단)
      "상속개시_5년내": bool,             # ⑥3호
      "혼전분양권_배우자혼전주택": bool,   # ⑥6호 혼인 완충
      "전용면적": float,                  # ⑥8·9호 소형 오피스텔 (60㎡ 이하)
      "취득당시가액": int,                # 〃 (수도권 6억 / 비수도권 3억 이하)
      "신축최초유상승계일": "YYYY-MM-DD",  # 〃 2024-01-10~2025-12-31
      "라벨": str (선택),
    }
    acquire_date: 이번 취득의 취득일 — 비수도권 저가주택 기준이 2025-01-02를 경계로
      1억↔2억으로 갈리므로(영 35477호 부칙 §2) 과거 취득분 판정에는 반드시 넣을 것.
    반환: 산입 주택수 + 항목별 판정과 근거. 세대내 공동소유 1개 간주(④)는 호출자가
    같은 물건을 1개로 넣는 것으로 처리.
    """
    acq = date.fromisoformat(acquire_date) if acquire_date else None
    counted, details = 0, []
    for it in items:
        kind = it.get("종류", "주택")
        std = int(it.get("시가표준액", 0))
        label = it.get("라벨") or kind
        excluded, why = False, None
        if it.get("상속개시_5년내"):
            excluded, why = True, "상속 후 5년 내 — 주택수 제외 (영 §28의4⑥3호)"
        elif it.get("혼전분양권_배우자혼전주택"):
            excluded, why = True, "혼전 분양권으로 취득 시 배우자 혼전 주택 제외 (영 §28의4⑥6호 — 혼인 후 취득 분양권에는 불가)"
        elif kind == "부속토지":
            if std and std <= LOW_PRICE_HOME_LIMIT_CAPITAL:
                excluded, why = True, ("시가표준액 1억 이하 부속토지만 소유 — 제외 "
                                       "(영 §28의4⑥5호, 부동산세제과-3435)")
        elif kind == "오피스텔":
            if std <= OFFICETEL_COUNT_LIMIT:
                excluded, why = True, "오피스텔 시가표준 1억 이하 — 제외 (영 §28의4⑥4호)"
            else:
                small, note = _is_small_officetel(it)
                if small:
                    excluded, why = True, note
        elif kind == "주택" and not it.get("정비구역"):
            limit, label_limit = _acq_low_price_limit(bool(it.get("수도권")), acq)
            if std and std <= limit:
                excluded, why = True, (f"저가주택({label_limit} 이하) — 제외 "
                                       "(영 §28의2 1호·§28의4⑥1호, 영 35477호 부칙 §2)")
        if not excluded:
            counted += 1
        details.append({"항목": label, "산입": not excluded, "사유": why or "산입 (영 §28의4①: 주택+입주권+분양권+오피스텔)"})
    return {
        "산입_주택수": counted,
        "항목별": details,
        "주의": [
            "분양권·입주권에 의한 주택 취득의 주택수 판정 시점은 잔금일이 아니라 권리 취득일(직접 분양은 분양계약일, 전매 다중취득은 가장 빠른 날) — 영 §28의4① 후단",
            "동시 2개 이상 취득 시 순서는 납세자 선택(③) — 시나리오 비교 대상",
        ],
    }


def _is_small_officetel(it: dict) -> tuple[bool, str]:
    """1.10 대책 소형 오피스텔 주택수 제외 (영 §28의4⑥8·9호)."""
    d = it.get("신축최초유상승계일") or it.get("유상승계취득일")
    area, price = it.get("전용면적"), int(it.get("취득당시가액", 0) or 0)
    if not (d and area is not None and price):
        return False, ""
    dt = date.fromisoformat(d)
    if not (_ACQ_SMALL_OFFI_FROM <= dt <= _ACQ_SMALL_OFFI_TO):
        return False, ""
    if area > _ACQ_SMALL_OFFI_AREA:
        return False, ""
    cap = _ACQ_SMALL_OFFI_PRICE_CAPITAL if it.get("수도권") else _ACQ_SMALL_OFFI_PRICE_LOCAL
    if price > cap:
        return False, ""
    return True, (f"1.10 대책 소형 오피스텔 — 전용 {area}㎡(60 이하) + 취득가액 {price:,}원"
                  f"({'수도권 6억' if it.get('수도권') else '비수도권 3억'} 이하) + "
                  f"{d} 최초 유상승계 → 주택수 제외 (영 §28의4⑥8·9호, 일몰 2026-12-31)")


def judge_acq_temporary_two_homes(new_acquire_date: str, prev_disposal_date: str | None,
                                  prev_disposal_kind: str = "매각",
                                  disposal_to_same_household: bool = False) -> dict:
    """취득세 일시적 2주택 판정 (영 §28의5).

    양도세 §155①과 별개다 — 1년 경과 요건이 없고, 종전 '주택등'에 입주권·분양권·오피스텔이
    포함되며, 기간은 3년이다.
    '처분'은 취득에 대비되는 개념 — 매각·증여 등으로 **타인에게 새로운 취득이 발생**하거나
    멸실로 지배권을 상실하는 것. 상속으로 소유권을 잃은 것도 처분이고(조심 2025지1039),
    **동일 세대원에게 이전한 것은 세대 주택수가 그대로여서 처분이 아니다**
    (행안부 2026-01-23, 부동산세제과-1190).
    취득 사유(이사·학업·취업·직장이전)는 예시일 뿐이고 신규주택 실거주·전입은 요건이 아니다
    (부동산세제과-3728).
    """
    n = date.fromisoformat(new_acquire_date)
    deadline = _add_years(n, 3)
    cites = [_cite(f"신규 취득 {new_acquire_date} + 3년 = {deadline.isoformat()} 내 종전 주택등 처분",
                   "영 §28의5① (양도세 §155①과 달리 1년 경과 요건 없음)", "A")]
    flags = ["취득 사유는 예시 — 임대목적 취득도 가능하고 신규주택 전입은 요건이 아니다"
             "(부동산세제과-3728)"]
    if not prev_disposal_date:
        return {"일시적2주택": None, "처분데드라인": deadline.isoformat(),
                "근거": cites, "플래그": flags + ["종전 주택등 처분(예정)일 미입력 — 판정 보류"]}

    if disposal_to_same_household:
        cites.append(_cite("동일 세대원에게 이전 — 세대 주택수에 변화가 없어 '처분'이 아니다",
                           "행안부 2026-01-23 · 부동산세제과-1190", "A"))
        return {"일시적2주택": False, "처분데드라인": deadline.isoformat(),
                "처분인정": False, "근거": cites, "플래그": flags}

    s = date.fromisoformat(prev_disposal_date)
    in_time = s <= deadline
    cites.append(_cite(
        f"{prev_disposal_kind}로 {prev_disposal_date} 처분 — 데드라인 {deadline.isoformat()} "
        f"{'이내 충족' if in_time else '경과·미충족'}",
        "영 §28의5① · 상속도 처분에 해당(조심 2025지1039)", "A"))
    return {"일시적2주택": in_time, "처분데드라인": deadline.isoformat(),
            "처분인정": True, "근거": cites, "플래그": flags}


def judge_acquisition_rate(counted_homes_including_new: int, in_adjusted_area: bool,
                           is_corporation: bool = False,
                           exclusive_area_m2: float | None = None,
                           is_gift: bool = False, gift_std_value: int = 0,
                           gift_from_one_home_household_to_family: bool = False,
                           temporary_two_homes: bool | None = None) -> dict:
    """취득세 세율 + 부가세 2종 실효율 판정 (지방세법 §13의2·§151, 농특세법 §5 — 노드 N13-2-1·N-LT151-2·N-NT5-6).

    counted_homes_including_new: 취득 주택 포함 산입 주택수 (count_acquisition_homes 출력 + 1 아님 — 포함해서 전달)
    is_gift: 무상취득(증여) — 조정대상지역 + 시가표준액 3억 이상이면 12% 중과
      (법 §13의2②·영 §28의6①). 1세대1주택자 소유 주택을 배우자·직계존비속이 무상취득하면
      제외(gift_from_one_home_household_to_family, 영 §28의6②1호).
    temporary_two_homes: 영 §28의5 일시적 2주택 해당 여부 — True면 §13의2①2호 중과에서 빠진다.
      judge_acq_temporary_two_homes()의 '일시적2주택' 값을 그대로 넘길 것.
    반환 세율은 그대로 calc_acquisition_tax 인자로 사용 가능.
    """
    n = counted_homes_including_new
    if is_gift:
        heavy_gift = (in_adjusted_area and gift_std_value >= GIFT_HEAVY_STD_VALUE
                      and not gift_from_one_home_household_to_family)
        why = ("조정대상지역 + 시가표준액 3억 이상 무상취득" if heavy_gift else
               "1세대1주택자 소유 주택을 배우자·직계존비속이 무상취득 — 중과 제외"
               if gift_from_one_home_household_to_family else
               "무상취득이나 조정대상지역·3억 기준 미충족 — 표준세율")
        return {
            "판정": f"무상취득 {'12% 중과' if heavy_gift else '표준 3.5%'} — {why}",
            "취득세율": 0.12 if heavy_gift else 0.035,
            "중과여부": heavy_gift,
            "지방교육세율(과표대비)": 0.004 if heavy_gift else 0.003,
            "농특세율(과표대비)": 0.0 if (exclusive_area_m2 is not None and exclusive_area_m2 <= 85)
                              else (0.010 if heavy_gift else 0.002),
            "농특세비고": "전용 85㎡ 이하 서민주택 농특세 비과세" if
                       (exclusive_area_m2 is not None and exclusive_area_m2 <= 85) else "전용 85㎡ 초과 가정",
            "근거": [_cite("조정대상지역 일정가액(시가표준 3억) 이상 무상취득 12%", "지방세법 §13의2②·영 §28의6①", "A"),
                   _cite("1세대1주택자→배우자·직계존비속 무상취득은 제외", "법 §13의2② 단서·영 §28의6②1호", "A")],
            "플래그": ["증여 취득은 유상거래 중과(§13의2①)와 별개 트랙 — 주택수 매트릭스가 아니라 가액 기준"],
        }
    if temporary_two_homes:
        return {
            "판정": "일시적 2주택 — 중과 배제(영 §28의5)",
            "취득세율": "1~3% (6~9억 사잇공식은 호출자 계산 — §11①8호)",
            "중과여부": False,
            "지방교육세율(과표대비)": "취득세율×50%×20% (0.1~0.3%)",
            "농특세율(과표대비)": 0.0 if (exclusive_area_m2 is not None and exclusive_area_m2 <= 85) else 0.002,
            "농특세비고": "전용 85㎡ 이하면 0",
            "근거": [_cite("일시적 2주택은 §13의2①2호 중과 대상에서 제외", "지방세법 §13의2①2호 괄호·영 §28의5", "A")],
            "플래그": ["3년 내 종전 주택등 미처분 시 중과세율로 추징 — 사후관리 대상"],
        }
    if is_corporation:
        rate, tier = 0.12, "법인 12% (§13의2①1호)"
    elif in_adjusted_area:
        rate, tier = (None, "1~3% 사잇공식") if n <= 1 else (0.08, "조정 2주택 8%") if n == 2 else (0.12, "조정 3주택↑ 12%")
    else:
        rate, tier = (None, "1~3% 사잇공식") if n <= 2 else (0.08, "비조정 3주택 8%") if n == 3 else (0.12, "비조정 4주택↑ 12%")

    heavy = rate in (0.08, 0.12)
    if heavy:
        edu = 0.004  # (4%−2%)×20% 고정 — §151①1호나목
        rural = 0.006 if rate == 0.08 else 0.010  # (2%+가산)×10% — 농특세법 §5①6호
    else:
        edu = None   # 취득세율×50%×20% — 세율 확정 후 계산 (1~3% 구간)
        rural = 0.002
    if exclusive_area_m2 is not None and exclusive_area_m2 <= 85:
        rural = 0.0
        rural_note = "전용 85㎡ 이하 서민주택 — 농특세 비과세 (농특세법 §4 9·11호·영 §4⑤)"
    else:
        rural_note = "전용면적 미확인 시 과세 가정 — 85㎡ 이하면 0"

    return {
        "판정": tier,
        "취득세율": rate if rate else "1~3% (6~9억 사잇공식은 호출자 계산 — §11①8호)",
        "중과여부": heavy,
        "지방교육세율(과표대비)": edu if edu is not None else "취득세율×50%×20% (0.1~0.3%)",
        "농특세율(과표대비)": rural,
        "농특세비고": rural_note,
        "근거": [
            _cite("중과 매트릭스", "지방세법 §13의2① (조정2/비조정3=8%, 조정3·법인=12%)", "A"),
            _cite("중과 시 지방교육세 0.4% 고정", "지방세법 §151①1호나목", "A"),
            _cite("농특세 0.2/0.6/1.0%", "농특세법 §5①6호 (표준세율 2% 치환+중과가산 유지)", "A"),
        ],
        "플래그": ["일시적 2주택(영 §28의5: 종전 주택등 1개+3년 내 처분, 1년 경과 요건 없음) 해당 시 중과 배제 — 별도 확인"] if heavy else [],
    }



def judge_acquisition_homes_and_rate(
        homes: list[dict], in_adjusted_area: bool,
        is_corporation: bool = False, exclusive_area_m2: float | None = None,
        acquire_date: str | None = None,
        prev_disposal_date: str | None = None, prev_disposal_kind: str = "매각",
        disposal_to_same_household: bool = False, new_home_for_rental: bool = False,
        is_gift: bool = False, gift_std_value: int = 0,
        gift_from_one_home_household_to_family: bool = False) -> dict:
    """취득세 주택수 산정 + 일시적 2주택 + 세율 판정 결합 (server.py 래퍼가 그대로 부른다).

    acquire_date는 비수도권 저가주택 기준(1억↔2억)과 일시적 2주택 기산에 모두 쓰인다.
    new_home_for_rental은 판정을 바꾸지 않는다 — 임대목적 취득도 일시적 2주택이 되기 때문에
    입력으로만 받아 근거에 남긴다(부동산세제과-3728).
    """
    counting = count_acquisition_homes(homes, acquire_date)
    temp = None
    if acquire_date and (prev_disposal_date or disposal_to_same_household):
        temp = judge_acq_temporary_two_homes(
            acquire_date, prev_disposal_date, prev_disposal_kind, disposal_to_same_household)
    rate = judge_acquisition_rate(
        counting["산입_주택수"], in_adjusted_area, is_corporation, exclusive_area_m2,
        is_gift, gift_std_value, gift_from_one_home_household_to_family,
        temp["일시적2주택"] if temp else None)
    if new_home_for_rental and temp:
        temp["플래그"].append("신규주택을 임대목적으로 취득 — 일시적 2주택 판정에 영향 없음")
    return {"산입_주택수": counting["산입_주택수"],
            "취득세율": rate.get("취득세율"), "중과여부": rate.get("중과여부"),
            "판정": rate.get("판정"),
            "농특세율(과표대비)": rate.get("농특세율(과표대비)"),
            "일시적2주택": temp["일시적2주택"] if temp else None,
            "주택수_산정": counting, "세율_판정": rate, "일시적2주택_판정": temp}


# ── 2. 양도세: 비과세·중과·장특공·고가주택 판정 ────────────────────────────
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


# ── 중과세율·한시배제 경과규정 ───────────────────────────────────────────────
_HEAVY_RATE_UP_FROM = date(2021, 6, 1)   # 법 17477호 부칙 §3 — 이후 양도분 20/30%p (그 전 10/20%p)
# 한시배제는 창(窓)이다 — 끝만 보고 시작을 안 보면 그 전 양도분까지 소급 배제된다.
_TEMP_EXCL_FROM = date(2022, 5, 10)      # 영 32654호 부칙 §4 — 2022-05-10 이후 양도분부터 적용
_TEMP_EXCL_CONTRACT_MONTHS = 4           # 영 §167의3①12호의2 다목 — 계약 후 양도기한(일부 지역 6개월)


def _heavy_surcharge(homes: int, sale: date | None) -> tuple[float, str]:
    """중과 가산세율 — 양도일로 10/20%p ↔ 20/30%p가 갈린다."""
    if sale is not None and sale < _HEAVY_RATE_UP_FROM:
        return (0.1 if homes == 2 else 0.2), \
            "구 법 §104⑦ — 2021-06-01 전 양도분은 2주택 +10%p / 3주택 +20%p"
    return (0.2 if homes == 2 else 0.3), \
        "법 §104⑦(2020.8.18 개정, 17477호 부칙 §3) — 2021-06-01 이후 양도분 2주택 +20%p / 3주택 +30%p"


def _temp_exclusion(sale: date | None, holding_years: float, contract: date | None,
                    deposit_received: bool, months: int) -> tuple[bool, str]:
    """중과 한시배제 (영 §167의3①12호의2) — 보유 2년 이상이 대전제."""
    if sale is None:
        return False, ""
    if sale < _TEMP_EXCL_FROM:
        return False, (f"한시배제 신설 전 양도({sale.isoformat()} < {_TEMP_EXCL_FROM.isoformat()}) "
                       "— 영 32654호 부칙 §4로 2022-05-10 이후 양도분부터 적용된다")
    if holding_years < 2:
        return False, ("한시배제는 '보유기간 2년 이상인 주택'이 전제 — 보유 "
                       f"{holding_years}년이라 대상 아님 (영 §167의3①12호의2 각 호 외의 부분)")
    if sale <= date.fromisoformat(TEMP_EXCLUSION_SALE_DEADLINE):
        return True, (f"{sale.isoformat()} ≤ {TEMP_EXCLUSION_SALE_DEADLINE} 양도 — 중과 한시배제 "
                      "(영 §167의3①12호의2 가목)")
    if contract and deposit_received and contract <= date.fromisoformat(TEMP_EXCLUSION_SALE_DEADLINE):
        limit = _add_months(contract, months)
        if sale <= limit:
            return True, (f"{contract.isoformat()} 계약+계약금 수령 후 {months}개월 내"
                          f"({limit.isoformat()}까지) 양도 — 한시배제 (영 §167의3①12호의2 나·다목)")
        return False, (f"계약은 기한 내({contract.isoformat()})이나 양도가 {months}개월을 넘겼다 "
                       f"— 기한 {limit.isoformat()}")
    return False, ""


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    last = [31, 29 if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0 else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def judge_transfer_reliefs(is_one_household_one_home: bool, holding_years: float,
                           residing_years: float, sale_price: int,
                           adjusted_at_sale: bool = False, heavy_home_count: int = 1,
                           sale_date: str = "", meets_exemption_requirements: bool = True,
                           contract_date: str = "", deposit_received: bool = False,
                           contract_months_limit: int = _TEMP_EXCL_CONTRACT_MONTHS) -> dict:
    """양도세 특례 판정 오케스트레이터 (노드 N95-2-1·N95-2-2·N159의4-1·N104-7-1·N160-1).

    반환값을 calc_transfer_tax 인자(long_term_deduction_rate·surcharge_rate)로 연결.
    - is_one_household_one_home: 트리①·②의 출력(비과세 특례 간주 포함)
    - heavy_home_count: 중과판정 주택수 (영 §167의3~11 제외 적용 후)
    - meets_exemption_requirements: 보유 2년(+취득당시 조정이면 거주 2년) 충족 여부
    """
    flags, citations = [], []
    surcharge = 0.0
    heavy = False

    s = date.fromisoformat(sale_date) if sale_date else None
    if adjusted_at_sale and heavy_home_count >= 2 and not is_one_household_one_home:
        heavy = True
        surcharge, rate_basis = _heavy_surcharge(heavy_home_count, s)
        citations.append(_cite(f"조정지역 {heavy_home_count}주택 중과 +{int(surcharge*100)}%p", rate_basis, "A"))
        excluded, why = _temp_exclusion(
            s, holding_years, date.fromisoformat(contract_date) if contract_date else None,
            deposit_received, contract_months_limit)
        if excluded:
            heavy, surcharge = False, 0.0
            citations.append(_cite(why, "영 §167의3①12호의2", "A"))
        elif why:
            flags.append(f"한시배제 미해당 — {why}")
        if heavy:
            flags.append("한시배제 나·다목(2026-05-09까지 계약+계약금 후 4개월, 일부 지역 6개월 내 양도)"
                         " 해당 여부를 contract_date·deposit_received·contract_months_limit로 재확인할 것")

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
        # 2026-08-30 — 비교과세를 calc_transfer_tax가 직접 수행하도록 바뀌었다.
        # 종전의 "두 번 호출해 큰 쪽 채택" 안내는 호출자가 빠뜨리기 쉬워 폐기.
        flags.append("보유 2년 미만 — 단기세율(주택등 1년미만 70%·1~2년 60%)과 비교과세 대상. "
                     "calc_transfer_tax에 holding_years·asset_type을 정확히 넘기면 "
                     "§104① 후단·⑦ 후단 비교를 함수가 수행하고 결과의 '세율 비교' 항목에 "
                     "두 후보 세액이 함께 표시된다")

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
_FAIR_RATE_HISTORY = [  # 당좌대출이자율 연혁 — 법인규칙 §43② eflaw 실측 (2026-08-24)
    ("2016-03-07", 0.046),   # 2016.3.7 개정 — 현행
    ("2012-02-28", 0.069),   # 2012.2.28 개정
    ("0000-01-01", 0.085),   # 종전 (2011.2.28 개정 1,000분의 85)
]


def judge_family_loan(loan_amount: int, agreed_interest_rate: float = 0.0,
                      loan_date: str = "", is_related: bool = True,
                      justifiable_reason: bool = False) -> dict:
    """금전 무상·저리 대출 증여 판정 (상증법 §41의4·영 §31의4·법인규칙 §43② — 노드 N41의4-1·N-적정이자율-1).

    loan_date: 대출일(재대출 간주 시 각 1년 단위 개시일) — 당시 적정이자율로 판정:
      4.6%(2016-03-07~) / 6.9%(2012-02-28~) / 8.5%(그 전). 미입력 시 현행 4.6%.
    is_related=False(비특수관계): 거래관행상 정당한 사유(justifiable_reason)가 있으면 과세
      제외(§41의4③) — 사유가 없으면 포괄주의로 과세(조심 2013서1231·2013서0854).
    """
    rate = FAIR_INTEREST_RATE
    rate_note = "현행 4.6%"
    if loan_date:
        for frm, r in _FAIR_RATE_HISTORY:
            if loan_date >= frm:
                rate = r
                rate_note = f"대출일 {loan_date} 당시 {r:.1%}"
                break
    benefit = int(loan_amount * rate - loan_amount * agreed_interest_rate)
    flags = [
        "취득자금 증여추정(§45)과 별개 — 차용증·이자 실지급·상환 내역이 자금출처 소명의 방어선 (미입증액 < min(취득가 20%, 2억)이면 추정 배제, 상증령 §34)",
        "부모가 전세계약을 체결하고 자녀가 거주하는 구조는 금전무상대여가 아니라 임차권(부동산 임대용역) "
        "무상제공으로 본다 — 이 툴의 대상이 아님(조심 2023서7797·2025서3447)",
        "미지급금·임차료를 특별한 사유 없이 지연 지급하는 것도 그 상당액의 무상대출로 본다"
        "(조심 2020서1246·2022서7790)",
    ]
    if not is_related:
        if justifiable_reason:
            return {"연간_증여이익": max(benefit, 0), "과세대상": False,
                    "판정": "비특수관계 + 거래관행상 정당한 사유 — 과세 제외(§41의4③)",
                    "무상대출_안전선": int(LOAN_GIFT_THRESHOLD / rate),
                    "근거": [_cite("특수관계인이 아닌 자 간의 거래로서 거래의 관행상 정당한 사유가 있으면 "
                                 "적용하지 않음", "상증법 §41의4③", "A")],
                    "플래그": flags + ["'정당한 사유'는 사실판단 영역 — 차용증·이자수수·상환계획 등 "
                                    "증빙으로 다퉈진다(조심 2013서1231은 사유 부정)"]}
        flags.append("비특수관계자라도 정당한 사유가 없으면 포괄주의로 과세(조심 2013서1231·2013서0854)")
    taxable = benefit >= LOAN_GIFT_THRESHOLD
    safe_line = int(LOAN_GIFT_THRESHOLD / rate)
    return {
        "연간_증여이익": max(benefit, 0),
        "과세대상": taxable,
        "적용이자율": rate,
        "판정": (f"이익 {benefit:,}원 ≥ 1천만 — 대출일 기준 증여재산가액 (매년 재계산: 1년 단위 재대출 간주)"
                  if taxable else f"이익 {max(benefit,0):,}원 < 1천만 — 과세 제외"),
        "무상대출_안전선": safe_line,
        "근거": [
            _cite(f"적정이자율 {rate_note}", "법인규칙 §43②(연혁: 8.5%→6.9%〔2012-02-28〕→4.6%"
                  "〔2016-03-07〕) ← 상증규칙 §10의5 ← 영 §31의4 4단 위임", "A"),
            _cite("기준금액 1천만", "상증령 §31의4②", "B"),
            _cite("1년 단위 재대출 간주 — 저리 약정이라도 적정이자율 기준으로 차액 산정",
                  "상증법 §41의4②·① (조심 2021중2549)", "A"),
        ],
        "플래그": flags,
    }


# ── 4. 자금조달계획서 제출 판정 ────────────────────────────────────────────
def judge_fund_plan_requirement(actual_price: int, in_speculation_zone: bool = False,
                                in_adjusted_area: bool = False, in_permit_zone: bool = False,
                                is_corporation: bool = False) -> dict:
    """주택 매수 시 자금조달계획서(+입주계획) 제출·증빙 판정 (거래신고령 별표 1, 규칙 별지 1호의3 — 노드 NRTMS-별표1-1·서식1의3-1)."""
    required = is_corporation or in_speculation_zone or in_adjusted_area or in_permit_zone or actual_price >= FUND_PLAN_PRICE_LIMIT
    evidence = in_speculation_zone or in_permit_zone
    basis = ("법인 매수 — 전부 제출 (별표1 2호)" if is_corporation else
             "투기과열지구·조정대상지역 소재 — 금액 무관 제출 (별표1 3호)" if (in_speculation_zone or in_adjusted_area) else
             "토지거래허가구역 주택 (별표1 3호의2)" if in_permit_zone else
             f"실거래가 {actual_price:,} ≥ 6억 (별표1 3호)" if required else "제출 대상 아님")
    return {
        "제출대상": required,
        "증빙서류_첨부": evidence,
        "판정근거": basis,
        "서식": "별지 1호의3 (2026-02-06 개정) — 자기자금: 예금/주식·가상화폐 매각/증여·상속(신고여부)/현금기타/부동산처분, 차입금: 금융기관(종류·기존주택 보유)/취득주택 임대보증금(갭투자)/회사지원금·사채/그밖의 차입금(관계) + 지급방식·입주계획. ⚠️ '소득' 항목 없음 — 장래소득은 잔금일 기준 확보 예정 자금으로 예금/현금기타 귀속",
        "근거": [
            _cite("제출 대상", "거래신고령 별표 1 (2025-12-09 개정)", "B"),
            _cite("증빙 첨부 = 투기과열지구·허가구역", "별표 1 3호·3호의2", "B"),
        ],
        "플래그": [
            "자금출처 소명 대비: 미입증액 < min(취득가 20%, 2억) 이면 증여추정 배제 (상증령 §34) — judge_family_loan과 연계",
            "신고 전 대금 완납 시 '조달계획'은 '조달방법'으로 기재 (별표1 비고 9)",
        ],
    }


# ── 5. 트리① 세대 동일성 판정 ─────────────────────────────────────────────
FAMILY_SCOPE = {"배우자", "직계존속", "직계비속", "직계존비속의 배우자", "형제자매"}


def judge_same_household(relationship: str, lives_together: bool = True,
                         shares_livelihood: bool = True, age: int | None = None,
                         is_married_or_was: bool = False,
                         income_over_40pct_median: bool = False,
                         is_minor: bool = False, tax_kind: str = "양도세",
                         legally_divorced_but_living_together: bool = False,
                         is_de_facto_marriage: bool = False,
                         merged_for_parent_care: bool = False,
                         descendant_age: int | None = None) -> dict:
    """트리① — 본인과 특정인이 같은 1세대인지 판정 (소법 §88 6호·영 §152의3 / 지방령 §28의3 / 종부령 §1의2).

    relationship: 배우자|직계존속|직계비속|직계존비속의 배우자|형제자매|기타(이모·조카·사돈 등)
    tax_kind: 양도세(실질 기준)|취득세(주민등록 기준)|종부세

    ⚠️ 세대 정의는 세목마다 다르다 — 하나로 뭉치면 안 된다(2026-08-24 조문 실측):
      | | 양도세(소법 §88 6호) | 취득세(지방령 §28의3) |
      | 기준 | 같은 주소 + 생계동일(실질) | 세대별 주민등록표 |
      | 사실혼 배우자 | 해석 영역 | **명문 제외** |
      | 미혼 30세 미만 자녀 | 실질 판단 | 분리 거주해도 같은 세대 |
      | 소득요건 측정기간 | 명문 없음(실무 프록시) | **직전 12개월** 명문 |
      | 동거봉양 존속 연령 | 60세(§155④) | **65세**(§28의3②2호) |

    legally_divorced_but_living_together: 법률상 이혼했으나 생계를 같이 하는 등 사실상 이혼으로
      보기 어려운 관계 — 소법 §88 6호 괄호·지방령 §28의3①이 배우자에 포함시킨다(위장이혼 차단).
    merged_for_parent_care·descendant_age: 취득세 동거봉양 합가 별도세대 예외(§28의3②2호) 판정용.
    반환: 동일세대 여부 + 분리 가능 조건 + 근거·플래그.
    """
    flags, citations = [], []

    # 1) 가족 범위 밖 = 세목 불문 별도 세대 (사례⑭ 이모-조카)
    if relationship == "배우자":
        if is_de_facto_marriage and tax_kind == "취득세":
            citations.append(_cite("취득세 세대의 배우자는 사실혼을 명문으로 제외 — 별도 세대",
                                   "지방세법 시행령 §28의3①", "A"))
            flags.append("양도세는 사실혼을 명문으로 배제하지 않아 실질 판단 영역 — 세목별로 결론이 갈린다")
            return {"동일세대": False, "분리가능": True, "근거": citations, "플래그": flags}
        if legally_divorced_but_living_together:
            citations.append(_cite("법률상 이혼했으나 생계를 같이 하는 등 사실상 이혼으로 보기 어려운 관계 "
                                   "— 배우자에 포함(위장이혼 차단)",
                                   "소법 §88 6호 괄호 / 지방령 §28의3①", "A"))
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
                               "지방세법 시행령 §28의3①", "A"))
        # 별도세대 예외 (§28의3②) — 양도세와 요건이 다르다.
        if (merged_for_parent_care and relationship == "직계존속"
                and age is not None and descendant_age is not None):
            if age >= 65 and descendant_age >= 30:
                citations.append(_cite(f"65세 이상 직계존속({age}세) 동거봉양 위해 30세 이상 직계비속"
                                       f"({descendant_age}세)이 합가 — 별도 세대",
                                       "지방세법 시행령 §28의3②2호", "A"))
                return {"동일세대": False, "분리가능": True, "근거": citations, "플래그": flags}
            citations.append(_cite(f"동거봉양 합가이나 직계존속이 {age}세 — 취득세는 **65세** 기준이라 "
                                   "별도세대 예외에 해당하지 않는다(양도세 §155④의 60세와 다름)",
                                   "지방세법 시행령 §28의3②2호", "A"))
            flags.append("양도세 동거봉양 특례는 60세 기준이라 같은 사실관계에서 세목별 결론이 갈릴 수 있다")
            return {"동일세대": True, "분리가능": False, "근거": citations, "플래그": flags}
        if relationship == "직계비속" and age is not None and age < 30 and not is_married_or_was:
            if (not lives_together) and income_over_40pct_median and not is_minor:
                citations.append(_cite("부모와 다른 주민등록표 + 직전 12개월 소득이 기준 중위소득 40% 이상 "
                                       "+ 독립 생계 — 별도 세대",
                                       "지방세법 시행령 §28의3②1호 (측정기간 '직전 12개월' 명문)", "A"))
                return {"동일세대": False, "분리가능": True, "근거": citations, "플래그": flags}
            citations.append(_cite("미혼 30세 미만 자녀는 주민등록을 분리해도 같은 세대 — "
                                   "소득요건(직전 12개월 40%)을 충족해야 별도 세대",
                                   "지방세법 시행령 §28의3①·②1호", "A"))
            return {"동일세대": True, "분리가능": bool(income_over_40pct_median and not is_minor),
                    "근거": citations, "플래그": flags}

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


# ── 6. 트리② 양도세 비과세 판정용 주택수 산정 ─────────────────────────────
RIGHT_COUNT_FROM = date(2021, 1, 1)  # 분양권 주택수 산입 시작 (소법 §88 10호, 2021 취득분부터)


def count_transfer_homes(items: list[dict]) -> dict:
    """트리② — 1세대1주택 비과세 판정용 주택수 산정 (소법 §88·§89, 영 §154~156의3 노드).

    items 각 원소: {
      "종류": "주택"|"조합원입주권"|"분양권"|"오피스텔",
      "사실상주거용": bool (오피스텔·겸용 판정 — 양도세는 공부 아닌 현황),
      "취득일": "YYYY-MM-DD" (분양권 2021-01-01 이후 취득분만 산입 — 기산은 청약당첨일이
        아니라 **분양계약일**, 대법원 2024두54560),
      "상속특례주택": bool (§155② 선순위 상속주택 — 별도세대 피상속인),
      "공동상속_소수지분": bool (§155③),
      "농어촌주택특례": bool (§155⑦),
      "등록임대_거주주택특례": bool (§155⑳ 장기임대 — 거주주택 비과세 판정 시 제외),
      "라벨": str,
    }
    """
    counted, details, flags = 0, [], []
    combined_all_house = None
    for it in items:
        kind = it.get("종류", "주택")
        label = it.get("라벨") or kind
        inc, why = True, "산입"
        if kind == "다가구주택":
            # 영 §155⑮ — 원칙은 구획별 각각 1주택, 하나의 매매단위로 양도하면 전체가 1주택.
            n = int(it.get("구획수", 1) or 1)
            if it.get("일괄양도"):
                counted += 1
                details.append({"항목": label, "산입": True,
                                "사유": f"다가구주택 {n}구획을 하나의 매매단위로 양도 — 전체를 하나의 주택으로 "
                                      "본다 (영 §155⑮ 단서)"})
            else:
                counted += n
                details.append({"항목": label, "산입": True,
                                "사유": f"다가구주택을 구획별로 양도 — 구획 {n}개를 각각 하나의 주택으로 "
                                      "본다 (영 §155⑮ 본문)"})
                flags.append(f"{label}: 구획별 양도는 다주택이 된다 — 일괄양도 여부가 비과세를 가르는 분기")
            continue
        if kind == "겸용주택":
            # 영 §154③ — 주택 연면적이 주택외보다 크면 전부 주택, 적거나 같으면 주택 부분만.
            ha, oa = float(it.get("주택연면적", 0)), float(it.get("주택외연면적", 0))
            all_house = ha > oa
            combined_all_house = all_house if combined_all_house is None else (combined_all_house and all_house)
            counted += 1
            details.append({"항목": label, "산입": True,
                            "사유": (f"겸용주택 주택 {ha}㎡ vs 주택외 {oa}㎡ — "
                                   + ("전부를 주택으로 본다 (영 §154③ 본문)" if all_house else
                                      "주택외 부분은 주택으로 보지 않는다 (영 §154③ 단서). "
                                      "부수토지는 주택 연면적 비율로 안분(영 §154④)"))})
            flags.append(f"{label}: 겸용주택 판정 기준은 **양도 당시 사용용도** — 공부가 아니다"
                         "(재일46014-2357). 용도변경으로 주택면적이 커진 경우도 전부 주택(재산세과-264)")
            continue
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
    if any(it.get("종류") == "분양권" for it in items):
        flags.append("분양권 취득일(보유 기산)은 청약당첨일이 아니라 분양계약일 — 당첨일로 넣으면 "
                     "2021-01-01 경과규정 판정이 뒤집힐 수 있다(대법원 2024두54560, 취득세 영 "
                     "§28의4①과 정합)")
    return {
        "비과세판정_주택수": counted,
        "1세대1주택_간주가능": counted == 1,
        "겸용주택_전부주택": combined_all_house,
        "항목별": details,
        "플래그": flags,
        "주의": "이 산정은 비과세(§89) 판정용 — 중과판정 주택수(영 §167의3~11: 지방 3억·기준시가 1억 등 별도 제외)와 다르다. 세목별 주택수 분리 원칙",
    }


# ── 7. §155① 일시적 2주택 날짜 산식 ───────────────────────────────────────
# ── §155① 조정대상지역 일시적 2주택 경과규정 상수 ─────────────────────────
# 양도일 기준 전환점 (부칙은 모두 "양도하는 경우부터 적용")
_R155_REL_2Y = date(2022, 5, 10)   # 영 32654호 부칙 §3 — 이후 양도분: 전입요건·1년 폐지 → 2년
_R155_REL_3Y = date(2023, 1, 12)   # 영 33267호 부칙 §8 — 이후 양도분: 3년 단일
_R155_EFF_29242 = date(2018, 10, 23)  # 영 29242호 시행일 (조정 2년 규정 신설)
_R155_EFF_30395 = date(2020, 2, 11)   # 영 30395호 시행일 (조정 1년+전입요건 신설)
# 신규주택 취득일 기준 경과규정 (부칙 각 §2②·§15② — 대책 발표일 이전 취득·계약은 종전규정)
_R155_ACQ_2Y = date(2018, 9, 14)   # 2018.9.13 이전 취득·계약 → 종전규정(3년)
_R155_ACQ_1Y = date(2019, 12, 17)  # 2019.12.16 이전 취득·계약 → 2년 규정


def _r155_regime(n: date, sale: date | None, prev_adj: bool, new_adj: bool,
                 new_contract: date | None,
                 prev_adjusted_after_new_contract: bool = False) -> tuple[int, bool, str]:
    """(양도기한 연수, 전입요건 적용 여부, 적용법령 설명) — 조정→조정만 단축·전입요건 대상.

    prev_adjusted_after_new_contract: 종전주택이 신규주택 취득계약 체결 후에 비로소 조정대상
    지역으로 지정된 경우 — 조정대상지역 지정 고시는 소급하지 않으므로 '취득 당시 둘 다 조정'
    요건에서 빠져 단축(2년/1년) 대상이 아니다(3년). 상담사례 세법상담-500이 인용하는
    서면-2020-부동산-3583(부동산납세과-1478, 2020.12.16.) — 예규 본문 미확보라 D급.
    """
    if prev_adj and new_adj and prev_adjusted_after_new_contract:
        return 3, False, ("영 §155① — 종전주택이 신규주택 취득계약 후 조정지정됨(고시 불소급). "
                          "'취득 당시 둘 다 조정' 요건 미충족 → 3년 (서면-2020-부동산-3583, D급·예규 본문 확인 권장)")
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
                              other_homes_at_acquisition: int = 0,
                              prev_adjusted_after_new_contract: bool = False) -> dict:
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
        date.fromisoformat(new_contract_date) if new_contract_date else None,
        prev_adjusted_after_new_contract)
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


def _add_years(d: date, years: int) -> date:
    if d.month == 2 and d.day == 29:
        return date(d.year + years, 2, 28)
    return date(d.year + years, d.month, d.day)


# ── 8. §155 나머지 특례 — 혼인·동거봉양·상속·거주주택 ──────────────────────
# ── §155④⑤ 특례기간 경과규정 — 둘 다 양도일 기준으로 5년/10년이 갈린다 ──────
# 부칙이 "이 영 시행 이후 양도하는 경우부터 적용"이므로 합가·혼인일이 아니라 양도일이 기준.
_R155_MARRY_10Y = date(2024, 11, 12)   # 영 34990호 부칙 §2 — 이후 양도분 10년(그 전 5년)
_R155_CARE_10Y = date(2018, 2, 13)     # 영 28637호 시행일 — 이후 양도분 10년(그 전 5년)
_R155_CARE_FEMALE_55 = date(2009, 2, 4)  # 이 날 전 합가는 여성 직계존속 55세 기준


def _r155_period(kind: str, sale: date | None) -> tuple[int, str]:
    """(특례기간 연수, 근거 설명). sale 미정이면 현행 10년."""
    if kind == "혼인":
        if sale is None or sale >= _R155_MARRY_10Y:
            return 10, "영 §155⑤(2024.11.12 개정, 34990호 부칙 §2) — 2024-11-12 이후 양도분 10년"
        return 5, "구 영 §155⑤ — 2024-11-12 전 양도분은 5년"
    if sale is None or sale >= _R155_CARE_10Y:
        return 10, "영 §155④(2018.2.13 개정, 28637호) — 2018-02-13 이후 양도분 10년"
    return 5, "구 영 §155④ — 2018-02-13 전 양도분은 5년"


def judge_155_special(kind: str, event_date: str = "", sale_date: str = "",
                      homes_mine: int = 1, homes_spouse_or_parent: int = 1,
                      parent_max_age_at_merge: int | None = None,
                      separate_household_at_inheritance: bool = True,
                      general_home_acquired_before_inheritance: bool = True,
                      is_first_priority_inherited: bool = True,
                      gifted_within_2y_before_inheritance: bool = False,
                      rental_registered: bool = False,
                      residence_years_in_home: float = 0.0,
                      first_time_use: bool = True,
                      excluded_homes_mine: int = 0,
                      excluded_homes_spouse_or_parent: int = 0,
                      parent_is_female: bool = False,
                      merged_for_parent_care: bool = False,
                      held_before_merge: bool = True,
                      designated_by_agreement: bool = False) -> dict:
    """§155 특례 판정 디스패처 (kind: 혼인|동거봉양|상속주택|거주주택).

    - 혼인(§155⑤): 각 1주택끼리 혼인 → 혼인일부터 10년(2024-11-12 전 양도분은 5년) 내
      먼저 양도분 비과세. 1+1 한정(사례⑩). **주택수는 양도일이 아니라 혼인합가 당시 기준**
      (서면-2023-법규재산-0887·서면-2022-법규재산-4283).
    - 동거봉양(§155④): 60세↑ 직계존속(한쪽만 60↑ 포함) 합가 → 합가일부터 10년
      (2018-02-13 전 양도분은 5년) 내 먼저 양도분. 2009-02-04 전 합가는 여성 존속 55세 기준.
    - 상속주택(§155②): 별도세대 피상속인의 선순위 상속주택 → 일반주택 양도 시 없는 것으로 간주.
      동거봉양 합가로 동일세대가 된 경우에는 **합치기 이전부터 보유하던 주택만** 상속주택으로 본다.
    - 거주주택(§155⑳): 장기임대 등록 + 거주주택 2년 거주 → 생애 1회 비과세(사후관리부).

    event_date = 혼인일/합가일, sale_date = 양도일 (YYYY-MM-DD). 특례기간이 양도일로 갈리므로
    과거 양도분 상담·경정청구에서는 sale_date를 반드시 넣을 것.
    excluded_homes_*: 다른 특례로 주택수에서 빠지는 주택 수(공동상속 §155③·농어촌 조특법 §99의4 등)
      — 1+1 판정 전에 차감한다(서면-2021-부동산-7265).
    """
    flags, citations = [], []
    s = date.fromisoformat(sale_date) if sale_date else None
    mine = max(homes_mine - excluded_homes_mine, 0)
    theirs = max(homes_spouse_or_parent - excluded_homes_spouse_or_parent, 0)
    if excluded_homes_mine or excluded_homes_spouse_or_parent:
        citations.append(_cite(
            f"주택수 산정에서 특례 제외 주택 차감 — {homes_mine}+{homes_spouse_or_parent} → {mine}+{theirs}"
            "(공동상속 §155③·농어촌 조특법 §99의4 등)", "서면-2021-부동산-7265", "A"))

    if kind == "혼인":
        if mine != 1 or theirs != 1:
            return {"특례적용": False, "사유": f"1주택+1주택 결합만 가능 — {mine}+{theirs}는 탈락 (사례⑩: 2+1 불가)",
                    "근거": citations + [_cite("혼인 합가 특례는 각 1주택 한정 — 임대주택도 주택수에 든다"
                                             "(서면-2024-부동산-2331)", "영 §155⑤ 문언", "A")],
                    "플래그": ["주택수는 혼인합가 당시 기준으로 판정한다(양도일 현재가 아님)"]}
        years, basis = _r155_period("혼인", s)
        dl = _add_years(date.fromisoformat(event_date), years)
        ok = (s <= dl) if s else None
        citations.append(_cite(f"혼인일 {event_date} + {years}년 = {dl.isoformat()} 내 먼저 양도분 비과세", basis, "A"))
        flags.append("주택수 요건은 혼인합가 '당시' 주택수로 판정 — 양도일 현재 주택수와 무관"
                     "(서면-2023-법규재산-0887)")
        flags.append("먼저 양도하는 주택에만 적용 — 양도 순서 선택권이 절세 레버. 각 주택 자체 비과세 요건 충족 전제")
        flags.append("§155 특례 규정의 3중첩은 불허(서면-2022-법규재산-4283) — 2중첩(혼인+일시적2주택, "
                     "혼인+상속)까지만")
        flags.append("세목 분기: 종부세는 세대 자체 10년 분리(종부령 §1의2④), 취득세 완충은 혼전 분양권 케이스만")
        return {"특례적용": ok if sale_date else True, "특례기간연수": years,
                "데드라인": dl.isoformat(), "근거": citations, "플래그": flags}

    if kind == "동거봉양":
        merged = date.fromisoformat(event_date) if event_date else None
        age_floor = 55 if (parent_is_female and merged and merged < _R155_CARE_FEMALE_55) else 60
        if age_floor == 55:
            citations.append(_cite(f"2009-02-04 전 합가 + 여성 직계존속 — 연령 기준 55세",
                                   "구 영 §155④ (부동산거래관리과-1259)", "A"))
        if parent_max_age_at_merge is not None and parent_max_age_at_merge < age_floor:
            flags.append(f"직계존속 모두 {age_floor}세 미만 — 원칙 불가. 단 요양급여 대상 60세 미만 존속은 "
                         "예외(§155④3호) 확인")
            return {"특례적용": False, "사유": f"합가 당시 {age_floor}세 이상 직계존속 요건 미충족",
                    "근거": citations + [_cite(f"{age_floor}세 이상 직계존속 동거봉양", "영 §155④", "B")],
                    "플래그": flags}
        if mine != 1 or theirs != 1:
            return {"특례적용": False, "사유": f"각 1주택 세대끼리의 합가만 가능 — {mine}+{theirs}",
                    "근거": citations + [_cite("1주택+1주택 합가", "영 §155④", "B")], "플래그": flags}
        years, basis = _r155_period("동거봉양", s)
        dl = _add_years(date.fromisoformat(event_date), years)
        ok = (s <= dl) if s else None
        citations.append(_cite(f"합가일 {event_date} + {years}년 = {dl.isoformat()} 내 먼저 양도분 비과세 "
                               "(한쪽 존속만 60세↑여도 가능)", basis, "A"))
        if s and date(2018, 1, 1) <= s < _R155_CARE_10Y:
            flags.append("양도일이 2018-01-01~2018-02-12 구간 — 영 28637호에 §155④ 기간 관련 개별 적용례가 "
                         "없어 일반적 적용례(부칙 §2, 시행일이 속하는 과세기간 소득분)로 2018년 양도분 전체에 "
                         "10년을 적용할 여지가 있다. 회색지대 — 전문가 확인 필요(등급 c)")
        flags.append("종부세 동거봉양은 세대 분리 간주 10년(종부령 §1의2⑤ — 60세 도달 규칙 별도)·상속공제 동거주택 판정에도 합가 예외 있음(상증령 §20의2①6호)")
        return {"특례적용": ok if sale_date else True, "특례기간연수": years,
                "회색지대": bool(s and date(2018, 1, 1) <= s < _R155_CARE_10Y),
                "데드라인": dl.isoformat(), "근거": citations, "플래그": flags}

    if kind == "상속주택":
        same_household_ok = separate_household_at_inheritance or (merged_for_parent_care and held_before_merge)
        ok = (same_household_ok and general_home_acquired_before_inheritance
              and is_first_priority_inherited and not gifted_within_2y_before_inheritance)
        if not separate_household_at_inheritance:
            if merged_for_parent_care and held_before_merge:
                citations.append(_cite("동거봉양 합가로 1세대가 된 경우 — 합치기 이전부터 보유하던 주택만 "
                                       "상속받은 주택으로 본다", "영 §155② 괄호", "A"))
            elif merged_for_parent_care:
                flags.append("동거봉양 합가 '이후' 취득한 주택은 §155② 괄호의 대상이 아니다 — 특례 배제"
                             "(사전-2021-법령해석재산-1566·부동산거래관리과-1)")
            else:
                flags.append("상속개시 당시 동일세대 — 특례 배제. 동거봉양 합가로 동일세대가 된 경우라면 "
                             "merged_for_parent_care·held_before_merge를 넣어 재판정할 것")
        if designated_by_agreement:
            flags.append("상속인간 협의로 후순위 상속주택을 선순위로 지정할 수 없다 — §155② 각 호의 순위가 "
                         "명확(사전-2024-법규재산-0433)")
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


# ── 9. 중과판정 주택수 자동화 (영 §167의3~11) ─────────────────────────────
HEAVY_LOCAL_PRICE_LIMIT = 300_000_000   # 지방 저가 불산입 (영 §167의3①1호 등)
HEAVY_TWO_HOME_LOW_LIMIT = 100_000_000  # 2주택 판정 전용 1억 제외 (영 §167의10①9호)


_SMALL_NEW_FROM = date(2024, 1, 10)   # 영 §167의3①12호 가목 — 소형 신축주택 특례 기간
_SMALL_NEW_TO = date(2027, 12, 31)
_SMALL_NEW_AREA = 60.0
_SMALL_NEW_PRICE_CAPITAL = 600_000_000
_SMALL_NEW_PRICE_LOCAL = 300_000_000


def _is_small_new_house(it: dict) -> tuple[bool, str]:
    """영 §167의3①12호 가목 소형 신축주택 — 요건을 전부 갖춰야 불산입."""
    acq, done = it.get("취득일"), it.get("준공일")
    area, price = it.get("전용면적"), int(it.get("취득가액", 0) or 0)
    if not (acq and done and area is not None and price):
        return False, ""
    a, d = date.fromisoformat(acq), date.fromisoformat(done)
    if not (_SMALL_NEW_FROM <= a <= _SMALL_NEW_TO and _SMALL_NEW_FROM <= d <= _SMALL_NEW_TO):
        return False, ""
    if area > _SMALL_NEW_AREA or it.get("아파트"):
        return False, ""
    cap = _SMALL_NEW_PRICE_LOCAL if it.get("지방소재") else _SMALL_NEW_PRICE_CAPITAL
    if price > cap:
        return False, ""
    return True, (f"소형 신축주택 — 전용 {area}㎡(60 이하)·취득가 {price:,}원"
                  f"({'지방 3억' if it.get('지방소재') else '수도권 6억'} 이하)·"
                  f"{acq} 취득/{done} 준공(2024-01-10~2027-12-31)·아파트 아님 → 불산입 "
                  "(영 §167의3①12호 가목)")


def count_heavy_homes(items: list[dict], heavy_tier: int = 3) -> dict:
    """양도세 중과판정 주택수 산정 (영 §167의3②·167의4②·167의11② 불산입 자동 적용).

    items 원소: {"종류": 주택|조합원입주권|분양권, "기준시가": 원(입주권=종전주택가·분양권=공급가),
    "지방소재": bool(수도권·광역시·특별자치시 밖 — 군·읍·면 포함), "인구감소등_12호": bool,
    "전용면적"·"취득가액"·"취득일"·"준공일"·"아파트": 12호 가목 소형 신축주택 판정용,
    "정비구역": bool, "라벨": str}. 반환 주택수를 judge_transfer_reliefs의 heavy_home_count로 연결.

    heavy_tier: 어느 계열로 세는지 — 2(2주택 중과, 영 §167의10)면 기준시가 1억 이하 불산입이
      추가로 적용된다. 3(3주택 이상, 영 §167의3)에는 그 완화가 없다. **같은 주택이라도 계열에
      따라 세는 수가 달라진다.**
    """
    counted, details = 0, []
    for it in items:
        label = it.get("라벨") or it.get("종류", "주택")
        std = int(it.get("기준시가", 0))
        inc, why = True, "산입"
        small, small_why = _is_small_new_house(it)
        if it.get("인구감소등_12호"):
            inc, why = False, "§167의3①12호(소형신축·인구감소지역 등) — 불산입"
        elif small:
            inc, why = False, small_why
        elif it.get("지방소재") and std <= HEAVY_LOCAL_PRICE_LIMIT:
            inc, why = False, "지방(수도권·광역시·특자시 밖) + 기준시가 3억 이하 — 불산입 (영 §167의3①1호·167의4②·167의11②)"
        elif heavy_tier == 2 and std and std <= HEAVY_TWO_HOME_LOW_LIMIT and not it.get("정비구역"):
            inc, why = False, ("2주택 중과 판정 전용 — 기준시가 1억 이하(정비구역 제외) 불산입 "
                               "(영 §167의10①9호). 3주택 계열에는 이 완화가 없다")
        if inc:
            counted += 1
        details.append({"항목": label, "산입": inc, "사유": why})
    flags = [f"heavy_tier={heavy_tier} 기준으로 셌다 — 2주택/3주택 계열은 불산입 규정이 다르므로 "
             "계열을 바꿔 다시 세야 할 수 있다 (영 §167의10①3·9호는 2주택 전용)",
             "양도 주택 자체의 중과 제외(장기임대·상속 5년·한시배제·비과세특례 주택 등)는 judge_transfer_reliefs의 sale_date·별도 확인",
             "혼인 5년 완충(§167의3⑨·167의4⑤)은 3주택 계열만 — 해당 시 배우자 보유분 차감"]
    return {"중과판정_주택수": counted, "항목별": details, "플래그": flags,
            "주의": "비과세 판정용 주택수(count_transfer_homes)와 별개 — 같은 세대가 두 값이 다를 수 있음"}


# ── 10. 종부세 1세대1주택자 간주 4유형 (법 §8④·영 §4의2) ──────────────────
JB_INHERIT_SHARE_LIMIT = 0.40
JB_INHERIT_PRICE_CAP = 600_000_000      # 지분 상당 공시가 (비수도권 3억)
JB_INHERIT_PRICE_NONCAP = 300_000_000
JB_LOW_PRICE_LIMIT = 400_000_000        # 지방 저가주택 4억 (2025-02-28 영 35352호 — 종전 3억)
JB_LOW_PRICE_LIMIT_OLD = 300_000_000    # 〃 2025-02-28 전 (신설 2022-09-23 원문)
_JB_LOW_PRICE_4E_FROM = date(2025, 2, 28)   # 영 35352호 시행일 — 과세기준일(6/1) 기준 분기
_JB_TEMP_3Y_FROM = date(2023, 2, 28)        # 일시적 2주택 2년→3년 (영 33266호)
_JB_TYPES_FROM = date(2022, 6, 1)           # 간주 2~4호 신설 — 법 18977호(2022-09-15) 부칙 §2로
                                            # 2022년 납세의무 성립분(과세기준일 2022-06-01)부터


def judge_jongbu_one_home_status(other_homes: list[dict], base_date: str = "") -> dict:
    """종부세 1세대1주택자 간주 판정 — 주된 1주택 외 보유분이 간주 4유형에 해당하는지 (법 §8④·영 §4의2).

    other_homes 원소: {"유형": "부속토지"|"일시적신규"|"상속"|"지방저가"|"일반",
      "신규취득일": "YYYY-MM-DD" (일시적신규 — 과세기준일 현재 3년〔2023-02-28 전 성립분 2년〕
        미경과 요건), "재건축완공": bool (구주택 재건축 준공은 신규취득 아님 — 조심 2025소4289),
      "구주택취득일": "YYYY-MM-DD" (재건축완공 시 승계되는 취득일),
      "상속개시일": "YYYY-MM-DD", "지분율": 0~1, "지분공시가": 원, "수도권": bool,
      "공시가격": 원, "소재요건충족": bool (지방저가 — 비수도권 비광역시 등), "라벨": str}
    base_date: 과세기준일(기본 매년 6/1) — 미지정 시 기간요건은 플래그로만.

    ⚠️경과규정(2026-08-24 eflaw 연혁 실측): 간주 2~4호(일시적·상속·지방저가)는 법 18977호
    (2022-09-15) 신설 — 부칙 §2로 2022년 납세의무 성립분부터. 2021 귀속 이전엔 규정 자체가
    없다(조심 2022서6288 등 일관 기각). 일시적 기간은 신설 시 2년 → 2023-02-28(영 33266호)
    3년. 지방저가는 신설 시 3억 → 2025-02-28(영 35352호) 4억.
    """
    ok_all, details, flags = True, [], []
    bd = date.fromisoformat(base_date) if base_date else None
    no_new_types = bd is not None and bd < _JB_TYPES_FROM
    for it in other_homes:
        t, label = it.get("유형", "일반"), it.get("라벨") or it.get("유형", "일반")
        good, why = False, None
        if t == "부속토지":
            good, why = True, "다른 주택의 부속토지만 보유 — 간주 1유형 (법 §8④1호)"
        elif no_new_types and t in ("일시적신규", "상속", "지방저가"):
            why = (f"{t} 간주는 법 18977호(2022-09-15) 신설 — 부칙 §2로 2022년 성립분부터 적용. "
                   "과세기준일이 2022-06-01 전이면 규정 자체가 없어 탈락"
                   "(조심 2022서6288·2022서6174·2017서0608)")
        elif t == "일시적신규":
            if it.get("재건축완공"):
                inherited = it.get("구주택취득일") or "구주택 취득일"
                why = (f"재건축 준공주택은 멸실된 구주택과 별개 주택이 아니다 — 취득일은 {inherited} "
                       "승계라 '신규주택 취득' 자체가 성립하지 않음(조심 2025소4289)")
            elif bd and it.get("신규취득일"):
                yrs = 3 if bd >= _JB_TEMP_3Y_FROM else 2
                good = bd <= _add_years(date.fromisoformat(it["신규취득일"]), yrs)
                why = (f"신규주택 취득 {yrs}년 {'미경과 — 간주' if good else '경과 — 탈락'} "
                       f"(영 §4의2①{' — 2023-02-28 전 성립분은 2년' if yrs == 2 else ''})")
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
            cap = JB_LOW_PRICE_LIMIT if (bd is None or bd >= _JB_LOW_PRICE_4E_FROM) else JB_LOW_PRICE_LIMIT_OLD
            good = int(it.get("공시가격", 0)) <= cap and bool(it.get("소재요건충족"))
            why = (f"지방 저가주택 — 공시 {cap // 100_000_000}억↓ + 소재요건(비수도권 비광역시 등): "
                   f"{'충족' if good else '미충족'} (영 §4의2③ — 4억은 2025-02-28 영 35352호부터, 종전 3억)")
        else:
            why = "일반 주택 — 간주 유형 아님 → 1세대1주택자 탈락"
        ok_all = ok_all and good
        details.append({"항목": label, "간주인정": good, "사유": why})
    if ok_all and other_homes:
        flags.append("간주 인정돼도 그 주택 공시가는 과세표준에 합산 유지 — 12억 공제·연령/보유 세액공제만 1주택자 대우 (법 §8④ 후단)")
        flags.append("신청제: 9/16~9/30 관할세무서장 신청(최초 1회, 변동 없으면 생략 가능 — 법 §8⑤·영 §4의2④⑤)")
        flags.append("세액공제 안분: 간주분(부속토지·일시적·상속·지방저가)은 공제율 적용에서 안분 제외 (법 §9⑦⑨ — calc_jongbu_tax 미지원 명시)")
    flags.append("전제: 주된 1주택은 세대원 중 1명 단독 소유(영 §2의3) — 부부 공동명의 1주택은 이 판정이 "
                 "아니라 법 §10의2 공동명의 1주택자 특례 신청(9/16~9/30) 사안(조심 2010서4078)")
    return {"1세대1주택자_간주": ok_all if other_homes else True, "항목별": details, "플래그": flags,
            "근거": [_cite("간주 4유형: 부속토지·일시적 2주택 3년(2023-02-28 전 2년)·상속(5년/지분40%/6억·3억)·"
                         "지방저가 4억(2025-02-28 전 3억) — 2~4호는 2022년 성립분부터",
                         "종부세법 §8④(18977호 부칙 §2)·영 §4의2 연혁 실측", "A")]}


# ── 11. 트리③ 조합원 지위양도 제한 (도시정비법 §39·영 §37 — 13·14차 순회 + 외부대조 ⑯~㉔ 보정 반영) ──
RECON_OWN_YEARS = 10     # 영 §37①1호 (N37-1-1)
RECON_RESIDE_YEARS = 5   # 영 §37①2호 — 배우자·직계존비속 거주 합산, 상속 시 피상속인 기간 합산

_TRANSFEROR_EXCEPTIONS = {  # §39② 단서 1~3·5·6호 (N39-2-2)
    "세대이전": ("근무·생업·질병치료(의료기관장 1년↑ 인정)·취학·결혼으로 세대원 전원이 사업구역 밖 시·군 등으로 이전", "1호"),
    "상속주택이전": ("상속 취득 주택으로 세대원 전원 이전", "2호"),
    "해외이주": ("세대원 전원 해외이주 또는 전원 2년 이상 해외체류", "3호"),
    "지분형주택": ("§80 지분형주택 공급 위해 토지주택공사등과 공유", "5호"),
    "공공재개발양도": ("공공임대·공공분양 공급 목적의 공공재개발사업 시행자에 양도", "6호"),
}

_DECREE_37_3 = {  # 영 §37③ (N37-3-1·2)
    "조합설립인가3년미신청": "조합설립인가일부터 3년↑ 사업시행인가 신청 없는 재건축 건축물을 3년↑ 계속 소유 + 신청 전 양도 (§37③1호)",
    "사업시행인가3년미착공": "사업시행계획인가일부터 3년 내 미착공 재건축 토지·건축물을 3년↑ 계속 소유 + 착공 전 양도 (§37③2호)",
    "착공3년이상미준공": "착공일부터 3년↑ 미준공 재개발·재건축 토지를 3년↑ 계속 소유 (§37③3호)",
    "부칙상속이혼": "법률 제7056호 부칙 제2항 토지등소유자로부터 상속·이혼 취득 (§37③4호)",
    "국가지자체금융기관경매": "국가·지자체·금융기관(주택법 영 §71① 각 목) 채무 불이행 경매·공매 (§37③5호)",
    "투기과열지구지정전계약": "지정 전 계약(계약금 증빙 한정)+지정일부터 60일 내 거래신고, 또는 지정 전 토허가 신청 후 계약 (§37③6·7호)",
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
    permit_application_date: str = "",
) -> dict:
    """트리③ — 재건축·재개발 조합원 지위양도 제한 판정 (도시정비법 §39②③·영 §37①③).

    permit_application_date: (재개발) 사업시행인가 **최초** 신청일 YYYY-MM-DD — 재개발 제한은
    법 14943호 부칙 §1·§2로 2018-01-24 시행 후 최초로 사업시행인가를 신청하는 구역부터.
    그 전 신청 구역은 관리처분인가 후에도 제한 없음(구법).

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
        flags.append("이전고시 후 양수인에게 조합원 지위가 자동승계되지는 않는다 — 청산금·부과금 정산 "
                     "관계(조합 청산 완료 전)는 정관·특약으로 별도 확인(대법원 2022두52874)")
        return {"조합원지위승계가능": True,
                "사유": "이전고시 후 — 분양받을 자가 소유권 취득(§86②)해 완성 부동산 거래, 조합원 자격 무의미(제한 실효)",
                "근거": citations + [_cite("이전고시 다음 날 소유권 취득 → 등기 촉탁", "도시정비법 §86②·§88①", "A"),
                                  _cite("이전고시 후엔 소유권 양도로 조합원 지위가 자동승계되지 않음",
                                        "대법원 2022두52874 (2024-04-25)", "A")], "플래그": flags}

    if not in_speculation_overheated_zone:
        return {"조합원지위승계가능": True, "사유": "투기과열지구 아님 — §39② 미적용",
                "근거": citations, "플래그": ["투기과열지구 지정은 상시 변동 — search_law(admrul)로 거래 시점 재확인 필수"]}

    if project_type == "재건축":
        trigger, basis = association_established, "§39②본문(재건축=조합설립인가 후)"
    elif project_type == "재개발":
        trigger, basis = management_disposal_approved, "§39②본문(재개발=관리처분계획인가 후)"
        # 경과규정 — 재개발 제한은 법 14943호 부칙 §1·§2로 2018-01-24 시행,
        # '시행 후 최초로 사업시행인가를 신청하는 경우부터' 적용 (2026-08-24 부칙 원문 실측)
        if trigger:
            if permit_application_date and permit_application_date < "2018-01-24":
                return {"조합원지위승계가능": True,
                        "사유": f"재개발 제한 미적용 — 사업시행인가 최초 신청일 {permit_application_date}이 "
                              "2018-01-24 전이라 구법(제한 없음) 적용(법 14943호 부칙 §2)",
                        "근거": citations + [_cite("재개발 조합원 자격 취득 제한은 2018-01-24 시행 후 최초로 "
                                                "사업시행인가를 신청하는 경우부터",
                                                "법 14943호 부칙 §1 단서·§2", "A")],
                        "플래그": ["신청일은 '최초' 신청 기준 — 변경신청·재신청 이력이 있으면 최초 신청일 "
                                 "증빙(인가신청 접수증 등) 확인"]}
            if not permit_application_date:
                flags.append("재개발 제한은 2018-01-24 이후 최초 사업시행인가 신청 구역부터(법 14943호 부칙 "
                             "§2) — 신청일 미입력이라 현행 제한을 가정. 2018-01-24 전 신청 구역이면 제한 없음")
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


# ── 12. 트리④ 비과세 요건 (소법 §89·영 §154 — 판정 결과를 judge_transfer_reliefs 입력으로) ──
_R154_5HO_SALE = ("매매", "분양")          # 5호가 말하는 '매매계약'에 해당하는 취득원인
_R154_5HO_SUCCESSION = ("증여", "상속")    # 동일세대원 승계면 원 계약자 지위를 잇는다


def _r154_5ho(contract_before, legacy_flag, deposit_full, no_home, cause,
              same_household) -> tuple[bool, str]:
    """영 §154①5호(조정 공고 전 계약) 거주요건 배제 판정 → (배제여부, 사유).

    구버전은 boolean 하나로 받아 계약금 일부 지급·계약 당시 유주택을 구분하지 못했다.
    2026-08-24 예규 회귀 검증으로 사실 4개 분해가 확정됐다.
    """
    if contract_before is None:                 # 새 인자 미사용 — 구버전 호출 하위호환
        contract_before = bool(legacy_flag)
    if not contract_before:
        return False, ""
    if not deposit_full:
        return False, "계약금을 일부만 지급 — 전액 지급이라야 5호 해당(기준-2024-법규재산-0173)"
    if not no_home:
        return False, "계약 당시 세대가 유주택 — 이후 세대분리해도 거주요건 적용(서면-2020-부동산-6165)"
    if cause in _R154_5HO_SALE:
        return True, "조정 공고 전 매매(분양)계약 + 계약금 전액 지급 + 계약금 지급일 무주택"
    if cause in _R154_5HO_SUCCESSION:
        if same_household:
            return True, (f"동일세대원 간 {cause}로 원 계약자의 지위 승계 — 거주요건 미적용"
                          "(증여 서면-2023-법규재산-2724 / 상속 서면-2020-법령해석재산-3884)")
        return False, (f"별도세대원으로부터의 {cause} 취득 — 5호는 '매매계약' 한정이라 배제 불가"
                       "(기재부 조세법령운용과-988·법규재산-2823)")
    return False, f"{cause}은(는) '매매계약'이 아니므로 5호 배제 불가(서면-2020-법령해석재산-3871)"


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
    contract_before_adjusted_announce: bool | None = None,
    deposit_paid_in_full: bool = True,
    no_home_at_contract: bool = True,
    same_household_succession: bool = False,
    partial_non_residence_unavoidable: bool = False,
    sangsaeng_nonresident_contract: bool = False,
) -> dict:
    """트리④ — 1세대1주택 비과세 요건 판정 (소법 §89①3호·영 §154, 노드 N154 계열).

    입력은 트리①(세대)·트리②(주택수)의 출력을 전제: is_one_household_one_home.
    holding_years는 비과세용 보유기간(§95④ 준용 기산 — 장특공·세율 기산과 별개, B5).
    acquired_in_adjusted_area: '취득 당시' 조정대상지역 여부 — 현재 지정현황이 아니라
    취득시점 지정이력 기준(B2). 입주권·분양권 승계취득은 사용승인일 기준(대조 143346).
    waiver_reason: ""|건설임대5년거주|수용|해외이주2년|취학근무국외|부득이1년거주 (§154①1~3호).
    sangsaeng_rental_ok: 상생임대 3요건 충족(§155의3 — 거주요건만 배제, N155의3-1).
      sangsaeng_nonresident_contract=True면 특례가 무효화된다(비거주자 체결 계약, 서면-2025-부동산-0225).

    §154①5호(조정 공고 전 계약)는 단일 boolean으로 판정할 수 없어 사실 4개로 분해한다
    (2026-08-24 예규 회귀 검증에서 확정 — 종전 pre_announce_contract_no_home 하나로는
    계약금 전액 지급 여부·계약 당시 무주택 여부를 표현하지 못해 오판정했다):
      contract_before_adjusted_announce: 조정대상지역 공고 전 계약 체결
      deposit_paid_in_full: 계약금 '전액' 지급 — 일부 지급이면 배제 불가(기준-2024-법규재산-0173)
      no_home_at_contract: 계약금 지급일 현재 세대 무주택 — 유주택이면 이후 세대분리해도
        거주요건 적용(서면-2020-부동산-6165)
      acquisition_cause: 매매|분양|증여|상속|자가건설|조합가입 — 5호는 '매매계약' 한정이라
        자가건설·조합가입은 배제 불가(서면-2020-법령해석재산-3871)
      same_household_succession: 동일세대원 간 증여·상속은 원 계약자의 지위를 승계해 배제 유지
        (증여 서면-2023-법규재산-2724 / 상속 서면-2020-법령해석재산-3884). 별도세대 승계는 배제 불가
        (기재부 조세법령운용과-988).
    pre_announce_contract_no_home: 위 4개를 한 번에 주는 구버전 인자(하위호환). 새 인자가
      주어지지 않은 경우에만 쓰인다.
    partial_non_residence_unavoidable: 세대원 일부가 부득이한 사유로 처음부터 미거주 —
      나머지 세대원이 충족하면 1세대가 거주한 것으로 본다(서면-2018-부동산-0442, D급→B급 상향).
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
            sangsaeng_ok = sangsaeng_rental_ok and not sangsaeng_nonresident_contract
            if sangsaeng_rental_ok and sangsaeng_nonresident_contract:
                citations.append(_cite("비거주자가 직전임대차 또는 상생임대차 계약을 체결 — 상생임대주택 특례 대상 아님",
                                       "영 §155의3① + 서면-2025-부동산-0225", "A"))
                flags.append("상생임대 특례가 무효화돼 거주요건이 되살아난다 — 계약 체결 당시 거주자 신분 확인 필요")
            exempt_5ho, reason_5ho = _r154_5ho(
                contract_before_adjusted_announce, pre_announce_contract_no_home,
                deposit_paid_in_full, no_home_at_contract, acquisition_cause,
                same_household_succession)

            if sangsaeng_ok:
                citations.append(_cite("상생임대주택 — 직전임대 1년6개월↑+5%↓ 인상 계약(2021-12-20~2026-12-31 체결)+임대 2년↑ → 거주기간 제한 배제", "영 §155의3①", "B"))
                flags.append("상생임대 특례적용신고서+계약서 2건 제출 요건(§155의3⑤) — 일몰 2026-12-31 감시")
                flags.append("상생임대 세부요건(직전임대차 성립·기간 합산·갱신 처리)은 이 함수가 판정하지 않는다 "
                             "— 예규 8건이 회귀셋 대기 중(다른 임차인 1년 이하 2계약 합산 불가, 4년 단일계약 "
                             "임의분할 불가, 2년→1년→2년 순차는 1·2차를 직전임대차로 봄 등)")
            elif exempt_5ho:
                citations.append(_cite(f"§154①5호 거주요건 배제 — {reason_5ho}", "영 §154①5호", "A"))
            else:
                reside_ok = residing_years >= 2.0
                if reason_5ho:
                    citations.append(_cite(f"§154①5호 배제 불가 — {reason_5ho}", "영 §154①5호 + 예규", "A"))
                if partial_non_residence_unavoidable and reside_ok:
                    citations.append(_cite("세대원 일부가 부득이한 사유로 처음부터 미거주 — 나머지 세대원이 충족하면 "
                                           "1세대가 거주한 것으로 본다", "서면-2018-부동산-0442", "B"))
                citations.append(_cite(f"취득 당시 조정대상지역 — 거주 {residing_years}년(2년↑: {reside_ok}, 주민등록표 기준·공동상속은 최장 상속인 기준)", "영 §154①·N154-6·N154-12", "B"))
                if not reside_ok:
                    flags.append("거주요건 대체 경로 검토: 상생임대(§155의3)·세대원 일부 부득이 미거주"
                                 "(서면-2018-부동산-0442)")
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


# ── 13. 출력 포맷터 — 상담 결과의 표준 출력 (설계 §11 출력규약의 코드화) ──────
# 규약: ①단일 숫자 금지 — 쟁점(D~F급)이 있으면 시나리오 2개 이상 병기 강제
#      ②차액 = 리드 스코어(전문가 매칭 우선순위) ③단정 금지 — 세무사법 안전선 문구 필수
#      ④근거 없는 시나리오 등재 거부(근거 필수 원칙)
LEAD_THRESHOLD_DEFAULT = 5_000_000  # 차액이 이 이상이면 전문가 검토 권장 (설계 §11 가안)

_DISCLAIMER = ("본 결과는 기재된 사실관계와 현행 법문·공개 해석례를 기준으로 한 참고용 산정이며 "
               "세무대리 업무가 아닙니다. 개별 사실관계에 따라 결론이 달라질 수 있으므로 "
               "실행 전 세무사 등 전문가 검토를 권장합니다.")


def format_consultation_output(
    scenarios: list[dict],
    dividing_issue: str = "",
    issue_grade: str = "",
    lead_threshold: int = LEAD_THRESHOLD_DEFAULT,
    extra_flags: list[dict] | None = None,
) -> dict:
    """상담 결과 표준 출력 생성 (설계 §11 — 시나리오 병기·차액 리드스코어·단정 금지).

    scenarios 원소: {"라벨": str, "세액": int, "전제": str(이 시나리오가 성립하는 조건),
    "근거": [str|dict]} — 근거 비어 있으면 해당 시나리오 등재 거부.
    dividing_issue: 시나리오를 가르는 쟁점(2개 이상일 때 필수).
    issue_grade: 쟁점의 근거등급 A~F — A~C(법령 명확)는 시나리오 1개(결정적) 허용,
    D~F(해석·사실판단)는 반드시 2개 이상 병기(단일 숫자 금지 규약).
    """
    if not scenarios:
        return {"오류": "시나리오가 없습니다"}
    for s in scenarios:
        if not s.get("근거"):
            return {"오류": f"근거 없는 시나리오 등재 거부(근거 필수 원칙): {s.get('라벨', '?')}"}
        if "세액" not in s or "라벨" not in s:
            return {"오류": f"시나리오에 라벨·세액 필수: {s}"}

    grade = (issue_grade or "").upper()[:1]
    contested = grade in ("D", "E", "F") or len(scenarios) >= 2
    if grade in ("D", "E", "F") and len(scenarios) < 2:
        return {"오류": f"쟁점 등급 {grade}(해석·사실판단)인데 시나리오가 1개 — 단일 숫자 금지 규약 위반. "
                        "포함/제외(성립/불성립) 양쪽 세액을 모두 계산해 넘길 것"}
    if len(scenarios) >= 2 and not dividing_issue:
        return {"오류": "시나리오 2개 이상이면 dividing_issue(갈리는 쟁점) 필수"}

    ordered = sorted(scenarios, key=lambda s: s["세액"])
    spread = ordered[-1]["세액"] - ordered[0]["세액"]
    if spread >= 100_000_000:
        lead_tier = "최상(1억↑)"
    elif spread >= 30_000_000:
        lead_tier = "상(3천만↑)"
    elif spread >= lead_threshold:
        lead_tier = "중(기준 이상)"
    else:
        lead_tier = "하(기준 미만)"
    needs_expert = spread >= lead_threshold and contested

    lines = []
    for s in ordered:
        lines.append(f"[{s['라벨']}] {s['세액']:,}원 — 전제: {s.get('전제', '')}")
    if len(ordered) >= 2:
        lines.append(f"갈리는 쟁점: {dividing_issue}" + (f" (근거등급 {grade} — 사실관계 의존)" if grade else ""))
        lines.append(f"차액: {spread:,}원")
    if needs_expert:
        lines.append("→ 차액이 커서 전문가 검토의 기대가치가 높습니다. 세무사 검토를 권장합니다.")
    lines.append(_DISCLAIMER)

    return {
        "시나리오": ordered,
        "차액": spread,
        "리드스코어": lead_tier,
        "전문가검토권장": needs_expert,
        "결정적": (not contested) and len(ordered) == 1,
        "갈리는쟁점": dividing_issue,
        "출력문": "\n".join(lines),
        "플래그": extra_flags or [],
    }


# ── 13의2. '취득 당시' 조정대상지역 판정 (트리④ B2 — 이력 lookup) ─────────────
import json as _json

_ADJ_HISTORY_PATH = None  # 지연 로드 — 서버·스크립트 양쪽에서 경로 고정


_SIDO_NAMES = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
               "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주")
_SIDO_SUFFIX = ("특별자치시", "특별자치도", "특별시", "광역시", "도", "시")


def _adj_split_region(norm: str) -> tuple[str | None, str]:
    """공백 제거된 지역 문자열에서 (시도, 나머지)를 뗀다. 시도 없으면 (None, 전체)."""
    for s in _SIDO_NAMES:
        if norm.startswith(s):
            rest = norm[len(s):]
            for suf in _SIDO_SUFFIX:
                if rest.startswith(suf):
                    rest = rest[len(suf):]
                    break
            return s, rest
    return None, norm


def judge_adjusted_area_at_date(region: str, target_date: str) -> dict:
    """특정 날짜에 해당 지역이 조정대상지역이었는지 판정 (data/adj_regions_history.json replay).

    region: "서울 마포구"·"성남시 분당구" 등. target_date: YYYY-MM-DD (취득일 — 분양권·입주권
    승계는 사용승인일 기준임을 주의). 이력 events를 시행일 오름차순으로 재생해 해당 날짜의
    지정 상태를 복원한다(2026-08-22 과거분 백필). 부분지정·시군구 미만 모호 입력은 단정하지
    않고 확인을 요구한다 — 그럴듯한 오답 금지 원칙. 결과의 acquired_in_adjusted_area를
    judge_exemption_requirements에 연결.
    """
    global _ADJ_HISTORY_PATH
    if _ADJ_HISTORY_PATH is None:
        import os
        _ADJ_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "data", "adj_regions_history.json")
    try:
        hist = _json.load(open(_ADJ_HISTORY_PATH, encoding="utf-8"))
    except FileNotFoundError:
        return {"판정": "판단불가", "사유": "adj_regions_history.json 없음"}

    d = target_date
    flags = ["분양권·입주권 승계취득은 취득시기=사용승인일 — 그 날짜로 다시 조회할 것 (대조 143346)"]

    # 세법상 조정대상지역 개념은 2017-08-03(소득세법 시행령 §154② 간주표)부터
    if d < "2017-08-03":
        return {"판정": "비조정(세법상 조정대상지역 개념 이전)", "acquired_in_adjusted_area": False,
                "확신도": "B(소득세법 시행령 §154② 간주표 기산일)",
                "근거": [{"규칙": "세법효력시기", "근거": hist["meta"]["세법효력시기"], "등급": "B"}],
                "플래그": flags + ["2016-11-03~2017-08-02의 청약·전매 규제는 별개 축 — 세법 판정에 사용 금지"]}

    rn = region.replace(" ", "")
    in_sido, in_core = _adj_split_region(rn)

    # 이벤트 재생 — 키별 최종 상태 복원
    state: dict[str, dict] = {}
    for ev in sorted(hist["events"], key=lambda e: e["시행일"]):
        if ev["시행일"] > d:
            break
        for ent in ev["지역"]:
            kn = ent["키"].replace(" ", "")
            state[kn] = {
                "상태": ev["유형"], "범위": ent.get("범위", "전체"), "상세": ent.get("상세", ""),
                "등급": ev["등급"], "근거": ev["근거"], "시행일": ev["시행일"],
            }

    # 입력과 키 매칭 — strong: 키가 입력에 포함(입력이 키 이상으로 구체적) / weak: 그 반대
    # '용인시 처인구' vs '용인 처인구' 같은 市 표기 생략을 잇기 위해 비선두 '시'를 지운 형태로
    # 비교한다(선두 글자는 유지 — '시흥시'→'시흥'이 '흥'이 되지 않게).
    def _canon(s: str) -> str:
        return s[:1] + s[1:].replace("시", "") if s else s

    rn_c, in_core_c = _canon(rn), _canon(in_core)
    strong, weak = [], []
    for kn, st_ in state.items():
        k_sido, k_core = _adj_split_region(kn)
        k_core_c = _canon(k_core)
        if in_sido and k_sido != in_sido:
            continue
        if k_core and k_core_c in rn_c:
            strong.append((k_core, st_))
        elif in_core and in_core_c in k_core_c:
            weak.append((k_core, st_))
        elif not in_core and in_sido == k_sido:
            weak.append((k_core, st_))

    def _verdict(st_: dict, note: str = "") -> dict:
        cit = [{"규칙": "이력 replay", "근거": f"{st_['근거']} (시행 {st_['시행일']})", "등급": st_["등급"]}]
        fl = list(flags)
        if st_["등급"] not in ("A", "B"):
            fl.append(f"판정 근거 사건이 {st_['등급']}급(공고 원문 미열람) — 세액 확정 전 원문 대조 권장")
        if note:
            fl.append(note)
        if st_["상태"] == "지정" and st_["범위"] == "부분":
            return {"판정": "부분지정 구간 — 소재 읍면동·지구 확인 필요", "acquired_in_adjusted_area": None,
                    "부분상세": st_["상세"], "확신도": st_["등급"], "근거": cit, "플래그": fl}
        if st_["상태"] == "지정":
            return {"판정": "조정대상지역", "acquired_in_adjusted_area": True,
                    "확신도": st_["등급"], "근거": cit, "플래그": fl}
        return {"판정": "비조정(해제 구간)", "acquired_in_adjusted_area": False,
                "확신도": st_["등급"], "근거": cit, "플래그": fl}

    if strong:
        best_len = max(len(c) for c, _ in strong)
        best_core = next(c for c, _ in strong if len(c) == best_len)
        best_st = next(s for c, s in strong if len(c) == best_len)
        # 하위 키 충돌 가드: 입력이 상위 단위(예: '화성시')인데 그 하위 키(예: '화성시
        # 동탄구')의 상태가 다르면 단정 금지 — 그럴듯한 오답 방지
        subs = [
            (c2, s2) for kn2, s2 in state.items()
            for c2 in [_adj_split_region(kn2)[1]]
            if c2 != best_core and _canon(best_core) in _canon(c2) and _canon(c2) not in rn_c
            and (s2["상태"], s2["범위"]) != (best_st["상태"], best_st["범위"])
        ]
        if subs:
            return {"판정": "판단불가", "acquired_in_adjusted_area": None,
                    "사유": "하위 행정구역별로 지정 상태가 갈림 — 더 구체적으로 입력 필요: "
                            + ", ".join(sorted({c for c, _ in subs})) + f" (기준 {best_core})",
                    "근거": [{"규칙": "이력 replay", "근거": "data/adj_regions_history.json", "등급": "혼합"}],
                    "플래그": flags}
        return _verdict(best_st)
    if weak:
        distinct = {(s["상태"], s["범위"]) for _, s in weak}
        if len(distinct) == 1:
            note = ("하위 행정구역 단위 키 다수와 일치(상태 동일) — 구 단위까지 입력하면 더 정밀"
                    if len(weak) > 1 else "")
            return _verdict(weak[0][1], note)
        return {"판정": "판단불가", "acquired_in_adjusted_area": None,
                "사유": "하위 행정구역(구·군)별로 지정 상태가 갈림 — 구 단위까지 명시 필요: "
                        + ", ".join(sorted(c for c, _ in weak)),
                "근거": [{"규칙": "이력 replay", "근거": "data/adj_regions_history.json", "등급": "혼합"}],
                "플래그": flags}

    # 어떤 사건에도 등장한 적 없는 지역 — 연표상 지정 이력 없음
    return {"판정": "비조정(연표상 지정 이력 없음)", "acquired_in_adjusted_area": False,
            "확신도": "C(연표 완전성에 의존 — 2016~2022 사건은 공고 원문 미열람)",
            "근거": [{"규칙": "이력 replay", "근거": "data/adj_regions_history.json 전 사건 무관 지역", "등급": "C"}],
            "플래그": flags}


# ── 14. 상담 리포트 v2 — 소비자용 최종 양식 (2026-08-17 사용자 확정 양식) ──────
# 양식: 1. 최종결론(소비자는 결론만 원함 — 단 쟁점 있으면 전제 명시로 단정 금지 유지)
#      2. 근거(설명 ↔ 출처 1:1 매칭 강제 — 출처 없는 설명 등재 거부)
#      3. 소유자 맞춤형 추가질문 답변 정리(각 답변에도 근거 필수)
RULING_QUERY_MAP = {  # 쟁점 키워드 → search_tax_rulings 추천 쿼리 (③ 플래그-검색 연결)
    "세대": [("국세청해석", '"생계를 같이"'), ("국세청해석", '"세대분리"')],
    "별거": [("국세청해석", '"별거"')],
    "상생임대": [("국세청해석", '"상생임대"')],
    "동거봉양": [("국세청해석", '"동거봉양"')],
    "혼인": [("국세청해석", '"혼인 합가"')],
    "일시적": [("국세청해석", '"일시적 2주택"')],
    "조합원": [("국세청해석", '"조합원입주권"'), ("조세심판원", "조합원 지위 양도")],
    "재건축": [("국세청해석", '"재건축"')],
    "대체주택": [("국세청해석", '"대체주택"')],
    "상속주택": [("국세청해석", '"상속주택"')],
    "증여": [("국세청해석", '"증여 취득"')],
    "취득세": [("행안부해석", '"취득세 중과"'), ("조세심판원", "취득세 주택수")],
    "거주요건": [("국세청해석", '"거주요건"')],
    "고가주택": [("국세청해석", '"고가주택"')],
}


def suggest_ruling_queries(text: str) -> list[dict]:
    """쟁점 문구에서 해석례·심판례 추천 검색 쿼리 도출 — search_tax_rulings로 바로 실행 가능."""
    seen, out = set(), []
    for kw, queries in RULING_QUERY_MAP.items():
        if kw in text:
            for source, q in queries:
                if (source, q) not in seen:
                    seen.add((source, q))
                    out.append({"source": source, "query": q, "도구": "search_tax_rulings"})
    return out


def format_consultation_report(
    conclusion: str,
    evidences: list[dict],
    owner_qa: list[dict] | None = None,
    scenarios: list[dict] | None = None,
    dividing_issue: str = "",
    issue_grade: str = "",
    lead_threshold: int = LEAD_THRESHOLD_DEFAULT,
) -> dict:
    """소비자용 상담 리포트 최종 양식 — 1.최종결론 / 2.근거(설명↔출처 1:1) / 3.맞춤 Q&A.

    conclusion: 최종결론 한 단락. 쟁점(D~F급 시나리오 분기)이 있으면 결론에 전제를 명시할 것 —
    시나리오가 넘어오면 병기 요약을 결론 뒤에 자동 첨부(단정 금지 규약 유지).
    evidences 원소: {"설명": str, "출처": str, "등급": A~F} — 출처 없는 설명은 전체 리포트 거부
    (1:1 매칭 강제). owner_qa 원소: {"질문": str, "답변": str, "근거": str} — 근거 없는 답변 거부.
    scenarios·dividing_issue·issue_grade: format_consultation_output에 그대로 전달(선택).
    각 쟁점·질문 문구에서 해석례 추천검색(suggest_ruling_queries)을 자동 도출해 붙인다.
    """
    if not conclusion or not conclusion.strip():
        return {"오류": "최종결론은 필수"}
    if not evidences:
        return {"오류": "근거가 없는 결론은 출력 불가(근거 필수 원칙)"}
    for i, e in enumerate(evidences, 1):
        if not e.get("설명") or not e.get("출처"):
            return {"오류": f"근거 {i}번 — 설명과 출처는 1:1 필수 (누락: {'설명' if not e.get('설명') else '출처'})"}
    for i, qa in enumerate(owner_qa or [], 1):
        if not qa.get("질문") or not qa.get("답변"):
            return {"오류": f"Q&A {i}번 — 질문·답변 필수"}
        if not qa.get("근거"):
            return {"오류": f"Q&A {i}번 답변에 근거 없음 — 근거 없는 답변 등재 거부: {qa.get('질문')[:30]}"}

    scenario_block = None
    if scenarios:
        scenario_block = format_consultation_output(scenarios, dividing_issue, issue_grade, lead_threshold)
        if "오류" in scenario_block:
            return scenario_block

    lines = ["【1. 최종결론】", conclusion.strip()]
    if scenario_block and len(scenario_block["시나리오"]) >= 2:
        lines.append("")
        lines.append(f"(전제에 따라 갈립니다 — {dividing_issue}: "
                     + " / ".join(f"{s['라벨']} {s['세액']:,}원" for s in scenario_block["시나리오"])
                     + f", 차액 {scenario_block['차액']:,}원)")

    lines.append("")
    lines.append("【2. 근거】")
    for i, e in enumerate(evidences, 1):
        grade = f" [{e['등급']}급]" if e.get("등급") else ""
        lines.append(f"{i}. {e['설명']}")
        lines.append(f"   └ 출처: {e['출처']}{grade}")

    if owner_qa:
        lines.append("")
        lines.append("【3. 맞춤 질문 답변】")
        for i, qa in enumerate(owner_qa, 1):
            lines.append(f"Q{i}. {qa['질문']}")
            lines.append(f"A{i}. {qa['답변']}")
            lines.append(f"   └ 근거: {qa['근거']}")

    lines.append("")
    lines.append(_DISCLAIMER)

    issue_text = " ".join([dividing_issue] + [qa.get("질문", "") for qa in (owner_qa or [])])
    suggested = suggest_ruling_queries(issue_text)

    result = {
        "최종결론": conclusion.strip(),
        "근거": evidences,
        "맞춤QA": owner_qa or [],
        "리포트": "\n".join(lines),
        "추천검색": suggested,
    }
    if scenario_block:
        result["시나리오분석"] = {k: scenario_block[k] for k in ("시나리오", "차액", "리드스코어", "전문가검토권장")}
    return result


# ── 7. 임대소득세: 과세대상·주택수·분리과세 판정 ────────────────────────────
# 17차 순회 nodes_rental_income.json (15노드) — 트리⑤ 정본의 코드화.
RENTAL_NONTAX_PRICE = 1_200_000_000        # 비과세 1주택 기준시가 (§12제2호나목)
RENTAL_SEPARATE_LIMIT = 20_000_000         # 분리과세 기준 수입금액 (§14③7호)
RENTAL_SEPARATE_RATE = 0.14                # 분리과세 세율 (§64의2①2호가목)
RENTAL_EXPENSE_REGISTERED = 0.60           # 등록임대주택 필요경비율 (§64의2② 단서)
RENTAL_EXPENSE_PLAIN = 0.50                # 미등록 필요경비율 (§64의2② 본문)
RENTAL_DEDUCTION_REGISTERED = 4_000_000
RENTAL_DEDUCTION_PLAIN = 2_000_000
RENTAL_DEDUCTION_INCOME_CAP = 20_000_000   # 추가공제 조건 — 타 종합소득금액 2천만 이하
RENTAL_NO_REGISTRATION_PENALTY = 0.002     # 미등록 가산세 (§81의12①)
DEEMED_DEDUCTION = 300_000_000             # 간주임대료 산식 공제 3억 (영 §53③1호)
DEEMED_THRESHOLD_3HOMES = 300_000_000      # 3주택 요건 보증금 문턱 (§25①1호)
DEEMED_THRESHOLD_2HOMES = 1_200_000_000    # 2주택 요건 보증금 문턱 (영 §53①)
DEEMED_2HOMES_PRICE = 1_200_000_000        # 2주택 카운트 대상 기준시가 (§25①2호)
DEEMED_2HOMES_FROM_YEAR = 2026             # 부칙 제19933호(2023-12-31) §1제1호 시행일
DEEMED_RATIO = 0.60                        # 산식 60/100
SMALL_HOUSE_AREA = 40.0                    # 소형주택 전용면적 (§25① 단서)
SMALL_HOUSE_PRICE = 200_000_000            # 소형주택 기준시가
SMALL_HOUSE_SUNSET_YEAR = 2026             # 주택수 제외 일몰 2026-12-31
DEPOSIT_INTEREST_RATE_CURRENT = 0.031      # 정기예금이자율 현행 (규칙 §23①, 2025-03-21 개정으로 설정)

# 정기예금이자율 귀속연도별 이력 — 규칙 §23①은 매년 3월경 개정되는 연례 상수다.
# 각 개정 부칙의 경과조치가 "이 규칙 시행일이 **속하는 과세기간 전에** 발생한 소득분에
# 대해서는 종전의 규정에 따른다"이므로, 개정 시행일이 속한 과세기간(=시행연도)부터 신 요율이
# 적용된다. 값이 바뀐 판만 추린 원자료는 data/legal_nodes/itr_art23_history.json (eflaw 전수 순회).
# ⚠️ 2026-01-02 개정은 요율 변경이 아니라 기획재정부→재정경제부 부처명 변경이다(값 동일).
DEPOSIT_INTEREST_RATE_BY_YEAR = {
    2018: 0.018,   # 규칙 개정 2018-03-21 (1천분의 18)
    2019: 0.021,   # 2019-03-20 (21)
    2020: 0.018,   # 2020-03-13 (18)
    2021: 0.012,   # 2021-03-16 (12)
    2022: 0.012,   # 2022년 개정 없음 — 2021년 값 유지
    2023: 0.029,   # 2023-03-20 (29)
    2024: 0.035,   # 2024-03-22 (35)
    2025: 0.031,   # 2025-03-21 (31)
    2026: 0.031,   # 2026-01-02 개정은 부처명 변경뿐 — 요율 유지
}
DEPOSIT_RATE_MIN_YEAR = min(DEPOSIT_INTEREST_RATE_BY_YEAR)


def deposit_interest_rate_for(tax_year: int) -> tuple[float | None, str]:
    """귀속연도별 정기예금이자율 (규칙 §23① — 노드 N규칙23-1).

    미수록 구간은 추정하지 않고 None을 반환한다(입력값 출처등급 규약 — 근거 없는 숫자 금지).
    2017년 이전은 국세기본법 §45의2 경정청구 기한(5년) 밖이라 순회 대상에서 제외했다.
    """
    if tax_year in DEPOSIT_INTEREST_RATE_BY_YEAR:
        return DEPOSIT_INTEREST_RATE_BY_YEAR[tax_year], "규칙 §23① 개정이력 확정분"
    if tax_year < DEPOSIT_RATE_MIN_YEAR:
        return None, ("%d 과세기간은 이자율 이력 미확보(%d년 이후만 순회) — 경정청구 기한 밖 구간"
                      % (tax_year, DEPOSIT_RATE_MIN_YEAR))
    # 미래 연도: 아직 개정 전이면 현행값이 그대로 적용되나, 3월 개정 가능성이 남아 있다.
    return DEPOSIT_INTEREST_RATE_CURRENT, ("%d 과세기간 요율 미개정 — 현행 %.1f%% 잠정 적용, "
                                           "매년 3월경 규칙 개정 확인 필요"
                                           % (tax_year, DEPOSIT_INTEREST_RATE_CURRENT * 100))


def _is_small_house(home: dict) -> bool:
    """소형주택(주택수 제외 대상) — 40㎡ 이하 **and** 기준시가 2억 이하 (§25① 단서)."""
    area = home.get("전용면적")
    price = home.get("기준시가")
    if area is None or price is None:
        return False
    return float(area) <= SMALL_HOUSE_AREA and int(price) <= SMALL_HOUSE_PRICE


def _rental_price_cap(tax_year: int | None) -> int:
    """비과세·소수지분 나목 고가주택 기준 — 12억은 2023 과세기간부터(소법 2022-12-31 개정), 종전 9억."""
    if tax_year and int(tax_year) <= 2022:
        return 900_000_000
    return RENTAL_NONTAX_PRICE


def count_rental_homes(own_homes: list[dict], spouse_homes: list[dict] | None = None,
                       tax_year: int | None = None) -> dict:
    """임대소득세 주택수 산정 — **부부합산** (영 §8의2③, 노드 N영8의2-3).

    ⚠️ 양도세(1세대)·종부세(개인별)·취득세(세대)·도정법(법률혼+주민등록표)과 다른 제5의 기준.
    각 원소: {"라벨": str, "기준시가": int, "전용면적": float,
              "공동소유": bool, "지분율": float(0~1), "최대지분자": bool,
              "연임대수입": int, "전대": bool, "국외": bool}
    다가구주택은 1개로 넣고, 구분등기된 경우에만 호수만큼 나눠 넣는다(③1호).
    tax_year: ③2호나목 고가 기준(12억, 2022 귀속 이전 9억) 판정용 — 미지정 시 현행 12억.
    """
    rows, counted = [], 0
    for owner, homes in (("본인", own_homes or []), ("배우자", spouse_homes or [])):
        for h in homes:
            label = h.get("라벨") or (owner + " 주택")
            include, why = True, "산입"
            if h.get("공동소유"):
                share = float(h.get("지분율") or 0)
                price = int(h.get("기준시가") or 0)
                income = int(h.get("연임대수입") or 0)
                if h.get("최대지분자"):
                    why = "공동소유 — 최대지분자로 산입 (③2호 본문)"
                elif income >= 6_000_000:
                    why = "공동소유 소수지분이나 연 임대수입 600만원 이상 — 산입 (③2호 가목)"
                elif price > _rental_price_cap(tax_year) and share > 0.30:
                    why = (f"공동소유 소수지분이나 기준시가 {_rental_price_cap(tax_year) // 100_000_000}억 초과"
                           "+지분 30% 초과 — 산입 (③2호 나목)")
                else:
                    include, why = False, "공동소유 소수지분 — 최대지분자 소유로 계산 (③2호)"
            elif h.get("전대"):
                why = "전대·전전세 — 임차인의 주택으로 계산 (③3호)"
            if include:
                counted += 1
            rows.append({"소유자": owner, "라벨": label, "산입": include, "사유": why,
                         "소형주택": _is_small_house(h)})

    flags = []
    if any(h.get("국외") for h in (own_homes or []) + (spouse_homes or [])):
        flags.append("국외 주택 포함 — 비과세 판정에서 국외 주택 임대소득은 과세 대상(§12제2호나목). "
                     "주택수 산정 시 국외분 포함 여부는 법문에 명시가 없어 회색지대(전문가 확인 권장)")
    if spouse_homes is None:
        flags.append("배우자 주택 미입력 — 부부합산이 법정 기준이므로 주택수가 과소산정될 수 있음 (RI-2)")
    return {
        "주택수": counted,
        "본인": sum(1 for r in rows if r["소유자"] == "본인" and r["산입"]),
        "배우자": sum(1 for r in rows if r["소유자"] == "배우자" and r["산입"]),
        "항목별": rows,
        "소형주택수": sum(1 for r in rows if r["산입"] and r["소형주택"]),
        "근거": [_cite("주택수는 부부합산", "소득세법 시행령 §8의2③4호 (N영8의2-3)", "A"),
               _cite("다가구=1개, 공동소유=최대지분자, 전대=임차인", "영 §8의2③1~3호", "A")],
        "플래그": flags,
    }


def calc_deemed_rent(tax_year: int, deposits: list[dict], rental_home_count: int,
                     deposit_interest_rate: float | None = None,
                     financial_income: int = 0) -> dict:
    """주택 보증금 간주임대료 (소법 §25①·영 §53③1호 — 노드 N25-1-1·N25-1-2·N영53-3-1).

    deposits 각 원소: {"라벨", "보증금": int, "일수": int(기본 365), "기준시가": int, "전용면적": float}
    rental_home_count: count_rental_homes의 부부합산 주택수 (영 §53⑧이 §8의2③을 준용).
    """
    deposits = deposits or []
    days_in_year = 366 if (tax_year % 4 == 0 and (tax_year % 100 != 0 or tax_year % 400 == 0)) else 365
    flags = []
    if deposit_interest_rate is not None:
        rate, rate_note = float(deposit_interest_rate), "호출자 지정값"
        flags.append("정기예금이자율 %.1f%%는 호출자 지정값 — 규칙 §23① 개정이력(%d년 %.1f%%)과 대조할 것"
                     % (rate * 100, tax_year,
                        (DEPOSIT_INTEREST_RATE_BY_YEAR.get(tax_year) or DEPOSIT_INTEREST_RATE_CURRENT) * 100))
    else:
        rate, rate_note = deposit_interest_rate_for(tax_year)
        if rate is None:
            return {"간주임대료": None, "적용": None, "판단불가": True,
                    "판정": "판단불가 — " + rate_note,
                    "근거": [_cite("정기예금이자율 미확보 구간", "소득세법 시행규칙 §23① (N규칙23-1)", "A-")],
                    "플래그": ["이자율을 추정하지 않고 판단불가 반환 — 해당 연도 규칙 원문을 확인해 "
                             "deposit_interest_rate로 직접 지정하면 계산 가능"]}
        flags.append("정기예금이자율 %.1f%% 적용(%d 과세기간, 규칙 §23①) — %s" % (rate * 100, tax_year, rate_note))

    # 소형주택 제외 (일몰 2026-12-31)
    sunset_alive = tax_year <= SMALL_HOUSE_SUNSET_YEAR
    small = [d for d in deposits if _is_small_house(d)]
    if small and not sunset_alive:
        flags.append("소형주택 주택수 제외 특례는 2026-12-31 일몰 — %d 과세기간은 연장 여부 확인 필요 (RI-4)" % tax_year)
    eligible = [d for d in deposits if not (sunset_alive and _is_small_house(d))]
    effective_homes = rental_home_count - (len(small) if sunset_alive else 0)

    total_deposit = sum(int(d.get("보증금", 0)) for d in eligible)
    high_price = [d for d in eligible if int(d.get("기준시가") or 0) > DEEMED_2HOMES_PRICE]
    high_deposit = sum(int(d.get("보증금", 0)) for d in high_price)

    applies, ground, target = False, None, []
    if effective_homes >= 3 and total_deposit > DEEMED_THRESHOLD_3HOMES:
        applies, target = True, eligible
        ground = _cite("3주택 이상 + 보증금 합계 3억 초과", "소득세법 §25①1호 (N25-1-1)", "A")
    elif len(high_price) == 2 and high_deposit > DEEMED_THRESHOLD_2HOMES:
        if tax_year >= DEEMED_2HOMES_FROM_YEAR:
            applies, target = True, high_price
            ground = _cite("2주택(기준시가 12억 초과 주택만 카운트) + 보증금 합계 12억 초과",
                           "소득세법 §25①2호·영 §53① — 2026-01-01 시행 (N25-1-2)", "A")
            flags.append("⭐2주택 간주임대료는 2026 과세기간부터 최초 적용 — 시중 통설('3주택 이상')과 갈리는 구간 (RI-1)")
            flags.append("2주택 요건의 문턱은 12억이나 영 §53③1호 산식의 공제액은 3억으로 유지 — "
                         "법문 문언 그대로 적용(개정 감시 대상)")
        else:
            ground = _cite("2주택 간주임대료 요건은 충족하나 시행 전",
                           "부칙 제19933호 §1제1호(시행 2026-01-01)·§15 경과조치 — %d 과세기간은 종전 규정" % tax_year, "A")
            flags.append("%d 과세기간은 2주택 간주임대료 시행 전 — 간주임대료 없음 (부칙 §15)" % tax_year)

    if not applies:
        return {"간주임대료": 0, "적용": False,
                "판정": ground["규칙"] if ground else "요건 미달 (주택수 %d, 보증금 %s원)" % (effective_homes, format(total_deposit, ",")),
                "근거": [ground] if ground else [_cite("간주임대료 요건 미달", "소득세법 §25①", "A")],
                "플래그": flags}

    # 보증금 적수가 가장 큰 주택부터 3억원을 순서대로 차감 (영 §53③1호 괄호)
    ordered = sorted(target, key=lambda d: int(d.get("보증금", 0)) * int(d.get("일수", days_in_year)), reverse=True)
    remain, jeoksu, breakdown = DEEMED_DEDUCTION, 0, []
    for d in ordered:
        principal = int(d.get("보증금", 0))
        days = int(d.get("일수", days_in_year))
        deducted = min(remain, principal)
        remain -= deducted
        base = principal - deducted
        jeoksu += base * days
        breakdown.append({"라벨": d.get("라벨", ""), "보증금": principal, "3억차감": deducted,
                          "산입원금": base, "일수": days, "적수": base * days})

    gross = jeoksu * DEEMED_RATIO / days_in_year * rate
    deemed = max(0, int(gross) - int(financial_income))
    return {
        "간주임대료": deemed,
        "적용": True,
        "판정": ground["규칙"],
        "산식": "(보증금−3억)적수 %s × 60/100 × 1/%d × %.3f%% − 금융수익 %s" % (
            format(jeoksu, ","), days_in_year, rate * 100, format(int(financial_income), ",")),
        "차감전개": breakdown,
        "근거": [ground, _cite("산식·적수·순서 차감", "소득세법 시행령 §53③1호 (N영53-3-1)", "A"),
               _cite("정기예금이자율 %.1f%% (%d 과세기간)" % (rate * 100, tax_year),
                     "소득세법 시행규칙 §23① — 개정 부칙 경과조치상 시행일이 속한 과세기간부터 적용 (N규칙23-1)", "A")],
        "플래그": flags + ["추계신고 시(영 §53④)는 금융수익 차감이 없다 — 장부 여부로 산식이 갈림"],
    }


def calc_rental_income_tax(registered_revenue: int = 0, unregistered_revenue: int = 0,
                           other_comprehensive_income: int | None = None,
                           tax_reduction: int = 0) -> dict:
    """분리과세 주택임대소득 세액 (소법 §64의2①②·영 §122의2⑦ — 노드 N64의2-1·2·N영122의2-7).

    registered_revenue: 등록임대주택(민특법 등록 + 세법 사업자등록 + 임대료 5% 상한 동시 충족)에서
    발생한 수입금액. unregistered_revenue: 그 외. 둘의 합이 2천만원 이하일 때만 분리과세 대상.
    other_comprehensive_income: 분리과세 주택임대소득을 제외한 종합소득금액 — 2천만원 이하일 때만
    추가공제(200만/400만) 적용. None이면 공제 없이 계산하고 플래그를 단다.
    """
    reg, plain = int(registered_revenue or 0), int(unregistered_revenue or 0)
    total = reg + plain
    flags = []
    if total > RENTAL_SEPARATE_LIMIT:
        return {"오류": "총수입금액 %s원 — 2천만원 초과는 분리과세 대상이 아님(전액 종합과세, §14③7호)" % format(total, ",")}

    expense = reg * RENTAL_EXPENSE_REGISTERED + plain * RENTAL_EXPENSE_PLAIN
    if other_comprehensive_income is None:
        deduction = 0
        flags.append("타 종합소득금액 미입력 — 추가공제(등록 400만/미등록 200만)는 타 종합소득금액 "
                     "2천만원 이하 조건부라 미적용으로 계산함. 입력 시 세액이 줄어들 수 있음 (RI-3)")
    elif int(other_comprehensive_income) <= RENTAL_DEDUCTION_INCOME_CAP:
        deduction = ((RENTAL_DEDUCTION_REGISTERED * reg + RENTAL_DEDUCTION_PLAIN * plain) / total) if total else 0
    else:
        deduction = 0
        flags.append("타 종합소득금액 %s원 > 2천만원 — 추가공제 배제 (§64의2② 괄호)"
                     % format(int(other_comprehensive_income), ","))

    income = max(0, total - expense - deduction)
    tax = max(0, income * RENTAL_SEPARATE_RATE - int(tax_reduction or 0))
    return {
        "총수입금액": total,
        "필요경비": int(expense),
        "추가공제": int(deduction),
        "사업소득금액": int(income),
        "분리과세세액": int(tax),
        "적용세율": RENTAL_SEPARATE_RATE,
        "산식": "(%s − 경비 %s − 공제 %s) × 14%%%s" % (
            format(total, ","), format(int(expense), ","), format(int(deduction), ","),
            (" − 감면 %s" % format(int(tax_reduction), ",")) if tax_reduction else ""),
        "근거": [
            _cite("필요경비 50%(등록임대 60%)·추가공제 200만(등록 400만, 타 종합소득 2천만 이하 조건)",
                  "소득세법 §64의2② (N64의2-2)", "A"),
            _cite("혼합 시 수입금액 비율 안분", "소득세법 시행령 §122의2⑦2·3호 (N영122의2-7)", "A"),
            _cite("분리과세 세율 14%", "소득세법 §64의2①2호가목 (N64의2-1)", "A"),
        ],
        "플래그": flags + ["§64의2①은 종합과세 결정세액과 비교해 납세자가 유리한 쪽을 선택하는 구조 — "
                       "타 소득 입력 시 종합과세안과 비교 필요"],
    }


def judge_rental_income_tax(
    tax_year: int,
    own_homes: list[dict],
    spouse_homes: list[dict] | None = None,
    monthly_rent_revenue: int = 0,
    registered_rent_revenue: int = 0,
    deposits: list[dict] | None = None,
    other_comprehensive_income: int | None = None,
    business_registered: bool = True,
    revenue_before_registration: int = 0,
    deposit_interest_rate: float | None = None,
    financial_income: int = 0,
    tax_reduction: int = 0,
) -> dict:
    """트리⑤ — 주택임대 종합소득세 판정 R0~R6 (17차 순회 노드 15종).

    tax_year: 과세연도(필수 — 2주택 간주임대료 시행일·연례 이자율 때문).
    monthly_rent_revenue: 해당 과세기간 월세 총수입금액(등록·미등록 합계).
    registered_rent_revenue: 그중 등록임대주택에서 발생한 수입금액.
    deposits: [{"라벨","보증금","일수","기준시가","전용면적"}] — 간주임대료 산정용.
    business_registered=False면 미등록 가산세(수입금액×0.2%)를 계산한다.
    """
    homes = count_rental_homes(own_homes, spouse_homes, tax_year=tax_year)
    n = homes["주택수"]
    flags = list(homes["플래그"])
    result = {"과세연도": tax_year, "주택수": homes}

    # R2. 비과세 판정 (§12제2호나목 — N12-2나-1)
    # 고가주택 기준 12억은 2023 과세기간부터(소법 2022-12-31 개정) — 2022 귀속 이전 9억
    price_cap = _rental_price_cap(tax_year)
    all_homes = (own_homes or []) + (spouse_homes or [])
    over_price = [h for h in all_homes if int(h.get("기준시가") or 0) > price_cap]
    overseas = [h for h in all_homes if h.get("국외")]
    if n <= 1 and not over_price and not overseas:
        result.update({
            "과세여부": "비과세",
            "판정": "1주택 + 기준시가 12억원 이하 + 국내 소재 — 주택임대소득 비과세",
            "총수입금액": 0,
            "세액": {"분리과세": 0, "종합과세": None},
            "신뢰등급": "b(법문 논리)",
            "근거": [_cite("1주택자 주택임대소득 비과세(12억 초과·국외 제외)",
                         "소득세법 §12제2호나목 (N12-2나-1)", "A"),
                   _cite("12억 판정 시점 = 과세기간 종료일 또는 양도일",
                         "소득세법 시행령 §8의2⑤ (N영8의2-5) — 종부세·재산세 6/1과 상이", "A")],
            "플래그": flags + ["전세보증금은 §25① 요건(2·3주택) 미달로 간주임대료 없음 — 1주택자는 전세 비과세"],
            "세목연동": ["종부세 합산배제·양도세 거주주택 비과세는 별도 판정(등록 요건 공유)"],
        })
        return result

    # R3. 총수입금액 = 월세 + 간주임대료
    deemed = calc_deemed_rent(tax_year, deposits or [], n, deposit_interest_rate, financial_income)
    if deemed.get("판단불가"):
        result.update({
            "과세여부": "판단불가",
            "총수입금액": None,
            "세액": {"분리과세": None, "종합과세": None},
            "신뢰등급": "판단불가",
            "판정": deemed["판정"],
            "근거": deemed["근거"],
            "플래그": flags + deemed["플래그"],
        })
        return result
    flags += deemed["플래그"]
    rent = int(monthly_rent_revenue or 0)
    if n <= 1 and over_price:
        note_r2 = "1주택이나 기준시가 12억 초과 — 월세 과세 (§12제2호나목 괄호)"
    elif n <= 1 and overseas:
        note_r2 = "1주택이나 국외 소재 — 월세 과세 (§12제2호나목 괄호)"
    else:
        note_r2 = "%d주택(부부합산) — 월세 과세" % n
    total_revenue = rent + deemed["간주임대료"]

    # 2014~2018 귀속 한시 비과세 — §12 2호나목 후단(총수입 2천만 이하, 다주택 포함)
    if 2014 <= int(tax_year) <= 2018 and total_revenue <= RENTAL_SEPARATE_LIMIT:
        result.update({
            "과세여부": "비과세",
            "판정": f"{tax_year} 귀속 총수입금액 {total_revenue:,}원 ≤ 2천만원 — 분리과세 시행(2019) 전 "
                  "한시 비과세(§12 2호나목 후단, 2018-12-31 이전에 끝나는 과세기간 한정)",
            "총수입금액": total_revenue,
            "세액": {"분리과세": 0, "종합과세": None},
            "신뢰등급": "b(법문 논리)",
            "근거": [_cite("총수입 2천만 이하 주택임대소득 비과세 — 2014~2018 과세기간 한정",
                         "소득세법 §12제2호나목 후단 (2014-01-01 개정 한시 규정)", "A")],
            "플래그": flags + ["2019 귀속부터는 같은 금액이 분리과세(14%) 대상으로 전환 — 연도 확인 필수"],
        })
        return result

    # R4~R5. 2천만원 분기
    if total_revenue > RENTAL_SEPARATE_LIMIT:
        tax_block = {
            "분리과세": None,
            "종합과세": "판단불가 — 전액 종합과세 대상. 장부 또는 추계(단순·기준경비율, 국세청 고시) "
                    "필요경비와 타 소득 합산이 필요해 현재 범위 밖",
        }
        method = "종합과세강제"
        grade = "c(회색지대 — 종합과세 경비 산정은 법문 밖)"
        flags.append("총수입금액 2천만원 초과 — 분리과세 선택 불가, 종합과세 신고 대상 (§14③7호)")
        calc = None
    else:
        reg = min(int(registered_rent_revenue or 0), rent)
        # 간주임대료는 보증금 귀속 주택 기준 — 등록 여부 구분 입력이 없으면 미등록분으로 본다
        calc = calc_rental_income_tax(reg, total_revenue - reg, other_comprehensive_income, tax_reduction)
        flags += calc.get("플래그", [])
        tax_block = {
            "분리과세": calc["분리과세세액"],
            "종합과세": (None if other_comprehensive_income is None
                     else "타 소득 합산 결정세액과 비교 필요 — §64의2① 선택 구조"),
        }
        method = "분리과세선택가능"
        grade = "b(법문 논리)"
        if other_comprehensive_income is None:
            flags.append("타 종합소득금액 미입력 — §64의2①1호(전액 종합과세) 비교 불가, 분리과세안만 확정 계산 (RI-3)")

    # R6. 부가 판정
    penalty = 0
    if not business_registered:
        base = int(revenue_before_registration or total_revenue)
        penalty = int(base * RENTAL_NO_REGISTRATION_PENALTY)
        flags.append("사업자 미등록 — 가산세 %s원(수입금액 %s×0.2%%) 발생. 2천만원 이하 분리과세자도 "
                     "등록의무 있음 (§168·§81의12, RI-5)" % (format(penalty, ","), format(base, ",")))

    result.update({
        "과세여부": "과세",
        "판정": note_r2,
        "총수입금액": {"월세": rent, "간주임대료": deemed["간주임대료"], "합계": total_revenue,
                  "간주임대료판정": deemed["판정"], "산식": deemed.get("산식")},
        "과세방식": method,
        "세액": tax_block,
        "미등록가산세": penalty,
        "계산내역": calc,
        "신뢰등급": grade,
        "근거": [
            _cite("2천만원은 소득이 아니라 수입금액 기준(주거용 건물 임대업 한정, 공동사업은 손익분배비율 분배 합산)",
                  "소득세법 §14③7호·영 §8의2⑥ (N14-3-7·N영8의2-6)", "A"),
        ] + deemed["근거"] + (calc["근거"] if calc else []),
        "플래그": flags,
        "세목연동": [
            "등록임대주택 요건(민특법 §5 등록 + 소법 §168 사업자등록 + 5% 상한)은 종부세 합산배제·"
            "양도세 거주주택 비과세와 공유 — 등록 말소 판정은 종부세 트리 관할",
            "필요경비 60%·공제 400만원 적용 시 10년 임대의무 — 미달 시 차액 추징 + 이자상당액 (§64의2③④, RI-6)",
        ],
    })
    return result


# ── 8. 조특법·지특법 감면 판정 (19차 순회 nodes_jotuk_relief.json) ──────────
# 감면은 순차 분기가 아니라 파이프라인이다: 게이트 → 요건 → 감면율 → 한도 컷 → 택일.
RELIEF_LIMIT_YEAR = 100_000_000            # §133①1호 과세기간 한도 (자경농지 등)
RELIEF_LIMIT_5YEAR = 200_000_000           # §133①2호나목 5개 과세기간 한도
RELIEF_LIMIT_5YEAR_DAETO = 100_000_000     # §133①2호가목 §70 농지대토 단독 5년 한도
RELIEF_LIMIT_YEAR_TAKING = 200_000_000     # §133②1호 공익수용 과세기간 한도 (2025-03-14 신설)
RELIEF_LIMIT_5YEAR_TAKING = 300_000_000    # §133②2호 공익수용 5개 과세기간 한도
RELIEF_LIMIT_YEAR_PRE2016 = 200_000_000    # ~2015 과세기간 한도 — 1억 축소는 법 13560호(2016-01-01 양도분부터)
RELIEF_LIMIT_5YEAR_WIDE = 300_000_000      # 2016~2017 §133①2호다목 광의 묶음 3억 (2017-12-19 삭제)
_RELIEF_SPLIT_YEAR = 2025                  # §133② 분리 — 법 20778호 부칙 §15① (과세연도 기준, 연초 소급)
FARMLAND_INCOME_EXCLUSION = 37_000_000     # 영 §66⑭1호 경작기간 제외 기준 (사업소득금액+총급여, 음수는 0)
_FARM_INCOME_RULE_FROM = date(2014, 7, 1)  # §66⑭ 시행 — 영 25211호 부칙 §1 단서 (양도일 기준, 조심 2026인1522)
_FARM_30KM_FROM = date(2015, 2, 3)         # 재촌 거리 20km→30km — 영 26070호 (조심 2018서2853)
FARMLAND_REVENUE_CAPS = {                  # §66⑭2호(2020-02-11 신설) — 소령 §208⑤2호 복식부기 기준
    "도소매": 300_000_000,                  # 가목: 농림어업·광업·도소매업 등
    "제조": 150_000_000,                    # 나목: 제조업·숙박음식점업·건설업 등
    "서비스": 75_000_000,                   # 다목: 부동산임대·서비스업 등
}
FARMLAND_RESIDE_DISTANCE_KM = 30           # 영 §66①3호 직선거리
FARMLAND_ZONE_GRACE_YEARS = 3              # 영 §66④ 용도지역 편입 후 유예
SMALL_RENTAL_PRICE_LIMIT = 600_000_000     # 영 §96②3호 임대개시일 기준시가
SMALL_RENTAL_AREA_LIMIT = 85.0             # 국민주택규모 (영 §96②2호)
RURAL_HOUSE_PRICE = 300_000_000            # §99의4①1호나목 농어촌주택 기준시가
RURAL_HOUSE_PRICE_HANOK = 400_000_000      # 같은 목 한옥
RURAL_HOUSE_HOLD_YEARS = 3
DEPOP_HOUSE_PRICE_NONCAPITAL = 900_000_000  # 영 §68의2①1호나목1) 수도권 밖 인구감소지역
DEPOP_HOUSE_PRICE_CAPITAL = 400_000_000     # 같은 목 2) 수도권 인구감소지역·인구감소관심지역
FIRST_HOME_PRICE_LIMIT = 1_200_000_000     # 지특법 §36의3① 취득당시가액
FIRST_HOME_RELIEF_SMALL = 3_000_000        # §36의3①1호 (소형·인구감소지역)
FIRST_HOME_RELIEF_PLAIN = 2_000_000        # §36의3①2호
UNSOLD_HOUSE_AREA_LIMIT = 85.0             # §98의9 준공후미분양 전용면적 (영 §98의8①1호)
UNSOLD_HOUSE_PRICE_LIMIT = 700_000_000     # 같은 항 2호 취득가액
DAETO_RESIDE_YEARS = 4                     # 영 §67① 농지대토 재촌·경작 기간
DAETO_ACQUIRE_MONTHS = 12                  # 영 §67③1호 양도→취득 기한(수용은 24개월)
DAETO_TOTAL_FARMING_YEARS = 8              # 종전+신규 합산 경작기간
DAETO_AREA_RATIO = 2 / 3                   # 신규 농지 면적 요건
DAETO_PRICE_RATIO = 1 / 2                  # 신규 농지 가액 요건


def judge_transfer_reduction_limit(
    reductions: list[dict],
    tax_year: int,
    prior_4year_reductions: int = 0,
    prior_4year_taking_reductions: int = 0,
    contract_price_mismatch: bool = False,
    unregistered_transfer: bool = False,
) -> dict:
    """양도소득세 감면 공통 게이트 — §129 배제 → §133 종합한도 → §127⑦ 택일.

    reductions 각 원소: {"조문": "69"|"70"|"77"|..., "감면세액": int, "라벨": str}
    같은 자산에 둘 이상 감면이 걸리면 §127⑦로 하나만 선택해야 하므로, 호출자는
    시나리오별로 나눠 호출하거나 후보 목록을 넘겨 비교한다(택일 안내를 반환).
    prior_4year_*: 직전 4개 과세기간에 이미 감면받은 세액(5개 과세기간 한도 계산용).
    """
    if contract_price_mismatch or unregistered_transfer:
        why = "매매계약서 거래가액 상이(다운·업 계약)" if contract_price_mismatch else "미등기양도자산"
        return {
            "감면가능": False,
            "최종감면세액": 0,
            "판정": f"{why} — 비과세·감면 전면 배제",
            "근거": [_cite("감면 전면 배제", "조세특례제한법 §129①② (N조특129-1)", "A")],
            "플래그": ["감면 요건을 갖췄더라도 이 게이트에서 탈락하면 전부 무효"],
        }

    LIMIT1 = {"33", "43", "66", "67", "68", "69", "69의2", "69의3", "69의4", "70", "85의10"}
    LIMIT2 = {"77", "77의2", "77의3"}
    year = int(tax_year or 0)
    split = year >= _RELIEF_SPLIT_YEAR  # §133② 분리는 2025 과세연도부터 (법 20778호 부칙 §15①)
    basket1 = [r for r in (reductions or []) if str(r.get("조문", "")).replace("제", "").replace("조", "") in LIMIT1]
    basket2 = [r for r in (reductions or []) if str(r.get("조문", "")).replace("제", "").replace("조", "") in LIMIT2]
    others = [r for r in (reductions or []) if r not in basket1 and r not in basket2]
    era_flags = []
    if not split:
        # 2024 이전: 공익수용 계열도 §133① 단일 바스켓 (과세기간 1억, 당시 §77은 1호 열거)
        basket1, basket2 = basket1 + basket2, []
        era_flags.append(f"과세연도 {year} — §133②(공익수용 2억/3억) 분리는 2025 과세연도 양도분부터"
                         "(법 20778호 부칙 §15①, 연초 소급). 공익수용도 §133① 바스켓으로 계산")

    def _cut(items, year_limit, five_limit, prior, label):
        raw = sum(int(i.get("감면세액", 0)) for i in items)
        if raw == 0:
            return 0, 0, []
        notes = []
        allowed = min(raw, year_limit)
        if allowed < raw:
            notes.append(f"{label} 과세기간 한도 {year_limit:,}원 초과분 {raw - allowed:,}원 감면 배제")
        five_room = max(0, five_limit - int(prior))
        if allowed > five_room:
            notes.append(f"{label} 5개 과세기간 한도 {five_limit:,}원 — 직전 4개 과세기간 감면 {int(prior):,}원 반영, "
                         f"잔여 {five_room:,}원까지만 감면")
            allowed = five_room
        return allowed, raw - allowed, notes

    daeto_only = basket1 and all(str(r.get("조문")) == "70" for r in basket1)
    if year and year <= 2015:
        year_limit1 = RELIEF_LIMIT_YEAR_PRE2016
        five_limit1 = RELIEF_LIMIT_5YEAR_WIDE
        era_flags.append("과세연도 2015 이전 — 과세기간 한도 1억 축소는 법 13560호로 2016-01-01 양도분부터라 "
                         "종전 2억 적용(조심 2020전8076 전제). 5개 과세기간 세부 묶음은 당시 조문 별도 확인")
    elif year and year <= 2017:
        year_limit1 = RELIEF_LIMIT_YEAR
        five_limit1 = RELIEF_LIMIT_5YEAR_DAETO if daeto_only else RELIEF_LIMIT_5YEAR_WIDE
        era_flags.append("과세연도 2016~2017 — 5개 과세기간 한도는 다목 3억(자경·수용 광의 묶음, 2017-12-19 "
                         "삭제). §70·§77 계열만의 묶음엔 나목 2억 서브 한도가 별도로 있음(해당 시 별도 확인)")
    else:
        year_limit1 = RELIEF_LIMIT_YEAR
        five_limit1 = RELIEF_LIMIT_5YEAR_DAETO if daeto_only else RELIEF_LIMIT_5YEAR
    a1, cut1, note1 = _cut(basket1, year_limit1, five_limit1, prior_4year_reductions, "§133① 바스켓")
    a2, cut2, note2 = _cut(basket2, RELIEF_LIMIT_YEAR_TAKING, RELIEF_LIMIT_5YEAR_TAKING,
                           prior_4year_taking_reductions, "§133② 공익수용 바스켓")
    other_sum = sum(int(r.get("감면세액", 0)) for r in others)

    flags = era_flags + list(note1) + list(note2)
    if split and basket2:
        flags.append("§133②2호 5개 과세기간 합산 시 2025-03-14 시행 전 §77의3 감면분은 합산하지 "
                     "않는다(법 20778호 부칙 §15②)")
    if year and 2016 <= year <= 2024 and any(
            str(r.get("조문", "")).startswith("77") for r in basket1):
        flags.append("2016 개정 전 사업인정 대규모개발사업 수용은 경과조치(영 27848호 부칙 §39 — 시행자 "
                     "1/2 이상 취득 등 요건) 충족 시 종전 2억 한도 적용 가능 — 요건 미충족이면 현행 1억"
                     "(조심 2020전8076)")
    if basket1 and basket2:
        flags.append("§133①과 §133②는 별도 바스켓 — 각각 한도를 계산하며 서로 잠식하지 않는다")
    if len(reductions or []) > 1:
        flags.append("같은 자산에 둘 이상 감면이 걸리면 §127⑦로 하나만 선택 — 감면율뿐 아니라 한도까지 "
                     "넣어 시나리오별로 비교할 것(토지 일부는 분리 적용 가능)")
    if others:
        flags.append(f"§133 한도 열거에 없는 감면 {[r.get('조문') for r in others]} — 한도 컷 없이 전액 반영. "
                     "다만 개별 조문의 자체 제한은 별도 확인")
    flags.append("§133③: 양도일 소급 1년 내 분할 후 일부 양도, 지분 양도 후 2년 내 나머지를 동일인·배우자에게 "
                 "양도하면 1개 과세기간으로 간주 — 해 넘겨 나눠 팔기로 한도를 두 번 쓰는 구조는 차단됨")

    return {
        "감면가능": True,
        "최종감면세액": int(a1 + a2 + other_sum),
        "바스켓별": {
            "§133①(자경·대토 등)": {"신청": sum(int(i.get("감면세액", 0)) for i in basket1), "인정": a1, "배제": cut1,
                              "적용한도": f"과세기간 {year_limit1:,} / 5개 과세기간 {five_limit1:,}"},
            "§133②(공익수용)": {"신청": sum(int(i.get("감면세액", 0)) for i in basket2), "인정": a2, "배제": cut2,
                            "적용한도": f"과세기간 {RELIEF_LIMIT_YEAR_TAKING:,} / 5개 과세기간 {RELIEF_LIMIT_5YEAR_TAKING:,}"},
            "한도외": {"신청": other_sum, "인정": other_sum},
        },
        "과세연도": tax_year,
        "근거": [
            _cite("§133① 과세기간 1억·5개 과세기간 2억(§70 단독 5년 1억)", "조세특례제한법 §133① (N조특133-1)", "A"),
            _cite("§133② 공익수용 과세기간 2억·5개 과세기간 3억", "조세특례제한법 §133② (2025-03-14 신설, N조특133-2)", "A"),
            _cite("둘 이상 감면 동시 해당 시 택일", "조세특례제한법 §127⑦⑧ (N조특127-7)", "A"),
        ],
        "플래그": flags,
    }


def judge_small_house_rental_reduction(
    tax_year: int,
    rental_house_count: int,
    is_long_term_general: bool = False,
    business_registered: bool = True,
    minteukbeop_registered: bool = True,
    exclusive_area_m2: float | None = None,
    published_price_at_start: int | None = None,
    rent_increase_rate: float | None = None,
    income_tax_before_reduction: int = 0,
    rental_months: int | None = None,
) -> dict:
    """조특법 §96 소형주택 임대사업자 세액감면 — 트리⑤ calc_rental_income_tax의 tax_reduction 산출.

    is_long_term_general: 공공지원민간임대주택 또는 장기일반민간임대주택 여부(감면율 75%/50%).
    published_price_at_start: 임대개시일 당시 주택+부수토지 기준시가 합계(6억 초과면 배제).
    rental_months: 실제 임대 개월 수 — 4년(43개월)·10년(108개월) 추징 판정용(선택).
    """
    fails, flags = [], []
    if tax_year > 2028:
        fails.append(f"일몰 — §96은 2028-12-31 이전에 끝나는 과세연도까지 적용({tax_year} 과세연도는 대상 아님). "
                     "연장 개정 여부 확인 필요")
    if not business_registered:
        fails.append("소법 §168 사업자등록 없음 (영 §96①1호)")
    if not minteukbeop_registered:
        fails.append("민특법 §5 임대사업자등록(또는 공공주택사업자 지정) 없음 (영 §96①2호)")
    if exclusive_area_m2 is not None and exclusive_area_m2 > SMALL_RENTAL_AREA_LIMIT:
        fails.append(f"국민주택규모 초과 (전용 {exclusive_area_m2}㎡ > 85㎡, 영 §96②2호)")
    elif exclusive_area_m2 is None:
        flags.append("전용면적 미입력 — 85㎡ 이하 요건 미검증 (다가구주택은 가구당 면적 기준)")
    if published_price_at_start is not None and published_price_at_start > SMALL_RENTAL_PRICE_LIMIT:
        fails.append(f"임대개시일 기준시가 {published_price_at_start:,}원 > 6억원 (영 §96②3호)")
    elif published_price_at_start is None:
        flags.append("임대개시일 기준시가 미입력 — 6억 이하 요건 미검증. 소법 §64의2 분리과세 등록임대주택에는 "
                     "없는 요건이라 분리과세 60%·400만원은 되는데 §96 감면은 안 되는 구간이 존재")
    if rent_increase_rate is not None and rent_increase_rate > 0.05:
        fails.append(f"임대료 증가율 {rent_increase_rate:.1%} > 5% (영 §96②4호)")

    if fails:
        return {"감면가능": False, "감면율": 0, "감면세액": 0, "미충족요건": fails,
                "근거": [_cite("§96 감면 요건", "조세특례제한법 §96① · 시행령 §96①② (N조특96-1·N조특령96-1)", "A")],
                "플래그": flags}

    # 호수별 차등(1호 30/75 · 2호+ 20/50)은 법 17759호(2020-12-29)로 2021 과세연도부터 —
    # 구법(~2020 귀속)은 호수 무관 30/75 (eflaw 2020-08-12본 원문 실측)
    if int(tax_year) <= 2020:
        rate = 0.75 if is_long_term_general else 0.30
        tier = f"구법({tax_year} 귀속 — 호수 무관)"
        flags.append("2020 귀속 이전은 호수별 차등 없이 30%(장기일반 75%) — 차등은 2021 과세연도부터"
                     "(법 17759호). 의무 임대기간도 구법은 장기일반 8년(현행 10년)")
    elif rental_house_count <= 1:
        rate = 0.75 if is_long_term_general else 0.30
        tier = "1호 임대"
    else:
        rate = 0.50 if is_long_term_general else 0.20
        tier = "2호 이상 임대"
    reduction = int(int(income_tax_before_reduction or 0) * rate)

    required_months = 108 if is_long_term_general else 43
    required_years = 10 if is_long_term_general else 4
    if rental_months is not None and rental_months < required_months:
        flags.append(f"임대 {rental_months}개월 — {required_years}년({required_months}개월) 미달 시 감면세액 추징 + "
                     f"이자상당가산액(§96②③). 자동말소 등 영 §96③ 사유는 제외")
    flags.append("소법 §64의2③(분리과세 60%·400만원의 10년 임대의무)과 추징 트리거가 별개로 병존 — 둘 다 점검")

    return {
        "감면가능": True,
        "감면율": rate,
        "감면세액": reduction,
        "판정": f"{tier} · {'장기일반민간임대주택등' if is_long_term_general else '그 외 임대주택'} → {rate:.0%} 감면",
        "의무임대기간": f"{required_years}년({required_months}개월)",
        "근거": [
            _cite("1호 30%(장기일반 75%) / 2호 이상 20%(50%), 일몰 2028-12-31",
                  "조세특례제한법 §96① (2025-12-23 개정, N조특96-1)", "A"),
            _cite("요건: 사업자등록+민특법등록+85㎡+기준시가 6억+5% 상한",
                  "조세특례제한법 시행령 §96①② (N조특령96-1)", "A"),
            _cite("추징 4년(장기일반 10년)·43/108개월 기준", "조특법 §96②③·영 §96③ (N조특96-2)", "A"),
        ],
        "플래그": flags,
    }


def judge_farmland_reduction(
    farming_years_claimed: float,
    resides_within_scope: bool,
    direct_farming: bool,
    yearly_incomes: list[dict] | None = None,
    zone_converted_date: str = "",
    transfer_date: str = "",
    estimated_tax: int = 0,
    distance_km: float | None = None,
    inherited_decedent_years: float = 0.0,
    heir_continuous_1yr: bool = False,
    inherited_sold_within_3yr: bool = False,
) -> dict:
    """조특법 §69 자경농지 양도세 100% 감면 판정 (영 §66 요건 포함).

    yearly_incomes 각 원소: {"연도": int, "사업소득금액": int, "총급여액": int,
      "총수입금액": int (선택), "업종군": "도소매"|"제조"|"서비스" (선택),
      "복식부기기준금액": int (선택 — 업종군 대신 직접 지정)}
    → 1호: 사업소득금액(음수는 0)+총급여 3,700만원 이상 과세기간 제외.
      2호(2020-02-11 신설): 총수입금액이 복식부기 기준(도소매 3억/제조 1.5억/서비스 0.75억)
      이상인 과세기간도 제외. §66⑭은 2014-07-01 시행 — 그 전 양도분엔 미적용(영 25211호
      부칙 §1 단서), 이후 양도분은 시행 전 과세기간에도 소급 적용(조심 2026인1522).
    zone_converted_date: 주거·상업·공업지역 편입일(YYYY-MM-DD). 편입 후 3년 경과면 감면 배제.
    distance_km: 농지↔거주지 직선거리 — 30km는 2015-02-03(영 26070호)부터, 종전 20km
      (양도일 기준, 조심 2018서2853). resides_within_scope(시군구·연접)와 어느 하나면 충족.
    inherited_decedent_years: 피상속인(배우자 포함) 경작기간 — 상속인이 1년 이상 계속
      경작(heir_continuous_1yr)했거나 상속 후 3년 내 양도(inherited_sold_within_3yr)면 통산
      (영 §66⑪⑫). 둘 다 아니면 통산 불가.
    """
    flags, fails = [], []
    excluded_years = []
    td = None
    try:
        td = date.fromisoformat(transfer_date) if transfer_date else None
    except ValueError:
        flags.append("양도일 형식 오류(YYYY-MM-DD) — 날짜 기반 경과규정 판정 생략")

    effective_years = float(farming_years_claimed or 0)
    if float(inherited_decedent_years or 0) > 0:
        if heir_continuous_1yr or inherited_sold_within_3yr:
            effective_years += float(inherited_decedent_years)
            flags.append(f"피상속인 경작 {inherited_decedent_years}년 통산 — "
                         + ("상속인 1년 이상 계속 경작(영 §66⑪)" if heir_continuous_1yr
                            else "상속 후 3년 내 양도(영 §66⑫)")
                         + ". 피상속인 기간에도 §66⑭ 소득 제외가 각각 적용되니 피상속인 소득자료도 확인")
        else:
            flags.append(f"피상속인 경작 {inherited_decedent_years}년 통산 불가 — 상속인이 1년 이상 계속 "
                         "경작하지 않았고 상속 후 3년 내 양도도 아님(영 §66⑪⑫, 조심 2010부1497 취지)")
    if yearly_incomes:
        if td and td < _FARM_INCOME_RULE_FROM:
            flags.append("양도일이 2014-07-01 전 — §66⑭(소득 기준 경작기간 제외)은 영 25211호 부칙 §1 "
                         "단서로 2014-07-01 시행이라 적용되지 않는다")
        else:
            for row in yearly_incomes:
                biz = max(0, int(row.get("사업소득금액", 0) or 0))  # 1호 후단 — 음수는 0
                total = biz + int(row.get("총급여액", 0) or 0)
                if total >= FARMLAND_INCOME_EXCLUSION:
                    excluded_years.append({"연도": row.get("연도"), "합계소득": total, "호": "1호"})
                    continue
                rev = int(row.get("총수입금액", 0) or 0)
                cap = int(row.get("복식부기기준금액", 0) or 0) or FARMLAND_REVENUE_CAPS.get(
                    str(row.get("업종군", "")), 0)
                if rev and cap and rev >= cap:
                    excluded_years.append({"연도": row.get("연도"), "총수입금액": rev, "호": "2호"})
            effective_years = max(0.0, effective_years - len(excluded_years))
    else:
        flags.append("연도별 소득자료 미입력 — 영 §66⑭(1호: 사업소득금액〔음수는 0〕+총급여 3,700만원 이상 / "
                     "2호: 총수입금액 복식부기 기준 이상 과세기간은 경작기간에서 제외)를 검증하지 못함. "
                     "겸업 농민은 달력상 8년을 채워도 탈락하는 실질 관문이므로 "
                     "소득금액증명·원천징수영수증으로 확인 필요")

    reside_ok = bool(resides_within_scope)
    if distance_km is not None:
        dist_limit = 30 if (td is None or td >= _FARM_30KM_FROM) else 20
        if float(distance_km) <= dist_limit:
            reside_ok = True
        if not reside_ok:
            fails.append(f"재촌 요건 미충족 — 시군구·연접 아님 + 직선거리 {distance_km}km > "
                         f"{dist_limit}km(양도일 기준{' — 30km는 2015-02-03부터' if dist_limit == 20 else ''}) "
                         "(영 §66①, 조심 2018서2853)")
    elif not reside_ok:
        fails.append("재촌 요건 미충족 — 농지 소재 시·군·구, 연접 시·군·구, 직선거리 30km(2015-02-03 전 양도분 "
                     "20km) 이내 거주 아님 (영 §66①)")
    if not direct_farming:
        fails.append("직접 경작 아님 — 상시 종사 또는 농작업 1/2 이상 자기 노동력 필요, 위탁영농 불인정 (영 §66⑬)")
    if effective_years < 8:
        fails.append(f"경작기간 {effective_years:.1f}년 < 8년"
                     + (f" (주장 {farming_years_claimed}년 중 소득초과 {len(excluded_years)}개 과세기간 제외)"
                        if excluded_years else ""))

    if zone_converted_date and transfer_date:
        try:
            conv = date.fromisoformat(zone_converted_date)
            trans = date.fromisoformat(transfer_date)
            if (trans - conv).days > FARMLAND_ZONE_GRACE_YEARS * 365:
                fails.append(f"주거·상업·공업지역 편입({zone_converted_date}) 후 3년 경과 — 감면 배제 (영 §66④1호). "
                             "대규모개발사업 지연·공공기관 시행 등 예외 3종 해당 여부 별도 확인")
            else:
                flags.append(f"용도지역 편입 후 3년 이내({zone_converted_date}) — 감면 유지되나 편입일까지 발생한 "
                             "소득만 감면 대상(§69① 단서). 3년 경과 전 양도가 유리")
        except ValueError:
            flags.append("편입일·양도일 형식 오류(YYYY-MM-DD) — 3년 경과 판정 생략")

    if fails:
        return {"감면가능": False, "감면율": 0, "감면세액": 0, "유효경작기간": round(effective_years, 1),
                "제외과세기간": excluded_years, "미충족요건": fails,
                "근거": [_cite("자경농지 8년 100% 감면", "조세특례제한법 §69①·시행령 §66 (N조특69-1)", "A")],
                "플래그": flags}

    flags.append("감면율은 100%지만 §133① 한도(과세기간 1억·5개 과세기간 2억)로 잘린다 — "
                 "judge_transfer_reduction_limit에 넘겨 최종 감면세액을 확정할 것. '전액 비과세' 안내 금지")
    return {
        "감면가능": True,
        "감면율": 1.0,
        "감면세액": int(estimated_tax or 0),
        "유효경작기간": round(effective_years, 1),
        "제외과세기간": excluded_years,
        "판정": f"자경농지 요건 충족(유효 경작 {effective_years:.1f}년) — 양도세 100% 감면 대상, 한도 컷 전",
        "근거": [
            _cite("8년 자경 100% 감면", "조세특례제한법 §69① (N조특69-1)", "A"),
            _cite("재촌 30km·직접경작 정의", "시행령 §66①⑬ (N조특령66-1·66-13)", "A"),
            _cite("소득 3,700만원 이상 과세기간 경작기간 제외", "시행령 §66⑭ (N조특령66-14)", "A"),
        ],
        "플래그": flags,
    }


def judge_farmland_daeto(
    prior_reside_years: float,
    transfer_date: str,
    new_acquire_date: str,
    farming_start_date: str = "",
    total_farming_years: float | None = None,
    new_area_ratio: float | None = None,
    new_price_ratio: float | None = None,
    is_expropriation: bool = False,
    estimated_tax: int = 0,
    new_acquired_by_inheritance_or_gift: bool = False,
    has_income_exclusion_period: bool = False,
) -> dict:
    """조특법 §70 농지대토 감면 판정 (시행령 §67 요건 — 23차 순회 N조특령67-1).

    ①종전 농지 양도일 현재 4년 이상 농지소재지 거주·경작 ②양도일부터 1년(수용 2년) 내 새 농지 취득
    ③취득일부터 1년 내 새 농지소재지 거주·경작 개시 ④종전+신규 합산 경작 8년 이상
    ⑤신규 농지 면적이 종전의 2/3 이상 **또는** 가액이 1/2 이상.
    자경농지(§69)와 달리 양도 시점에 8년을 채울 필요가 없고 사후 합산으로 채운다 — 대신 미달 시
    §70④로 2개월 내 추징 + 이자상당액.

    ⚠️경과규정(영 25211호 부칙 §1 단서·§9): 4년·합산 8년·§66⑭ 준용(⑥)은 **2014-07-01 이후**
    양도·취득 세트부터 — 구법은 3년 재촌·경작 + 신규 농지 3년 재촌·경작(사후요건).
    new_acquired_by_inheritance_or_gift: 새 농지를 상속·증여로 취득 — §67③1호 괄호로 배제.
    has_income_exclusion_period: 합산 8년이 차기 전에 §66⑭ 해당(소득 3,700만·총수입 기준 초과)
      과세기간 존재 — §67⑥ 후단으로 '계속 경작하지 않은 것'으로 간주(감면 배제·추징).
    """
    fails, flags = [], []
    old_law = False
    try:
        old_law = bool(transfer_date) and date.fromisoformat(transfer_date) < _FARM_INCOME_RULE_FROM
    except ValueError:
        pass
    reside_req = 3 if old_law else DAETO_RESIDE_YEARS
    if float(prior_reside_years or 0) < reside_req:
        fails.append(f"종전 농지 재촌·경작 {prior_reside_years}년 < {reside_req}년 "
                     f"(영 §67③1호{' — 구법(2014-07-01 전 양도)은 3년' if old_law else ''})")
    if new_acquired_by_inheritance_or_gift:
        fails.append("새로운 농지를 상속·증여로 취득 — 대토 취득에서 명문 제외(영 §67③1호 괄호)")
    try:
        td = date.fromisoformat(transfer_date)
        nd = date.fromisoformat(new_acquire_date)
        limit_days = (24 if is_expropriation else 12) * 30.44
        gap_days = abs((nd - td).days)
        if gap_days > limit_days:
            fails.append(f"양도일↔신규 취득일 간격 {gap_days // 30}개월 > "
                         f"{'2년(수용)' if is_expropriation else '1년'} (영 §67③1·2호)")
        if farming_start_date:
            fs = date.fromisoformat(farming_start_date)
            if (fs - nd).days > 366:
                fails.append("신규 농지 취득일부터 1년 내 경작 미개시 (영 §67③1호)")
    except (ValueError, TypeError):
        flags.append("날짜 형식 오류(YYYY-MM-DD) — 기한 요건 판정 생략")

    if old_law:
        flags.append("구법(2014-07-01 전 양도·취득 세트) — 합산 8년 요건 없음. 대신 새 농지에서 3년 이상 "
                     "재촌·경작 사후요건 미이행 시 추징(조심 2011구1462 취지). §66⑭ 준용(⑥)도 없음")
    else:
        if has_income_exclusion_period:
            fails.append("합산 8년이 차기 전에 §66⑭ 해당 과세기간(사업소득+총급여 3,700만 이상 또는 총수입 "
                         "복식부기 기준 이상) 발생 — 새로운 농지를 계속 경작하지 아니한 것으로 본다"
                         "(영 §67⑥ 후단, 2014-07-01 시행)")
        if total_farming_years is not None and total_farming_years < DAETO_TOTAL_FARMING_YEARS:
            fails.append(f"종전+신규 합산 경작 {total_farming_years}년 < 8년 — 미달 시 감면 배제 또는 추징 (영 §67③1호 단서)")
        elif total_farming_years is None:
            flags.append("합산 경작기간 미입력 — 8년 요건은 사후 충족도 인정되나 미달 시 2개월 내 추징+이자 (§70④⑤)")

    scale_ok = ((new_area_ratio is not None and new_area_ratio >= DAETO_AREA_RATIO)
                or (new_price_ratio is not None and new_price_ratio >= DAETO_PRICE_RATIO))
    if new_area_ratio is None and new_price_ratio is None:
        flags.append("신규 농지 면적비·가액비 미입력 — 면적 2/3 이상 또는 가액 1/2 이상 요건 미검증")
    elif not scale_ok:
        fails.append(f"규모 요건 미충족 — 면적비 {new_area_ratio}·가액비 {new_price_ratio} "
                     "(면적 2/3 이상 또는 가액 1/2 이상 중 하나 필요, 영 §67③1호 가·나목)")

    if fails:
        return {"감면가능": False, "감면율": 0, "감면세액": 0, "미충족요건": fails,
                "근거": [_cite("농지대토 감면", "조세특례제한법 §70·시행령 §67 (N조특70-1·N조특령67-1)", "A")],
                "플래그": flags}

    flags.append("§133①2호가목에 따라 §70 단독으로는 5개 과세기간 1억원 한도가 별도로 걸린다 — "
                 "judge_transfer_reduction_limit에 넘겨 최종 감면세액 확정")
    flags.append("재촌 요건 기간이 자경농지(§69, 8년)와 달리 4년 — 두 감면을 혼동하지 말 것")
    return {
        "감면가능": True,
        "감면율": 1.0,
        "감면세액": int(estimated_tax or 0),
        "판정": "농지대토 요건 충족 — 양도세 100% 감면 대상(한도 컷 전)",
        "근거": [
            _cite("농지대토 100% 감면", "조세특례제한법 §70① (N조특70-1)", "A"),
            _cite("재촌 4년·1년(수용 2년) 내 대토·합산 8년·면적 2/3 또는 가액 1/2",
                  "조세특례제한법 시행령 §67①③ (N조특령67-1)", "A"),
        ],
        "플래그": flags,
    }


def judge_second_home_exclusion(
    kind: str,
    acquired_date: str,
    published_price: int,
    is_hanok: bool = False,
    in_capital_area: bool = False,
    same_or_adjacent_area: bool = False,
    same_sigungu: bool = False,
    holding_years: float | None = None,
    acquired_after_general_home: bool = True,
    exclusive_area_m2: float | None = None,
    acquisition_price: int | None = None,
    first_contract: bool = True,
    seller_is_supplier: bool = True,
    transfer_date: str = "",
    land_area_m2: float | None = None,
) -> dict:
    """주택수 제외 특례 3형제 — 조특법 §99의4(농어촌·고향주택) / §71의2(인구감소지역) / §98의9(준공후미분양).

    kind: "농어촌주택" | "고향주택" | "인구감소지역주택" | "인구감소관심지역주택" | "준공후미분양주택"
    same_or_adjacent_area: (농어촌·고향주택) 일반주택과 같거나 연접한 읍·면·동(고향주택은 시)인지
    same_sigungu: (인구감소지역주택) 종전 보유 주택과 같은 시·군·구인지
    준공후미분양주택은 exclusive_area_m2(85㎡ 이하)·acquisition_price(7억 이하)·in_capital_area(수도권 배제)와
    first_contract(최초 매매계약자)·seller_is_supplier(양도자가 사업주체·분양사업자·시공자)를 함께 넘긴다.
    transfer_date: 일반주택 양도일 — §99의4 요건의 연혁 분기 기준(경과규정이 양도일 기준):
      기준시가 3억(한옥 4억)은 2023-01-01 이후 양도분부터(법 19199호 경과조치 §39 — 이전 2억),
      대지 660㎡ 면적요건 폐지는 2021-01-01 이후 양도분부터(법 17759호 부칙 §21②).
    land_area_m2: 농어촌주택 대지면적 — 2020-12-31 이전 양도 판정에만 사용.
    """
    fails, flags = [], []
    rural = kind in ("농어촌주택", "고향주택")
    unsold = kind == "준공후미분양주택"
    try:
        acq = date.fromisoformat(acquired_date)
    except (ValueError, TypeError):
        return {"주택수제외": False, "판정": "취득일 형식 오류(YYYY-MM-DD)", "근거": [], "플래그": []}
    td = None
    try:
        td = date.fromisoformat(transfer_date) if transfer_date else None
    except ValueError:
        flags.append("양도일 형식 오류(YYYY-MM-DD) — 연혁 분기는 현행 기준으로 판정")

    if rural:
        old_price_era = td is not None and td < date(2023, 1, 1)
        if old_price_era:
            limit = RURAL_HOUSE_PRICE_HANOK if is_hanok else 200_000_000
            flags.append("2022-12-31 이전 양도분 — 기준시가 한도는 종전 2억(법 19199호 경과조치 §39, "
                         "3억은 2023-01-01 이후 양도분부터)")
        else:
            limit = RURAL_HOUSE_PRICE_HANOK if is_hanok else RURAL_HOUSE_PRICE
        acq_from = date(2009, 1, 1) if kind == "고향주택" else date(2003, 8, 1)
        if not (acq_from <= acq <= date(2028, 12, 31)):
            fails.append(f"취득기간 밖 — {kind} {acq_from.isoformat()}~2028-12-31 (§99의4①, "
                         "고향주택은 농어촌주택과 시작일이 다름)")
        if published_price > limit:
            fails.append(f"취득 당시 기준시가 {published_price:,}원 > {limit:,}원{'(한옥)' if is_hanok else ''}")
        if td is not None and td < date(2021, 1, 1) and land_area_m2 is not None and land_area_m2 > 660:
            fails.append(f"대지면적 {land_area_m2}㎡ > 660㎡ — 면적요건 폐지는 2021-01-01 이후 양도분부터"
                         "(법 17759호 부칙 §21②)라 2020-12-31 이전 양도분엔 유효(조심 2019서3205)")
        if same_or_adjacent_area:
            fails.append("일반주택과 같거나 연접한 읍·면·동(고향주택은 같은·연접 시)에 소재 — 특례 배제 (§99의4③)")
        if holding_years is not None and holding_years < RURAL_HOUSE_HOLD_YEARS:
            flags.append(f"보유 {holding_years}년 — 3년 보유 전에 일반주택을 양도해도 특례는 적용되나(§99의4④), "
                         "이후 3년을 채우지 못하면 2개월 내 추징(§99의4⑥)")
        ground = _cite("농어촌주택등 취득자 양도세 과세특례", "조세특례제한법 §99의4 (N조특99의4-1)", "A")
    elif unsold:
        if not (date(2024, 1, 10) <= acq <= date(2026, 12, 31)):
            fails.append("취득기간 밖 — 2024-01-10~2026-12-31 취득분만 (§98의9①, 2026-12-31 일몰)")
        if in_capital_area:
            fails.append("수도권 소재 — 수도권 밖의 지역이어야 함 (§98의9①1호)")
        if exclusive_area_m2 is not None and exclusive_area_m2 > UNSOLD_HOUSE_AREA_LIMIT:
            fails.append(f"전용면적 {exclusive_area_m2}㎡ > 85㎡ (영 §98의8①1호)")
        elif exclusive_area_m2 is None:
            flags.append("전용면적 미입력 — 85㎡ 이하 요건 미검증")
        if acquisition_price is not None and int(acquisition_price) > UNSOLD_HOUSE_PRICE_LIMIT:
            fails.append(f"취득가액 {int(acquisition_price):,}원 > 7억원 (영 §98의8①2호)")
        elif acquisition_price is None:
            flags.append("취득가액 미입력 — 7억 이하 요건 미검증")
        if not first_contract:
            fails.append("양수자가 최초 매매(공급·분양)계약자가 아님 (영 §98의8①4호)")
        if not seller_is_supplier:
            fails.append("양도자가 사업주체·분양사업자·시공자가 아님 (영 §98의8①3호)")
        flags.append("'준공후미분양' 확인은 시장·군수·구청장의 매매계약서 날인 절차로 증명 (영 §98의8②)")
        flags.append("종부세도 1세대1주택자 간주되나 9월 16~30일 별도 신청 필요 (§98의9②③)")
        ground = _cite("수도권 밖 준공후미분양주택 과세특례",
                       "조세특례제한법 §98의9·시행령 §98의8 (N조특98의9-1·N조특령98의8-1)", "A")
    else:
        limit = DEPOP_HOUSE_PRICE_CAPITAL if (in_capital_area or kind == "인구감소관심지역주택") else DEPOP_HOUSE_PRICE_NONCAPITAL
        if not (date(2024, 1, 4) <= acq <= date(2026, 12, 31)):
            fails.append("취득기간 밖 — 2024-01-04~2026-12-31 취득분만 (§71의2①, 2026-12-31 일몰)")
        if published_price > limit:
            fails.append(f"기준시가 {published_price:,}원 > {limit:,}원 (영 §68의2①)")
        if same_sigungu:
            fails.append("종전 보유 주택과 같은 시·군·구 소재 — 특례 배제 (영 §68의2①1호가목3))")
        flags.append("종부세도 1세대1주택자로 간주되나 별도 신청 필요 — 해당 연도 9월 16일~30일 (§71의2②③)")
        ground = _cite("인구감소지역 주택 양도세·종부세 과세특례",
                       "조세특례제한법 §71의2·시행령 §68의2 (N조특71의2-1)", "A")

    if not acquired_after_general_home:
        fails.append("특례 주택을 종전 주택보다 먼저 취득 — 두 특례 모두 '취득 전부터 보유하던 주택'을 양도하는 "
                     "구조라 취득 순서가 뒤바뀌면 적용 불가")

    if fails:
        return {"주택수제외": False, "판정": " / ".join(fails), "미충족요건": fails,
                "근거": [ground], "플래그": flags}

    flags.append("주택수 제외 특례 3형제(§99의4 농어촌·§71의2 인구감소지역·§98의9 준공후미분양)의 중복 적용 "
                 "가능 여부는 법문에 명시가 없다 — 둘 이상 해당하면 쟁점 플래그(직격 해석례 미발견, D- 유지)")
    if kind in ("인구감소지역주택", "인구감소관심지역주택"):
        flags.append("취득원인·다른 특례와의 중첩은 2026년 해석례가 몰려 나온 쟁점 — 상속(서면-2025-법규재산-1621, "
                     "2026-01-14)·증여 취득(서면-2025-법규재산-2010, 2026-03-25)·분양권 중첩"
                     "(사전-2026-법규재산-0248, 2026-06-11). 본문 미수집이라 결론 미확정, 전문가 검토 유도 (N해석-71의2-1)")
    return {
        "주택수제외": True,
        "판정": f"{kind} — 일반주택 양도 시 소유주택에서 제외(소법 §89①3호 적용)",
        "근거": [ground],
        "플래그": flags,
    }


def judge_first_home_acquisition_relief(
    acquisition_price: int,
    no_home_history: bool = True,
    is_minor: bool = False,
    computed_tax: int = 0,
    exclusive_area_m2: float | None = None,
    house_type: str = "",
    in_depopulation_area: bool = False,
    acquired_date: str = "",
    co_owners: int = 1,
    in_capital_area: bool = False,
    household_income: int | None = None,
) -> dict:
    """지특법 §36의3 생애최초 주택 구입 취득세 감면 — 취득일 기준 3개 제도 구간.

    ① 2020-08-12~2022-06-20 취득(구제도): 1가구 무주택 + **합산소득 7천만 이하** + 가액 3억
      (수도권 4억) 이하 — 1.5억 이하 면제 / 초과 50% 경감(한도 없음), 20세 미만 제외.
    ② 2022-06-21~ (법 19230호 부칙 §5 소급): 본인·배우자 무주택 + 가액 12억 이하 — 200만 한도.
    ③ 300만 한도 확대 — 소형(전용 60㎡·가액 3억〔수도권 6억〕 이하 비아파트 공동주택·도시형생활
      주택·호수구분 다가구)은 2025-01-01 성립분부터(법 20632호 부칙 §2), 인구감소지역 소재는
      2026-01-01 성립분부터(법 21309호 부칙 §5①).
    house_type: "아파트"|"공동주택"|"도시형생활주택"|"다가구"|"단독주택" 등.
    """
    fails, flags = [], []
    ad = None
    if acquired_date:
        try:
            ad = date.fromisoformat(acquired_date)
        except ValueError:
            flags.append("취득일 형식 오류(YYYY-MM-DD) — 제도 구간·일몰 판정 생략(현행 기준)")
    if not no_home_history:
        fails.append("본인·배우자에게 주택 소유 이력 있음 — 다만 상속 공유지분 처분, 비도시지역 20년 이상·85㎡ 이하 "
                     "단독주택 후 이주, 전용 20㎡ 이하 주택 등 예외 있음 (§36의3③)")
    if is_minor:
        fails.append("미성년자(구제도는 20세 미만) 취득 — 감면 제외 (§36의3① 단서)")

    ground_old = _cite("구 생애최초 감면 — 소득 7천만·가액 3억(수도권 4억)·1.5억 이하 면제/초과 50%",
                       "구 지방세특례제한법 §36의3① (법 17474호 신설, 2020-08-12~2022-06-20 취득분)", "A")

    if ad and ad < date(2020, 8, 12):
        fails.append("§36의3 시행(2020-08-12) 전 취득 — 2013~2015년 구 한시 감면제도는 미순회 영역, "
                     "별도 확인 필요")
        return {"감면가능": False, "감면세액": 0, "미충족요건": fails,
                "근거": [ground_old], "플래그": flags}

    if ad and ad < date(2022, 6, 21):
        # 구제도 — 법 19230호 부칙 §5의 소급(2022-06-21)에 걸리지 않는 취득분
        price = int(acquisition_price or 0)
        price_cap = 400_000_000 if in_capital_area else 300_000_000
        if price > price_cap:
            fails.append(f"취득가액 {price:,}원 > 구제도 한도 {price_cap:,}원(수도권 4억/비수도권 3억) — "
                         "12억 한도는 2022-06-21 취득분부터(법 19230호 부칙 §5)")
        if household_income is not None and int(household_income) > 70_000_000:
            fails.append(f"세대 합산소득 {int(household_income):,}원 > 7천만원 — 구제도 소득요건 미충족")
        elif household_income is None:
            flags.append("합산소득 미입력 — 구제도(2020-08-12~2022-06-20 취득)는 세대 합산소득 7천만 이하 "
                         "요건이 있어 소득자료 없이는 확정 불가")
        if fails:
            return {"감면가능": False, "감면세액": 0, "미충족요건": fails,
                    "근거": [ground_old], "플래그": flags}
        computed = int(computed_tax or 0)
        relief = computed if price <= 150_000_000 else computed // 2
        flags.append("구제도는 정액 한도가 아니라 감면율 방식 — 1.5억 이하 100% 면제, 초과 50% 경감")
        flags.append("추징: 3개월 내 상시거주 미개시·거주 3년 미만 매각 등 — 구 §36의3④")
        return {"감면가능": True, "감면한도": None, "감면세액": relief,
                "납부세액": max(0, computed - relief),
                "판정": f"구제도 {'전액 면제(1.5억 이하)' if price <= 150_000_000 else '50% 경감'}",
                "근거": [ground_old], "플래그": flags}

    if int(acquisition_price or 0) > FIRST_HOME_PRICE_LIMIT:
        fails.append(f"취득당시가액 {int(acquisition_price):,}원 > 12억원 (§36의3①)")
    if ad and ad > date(2028, 12, 31):
        fails.append("일몰 — 2028-12-31까지 취득분 (§36의3①)")

    if fails:
        return {"감면가능": False, "감면세액": 0, "미충족요건": fails,
                "근거": [_cite("생애최초 주택 취득세 감면", "지방세특례제한법 §36의3① (N지특36의3-1)", "A")],
                "플래그": flags}

    small_price_cap = 600_000_000 if in_capital_area else 300_000_000
    small = (exclusive_area_m2 is not None and exclusive_area_m2 <= 60
             and house_type in ("공동주택", "도시형생활주택", "다가구")
             and int(acquisition_price or 0) <= small_price_cap)
    small_active = small and (ad is None or ad >= date(2025, 1, 1))
    depop_active = in_depopulation_area and (ad is None or ad >= date(2026, 1, 1))
    if small and not small_active:
        flags.append("소형주택 300만 한도는 2025-01-01 납세의무 성립분부터(법 20632호 부칙 §2) — "
                     "그 전 취득분은 200만")
    if in_depopulation_area and not depop_active:
        flags.append("인구감소지역 300만 한도는 2026-01-01 성립분부터(법 21309호 부칙 §5①) — "
                     "그 전 취득분은 200만")
    cap = FIRST_HOME_RELIEF_SMALL if (small_active or depop_active) else FIRST_HOME_RELIEF_PLAIN
    reason = ("전용 60㎡·가액 3억(수도권 6억) 이하 소형주택(아파트 제외)" if small_active else
              "인구감소지역 소재 주택" if depop_active else "일반 주택")
    computed = int(computed_tax or 0)
    relief = computed if computed <= cap else cap
    if co_owners > 1:
        flags.append(f"공동취득 {co_owners}인 — 감면 한도 {cap:,}원은 해당 주택 총 감면액 기준 (§36의3②)")
    flags.append("추징: 취득일부터 3개월 내 상시거주 미개시, 또는 거주 시작 후 3년 내 매각·증여·**임대** (§36의3④). "
                 "전세 끼고 사는 경로는 차단된다")
    flags.append("이 감면 적용 시 지방세법 §13의2 다주택 중과세율은 적용하지 않는다 (§36의3① 괄호)")
    flags.append("감면분에 대한 농어촌특별세 과세 여부는 미순회 — 별도 확인 필요")

    return {
        "감면가능": True,
        "감면한도": cap,
        "감면세액": relief,
        "납부세액": max(0, computed - relief),
        "판정": f"{reason} → 한도 {cap:,}원 ({'전액 면제' if computed <= cap else '한도까지 공제'})",
        "근거": [
            _cite("취득당시가액 12억 이하 유상거래·무주택·거주목적, 2028-12-31까지",
                  "지방세특례제한법 §36의3① (N지특36의3-1)", "A"),
            _cite("한도 300만원(소형·인구감소지역)/200만원(그 외)", "지특법 §36의3①1·2호 (2025-12-31 개정)", "A"),
            _cite("추징 요건", "지방세특례제한법 §36의3④ (N지특36의3-2)", "A"),
        ],
        "플래그": flags,
    }


# ── 21. 상속주택 선순위 산정 + 공동상속 귀속 (영 §155②③ — 20차 순회 A급) ──────
_INHERIT_PRIORITY_RULES = [
    ("1호", "피상속인이 소유한 기간이 가장 긴 1주택"),
    ("2호", "소유기간이 같으면 피상속인이 거주한 기간이 가장 긴 1주택"),
    ("3호", "소유·거주기간이 모두 같으면 피상속인이 상속개시 당시 거주한 1주택"),
    ("4호", "거주사실이 없고 소유기간이 같으면 기준시가가 가장 높은 1주택(기준시가도 같으면 상속인 선택)"),
]


def judge_inherited_house_priority(houses: list[dict], demolished_label: str | None = None,
                                   agreed_label: str | None = None) -> dict:
    """피상속인 다주택 시 선순위 상속주택 1개 확정 (영 §155② 1~4호).

    §155②는 상속주택이 2개 이상이면 '다음 각 호의 순위에 따른 1주택'만 특례 대상으로 한다.
    judge_155_special(kind="상속주택")의 is_first_priority_inherited 입력을 이 함수가 산출한다.
    상속받은 1주택이 재개발·재건축으로 2주택 이상이 된 경우도 같은 순위규정을 적용한다(§155② 괄호).

    houses 원소: {"라벨": str, "피상속인_소유기간_년": float, "피상속인_거주기간_년": float,
                  "상속개시당시_거주": bool, "기준시가": int}
    demolished_label: 멸실된 주택 라벨 — 선순위가 멸실돼도 후순위는 승격하지 않는다(조심 2022서1439)
    agreed_label: 상속인간 협의로 지정하려는 주택 라벨 — 협의로 순위를 바꿀 수 없다(사전-2024-법규재산-0433)
    """
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

    # 1호 — 소유기간 최장
    top = max(float(h.get("피상속인_소유기간_년", 0)) for _, h in pool)
    cand = [(i, h) for i, h in pool if float(h.get("피상속인_소유기간_년", 0)) == top]
    trace.append({"호": "1호", "기준": f"소유기간 최장 {top}년", "잔존": [_label(h, i) for i, h in cand]})
    if len(cand) == 1:
        applied = "1호"
    else:
        pool = cand
        # 2호 — 거주기간 최장
        top = max(float(h.get("피상속인_거주기간_년", 0)) for _, h in pool)
        cand = [(i, h) for i, h in pool if float(h.get("피상속인_거주기간_년", 0)) == top]
        trace.append({"호": "2호", "기준": f"거주기간 최장 {top}년", "잔존": [_label(h, i) for i, h in cand]})
        if len(cand) == 1:
            applied = "2호"
        else:
            pool = cand
            # 3호 — 상속개시 당시 거주
            cand3 = [(i, h) for i, h in pool if bool(h.get("상속개시당시_거주"))]
            trace.append({"호": "3호", "기준": "상속개시 당시 거주",
                          "잔존": [_label(h, i) for i, h in cand3]})
            if len(cand3) == 1:
                cand, applied = cand3, "3호"
            elif len(cand3) > 1:
                cand, pool = cand3, cand3
                applied = None
            # 4호 — 기준시가 최고 (거주사실 없는 경우의 규정이나, 3호로 못 가른 잔여도 여기서 처리)
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
    winner = _label(cand[0][1], cand[0][0])
    if demolished_label:
        flags.append(f"'{demolished_label}' 멸실 반영 안 함 — 선순위 상속주택이 멸실돼도 특별한 규정이 "
                     "없는 한 후순위가 상속주택으로 승격하지 않는다(조심 2022서1439)")
    if agreed_label and agreed_label != winner:
        flags.append(f"상속인간 협의로 '{agreed_label}'을 선순위로 지정할 수 없다 — §155② 각 호가 순위를 "
                     "명확히 규정(사전-2024-법규재산-0433[법규과-1536])")
    flags.append("상속개시 당시 피상속인과 동일세대였다면 §155② 단서 관문(동거봉양 합가 예외 외 특례 배제)이 "
                 "선행 — judge_155_special(kind='상속주택')로 판정")

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


_CO_INHERIT_PRIORITY_FROM = date(2017, 2, 3)  # 영 27829호 부칙 §1 — 공포일 시행, 기준일은 양도일


def judge_co_inherited_owner(shares: list[dict], is_first_priority: bool | None = None,
                             sale_date: str = "",
                             shares_changed_after_inheritance: bool = False,
                             same_household_at_inheritance: bool = False,
                             care_merge_exception: bool = False) -> dict:
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
    same_household_at_inheritance: 상속개시 당시 상속인이 피상속인과 동일세대였는지 —
      §155③은 별도 독립세대 전제라 동일세대원 공동상속주택은 불산입 불가
      (대법원 2023두53799). care_merge_exception(동거봉양 합가, §155② 단서)만 예외.
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

    # 소수지분 불산입이 이 주택에 적용되는지 — 동일세대 게이트 → 선순위 한정(2017-02-03~) 경계
    if same_household_at_inheritance and not care_merge_exception:
        exempt = False
        flags.append("상속개시 당시 피상속인과 동일세대 — §155③은 별도 독립세대 전제라 동일세대원 "
                     "공동상속주택은 '공동상속주택'에 해당하지 않아 불산입 불가(대법원 2023두53799). "
                     "동거봉양 합가(§155② 단서)면 care_merge_exception으로 예외")
        flags.append("세목 분기: 취득세는 최대지분→거주자→연장자(지방세법 영 §28의4⑤), "
                     "종부세는 소액지분(40%↓ 또는 지분공시가 6억·지방3억↓)이면 기간 무관 제외(영 §4의2②) — 결론이 갈릴 수 있음")
        return {
            "소유자귀속": owner,
            "적용기준": applied,
            "소수지분_불산입적용": False,
            "불산입_상속인": [],
            "근거": [
                _cite("§155③ 공동상속주택은 상속개시 당시 별도 독립세대 전제 — 동일세대원 공동상속은 "
                      "적용 배제(동거봉양 합가 예외)", "대법원 2023두53799 (2023-12-21)", "A"),
            ],
            "플래그": flags,
        }
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


# ── 22. 주택 부수토지 비과세 한도 배율 (영 §154⑦ — 20차 순회 A급) ──────────────
ATTACHED_LAND_MULTIPLES = {
    ("도시지역", "수도권", "주거상업공업"): 3,
    ("도시지역", "수도권", "녹지"): 5,
    ("도시지역", "비수도권", None): 5,
    ("비도시지역", None, None): 10,
}


def calc_attached_land_limit(building_footprint_m2: float, land_area_m2: float,
                             is_urban_area: bool = True, is_capital_region: bool = True,
                             urban_zone: str = "주거상업공업") -> dict:
    """주택 부수토지의 1세대1주택 비과세 한도 면적 판정 (소법 §89①3호·영 §154⑦).

    비과세 범위 = 건물이 정착된 면적 × 배율. 초과분은 비과세에서 빠져 별도 과세된다.
    building_footprint_m2: 건물 정착면적(바닥면적 — 연면적 아님)
    urban_zone: 주거상업공업|녹지 (도시지역·수도권일 때만 구분)
    """
    if is_urban_area:
        if is_capital_region:
            zone = "녹지" if urban_zone == "녹지" else "주거상업공업"
            mult = ATTACHED_LAND_MULTIPLES[("도시지역", "수도권", zone)]
            desc = f"도시지역·수도권·{zone}"
        else:
            mult = ATTACHED_LAND_MULTIPLES[("도시지역", "비수도권", None)]
            desc = "도시지역·수도권 밖"
    else:
        mult = ATTACHED_LAND_MULTIPLES[("비도시지역", None, None)]
        desc = "비도시지역"

    limit = float(building_footprint_m2) * mult
    excess = max(0.0, float(land_area_m2) - limit)
    flags = [
        "정착면적은 건물 '바닥면적'이다 — 연면적을 넣으면 한도가 과대 산정된다",
        "초과분은 1세대1주택 비과세에서 제외 — 비사업용 토지 해당 여부까지 별도 판정 필요(영 §168의6~14)",
        "수용 시엔 사업인정 고시일 전날의 용도지역을 적용한다(영 §154⑦ 후단, 2025-11-28 개정) — "
        "고시 후 용도지역이 바뀌어도 종전 기준 유지",
    ]
    if excess > 0:
        flags.append(f"초과 {excess:,.1f}㎡ — 양도가액을 면적 안분해 과세분을 분리해야 한다")
    return {
        "적용배율": mult,
        "지역구분": desc,
        "비과세_한도면적_m2": round(limit, 2),
        "초과면적_m2": round(excess, 2),
        "전부비과세": excess == 0,
        "근거": [
            _cite(f"{desc} → {mult}배", "소득세법 시행령 §154⑦ (20차 순회)", "A"),
            _cite("비과세 범위 = 건물 정착면적 × 지역별 배율", "소법 §89①3호", "A"),
        ],
        "플래그": flags,
    }


# ── 9. 사업자성(부동산매매업) 판정 — 20차 순회 nodes_business_test.json ──────
VAT_DEALER_ACQUIRE = 1   # 부가규칙 §2②2호 — 1과세기간 중 취득 횟수
VAT_DEALER_SELL = 2      # 같은 호 — 판매 횟수
DEALER_PREPAY_MONTHS = 2  # 소법 §69① 매매차익 예정신고 기한(매매일이 속하는 달의 말일부터)


def judge_business_dealer_status(
    acquisitions_in_period: int = 0,
    sales_in_period: int = 0,
    has_business_registration: bool = False,
    business_purpose_advertised: bool = False,
    is_self_built_sale: bool = False,
    is_residential_resale: bool = False,
    self_built_kind: str = "",
) -> dict:
    """사업자성 스크리닝 — 부동산매매업(사업소득)인지 양도소득인지 (P0 Q0 축).

    self_built_kind: 자영건설 판매 시 "주거"|"비주거" — 비주거는 매매업 명문 포함(영 §122①),
    주거 신축분양은 건설업(주거용 건물 개발·공급업)이라 양도소득도 매매업도 아니다.

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
        if self_built_kind == "비주거":
            hits.append("비주거용 건물 자영건설 판매 — 부동산매매업에 명문 포함(영 §122①)")
        flags.append("자영건설 판매의 갈림: 비주거용 = 부동산매매업(영 §122① — §64 비교과세 대상) / "
                     "주거용 신축분양 = 주거용 건물 개발·공급업(건설업 사업소득 — 비교과세 제외지만 "
                     "양도소득도 아님). '양도소득'으로 안내하면 안 되는 축")
    if is_residential_resale:
        hits.append("구입한 주거용 건물의 재판매 — 영 §122① 단서 괄호로 부동산매매업에 포함")

    if hits:
        verdict = "사업소득(부동산매매업) 가능성 높음"
        grade = "c(회색지대 — 사실판단 영역)"
    else:
        verdict = ("사업소득(건설업) 검토 — 자영건설 판매는 양도소득 아님" if is_self_built_sale
                   else "양도소득으로 판단(스크리닝 기준 미충족)")
        grade = "c(회색지대 — 사실판단 영역)"

    flags.append("⚠️소득세법에는 계속성·반복성의 임계값이 없다 — 위 기준은 부가가치세법 시행규칙 근거의 "
                 "**스크리닝 전용**이며 소득세 과세 판정을 단정하지 않는다 (N부가규칙2-2)")
    if hits:
        flags.append("사업소득으로 보더라도 §64 비교과세로 중과세율이 살아난다 — calc_dealer_comparative_tax로 "
                     "두 안을 비교할 것 (N법64-1)")
        flags.append("부동산매매업자는 매매일이 속하는 달의 말일부터 2개월 내 토지등 매매차익 예정신고 의무 "
                     "(차손이어도 신고). 예정신고 세율은 §104이되 보유 2년 미만이어도 단기세율(§104①2·3호)이 "
                     "아니라 기본세율(같은 항 1호)을 쓴다 — §69③ 단서 (N법69-1, 2026-09-19 정정)")
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


def calc_dealer_comparative_tax(
    comprehensive_income_tax: int,
    comprehensive_tax_base: int,
    housing_trade_profits: list[dict],
    tax_brackets: list[dict],
) -> dict:
    """소법 §64 부동산매매업자 비교과세 — 종합소득 산출세액 vs (중과 자산 양도세율 + 나머지 기본세율).

    housing_trade_profits 각 원소: {"라벨": str, "매매차익": int, "양도세율": float(0~1)}
      — §104①1호(분양권)·8호·10호·§104⑦ 대상 자산의 주택등매매차익. 세율은 호출자가
        judge_transfer_reliefs·search_law로 확정해 넘긴다(세율 하드코딩 금지 원칙).
    tax_brackets: [{"upto": 과세표준 상한(마지막 None), "rate": 세율, "deduction": 누진공제}] — §55 기본세율.
    """
    profits = housing_trade_profits or []
    total_profit = sum(int(p.get("매매차익", 0)) for p in profits)
    plan_a = int(comprehensive_income_tax or 0)

    ga = 0
    detail = []
    for p in profits:
        amt = int(p.get("매매차익", 0))
        rate = float(p.get("양도세율", 0) or 0)
        t = int(round(amt * rate))
        ga += t
        detail.append({"라벨": p.get("라벨", ""), "매매차익": amt, "세율": rate, "세액": t})

    remain_base = max(0, int(comprehensive_tax_base or 0) - total_profit)
    rate_b, ded_b = 0.0, 0
    for br in (tax_brackets or []):
        upto = br.get("upto")
        if upto is None or remain_base <= int(upto):
            rate_b, ded_b = float(br.get("rate", 0)), int(br.get("deduction", 0))
            break
    na = max(0, int(round(remain_base * rate_b - ded_b)))
    plan_b = ga + na

    chosen = "②(양도세율 적용안)" if plan_b > plan_a else "①(종합소득 산출세액)"
    return {
        "산출세액": max(plan_a, plan_b),
        "선택안": chosen,
        "안1_종합소득산출세액": plan_a,
        "안2_합계": plan_b,
        "안2_가목_주택등매매차익세액": ga,
        "안2_가목_내역": detail,
        "안2_나목_잔여과세표준세액": na,
        "안2_나목_과세표준": remain_base,
        "근거": [
            _cite("둘 중 많은 금액을 산출세액으로", "소득세법 §64① (N법64-1)", "A"),
            _cite("주택등매매차익 = 매매가액 − 필요경비 − 기본공제 − 장특공",
                  "소득세법 시행령 §122② (N영122-2)", "A"),
        ],
        "플래그": [
            "사업자 전환으로 중과세율을 피할 수 없다 — 대상 자산(§104①1호 분양권·8호·10호·§104⑦)에 "
            "해당하면 양도세율이 그대로 적용된다",
            "반대로 중과 대상이 아닌 자산은 안①이 적용돼 사업자 전환이 유리할 수 있다 — 두 안의 차액이 "
            "그대로 의사결정 값",
            "기본세율표는 호출자가 조회해 넘긴 값 — 과세연도 세율표와 일치하는지 확인할 것",
        ],
    }


# ── 10. 재건축부담금(재초환) 추정 — 21차 순회 nodes_jaechohwan.json ──────────
# ⚠️판례 0건 영역. 법령 + 시뮬레이션으로만 접근하며 반드시 추정치로 표기한다(설계 §9).
LEVY_EXEMPT_THRESHOLD = 80_000_000     # §12 1호 면제 기준 (2023-12-26 개정)
LEVY_BRACKETS = [                      # (상한, 누적기본액, 초과분 세율) — §12 2~6호
    (130_000_000, 0, 0.10),
    (180_000_000, 5_000_000, 0.20),
    (230_000_000, 15_000_000, 0.30),
    (280_000_000, 30_000_000, 0.40),
    (None, 50_000_000, 0.50),
]
LEVY_MAX_PERIOD_YEARS = 10             # §8② 부과기간 상한
LEVY_RELIEF_TABLE = [                  # §14의2① 1세대1주택 보유기간별 감경률
    (6, 0.10), (7, 0.20), (8, 0.30), (9, 0.40), (10, 0.50), (15, 0.60), (20, 0.70),
]
LEVY_DEFERRAL_AGE = 60                 # §17의2①2호


def estimate_reconstruction_levy(
    end_price_total: int,
    start_price_total: int,
    member_count: int,
    normal_rise_rate: float,
    development_cost: int = 0,
    start_date: str = "",
    end_date: str = "",
    management_plan_applied_date: str = "",
    one_home_holding_years: float | None = None,
    is_one_home_at_end: bool = False,
    age_at_end: int | None = None,
) -> dict:
    """재건축부담금 추정 (재초환법 §7·8·10·12·14의2 — 노드 9종).

    end_price_total/start_price_total: 종료·개시시점 부과대상 주택 가격 총액.
    normal_rise_rate: 정상주택가격상승분 비율 = max(고시 정기예금이자율, 시군구 평균주택가격상승률)
      — 외부 고시·통계이므로 호출 시점 조회값을 넘긴다(캐시 금지, §10①).
    one_home_holding_years·is_one_home_at_end: §14의2 1세대1주택 장기보유 감경 판정용.
    반환값은 전부 **추정치**다 — 가액은 감정평가, 개발비용은 실적 정산으로 확정된다.
    """
    flags = []
    if management_plan_applied_date:
        try:
            if date.fromisoformat(management_plan_applied_date) <= date(2017, 12, 31):
                return {
                    "부담금추정": 0,
                    "면제": True,
                    "판정": "2017-12-31까지 관리처분계획 인가를 신청한 재건축사업 — 재건축부담금 면제",
                    "근거": [_cite("면제 특례", "재초환법 §3의2 (N재초3의2-1)", "A")],
                    "플래그": ["신청일 기준이므로 인가일이 2018년 이후여도 면제 (최선행 게이트)"],
                }
        except ValueError:
            flags.append("관리처분 인가신청일 형식 오류(YYYY-MM-DD) — 면제 특례 판정 생략")

    if start_date and end_date:
        try:
            s, e = date.fromisoformat(start_date), date.fromisoformat(end_date)
            span = (e - s).days / 365.25
            if span > LEVY_MAX_PERIOD_YEARS:
                flags.append(f"⭐부과기간 {span:.1f}년 > 10년 — §8②에 따라 종료시점부터 역산 10년이 되는 날이 "
                             f"부과개시시점이 된다({(e - timedelta(days=int(LEVY_MAX_PERIOD_YEARS * 365.25))).isoformat()}). "
                             "개시시점 주택가액도 그 시점 기준으로 재산정해야 하므로, 입력한 개시가액이 "
                             "최초 조합설립인가일 기준이라면 이 추정치는 과대계상이다")
        except ValueError:
            flags.append("개시·종료일 형식 오류(YYYY-MM-DD) — 10년 상한 판정 생략")
    else:
        flags.append("개시·종료일 미입력 — §8② 10년 상한 적용 여부 미검증")

    normal_rise = int(int(start_price_total or 0) * float(normal_rise_rate or 0))
    excess = int(end_price_total or 0) - int(start_price_total or 0) - normal_rise - int(development_cost or 0)
    excess = max(0, excess)
    members = max(1, int(member_count or 1))
    per_member = excess // members

    if per_member <= LEVY_EXEMPT_THRESHOLD:
        base_levy, bracket = 0, "8천만원 이하 — 면제"
    else:
        base_levy, bracket = 0, ""
        for upper, fixed, rate in LEVY_BRACKETS:
            if upper is None or per_member <= upper:
                lower = {0.10: 80_000_000, 0.20: 130_000_000, 0.30: 180_000_000,
                         0.40: 230_000_000, 0.50: 280_000_000}[rate]
                base_levy = int(round((fixed + (per_member - lower) * rate) * members))
                bracket = f"1인당 평균이익 {per_member:,}원 — {int(rate * 100)}% 구간(기본 {fixed:,}원)"
                break

    relief_rate, relief = 0.0, 0
    if base_levy and is_one_home_at_end and one_home_holding_years is not None:
        for years, r in LEVY_RELIEF_TABLE:
            if one_home_holding_years >= years:
                relief_rate = r
        if relief_rate:
            relief = int(round(base_levy * relief_rate))
            flags.append(f"1세대1주택 {one_home_holding_years}년 보유 — {int(relief_rate * 100)}% 감경 (§14의2①). "
                         "보유기간은 1세대1주택자로서의 기간만 계산하며 부과종료시점에도 1세대1주택자여야 한다")
        else:
            flags.append("1세대1주택이나 보유 6년 미만 — 감경 없음 (§14의2① 최저 구간이 6년)")
    elif base_levy and not is_one_home_at_end:
        flags.append("1세대1주택 감경(§14의2, 최대 70%) 미적용 — 부과종료시점 1세대1주택 여부와 보유기간을 "
                     "입력하면 감경 후 금액을 산출한다")

    if base_levy and age_at_end is not None and age_at_end >= LEVY_DEFERRAL_AGE and is_one_home_at_end:
        flags.append(f"부과종료시점 {age_at_end}세·1세대1주택 — 담보 제공 조건으로 납부유예 신청 가능 (§17의2)")

    flags.append("⚠️재건축부담금은 세금이 아니라 부담금이며 1차 납부의무자는 조합이다(§6) — 조합원 개인 부담액은 "
                 "조합이 정한 분담기준·비율에 따르므로 이 값은 1인당 평균 기준 개산치")
    flags.append("판례 0건 영역 — 가액(감정평가)·개발비용(실적 정산)이 확정되기 전에는 추정 오차가 크다. "
                 "단정 표기 금지, 전문가 연결 권장")
    if development_cost:
        flags.append("개발비용은 회계감사를 받고 계약서·금융·세금납부 자료로 증명한 금액만 인정되며, 적정범위 초과분 중 "
                     "적정성이 확인되지 않는 비용은 불산입된다(영 §9③④) — 조합 제시 예정액과 최종 부과액이 "
                     "벌어지는 주된 원인 (N재초령9-1)")
    if is_one_home_at_end:
        flags.append("감경의 '세대'는 조합원+배우자+주민등록 동일 직계존속+직계비속(19세 미만 또는 동일 등록)이며 "
                     "동거봉양 합가(60세 이상)는 별도 세대로 본다. 주거용 오피스텔도 준주택으로 산입 "
                     "(영 §10의2①②③ — 제6의 세대 기준, N재초령10의2-1)")
        if age_at_end is not None and age_at_end >= LEVY_DEFERRAL_AGE:
            flags.append("납부유예 신청은 납부기간 만료일 **전 1개월 이내**로 창구가 짧다 (영 §13의2①, N재초령13의2-1)")
    flags.append("정기예금이자율·시군구 평균주택가격상승률은 국토교통부 고시·통계로 law_watch(법령 감시) 밖의 "
                 "별도 소스다 — 자동 조회 경로 미확보 (N재초령8-1)")

    return {
        "부담금추정": max(0, base_levy - relief),
        "면제": base_levy == 0,
        "재건축초과이익": excess,
        "조합원1인당평균이익": per_member,
        "정상주택가격상승분": normal_rise,
        "부과율구간": bracket,
        "감경률": relief_rate,
        "감경액": relief,
        "감경전부담금": base_levy,
        "산식": (f"({int(end_price_total or 0):,} − {int(start_price_total or 0):,} − 정상상승 {normal_rise:,} "
              f"− 개발비용 {int(development_cost or 0):,}) ÷ {members}명 = 1인당 {per_member:,}"),
        "신뢰등급": "c(회색지대 — 판례 0건·가액 미확정)",
        "근거": [
            _cite("부과기준 = 종료가액 − (개시가액 + 정상상승분 + 개발비용)", "재초환법 §7 (N재초7-1)", "A"),
            _cite("정상상승분 = 개시가액 × max(정기예금이자율, 시군구 평균주택가격상승률)",
                  "재초환법 §10① (N재초10-1)", "A"),
            _cite("부과율 면제 8천만 + 5구간 10~50%", "재초환법 §12 (2023-12-26 개정, N재초12-1)", "A"),
            _cite("1세대1주택 6년 10%~20년 70% 감경", "재초환법 §14의2① (2023-12-26 신설, N재초14의2-1)", "A"),
            _cite("부과기간 10년 상한", "재초환법 §8② (N재초8-2)", "A"),
        ],
        "플래그": flags,
    }


# ── 24차 순회. 주택+분양권 1세대1주택 특례 (영 §156의3, nodes_bunyang_special.json) ──
#
# 입주권 특례(§156의2)는 구현돼 있었는데 분양권 특례만 비어 있었다. 2021-01-01 이후
# 취득한 분양권이 주택수에 들어가면서 생긴 조문이라 상담 빈도가 낮지 않다.
#
# 날짜 상수는 전부 부칙에서 왔다. 시행일과 적용 기준일이 다른 자리가 있어 분리해 둔다.
_B3_APPLIES_FROM = date(2021, 1, 1)     # 부칙(2021.2.17) §10① — 이후 취득 분양권부터
_B3_MOVE_3Y_FROM = date(2023, 1, 12)    # 부칙(2023.2.28) §8① — 이후 '양도분'부터 2년→3년
_B3_1Y_RULE_FROM = date(2022, 2, 15)    # 부칙(2022.2.15) §12 — 이후 '취득한 분양권'부터 ③에 1년 요건

# ②항 후단이 인용하는 것은 §154①의 제1호·제2호'가목'·제3호뿐이다. 제2호 나목(해외이주
# 출국)·다목(국외 취학·근무 출국)은 빠져 있다 — '1~3호'로 읽으면 1년 요건을 과다 면제한다.
_B3_1Y_WAIVERS = {"건설임대5년거주", "수용", "부득이1년거주"}

# 규칙 §75① 열거 3가지. '안 팔려서'는 여기 없다.
_B3_DELAY_REASONS = {"캠코매각의뢰", "법원경매신청", "공매진행"}

# 규칙 §71③ 각 호 (규칙 §75의2①이 그대로 끌어 쓴다)
_B3_PARTIAL_MOVE_REASONS = {"취학", "근무", "질병", "학교폭력"}


def _b3_years_between(a: date, b: date) -> float:
    """표시용 경과연수. 판정은 반드시 _b3_add_years로 한다 — 아래 주석 참조."""
    return (b - a).days / 365.25


def _b3_add_years(d: date, n: int) -> date:
    """d로부터 n년 뒤 같은 날짜. 2월 29일은 2월 28일로 내린다.

    '1년 이상이 지난 후'·'3년 이내'를 일수/365.25로 재면 정확히 만 1년·만 3년이 되는
    날에서 판정이 뒤집힌다(365/365.25 = 0.9993). 경계일이야말로 상담에서 실제로
    다투는 날짜이므로 달력으로 센다.
    """
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def judge_156_3_special(
    prior_home_acquired: str,
    bunyang_acquired: str,
    sale_date: str,
    new_home_completed: str = "",
    moved_in_date: str = "",
    continuous_residence_years: float = 0.0,
    holding_waiver_reason: str = "",
    sale_delay_reason: str = "",
    delay_state_at_3y: bool = False,
    sold_by_that_method: bool = False,
    partial_move_reason: str = "",
    other_homes: int = 0,
    excluded_homes: int = 0,
    bunyang_already_completed: bool = False,
) -> dict:
    """주택과 분양권을 소유한 경우 1세대1주택 특례 판정 (영 §156의3②③, 규칙 §75·§75의2).

    **판정범위는 ②③항(일시적 1주택+1분양권)뿐이다.** ④⑤항(상속분양권)·⑥항(동거봉양·
    혼인 조합 — §156의2⑧⑨ 준용)·⑦⑧항(문화재·이농주택 조합)은 미구현이며, 반환의
    '판정범위' 필드와 플래그로 항상 알린다. 상속·합가·혼인이 얽힌 분양권 상담에
    이 툴의 결론을 그대로 쓰면 안 된다(N영156의3-10).

    ②항(3년 내 양도)을 먼저 보고, 안 되면 ③항(신축주택 실입주)으로 넘어간다.

    holding_waiver_reason: judge_exemption_requirements의 waiver_reason과 같은 어휘를 쓴다
      (""|건설임대5년거주|수용|해외이주2년|취학근무국외|부득이1년거주). 이 중 ②항 후단이
      1년 요건을 면제하는 것은 **건설임대5년거주·수용·부득이1년거주 셋뿐**이다 —
      해외이주2년·취학근무국외는 §154①제2호 나목·다목이라 인용 대상이 아니다(N영156의3-2).
    sale_delay_reason: 캠코매각의뢰|법원경매신청|공매진행 (규칙 §75① 열거 3가지).
      delay_state_at_3y는 '분양권 취득일부터 3년이 되는 날 현재' 그 상태였는지,
      sold_by_that_method는 실제로 그 방법으로 양도됐는지 — 둘 다 참이어야 한다.
    partial_move_reason: 세대 구성원 중 일부가 못 옮긴 사유 (취학|근무|질병|학교폭력).
      세대전원이 안 옮긴 경우를 봐주는 규정이 아니다(N규칙75의2-1).
    other_homes: 종전주택과 분양권(및 그 분양권으로 취득한 신축주택) 외에 보유한 주택 수.
    excluded_homes: 그중 주택수 제외 특례로 빠지는 수 — 농어촌주택(조특법 §99의4,
      서면-2022-부동산-4530)·인구감소지역주택(§71의2, 사전-2026-법규재산-0248)·
      준공후미분양(§98의9) 등. count_transfer_homes·judge_second_home_exclusion의
      출력을 넣는다. 제외 후에도 다른 주택이 남으면 ②항 전제가 무너진다(N영156의3-11).
    bunyang_already_completed: 양도 당시 분양권이 이미 완공돼 주택이 된 경우. 배제
      사유는 아니고 ③항 제2호 기한 확인을 촉구하는 플래그다.

    ③항은 조건부다 — 1년 계속거주를 못 채우면 사유 발생일 말일부터 2개월 내
    신고·납부해야 한다(⑩항). 반환의 '사후관리'에 그 사실을 담는다.
    """
    scope_note = ("이 판정은 ②③항(일시적 1주택+1분양권)에 한정된다 — 상속분양권(④⑤)·"
                  "동거봉양/혼인 조합(⑥, §156의2⑧⑨ 준용)·문화재/이농주택 조합(⑦⑧)은 "
                  "미구현이므로 해당 사실관계가 있으면 원문으로 판정할 것")
    flags, citations = [scope_note], []
    try:
        ph = date.fromisoformat(prior_home_acquired)
        bg = date.fromisoformat(bunyang_acquired)
        sd = date.fromisoformat(sale_date)
    except ValueError:
        return {"오류": "prior_home_acquired·bunyang_acquired·sale_date는 YYYY-MM-DD"}

    # 0. 적용 개시 게이트 — '탈락'이 아니라 '특례 불필요'다
    if bg < _B3_APPLIES_FROM:
        return {
            "판정범위": "②③항 한정(④~⑧ 미구현)",
            "특례적용": True,
            "판정근거항": "해당없음",
            "사유": "2021-01-01 전에 취득한 분양권은 주택수에 산입되지 않는다 — "
                  "§156의3 특례를 볼 필요 없이 종전주택이 1주택이다",
            "근거": [_cite("2021년 1월 1일 이후 취득한 분양권부터 적용",
                          "소득세법 시행령 부칙(2021.2.17) §10① (N영156의3-0)", "A")],
            "플래그": ["분양권 취득일이 기준이다 — 계약일이 아니라 취득일로 확인할 것"],
        }
    if sd < _B3_APPLIES_FROM:
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": True, "판정근거항": "해당없음",
                "사유": "2021-01-01 전 양도분은 이 특례의 적용 대상 기간이 아니다",
                "근거": [_cite("2021년 1월 1일 이후 양도분부터 적용",
                              "소득세법 시행령 부칙(2021.2.17) §10② (N영156의3-0)", "A")],
                "플래그": []}

    # 주택수 전제 — §156의3②은 문언상 "국내에 1주택을 소유한 1세대"다. 다른 주택이
    # 있어도 주택수 제외 특례를 거치면 적용되고(농어촌·인구감소지역), 거치지 못한
    # 주택이 남으면 이 항으로는 비과세되지 않는다. 최초 구현은 이 축을 아예 받지
    # 않아 2주택+1분양권을 True로 답했다(2026-08-31 S1 예규 교차검증에서 적발).
    net_other = max(int(other_homes) - int(excluded_homes), 0)
    if excluded_homes:
        citations.append(_cite(
            f"주택수 제외 특례로 {excluded_homes}채 차감 — {other_homes}채 중 {net_other}채만 남음",
            "조특법 §99의4·§71의2·§98의9 (서면-2022-부동산-4530·사전-2026-법규재산-0248)",
            "A"))
    if net_other > 0:
        flags.append(f"제외 특례를 거치지 않은 다른 주택 {net_other}채 — §155④⑤(동거봉양·"
                     "혼인)이나 §155②(상속) 등 별도 특례를 따로 검토할 것")
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": False,
                "판정근거항": "전제",
                "사유": f"§156의3②은 '1주택과 1분양권' 전제다 — 제외 후에도 주택 "
                      f"{net_other + 1}채라 이 항으로는 비과세되지 않는다",
                "근거": citations + [_cite(
                    "국내에 1주택을 소유한 1세대가 … 일시적으로 1주택과 1분양권을 소유하게 된 경우",
                    "소득세법 시행령 §156의3② 문언 (N영156의3-11)", "A")],
                "플래그": flags}
    if bunyang_already_completed:
        flags.append("양도 당시 분양권이 이미 완공됐다 — ③항 제2호(완성 후 기한 내 종전주택 "
                     "양도) 충족 여부를 반드시 확인할 것")

    gap_1y = _b3_years_between(ph, bg)
    gap_3y = _b3_years_between(bg, sd)
    waived = holding_waiver_reason in _B3_1Y_WAIVERS
    if holding_waiver_reason and not waived:
        flags.append(
            f"'{holding_waiver_reason}'은 §154①제2호 나목·다목이라 ②항 후단의 인용 대상이 "
            "아니다 — 1년 요건은 그대로 적용된다(N영156의3-2)")

    # 1. ②항 — 분양권 취득일부터 3년 이내 양도
    if sd <= _b3_add_years(bg, 3):
        ok_1y = bg >= _b3_add_years(ph, 1) or waived
        if ok_1y:
            citations.append(_cite(
                f"종전주택 취득 후 {gap_1y:.1f}년 뒤 분양권 취득, 분양권 취득 후 "
                f"{gap_3y:.1f}년 만에 양도 — ②항 충족",
                "소득세법 시행령 §156의3② (N영156의3-1)", "A"))
            if waived:
                citations.append(_cite(
                    f"'{holding_waiver_reason}' 해당 — 1년 경과 요건 배제",
                    "소득세법 시행령 §156의3② 후단 (N영156의3-2)", "A"))
            return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": True, "판정근거항": "②",
                    "사유": "일시적 1주택+1분양권 — 3년 내 종전주택 양도",
                    "근거": citations, "플래그": flags, "사후관리": ""}
        flags.append(f"종전주택 취득({prior_home_acquired}) 후 1년이 지나지 않아 분양권을 "
                     f"취득했다 — {_b3_add_years(ph, 1).isoformat()} 이후 취득분이어야 한다")
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": False, "판정근거항": "②",
                "사유": "종전주택 취득일부터 1년 이상 지난 후 분양권을 취득해야 한다",
                "근거": citations + [_cite(
                    "종전주택 취득 후 1년 경과 후 분양권 취득 요건",
                    "소득세법 시행령 §156의3② (N영156의3-1)", "A")],
                "플래그": flags}

    # 2. ②항 괄호 — 3년을 넘겼어도 규칙 §75① 사유면 ②항 유지
    if sale_delay_reason:
        if sale_delay_reason not in _B3_DELAY_REASONS:
            flags.append(
                f"'{sale_delay_reason}'은 규칙 §75① 열거(캠코매각의뢰·법원경매신청·공매진행)에 "
                "없다 — 시장에서 안 팔린 사정은 부득이한 사유가 아니다(N규칙75-1)")
        elif not (delay_state_at_3y and sold_by_that_method):
            missing = []
            if not delay_state_at_3y:
                missing.append("분양권 취득일부터 3년이 되는 날 현재 그 상태일 것")
            if not sold_by_that_method:
                missing.append("실제로 그 방법에 따라 양도될 것")
            flags.append("규칙 §75① 부수요건 미충족 — " + " / ".join(missing))
        else:
            ok_1y = bg >= _b3_add_years(ph, 1) or waived
            if ok_1y:
                citations.append(_cite(
                    f"3년 경과({gap_3y:.1f}년)했으나 '{sale_delay_reason}' 해당 — ②항 유지",
                    "소득세법 시행령 §156의3② 괄호 · 시행규칙 §75① "
                    "(N영156의3-3·N규칙75-1)", "A"))
                return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": True, "판정근거항": "②(부득이)",
                        "사유": "3년 내 양도하지 못했으나 규칙 §75① 사유에 해당",
                        "근거": citations, "플래그": flags, "사후관리": ""}
            flags.append(f"1년 요건 미달({gap_1y:.1f}년) — 부득이한 사유와 무관하게 탈락")

    # 3. ③항 — 3년 경과 양도, 신축주택 실입주 요건
    # 1년 요건은 2022-02-15 이후 '취득한 분양권'부터. 취득일 기준이지 양도일이 아니다.
    need_1y = bg >= _B3_1Y_RULE_FROM
    if not need_1y:
        citations.append(_cite(
            "2022-02-15 전에 취득한 분양권 — ③항의 1년 경과 요건은 종전 규정에 따라 미적용",
            "소득세법 시행령 부칙(2022.2.15) §12 (N영156의3-7)", "A"))
    elif not (bg >= _b3_add_years(ph, 1) or waived):
        flags.append(f"③항 1년 요건 미달 — 분양권을 {_b3_add_years(ph, 1).isoformat()} "
                     f"이후에 취득했어야 한다(취득일 {bunyang_acquired})")
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": False, "판정근거항": "③",
                "사유": "2022-02-15 이후 취득 분양권은 종전주택 취득 1년 경과 후 취득해야 한다",
                "근거": citations + [_cite(
                    "③항 1년 요건 신설", "소득세법 시행령 §156의3③ (2022.2.15 개정, "
                    "N영156의3-4·N영156의3-7)", "A")],
                "플래그": flags}

    if not new_home_completed:
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": False, "판정근거항": "③",
                "사유": f"분양권 취득 후 {gap_3y:.1f}년 만의 양도라 ③항 판정이 필요하다 — "
                      "신축주택 완성일(new_home_completed)이 있어야 한다",
                "근거": citations, "플래그": flags + ["완성일·이사일·거주기간을 받아 재판정할 것"]}

    nc = date.fromisoformat(new_home_completed)
    # 2년 구간은 분양권에서는 실제로 도달하지 않는다 — ③항은 분양권 취득 + 3년을
    # 지난 양도에만 열리고 분양권은 2021-01-01 이후 취득분만 대상이라, 양도일이
    # 항상 2024-01-01을 넘는다(N영156의3-9). 법문상 존재하는 구간이라 지우지 않는다.
    limit_years = 3 if sd >= _B3_MOVE_3Y_FROM else 2
    citations.append(_cite(
        f"완성 후 {limit_years}년 기준 적용 — 양도일 {sale_date}",
        "소득세법 시행령 §156의3③1·2호 · 부칙(2023.2.28) §8 "
        "(N영156의3-5·N영156의3-6)", "A"))
    if limit_years == 2:
        flags.append("2023-01-12 전 양도분이라 종전 규정(2년)이다 — 시행일(2023-02-28)이 "
                     "아니라 양도일 2023-01-12가 기준이다")

    deadline_years = limit_years

    # 제2호 — 완성 전 또는 완성 후 N년 이내 종전주택 양도
    sold_gap = _b3_years_between(nc, sd)
    ok_sale = sd < nc or sd <= _b3_add_years(nc, deadline_years)
    if not ok_sale:
        flags.append(f"신축주택 완성 후 {sold_gap:.1f}년 만에 종전주택 양도 — "
                     f"{deadline_years}년 초과")

    # 제1호 — 완성 후 N년 이내 세대전원 이사 + 1년 이상 계속 거주
    ok_move, move_gap = False, None
    if moved_in_date:
        md = date.fromisoformat(moved_in_date)
        move_gap = _b3_years_between(nc, md)
        ok_move = md <= _b3_add_years(nc, deadline_years)
        if not ok_move:
            flags.append(f"완성 후 {move_gap:.1f}년 만에 이사 — {deadline_years}년 초과")
    else:
        flags.append("세대전원 이사일(moved_in_date)이 없다 — ③항 제1호는 실입주가 요건이다")

    if partial_move_reason:
        if partial_move_reason in _B3_PARTIAL_MOVE_REASONS:
            citations.append(_cite(
                f"세대 구성원 중 일부가 '{partial_move_reason}'으로 이전하지 못한 경우 포함 — "
                "다른 시·군 이전이 전제이고 재학·재직·요양증명서로 확인",
                "소득세법 시행규칙 §75의2① · §71③ (N규칙75의2-1·N규칙71-3)", "A"))
        else:
            flags.append(
                f"'{partial_move_reason}'은 규칙 §71③ 열거(취학·근무·질병·학교폭력)에 없다. "
                "취학은 초·중학교를 제외한다(N규칙71-3)")

    ok_reside = continuous_residence_years >= 1.0
    if not ok_reside:
        flags.append(f"신축주택 계속거주 {continuous_residence_years:.1f}년 — 1년 미달")

    ok = ok_sale and ok_move and ok_reside
    aftercare = ("③항은 조건부다 — 신축주택에서 1년 이상 계속 거주하지 못하게 되면 그 사유가 "
                 "발생한 날이 속하는 달의 말일부터 2개월 이내에 ③항을 적용받지 않았을 경우의 "
                 "세액을 신고·납부해야 한다(영 §156의3⑩, N영156의3-8)")
    citations.append(_cite(
        "완성 후 기한 내 세대전원 이사 + 1년 이상 계속 거주 + 완성 전이나 기한 내 종전주택 양도",
        "소득세법 시행령 §156의3③1·2호 (N영156의3-4)", "A"))
    return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": ok, "판정근거항": "③",
            "사유": ("신축주택 실입주 요건 충족" if ok else "③항 요건 미충족 — 플래그 참조"),
            "근거": citations, "플래그": flags,
            "사후관리": aftercare if ok else ""}


def judge_156_3_from_portfolio(items: list[dict], sale_date: str, **kw) -> dict:
    """보유 목록 하나로 §156의3 특례를 판정한다 — 주택수 배선 자동화.

    judge_156_3_special은 other_homes·excluded_homes를 사람이 채워 넣어야 했다.
    빠뜨리면 조용히 "1주택+1분양권"으로 가정하고 답한다 — 그 침묵이 finding #39의
    본체였다. 여기서 count_transfer_homes와 같은 items 규약을 그대로 받아
    종전주택·분양권·나머지 주택수를 코드가 세고 넘긴다.

    items: count_transfer_homes와 동일한 규약. 다만 양도할 주택 하나에
      "양도대상": True를 표시해야 한다. 분양권은 "종류": "분양권".
    sale_date: 종전주택 양도일.
    **kw: judge_156_3_special에 그대로 전달 (new_home_completed·moved_in_date·
      continuous_residence_years·holding_waiver_reason·sale_delay_reason 등).
      other_homes·excluded_homes를 여기서 직접 주면 자동 산정을 덮어쓴다.
    """
    count = count_transfer_homes(items)
    by_label = {d["항목"]: d for d in count["항목별"]}

    target = [it for it in items if it.get("양도대상")]
    if len(target) != 1:
        return {"오류": "양도할 주택 하나에 '양도대상': True를 표시할 것 "
                      f"(현재 {len(target)}건)",
                "주택수산정": count}
    tgt = target[0]
    if tgt.get("종류", "주택") == "분양권":
        return {"오류": "양도대상은 주택이어야 한다 — 분양권 양도는 이 특례 대상이 아니다",
                "주택수산정": count}

    bunyang = [it for it in items
               if it.get("종류") == "분양권"
               and by_label.get(it.get("라벨") or "분양권", {}).get("산입")]
    all_bunyang = [it for it in items if it.get("종류") == "분양권"]
    if not all_bunyang:
        return {"오류": "분양권이 없다 — §156의3이 아니라 §155①(일시적 2주택) 계열을 볼 것",
                "주택수산정": count}
    if len(bunyang) > 1:
        return {"판정범위": "②③항 한정(④~⑧ 미구현)", "특례적용": False,
                "판정근거항": "전제",
                "사유": f"산입되는 분양권이 {len(bunyang)}개다 — ②③항은 '1주택과 1분양권' "
                      "전제이고, 1주택 2분양권 등은 ⑥항(§156의2⑧⑨ 준용) 영역이라 미구현",
                "근거": [_cite("1세대가 1주택과 1분양권, 1주택과 2분양권 … 을 소유하게 되는 "
                             "경우는 제156조의2제8항 또는 제9항에 따른다",
                             "소득세법 시행령 §156의3⑥ (N영156의3-10)", "A")],
                "플래그": ["원문으로 직접 판정할 것"], "주택수산정": count}

    # 산입되지 않은 분양권(2020-12-31 이전 취득 등)만 있으면 특례 판정 자체가 불필요하다.
    bg = (bunyang[0] if bunyang else all_bunyang[0]).get("취득일", "")

    # 종전주택·분양권을 뺀 나머지에서 산입/미산입을 센다.
    others = [it for it in items if it is not tgt and it.get("종류") != "분양권"]
    other_homes, excluded_homes, why = 0, 0, []
    for it in others:
        d = by_label.get(it.get("라벨") or it.get("종류", "주택"), {})
        other_homes += 1
        if not d.get("산입", True):
            excluded_homes += 1
            why.append(f"{it.get('라벨') or '주택'}: {d.get('사유', '제외')}")

    kw.setdefault("other_homes", other_homes)
    kw.setdefault("excluded_homes", excluded_homes)
    out = judge_156_3_special(tgt.get("취득일", ""), bg, sale_date, **kw)
    out["주택수산정"] = {
        "판정대상": tgt.get("라벨") or "종전주택",
        "분양권": (bunyang[0] if bunyang else all_bunyang[0]).get("라벨") or "분양권",
        "그 밖의 주택": other_homes,
        "그중 제외": excluded_homes,
        "제외사유": why,
        "트리② 원본": count,
    }
    return out
