"""법인의 부동산 양도 세액 도구 — 호스팅 서버에 붙인다(tax_http.py). 생성 파일 tax_server.py 는 건드리지 않는다.

계산은 전부 조문 노드(tax_nodes/beobin.py)가 한다. 이 파일은 도구 입출력만 맡는다.
세율은 data/tax_params.json 에서 사업연도 개시 연도로 읽고, 검증되지 않은 연도는 계산을 거부한다.
"""
from __future__ import annotations

TOOLS = ("calc_corporate_property_sale_tax",)

#: 결과에 항상 붙이는 범위 고지 — 도구가 답하지 않는 것을 모델이 지어내지 않게 한다.
NOT_COVERED = [
    "과세표준 계산 — 익금·손금·이월결손금은 계산하지 않는다. taxable_base 는 호출자가 준 값을 그대로 쓴다.",
    "비사업용 토지 해당 여부(법인세법 §55의2②③, 시행령 §92의3~§92의11)와 미등기 해당 여부(§55의2⑤) — 입력을 그대로 믿는다.",
    "임대주택 등 추가과세 제외 주택(시행령 §92의2② 각 호)의 세부 요건 — 해당 호를 입력으로 받는다.",
    "세액공제·감면·최저한세·중간예납·가산세, 조례에 의한 법인지방소득세 세율 가감(지방세법 §103의20②).",
    "취득세, 재산세, 종합부동산세(법인은 종합부동산세법 §9② 세율), 부가가치세, 주민세, 배당할 때 주주가 내는 소득세.",
]


def calc_corporate_property_sale_tax(
    business_year: int,
    sales: list[dict],
    taxable_base: int | None = None,
    small_rental_corporation: bool = False,
    business_year_months: int = 12,
) -> dict:
    """Korea corporate tax when a company sells real estate: regular corporate tax on the taxable base, the additional tax on gains from housing, non-business land and housing rights (Corporate Tax Act art. 55-2), and local corporate income tax. Returns the statute trail.

    법인이 부동산을 양도한 사업연도의 법인세와 법인지방소득세를 계산한다.

    세 부분으로 나뉜다. (1) 각 사업연도 소득에 대한 법인세 = 과세표준 × 법인세법 §55① 세율.
    (2) 토지등 양도소득에 대한 법인세 = (양도금액 − 장부가액) × §55의2① 각 호 세율 — (1)에 추가로 낸다.
    주택·별장 20%, 비사업용 토지 10%, 조합원입주권·분양권 20%, 미등기 주택·별장·비사업용 토지 40%.
    상가·사업용 토지 등은 추가과세가 없다. (3) 법인지방소득세 = 지방세법 §103의20·§103의31.

    Args:
        business_year: 사업연도 개시일이 속하는 연도. 세율 조회 키이며 필수다. 검증되지 않은 연도는 계산을 거부한다
            (2026년 1월 1일 이후 개시 사업연도부터 현행 세율 — 법인세법 부칙 제21217호 §5).
        sales: 그 사업연도에 양도한 토지등 목록. 각 원소
            {"라벨": str, "종류": "주택"|"별장"|"비사업용토지"|"조합원입주권"|"분양권"|"그밖",
             "양도금액": 원, "장부가액": 원(양도 당시의 세무상 장부가액),
             "미등기": bool, "양도일": "YYYY-MM-DD", "국외": bool,
             "제외주택호": 시행령 §92의2② 각 호에 해당하는 주택이면 그 호(예 "3" = 저당권 실행·대물변제 취득 후 3년 내),
             "농어촌주택": bool(§55의2①2호 단서),
             "적용제외호": §55의2④ 각 호에 해당하면 "1"(파산)·"2"(농지 교환·분할·통합)·"3"(환지처분 등)}
            "그밖"은 상가·사업용 토지처럼 §55의2① 각 호에 해당하지 않는 자산이다.
        taxable_base: 법인세법 §13 과세표준(원) — 이번 양도차익을 포함해 호출자가 계산한 값. 생략하면
            각 사업연도 소득에 대한 법인세는 계산하지 않고 토지등 양도소득 추가과세만 돌려준다.
        small_rental_corporation: 법인세법 §60의2①1호 법인이면 True — 지배주주등 지분 50% 초과 + 부동산임대업이
            주된 사업이거나 임대·이자·배당 수입이 매출액의 50% 이상 + 상시근로자 5명 미만(시행령 §42②)을 모두 갖춘
            법인. 200억원 이하 구간에 20%가 적용된다. 매매가 주된 사업이면 해당하지 않는다.
        business_year_months: 사업연도 월수. 12 미만이면 §55② 환산을 적용한다.

    Returns:
        세목별 세액, 자산별 양도소득·세율·사유, 적용 조문, 미적용 조문(사유 포함), 값 출처, 다루지 않는 것.
    """
    from tax_nodes import beobin

    if not sales and taxable_base is None:
        raise ValueError("sales(양도한 토지등)나 taxable_base(과세표준) 중 하나는 있어야 합니다")
    if taxable_base is not None and taxable_base < 0:
        raise ValueError("taxable_base 는 0 이상이어야 합니다 — 결손이면 0을 넣는다")
    r = beobin.법인_부동산양도(business_year, sales or [], 과세표준=taxable_base,
                         성실신고소규모법인=small_rental_corporation, 사업연도_월수=business_year_months)
    r.pop("근거표", None)
    total = sum(v for v in (r["법인세_각사업연도소득"], r["토지등양도소득_법인세"],
                            r["법인지방소득세_각사업연도소득"], r["법인지방소득세_토지등양도"]) if v is not None)
    notes = list(r.pop("차감메모", []))
    if taxable_base is None:
        notes.append("taxable_base 가 없어 각 사업연도 소득에 대한 법인세·법인지방소득세는 계산하지 않았다 — 합계는 토지등 양도소득 추가과세분뿐이다")
    if any(a["세율"] > 0 for a in r["자산별"]):
        notes.append("토지등 양도소득에 대한 법인세는 과세표준에 대한 법인세와 따로 계산해 더한다 — 같은 양도차익이 과세표준에도 들어간다")
    return {
        "사업연도": business_year,
        "과세표준": taxable_base,
        "법인세_각사업연도소득": r["법인세_각사업연도소득"],
        "토지등양도소득_법인세": r["토지등양도소득_법인세"],
        "법인세_산출세액": r["법인세_산출세액"],
        "법인지방소득세_각사업연도소득": r["법인지방소득세_각사업연도소득"],
        "법인지방소득세_토지등양도": r["법인지방소득세_토지등양도"],
        "세액합계": total,
        "적용세율표": r["세율표_호"],
        "자산별": r["자산별"],
        "세율별양도소득": r["세율별양도소득"],
        "적용 조문": r["적용 조문"],
        "미적용 조문": r["미적용 조문"],
        "값 출처": r["값 출처"],
        "주의": notes,
        "다루지 않는 것": NOT_COVERED,
    }
