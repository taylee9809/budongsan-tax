# -*- coding: utf-8 -*-
"""취득세 중과 판정 수정 전(v0) 스냅샷 — run#7(수정 전 상태) 재현 전용.

2026-08-24 취득세 회귀 검증에서 폐기된 구현. 없는 것:
  ① 지방 저가주택 기준의 취득일 경과규정 — 비수도권 2억을 무조건 적용
     (실제로는 영 35477호 부칙 §2로 2025-01-02 이후 취득분부터, 그 전은 1억)
  ② 영 §28의4⑥5호 1억 이하 부속토지, ⑥8·9호 1.10대책 소형 오피스텔
  ③ 영 §28의5 일시적 2주택 판정 — 플래그 문구만 있고 판정을 안 했다
  ④ 법 §13의2②·영 §28의6 무상취득 중과(조정지역 시가표준 3억↑ 12%)
런타임에서 import 하지 말 것. 러너가 `--impl legacy_acq_v0`일 때만 로드한다.
"""
from tax_judgment import (LOW_PRICE_HOME_LIMIT_CAPITAL, LOW_PRICE_HOME_LIMIT_NONCAPITAL,
                          OFFICETEL_COUNT_LIMIT, _cite)


def judge_acquisition_homes_and_rate(homes, in_adjusted_area, is_corporation=False,
                                     exclusive_area_m2=None):
    """수정 전 결합 판정 — 취득일·일시적2주택·무상취득 인자를 아예 받지 못했다."""
    counting = count_acquisition_homes(homes)
    rate = judge_acquisition_rate(counting["산입_주택수"], in_adjusted_area,
                                  is_corporation, exclusive_area_m2)
    return {"산입_주택수": counting["산입_주택수"],
            "취득세율": rate.get("취득세율"), "중과여부": rate.get("중과여부"),
            "판정": rate.get("판정"),
            "농특세율(과표대비)": rate.get("농특세율(과표대비)"),
            "주택수_산정": counting, "세율_판정": rate}


def count_acquisition_homes(items: list[dict]) -> dict:
    """취득세 세대 주택수 산정 (지방세법 시행령 §28의4, 노드 N28-4-1~6).

    items 각 원소: {
      "종류": "주택"|"조합원입주권"|"주택분양권"|"오피스텔",
      "시가표준액": int,                  # 지분·부속토지만이면 전체 기준 (영 §28의2 1호)
      "수도권": bool,
      "정비구역": bool,                   # 저가주택 제외의 예외 (재개발 딱지 차단)
      "상속개시_5년내": bool,             # ⑥3호
      "혼전분양권_배우자혼전주택": bool,   # ⑥6호 혼인 완충
      "라벨": str (선택),
    }
    반환: 산입 주택수 + 항목별 판정과 근거. 세대내 공동소유 1개 간주(④)는 호출자가
    같은 물건을 1개로 넣는 것으로 처리.
    """
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
        elif kind == "오피스텔" and std <= OFFICETEL_COUNT_LIMIT:
            excluded, why = True, f"오피스텔 시가표준 1억 이하 — 제외 (영 §28의4⑥4호)"
        elif kind == "주택" and not it.get("정비구역"):
            limit = LOW_PRICE_HOME_LIMIT_CAPITAL if it.get("수도권") else LOW_PRICE_HOME_LIMIT_NONCAPITAL
            if std and std <= limit:
                excluded, why = True, (
                    f"저가주택({'수도권 1억' if it.get('수도권') else '비수도권 2억'} 이하) — 제외 "
                    "(영 §28의2 1호·§28의4⑥1호가목, 2026-08-17 개정 확인)")
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


def judge_acquisition_rate(counted_homes_including_new: int, in_adjusted_area: bool,
                           is_corporation: bool = False,
                           exclusive_area_m2: float | None = None) -> dict:
    """취득세 세율 + 부가세 2종 실효율 판정 (지방세법 §13의2·§151, 농특세법 §5 — 노드 N13-2-1·N-LT151-2·N-NT5-6).

    counted_homes_including_new: 취득 주택 포함 산입 주택수 (count_acquisition_homes 출력 + 1 아님 — 포함해서 전달)
    반환 세율은 그대로 calc_acquisition_tax 인자로 사용 가능.
    """
    n = counted_homes_including_new
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
