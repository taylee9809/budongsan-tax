# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — 임대 계열 (count_rental_homes / judge_rental_income_tax /
judge_small_house_rental_reduction).

결함: ①고가주택 기준 12억을 전 연도에 적용(2022 귀속 이전은 9억 — 소법 §12 2호나목
2022-12-31 개정) ②2014~2018 귀속 총수입 2천만 이하 한시 비과세(§12 2호나목 후단) 부재
③§96 호수별 차등감면(1호 30/75·2호+ 20/50)을 2020 귀속 이전에도 적용(차등은 법 17759호로
2021 과세연도부터 — 구법은 호수 무관 30/75).
"""
from tax_judgment import *          # noqa: F401,F403 — 변경 없는 헬퍼·상수 재사용
from tax_judgment import _cite, _is_small_house  # noqa: F401


def count_rental_homes(own_homes: list[dict], spouse_homes: list[dict] | None = None) -> dict:
    """임대소득세 주택수 산정 — **부부합산** (영 §8의2③, 노드 N영8의2-3).

    ⚠️ 양도세(1세대)·종부세(개인별)·취득세(세대)·도정법(법률혼+주민등록표)과 다른 제5의 기준.
    각 원소: {"라벨": str, "기준시가": int, "전용면적": float,
              "공동소유": bool, "지분율": float(0~1), "최대지분자": bool,
              "연임대수입": int, "전대": bool, "국외": bool}
    다가구주택은 1개로 넣고, 구분등기된 경우에만 호수만큼 나눠 넣는다(③1호).
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
                elif price > RENTAL_NONTAX_PRICE and share > 0.30:
                    why = "공동소유 소수지분이나 기준시가 12억 초과+지분 30% 초과 — 산입 (③2호 나목)"
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
    homes = count_rental_homes(own_homes, spouse_homes)
    n = homes["주택수"]
    flags = list(homes["플래그"])
    result = {"과세연도": tax_year, "주택수": homes}

    # R2. 비과세 판정 (§12제2호나목 — N12-2나-1)
    all_homes = (own_homes or []) + (spouse_homes or [])
    over_price = [h for h in all_homes if int(h.get("기준시가") or 0) > RENTAL_NONTAX_PRICE]
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

    if rental_house_count <= 1:
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
