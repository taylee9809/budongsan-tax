"""법인 명의 부동산 도구 — 양도 세액·비사업용 토지 판정·주택분 종합부동산세·취득세. 호스팅 서버에 붙인다(tax_http.py).
생성 파일 tax_server.py 는 건드리지 않는다.

계산·판정은 전부 조문 노드(tax_nodes/beopin_toji.py, beopin_bisaeop.py, jongbu.py, jongbu_setdae.py, chwideuk.py, chwideuk_gwase.py)가 한다.
이 파일은 도구 입출력만 맡는다. 세율은 data/tax_params.json 에서 연도로 읽고, 검증되지 않은 연도는 계산을 거부한다.

calc_corporate_jongbu_tax · calc_corporate_acquisition_tax 는 2026-11-17 에 더했다. 생성 도구 calc_jongbu_tax 는 법인이면 호출자가
공제 0원·세율표·세 부담 상한 배제를 직접 넘겨야 하는데 basic_deduction=0 이 '미지정'으로 읽혀 넘길 수조차 없고, calc_acquisition_tax 는
대도시 법인 중과(지방세법 §13②)를 받는 입력이 없다(findings 95·97). 이 두 도구는 '법인'이라는 사실만 받고 나머지는 노드가 정한다.
"""
from __future__ import annotations

TOOLS = ("calc_corporate_property_sale_tax", "judge_corporate_non_business_land",
         "calc_corporate_jongbu_tax", "calc_corporate_acquisition_tax")

#: 결과에 항상 붙이는 범위 고지 — 도구가 답하지 않는 것을 모델이 지어내지 않게 한다.
NOT_COVERED = [
    "과세표준 계산 — 익금·손금·이월결손금은 계산하지 않는다. taxable_base 는 호출자가 준 값을 그대로 쓴다.",
    "비사업용 토지 해당 여부(법인세법 §55의2②③, 시행령 §92의3~§92의11)와 미등기 해당 여부(§55의2⑤) — 이 계산은 입력을 그대로 믿는다. 판정은 judge_corporate_non_business_land 가 한다.",
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
    from tax_nodes import beopin_toji

    if not sales and taxable_base is None:
        raise ValueError("sales(양도한 토지등)나 taxable_base(과세표준) 중 하나는 있어야 합니다")
    if taxable_base is not None and taxable_base < 0:
        raise ValueError("taxable_base 는 0 이상이어야 합니다 — 결손이면 0을 넣는다")
    r = beopin_toji.법인_부동산양도(business_year, sales or [], 과세표준=taxable_base,
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


#: judge_corporate_non_business_land 결과에 붙이는 범위 고지.
NON_BUSINESS_LAND_NOT_COVERED = [
    "기준면적 표 — 시행령 별표 1의2(가축별 기준면적), 시행규칙 별표 7~10(체육시설·예비군훈련장), 부설주차장 설치기준, 최저차고기준면적. 호출자가 계산해 넘긴다.",
    "시행령 §92의8① 각 호(체육시설업·골재채취장·폐기물처리업 등)의 업종·허가 사실과 시행규칙 §46⑦·⑪·⑭의 토지 범위 — 해당 호를 입력으로 받는다.",
    "전세금·보증금의 간주임대료(시행령 §92의8③1호), 연접 다필지의 기준면적 초과분 순위(§92의8⑤).",
    "시행령 §92의11③2호나목의 2021년 5월 4일 전 사업인정고시분에 적용되는 종전 규정 — 그 사안은 수용으로 배제하지 않고 사유만 남긴다.",
    "재산세 과세구분(종합합산·별도합산·분리과세) 판정, 주된 사업 판정에 쓰는 사업별 수입금액·자산가액 집계 — 호출자가 준 값을 쓴다.",
    "세액 — 판정 결과를 calc_corporate_property_sale_tax 의 sales[].종류(\"비사업용토지\" 또는 \"그밖\")와 미등기에 넣어 계산한다.",
]


def judge_corporate_non_business_land(
    land_type: str,
    transfer_date: str,
    acquisition_date: str | None = None,
    facts: dict | None = None,
) -> dict:
    """Korea Corporate Tax Act art. 55-2(2)-(3): judges whether land sold by a company is non-business land (비사업용 토지, extra 10% tax on the gain) by land type, the holding-period test and unavoidable-cause exclusions, and whether it is unregistered. Returns the statute trail.

    법인이 양도하는 토지가 법인세법 §55의2②의 비사업용 토지인지 판정한다.

    세 단계다. (1) 토지 종류별로 §55의2② 각 호에 해당하는 상태인지(농지는 농업이 주된 사업인지와 도시지역 여부,
    임야는 공익·임업·업무 관련 예외, 목장용지는 축산업 주업·기준면적·도시지역, 그 밖의 토지는 재산세 과세구분과
    시행령 §92의8① 각 호, 주택 부속토지는 정착면적의 5배·10배 초과분, 별장 부속토지). (2) 그 상태였던 기간이
    시행령 §92의3의 기간기준을 넘는지. (3) 법 §55의2③·시행령 §92의11·시행규칙 §46의2의 부득이한 사유.
    개인(소득세법 §104의3)과 요건이 다르다 — 재촌·자경이 아니라 주된 사업을 본다.
    입력이 모자라면 추정하지 않고 비사업용토지=None 과 판정불가_사유를 돌려준다.

    Args:
        land_type: "농지" | "임야" | "목장용지" | "기타"(나대지·잡종지 등 그 밖의 토지) | "주택부수토지" | "별장부속토지".
            사실상의 현황으로 정한다(시행령 §92의4).
        transfer_date: 양도일 "YYYY-MM-DD". 그 연도의 상수(검증된 연도만)로 판정한다.
        acquisition_date: 취득일 "YYYY-MM-DD". 기간기준 계산에 필요하다(없으면 facts 의 소유일수).
        facts: 토지 종류에 따라 필요한 사실. 키는 한국어 그대로.
            공통 — 비사업용_구간 [["시작","종료"],…](비사업용 상태였던 기간, 없으면 소유기간 내내 같은 상태로 본다),
                비사업용일수·직전5년_비사업용일수·직전3년_비사업용일수, 소유일수, 면적(㎡).
            농지 — 농업_주업(bool) 또는 사업별_수입금액{"농업": 원, …}, 농산물_자사원료_구분경리+원료_사용비율(0~1),
                농지_예외호(시행령 §92의5③ 1~6), 시지역_도시지역(bool, 특별시·광역시·시 지역의 도시지역 안인지),
                녹지지역_또는_GB(bool), 도시지역_편입일.
            임야 — 임야_공익호(§92의6① 1~13), 임업_주업 또는 사업별_자산가액, 독림가, 임야_임업호(§92의6③ 1|2), 산지_안,
                도시지역, 보전녹지지역, 도시지역_편입일, 임야_사업호(§92의6④ 1~7).
            목장용지 — 축산업_주업 또는 사업별_수입금액{"축산업": 원, …}, 농업협동조합, 목장용지_예외호(§92의7② 1~4),
                축산_기준면적(별표 1의2로 계산한 ㎡), 시지역_도시지역, 녹지지역_또는_GB, 도시지역_편입일.
            기타 — 재산세_비과세면제, 재산세_토지구분("종합합산"|"별도합산"|"분리과세"), 기타토지_사업호(§92의8① 1~13),
                기준면적내, 주차장운영업, 양어장_다목, 기타토지_12호_업종("블록석물토관제조업"|"조경작물식재업"|
                "화훼판매시설업"|"정비운전학원"|"농업학원"|"도소매업용"), 연간수입금액, 토지가액(기준시가),
                직전_연간수입금액, 직전_토지가액, 조성완료일, 수용정원, 최대사용면적.
            주택부수토지 — 주택_정착면적, 면적, 도시지역(bool).
            별장부속토지 — 별장_경계불명확, 건축물_바닥면적, 읍면_소재, 건물_연면적, 기준시가, 조특법99의4_제외지역.
            부득이한 사유 — 사용제한_구간(법령상 사용 금지·제한 기간), 부득이사유호(시행규칙 §46의2① 1~13)와
                부득이_구간·부득이_기산일·착공일·건설종료일, 최초경매기일, 공매일, 매각위임일, 최초매각공고일+매각공고_요건충족,
                양도사유("합병"|"분할"|"수용"|"협의매수"), 사업인정고시일, 종중소유, 학교법인_기부받은토지,
                부득이_배제호(§46의2③ 1~14).
            미등기 — 취득등기_없이_양도(bool), 장기할부_등기불가, 미등기_제외호(시행령 §92의2⑤ 1|2).

    Returns:
        비사업용토지(True·False·None), 해당호, 사유, 비사업용_면적(일부만 해당할 때), 기간기준(일수와 각 목 충족),
        배제(부득이한 사유), 미등기, calc_입력_종류, 적용 조문, 미적용 조문(사유 포함), 값 출처, 주의, 다루지 않는 것.
    """
    from tax_nodes import beopin_bisaeop

    facts = dict(facts or {})
    for k in ("양도일", "취득일", "토지종류", "연도"):
        if k in facts:
            raise ValueError("facts 에 %s 를 넣지 않는다 — transfer_date·acquisition_date·land_type 인자로 준다" % k)
    if land_type not in beopin_bisaeop.토지종류들:
        raise ValueError("land_type 은 %s 중 하나여야 합니다: %r" % (" | ".join(beopin_bisaeop.토지종류들), land_type))
    r = beopin_bisaeop.법인_비사업용토지_판정(transfer_date, 취득일=acquisition_date or "", 토지종류=land_type, **facts)
    r.pop("근거표", None)
    notes = []
    if r["비사업용토지"] is None:
        notes.append("입력이 모자라 판정하지 않았다 — 판정불가_사유에 적힌 사실을 채워 다시 부른다. 비사업용 토지가 아니라는 뜻이 아니다")
    if r.get("비사업용_면적") is not None and r["비사업용토지"]:
        notes.append("토지 전부가 아니라 %s㎡만 비사업용 토지다 — 양도금액·장부가액을 면적으로 나눠 그 부분만 비사업용토지로 계산한다" % r["비사업용_면적"])
    for m in (r.get("기간기준") or {}).get("메모", []):
        notes.append(m)
    if land_type == "별장부속토지":
        notes.append("법인세법 §55의2②6호에는 소득세법 §104의3①6호와 달리 읍·면 농어촌주택 제외 단서가 없다. 농어촌주택 제외는 ①2호 단서"
                     "(주택·별장 20%)에만 있다 — 농어촌주택의 부속토지가 ②6호에서도 빠지는지는 문언에 없어 확인이 필요하다")
    if land_type == "주택부수토지":
        notes.append("배율 이내의 부속토지는 주택에 부수되는 토지로 §55의2①2호(주택 20%) 대상이 될 수 있다 — 이 도구는 비사업용 토지(3호) 쪽만 본다")
    if any("종전 규정을 읽지 못해" in m["사유"] for m in r["미적용 조문"]):
        notes.append("2021년 5월 4일 전에 사업인정고시된 사업의 수용·협의매수는 종전 규정이 적용된다 — 이 도구는 그 규정을 싣지 않아 수용을 이유로 배제하지 않았다")
    if "부득이한 사유 기간" in r["값 출처"] and r.get("배제") and "규칙 §46의2③" in r["배제"]:
        notes.append("시행규칙 §46의2③은 1호 괄호의 '2008년 12월 31일 이전에 취득한 것에 한정한다. 이하 이 항에서 같다'를 문언대로 모든 호에 적용했다")
    notes.append("기간은 취득일 다음 날부터 양도일까지의 일수로 세고 'N년 초과'는 N×365일로 봤다 — 조문에 세는 법이 없어 경계 하루 이틀이 갈리는 사안은 확인이 필요하다")
    r["calc_입력_종류"] = None if r["비사업용토지"] is None else ("비사업용토지" if r["비사업용토지"] else "그밖")
    r["주의"] = notes
    r["다루지 않는 것"] = NON_BUSINESS_LAND_NOT_COVERED
    return r


# ── 법인 주택분 종합부동산세 ────────────────────────────────────────────────
#: calc_corporate_jongbu_tax 결과에 붙이는 범위 고지.
JONGBU_NOT_COVERED = [
    "재산세 — 종합부동산세와 따로 7월·9월에 고지된다. 주택은 calc_property_tax, 건축물은 calc_building_property_tax 로 계산한다. 이 도구는 종합부동산세에서 빼는 재산세액(§9③)만 계산한다.",
    "토지분 종합부동산세(종합부동산세법 제3장 — 종합합산·별도합산 토지) — 도구가 없다. 상가 부속토지·나대지를 가진 법인의 토지분은 계산하지 않는다.",
    "합산배제 주택(§8② — 등록 임대주택, 사원용 주택, 주택건설사업자의 미분양주택 등) 해당 여부와 9월 16일~30일 신고(§8③) — total_official_price 에서 이미 뺀 값을 받는다.",
    "주택 수 계산(시행령 §4의3③ — 공동소유, 다가구주택, 합산배제 주택·상속주택 등의 제외) — home_count 는 호출자가 센 값을 그대로 쓴다.",
    "공익법인등·공공주택사업자 등 해당 여부(§9②1·2호, 시행령 §4의4①)와 서류 제출 요건(시행령 §4의4②) — corporation_type 을 그대로 믿는다.",
    "신탁주택의 납세의무자(§7②), 분납(§20), 조례로 가감된 재산세율(지방세법 §111③)·재산세 세 부담 상한(§122)이 적용된 실제 재산세 고지액.",
]

_JONGBU_TYPES = {
    "일반": None, "공익법인": None,
    "공공주택사업자": 1, "주택조합": 3, "정비사업시행자": 4, "민간건설임대사업자": 5,
    "임대주택건설의무사업시행자": "5의2", "사회적기업등": 6, "종중": 7,
}


def calc_corporate_jongbu_tax(
    year: int,
    total_official_price: int,
    home_count: int,
    prev_year_official_price: int = 0,
    corporation_type: str = "일반",
    public_interest_use_only: bool = False,
) -> dict:
    """Korea comprehensive real estate holding tax (종합부동산세) on housing owned by a company on June 1: flat 2.7% (two homes or fewer) or 5% (three or more), no basic deduction, no tax burden cap (Comprehensive Real Estate Holding Tax Act art. 8(1)2, 9(2), 10 proviso), property-tax credit and rural special tax. Returns the statute trail.

    법인(법인으로 보는 단체 포함)이 과세기준일(6월 1일)에 소유한 주택의 종합부동산세를 계산한다.

    일반 법인은 종합부동산세법 §9②3호 — 2주택 이하 1천분의 27, 3주택 이상 1천분의 50의 단일세율이고,
    공제금액이 0원이며(§8①2호), 세 부담 상한이 없다(§10 단서). 1세대 1주택자 세액공제(§9⑤)도 없다.
    공시가격이 낮아도, 한 채뿐이어도 세액이 나온다. 6월 1일에 소유하고 있으면 그 해 전부를 낸다(§3, 지방세법 §114).
    과세표준 = 공시가격 합계 × 공정시장가액비율(§8①, 시행령 §2의4①). 여기에서 주택분 재산세로 부과된 세액 중
    과세표준에 해당하는 부분을 빼고(§9③, 시행령 §4의3①), 종합부동산세액의 100분의 20을 농어촌특별세로 더한다.
    공익법인등·공공주택사업자·주택조합·정비사업 시행자·종중 등은 개인과 같은 누진세율과 공제 9억원이다(§9②1·2호, 시행령 §4의4①).

    Args:
        year: 과세연도(과세기준일 6월 1일이 속하는 해). 세율·비율 조회 키이며 필수다. 검증되지 않은 연도는 계산을 거부한다.
        total_official_price: 6월 1일 현재 법인이 소유한 주택 공시가격의 합계(원). 합산배제 주택(§8②)은 빼고 넣는다.
        home_count: 법인이 소유한 주택 수(시행령 §4의3③으로 센 값). 3 이상이면 5%, 2 이하면 2.7%. 추정해서 넣지 않는다.
        prev_year_official_price: 같은 주택의 직전 연도 공시가격 합계(원). 재산세 과세표준 상한(지방세법 §110③)과
            재산세액 공제 계산에 쓴다. 0이면 재산세액 공제를 계산하지 못해 세액이 더 크게 나온다(주의에 적힌다).
        corporation_type: "일반"(§9②3호 단일세율) | "공익법인"(상속세 및 증여세법 §16의 공익법인등) |
            "공공주택사업자" | "주택조합" | "정비사업시행자" | "민간건설임대사업자" | "임대주택건설의무사업시행자" |
            "사회적기업등" | "종중" (시행령 §4의4① 각 호 — 요건은 호출자가 확인한다).
        public_interest_use_only: corporation_type 이 "공익법인"일 때, 직접 공익목적사업에 사용하는 주택만 보유하면 True(§9②1호).

    Returns:
        세율구분, 공제금액, 과세표준, 적용세율, 산출세액, 재산세액 공제, 종합부동산세, 농어촌특별세, 총납부세액,
        세부담상한 적용여부, 적용 조문, 미적용 조문(사유 포함), 값 출처, 주의, 다루지 않는 것.
    """
    from tax_nodes import jongbu, jongbu_setdae  # noqa: F401 — jongbu_setdae 에 법 §9②·영 §4의4 노드가 있다

    if corporation_type not in _JONGBU_TYPES:
        raise ValueError("corporation_type 은 %s 중 하나여야 합니다: %r" % (" | ".join(_JONGBU_TYPES), corporation_type))
    if total_official_price <= 0:
        raise ValueError("total_official_price 는 0보다 커야 합니다")
    if not isinstance(home_count, int) or isinstance(home_count, bool) or home_count < 1:
        raise ValueError("home_count 는 1 이상의 정수여야 합니다 — 2주택 이하와 3주택 이상의 세율이 다르다")
    if public_interest_use_only and corporation_type != "공익법인":
        raise ValueError("public_interest_use_only 는 corporation_type 이 \"공익법인\"일 때만 씁니다")
    if int(year) < 2023:
        raise ValueError("종합부동산세법 §9②는 2022. 12. 31. 개정됐다 — 그 전 과세연도의 법인 세율은 이 엔진에 검증된 값이 없어 계산하지 않습니다")
    사실 = {"법인": True, "주택수": home_count}
    if corporation_type == "공익법인":
        사실.update(공익법인=True, 공익목적사업_주택만=bool(public_interest_use_only))
    elif _JONGBU_TYPES[corporation_type] is not None:
        사실["법인유형"] = _JONGBU_TYPES[corporation_type]
    r = jongbu.종부세_주택(total_official_price, int(year), 직전연도_합산공시가격=prev_year_official_price or 0, **사실)
    구분 = jongbu_setdae.법인_세율(연도=int(year), **{k: v for k, v in 사실.items() if k != "법인"})["세율구분"]
    r.pop("근거표", None)
    for k in ("1세대1주택자 세액공제율(연령+보유, 한도적용)", "1세대1주택자 세액공제액"):
        r.pop(k, None)                      # 법인에는 §9⑤ 공제가 없다 — 0 이라는 숫자도 내보내지 않는다
    단일 = 구분.startswith("3호")
    notes = []
    if r.get("과세표준") == 0:
        r.setdefault("종합부동산세", 0)
        r.setdefault("농어촌특별세", 0)
        r.setdefault("총납부세액", 0)
    else:
        if not prev_year_official_price:
            notes.append("prev_year_official_price 가 없어 재산세액 공제(§9③)를 계산하지 않았다 — 실제 세액은 이보다 작다")
        elif home_count > 1:
            notes.append("재산세액 공제는 공시가격 합계를 한 채로 보고 계산한 근사다 — 재산세는 주택별로 누진세율이 적용되므로 "
                         "여러 채면 실제 공제액과 다르다(시행령 §4의3①의 분자·분모를 주택별 재산세로 다시 계산해야 한다)")
    if 단일:
        notes.append("§9②3호 법인은 공제금액 0원(§8①2호)·세 부담 상한 없음(§10 단서)이다 — 개인의 9억원 공제와 150% 상한을 적용하지 않았다")
        notes.append("세액 산식은 §9① 노드가 §9②3호 단일세율표를 받아 계산한다 — 적용 조문의 §9①은 누진세율을 썼다는 뜻이 아니다")
    else:
        notes.append("%s — 개인과 같은 누진세율·공제 9억원(§8①3호)·세 부담 상한(§10)을 적용했다. 시행령 §4의4②의 서류를 "
                     "9월 16일~30일에 내야 한다" % 구분)
    if any("미검증" in str(v) for v in (r.get("값 출처") or {}).values()):
        notes.append("%d년 값은 아직 검증되지 않아 현행법 기준으로 추정했다 — 값 출처에 표시된 항목을 그 해 시행 법령으로 확인해야 한다" % int(year))
    notes.append("6월 1일에 소유한 자가 그 해 세액 전부를 낸다 — 6월 1일 전에 팔거나 6월 2일 이후에 사면 그 해 종합부동산세가 없다(§3·§7①)")
    if 단일:
        # 상한이 없으니 직전 연도 총세액상당액(시행령 §5②)과 §9⑤ 공제는 세액에 쓰이지 않았다 — 적용 조문에서 미적용으로 옮긴다
        r.pop("직전연도 총세액상당액", None)
        빼기 = {"종합부동산세법 §9⑤": "1세대 1주택자 세액공제 — 법인은 1세대 1주택자가 아니다",
              "종합부동산세법 시행령 §5②": "직전 연도 총세액상당액 — §10 단서로 세 부담 상한이 없어 쓰지 않았다"}
        r["미적용 조문"] = list(r.get("미적용 조문", [])) + [
            {"표기": k, "제목": v.split(" — ")[0], "사유": v.split(" — ")[1]} for k, v in 빼기.items() if k in r.get("적용 조문", [])]
        r["적용 조문"] = [c for c in r.get("적용 조문", []) if c not in 빼기]
    out = {"납세의무자": "법인", "세율구분": 구분, "주택수": home_count}
    out.update(r)
    out["주의"] = notes
    out["다루지 않는 것"] = JONGBU_NOT_COVERED
    return out


# ── 법인 취득세 (대도시 중과 포함) ──────────────────────────────────────────
#: calc_corporate_acquisition_tax 결과에 붙이는 범위 고지.
ACQUISITION_NOT_COVERED = [
    "과세표준 산정(지방세법 §10~§10의6) — acquisition_price 를 그대로 쓴다. 경매는 낙찰대금 외에 인수하는 채무·비용이 사실상의 취득가격에 들어갈 수 있다.",
    "대도시 해당 여부 — property_location(소재지)을 주면 수도권정비계획법 시행령 별표 1의 과밀억제권역을 시·군·구 단위로 판정하지만, 일부 지역만 해당하는 인천·남양주시·시흥시(경제자유구역·남동 국가산업단지·반월특수지역 경계)와 산업단지 지정 여부는 판정하지 않는다. property_in_metro 를 주면 그 값을 그대로 믿는다.",
    "본점·주사무소·지점·분사무소 해당 여부와 그 설립·설치·전입일의 사실 판단(시행령 §27③, 시행규칙이 정하는 사무소등) — 입력을 그대로 믿는다.",
    "대도시 중과 제외 업종(시행령 §26① 각 호)에 실제로 해당하는지와 그 업종에 직접 사용하는지 — excluded_business_item 으로 받은 호의 단서 요건 가운데 사실로 준 것만 판정한다. 사후관리(지방세법 §13③④ — 1년 내 미사용·2년 내 매각 등으로 다시 중과)는 계산하지 않고 주의에 적는다.",
    "과밀억제권역 본점용 신축·증축과 공장 신설·증설(§13①, §13②2호), 사치성 재산(§13⑤ 고급주택·고급오락장 등)과 그 중복(§13⑥⑦, §13의2③).",
    "휴면법인 인수 여부(시행령 §27①), 분할·합병 예외(§27④⑤), 신탁재산(§27⑥), 과점주주 간주취득(§7⑤), 조례에 의한 세율 조정(§14), 감면(지방세특례제한법).",
    "주택 유상거래 중과 예외 가운데 시가표준액 기준(시행령 §28의2 1호) 밖의 호 — heavy_exception_item 으로 받은 호의 요건 가운데 heavy_exception_facts 로 준 것만 판정한다. 그 호의 주체·목적(공공주택사업자, 멸실 목적 등)과 취득 뒤의 사후관리는 확인하지 않는다.",
    "등기 비용(등록면허세·인지세·국민주택채권), 부가가치세.",
]

_ACQ_KIND = {"주택": "주택유상", "주택외": "유상.농지외", "농지": "유상.농지"}


def _acq_parts(r: dict) -> dict:
    return {"적용세율": r["적용세율(표준+중과+조례)"], "세율근거": r["세율근거"], "취득세": r["취득세"],
            "지방교육세": r["지방교육세"], "농어촌특별세": r["농어촌특별세"], "총납부세액": r["총납부세액"]}


def calc_corporate_acquisition_tax(
    acquisition_price: int,
    acquire_date: str,
    property_kind: str,
    property_in_metro: bool | None = None,
    metro_office_date: str | None = None,
    no_metro_office: bool = False,
    excluded_business: bool = False,
    exclusive_area: float | None = None,
    standard_value: int | None = None,
    in_capital_area: bool | None = None,
    in_redevelopment_zone: bool = False,
    heavy_exception_item: str | None = None,
    excluded_business_item: str | None = None,
    excluded_business_facts: dict | None = None,
    property_location: str | None = None,
    in_industrial_complex: bool | None = None,
    heavy_exception_facts: dict | None = None,
) -> dict:
    """Korea acquisition tax (취득세) when a company buys real estate for consideration (purchase or auction): 12% on housing (Local Tax Act art. 13-2(1)1) with the low-value home exception, and the large-city surcharge on companies set up or moved into the Seoul overconcentration zone within five years (art. 13(2): standard rate x3 minus 4%p, e.g. 8% on shops and land), plus local education tax and rural special tax. Returns the statute trail.

    법인이 부동산을 유상(매매·경매)으로 취득할 때의 취득세·지방교육세·농어촌특별세를 계산한다.

    두 가지 중과를 본다. (1) 법인의 주택 취득 — 지방세법 §13의2①1호, 주택 수와 무관하게 12%(§11①7호나목 4% + 중과기준세율
    2%의 400%). 시가표준액이 수도권 1억원·그 밖의 지역 2억원 이하인 주택 등 시행령 §28의2 각 호의 주택은 중과에서 빠져
    §11①8호의 1~3%다. (2) 대도시 법인 중과 — §13②1호. 과밀억제권역(산업단지 제외)에서 법인을 설립하거나 지점을 설치하거나
    본점·지점을 대도시로 전입한 뒤 5년 이내에 대도시의 부동산을 취득하면(시행령 §27③ — 업무용·비업무용을 가리지 않는다)
    표준세율의 3배에서 중과기준세율의 2배를 뺀 세율이다: 주택 외 부동산 4%×3 − 4% = 8%, 농지 3%×3 − 4% = 5%.
    주택은 §13② 괄호로 §13의2①1호 세율(12%)이다. 대도시 중과 제외 업종(시행령 §26①)에 직접 쓸 목적이면 §11 세율이다.
    대도시 중과 여부를 정할 사실이 모자라면 추정하지 않고 대도시중과=None 과 두 경우의 세액을 함께 돌려준다.

    Args:
        acquisition_price: 취득가액 — 과세표준(원). 경매는 낙찰대금에 인수한 채무 등을 더한 사실상의 취득가격.
        acquire_date: 취득일(잔금일·경매 대금 납부일) "YYYY-MM-DD". 그 연도의 세율(검증된 연도만)로 계산한다.
        property_kind: "주택" | "주택외"(상가·사무실·오피스텔·토지 등 주택과 농지가 아닌 부동산) | "농지".
        property_in_metro: 취득하는 부동산이 대도시(과밀억제권역, 산업단지 제외) 안에 있는지. 모르면 None 으로 두고 property_location 을 준다.
        metro_office_date: 법인의 본점·주사무소·지점·분사무소가 대도시에서 설립·설치되거나 대도시로 전입한 날
            "YYYY-MM-DD"(서울 밖 수도권에서 서울로 옮긴 것도 전입이다 — §13②1호). 휴면법인을 인수했으면 그 법인의
            과점주주가 처음 된 날(시행령 §27②). 여러 사무소가 있으면 가장 최근의 설립·설치·전입일.
        no_metro_office: 대도시 안에 본점·지점 등이 없고 이 취득으로도 설치하지 않으면 True — 대도시 중과가 아니다.
        excluded_business: 대도시 중과 제외 업종(시행령 §26① 각 호)에 직접 사용할 목적의 취득이면 True. 어느 호인지 알면 excluded_business_item 을 준다.
        exclusive_area: 주택의 전용면적(㎡). 85 이하면 농어촌특별세가 붙지 않는다(농어촌특별세법 §4 11호). 주택일 때만.
        standard_value: 주택의 시가표준액(원, 지분·부속토지만 취득해도 주택 전체 기준). 시행령 §28의2 1호 판정에 쓴다.
        in_capital_area: 주택이 수도권(서울·인천·경기)에 있는지. standard_value 를 줄 때 필요하다.
        in_redevelopment_zone: 주택이 정비구역·소규모주택정비 사업시행구역에 있으면 True — 1호 예외에서 제외된다.
        heavy_exception_item: 시행령 §28의2의 1호 밖 다른 호에 해당하면 그 호 번호("3", "8", "12", "13의2" 등).
        excluded_business_item: 대도시 중과 제외 업종의 호 번호("1"~"37" — 예 "9" 의료업, "31" 등록 임대사업자의 주택임대사업).
            그 업종에 직접 사용할 목적의 취득일 때 준다. 호의 단서에 걸리면(예: 34호인데 대도시 밖에서 전입) 제외 업종으로 보지 않는다.
        excluded_business_facts: 그 호의 단서 요건 사실. 3호 {"예외업종_세부": "해외건설업"|"주택건설사업", "해외건설_당해실적": bool,
            "해외건설_사무실용": bool, "주택건설_3년내착공": bool}, 8호 {"정부출자비율": 0.25}, 10호 {"법인전환_초과부분": bool, "법인전환후_취득": bool},
            17·25호 {"설립후1개월내_등록": bool}, 34호 {"대도시밖에서_전입": bool}, 36호 {"매입임대_약정일": "YYYY-MM-DD", "주거용오피스텔": bool}.
            주지 않은 요건은 판정하지 않고 결과의 확인필요에 적힌다.
        property_location: 취득하는 부동산의 소재지("서울 강남구 역삼동", "경기도 성남시 분당구", "인천 서구 불로동"). property_in_metro 가
            None 일 때 수도권정비계획법 시행령 별표 1로 과밀억제권역인지 판정한다. 일부 지역만 해당하는 인천(강화군·옹진군·서구 8개 동 제외)·
            남양주시·시흥시는 판정하지 않는다(대도시중과=None).
        in_industrial_complex: 부동산이 산업단지(산업집적활성화 및 공장설립에 관한 법률) 안이면 True — 과밀억제권역이어도 대도시가 아니다.
            property_location 과 함께 쓴다. 모르면 None(과밀억제권역이면 대도시로 계산하고 주의에 남긴다).
        heavy_exception_facts: heavy_exception_item 으로 준 호의 요건 사실. 예 12호 {"전용면적": 59, "주택유형": "아파트", "특수관계인_제공": false},
            17호 {"전용면적": 84, "취득당시가액": 500000000}, 7호는 standard_value, 8호 {"멸실취득_주체": "주택건설사업자"}, 18호 {"인구감소지역": true,
            "임대등록_60일내": true}. 숫자·기간·지역 요건에 어긋나면 예외로 보지 않는다.

    Returns:
        법인주택중과, 주택중과_예외(확인필요·사후관리 포함), 대도시_소재지판정, 대도시중과_제외업종, 대도시중과(True·False·None), 대도시중과_사유, 적용세율, 세율근거, 취득세, 지방교육세,
        농어촌특별세, 총납부세액 (대도시중과가 None 이면 세액 대신 경우별_세액), 적용 조문, 미적용 조문, 값 출처, 주의, 다루지 않는 것.
    """
    from tax_nodes.chwideuk import 취득세_부동산
    from tax_nodes.chwideuk_gwase import 대도시_판정, 대도시중과_범위, 주택중과_예외

    if property_kind not in _ACQ_KIND:
        raise ValueError("property_kind 는 %s 중 하나여야 합니다: %r" % (" | ".join(_ACQ_KIND), property_kind))
    if acquisition_price <= 0:
        raise ValueError("acquisition_price 는 0보다 커야 합니다")
    if not acquire_date or len(acquire_date) != 10:
        raise ValueError("acquire_date 는 \"YYYY-MM-DD\" 로 줍니다 — 세율과 대도시 5년 기간의 기준일이다")
    if no_metro_office and metro_office_date:
        raise ValueError("no_metro_office 와 metro_office_date 를 함께 줄 수 없습니다")
    주택 = property_kind == "주택"
    if not 주택 and (exclusive_area is not None or standard_value is not None or heavy_exception_item is not None
                   or in_redevelopment_zone or heavy_exception_facts):
        raise ValueError("exclusive_area · standard_value · in_redevelopment_zone · heavy_exception_item · heavy_exception_facts 는 주택일 때만 씁니다")
    if heavy_exception_facts and heavy_exception_item is None:
        raise ValueError("heavy_exception_facts 는 heavy_exception_item(시행령 §28의2의 호)과 함께 줍니다")
    if excluded_business_facts and excluded_business_item is None:
        raise ValueError("excluded_business_facts 는 excluded_business_item(시행령 §26①의 호)과 함께 줍니다")
    if in_industrial_complex is not None and property_in_metro is not None:
        raise ValueError("in_industrial_complex 는 property_location 으로 대도시를 판정할 때만 씁니다 — property_in_metro 는 산업단지를 뺀 대도시 여부다")
    if standard_value is not None and in_capital_area is None:
        raise ValueError("standard_value 를 주면 in_capital_area(수도권 여부)도 줘야 합니다 — 기준액이 1억원과 2억원으로 갈린다")
    연도 = int(acquire_date[:4])
    notes, 출처 = [], {}

    # (1) 주택 중과 예외 — 시행령 §28의2
    예외, 예외정보 = False, None
    if 주택:
        요건 = {k: v for k, v in (heavy_exception_facts or {}).items()
              if k not in ("취득일", "시가표준액", "수도권", "정비구역", "주택중과_예외호", "취득원인")}
        if exclusive_area is not None:
            요건.setdefault("전용면적", exclusive_area)
        if heavy_exception_item is not None:
            요건.setdefault("취득당시가액", acquisition_price)
            요건.setdefault("법인", True)
        e = 주택중과_예외(취득일=acquire_date, 시가표준액=standard_value,
                    수도권=bool(in_capital_area) if (in_capital_area is not None or heavy_exception_item is None) else None,
                    정비구역=in_redevelopment_zone, 주택중과_예외호=heavy_exception_item, **(요건 if heavy_exception_item is not None else {}))
        예외 = e["중과예외"]
        예외정보 = {"해당": 예외, "호": e["호"], "근거": e["근거"]}
        if heavy_exception_item is not None:
            예외정보.update({"확인필요": e["확인필요"], "사후관리": e["사후관리"]})
            if not 예외:
                예외정보["사유"] = e["사유"]
                notes.append("heavy_exception_item=%s 은 시행령 §28의2의 예외로 보지 않았다 — %s" % (heavy_exception_item, e["사유"]))
            elif e["호"] != "1호 저가주택":
                notes.append("시행령 §28의2 %s는 호출자가 넘긴 호다 — 요건 가운데 사실로 준 것만 판정했다. 주택중과_예외의 확인필요·사후관리를 확인한다" % e["호"])
        if 예외 and e["근거"]:
            출처["주택 중과 예외"] = e["근거"]
        if standard_value is None and heavy_exception_item is None:
            notes.append("standard_value(시가표준액)가 없어 시행령 §28의2 1호(수도권 1억원·그 밖 2억원 이하 주택)를 보지 못했다 — "
                         "해당하면 12%가 아니라 1~3%다")

    # (2-가) 소재지로 대도시(과밀억제권역 − 산업단지) 판정 — 수도권정비계획법 시행령 §9·별표 1
    소재지판정 = None
    if property_location:
        z = 대도시_판정(property_location, 산업단지=in_industrial_complex)
        소재지판정 = {k: z[k] for k in ("소재지", "과밀억제권역", "대도시", "사유", "확인필요", "읽은_지역", "근거")}
        if property_in_metro is None:
            property_in_metro = z["대도시"]
            출처["대도시 소재지 판정"] = "%s — %s" % (z["근거"], z["사유"])
            if z["대도시"] is None:
                notes.append("소재지 '%s' 로는 대도시(과밀억제권역) 여부를 판정하지 않았다 — %s" % (property_location, z["사유"]))
            for x in z["확인필요"]:
                notes.append("대도시 판정 확인 필요: " + x)
        elif z["대도시"] is not None and z["대도시"] != property_in_metro:
            notes.append("property_in_metro=%s 와 소재지 판정(%s — %s)이 다르다 — property_in_metro 를 따랐다. 확인이 필요하다"
                         % (property_in_metro, "대도시" if z["대도시"] else "대도시 아님", z["사유"]))

    # (2-나) 대도시 중과 제외 업종 — 시행령 §26① 각 호
    제외업종, 업종정보 = bool(excluded_business), None
    if excluded_business_item is not None:
        b = 대도시중과_범위(취득일=acquire_date, 대도시_예외업종호=excluded_business_item,
                      **{k: v for k, v in (excluded_business_facts or {}).items() if k not in ("취득일", "대도시_예외업종호")})
        if b["대도시중과_예외업종"]:
            제외업종 = True
            업종정보 = {"해당": True, "호": b["대도시중과_예외업종_호"], "근거": b["대도시중과_예외업종_근거"],
                    "확인필요": b["대도시중과_예외업종_확인필요"], "사후관리": b["대도시중과_예외업종_사후관리"]}
            출처["대도시 중과 제외 업종"] = b["대도시중과_예외업종_근거"]
        else:
            제외업종 = False
            업종정보 = {"해당": False, "호": None, "사유": b.get("대도시중과_예외업종_사유")}
            notes.append("excluded_business_item=%s 은 대도시 중과 제외 업종으로 보지 않았다 — %s%s" % (
                excluded_business_item, b.get("대도시중과_예외업종_사유"),
                " (excluded_business=True 도 함께 왔지만 호의 판정을 따랐다)" if excluded_business else ""))
    excluded_business = 제외업종

    # (2) 대도시 중과 — 법 §13②1호, 시행령 §27③
    대도시, 사유 = None, None
    if property_in_metro is False:
        대도시, 사유 = False, "취득하는 부동산이 대도시(과밀억제권역, 산업단지 제외) 밖이다" + (
            " — " + 소재지판정["사유"] if 소재지판정 and 소재지판정["대도시"] is False else "")
    elif no_metro_office:
        대도시, 사유 = False, "대도시 안에 본점·지점 등이 없고 설치하지도 않는다 — §13②1호의 설립·설치·전입에 따른 취득이 아니다"
    elif property_in_metro is None:
        사유 = "property_in_metro(부동산이 대도시 안인지)를 모른다" + (
            " — 소재지 '%s' 는 판정하지 않았다(%s)" % (property_location, 소재지판정["사유"]) if 소재지판정 else "")
    elif not metro_office_date:
        사유 = "metro_office_date(대도시 안 본점·지점의 설립·설치·전입일)를 모른다 — 대도시에 사무소가 없으면 no_metro_office=True"
    else:
        범위 = 대도시중과_범위(대도시_설립전입일=metro_office_date, 취득일=acquire_date)["대도시중과_취득범위"]
        출처["대도시 중과 범위"] = "지방세법 시행령 §27③ — %s" % 범위
        if isinstance(범위, str) and 범위.startswith("설립·전입 후 5년 이내"):
            대도시, 사유 = True, "대도시 설립·설치·전입(%s) 후 5년 이내의 대도시 부동산 취득 — 용도를 가리지 않는다(시행령 §27③)" % metro_office_date
        elif isinstance(범위, str) and 범위.startswith("설립·전입 후 5년 경과"):
            대도시, 사유 = False, "대도시 설립·설치·전입(%s) 후 5년이 지났다(시행령 §27③)" % metro_office_date
        else:
            사유 = ("취득일이 설립·설치·전입일(%s)보다 앞선다 — 설립·전입 전 취득은 본점·지점 용도로 직접 사용하기 위한 것만 "
                  "중과다(시행령 §27③). 이 도구는 그 용도를 판정하지 않는다" % metro_office_date)
        notes.append("5년은 설립·설치·전입일부터 취득일까지 5×365일 이내인지로 셌다 — 만 5년이 되는 날 전후 하루 이틀은 확인이 필요하다")
    if 대도시 and excluded_business:
        notes.append("대도시 중과 제외 업종에 직접 사용할 목적이라 §11 세율을 적용했다(§13② 단서). 취득 후 1년 안에 그 업종에 쓰지 않거나 "
                     "2년 이상 쓰지 않고 팔면 중과세율로 추징된다(§13③)")
        if 업종정보:
            notes.extend("제외 업종 확인 필요(판정하지 않음): " + x for x in 업종정보["확인필요"])
            notes.extend("제외 업종 사후관리: " + x for x in 업종정보["사후관리"][1:])

    def 계산(중과: bool) -> dict:
        return 취득세_부동산(acquisition_price, 연도, _ACQ_KIND[property_kind], 취득일=acquire_date,
                        법인=(주택 and not 예외) or None, 전용면적=exclusive_area if 주택 else None,
                        대도시_법인설립전입_부동산=True if 중과 else None,
                        대도시_중과제외업종=True if (중과 and excluded_business) else None)

    def 근거맞춤(r: dict) -> tuple[list, list]:
        """개인용 취득세 노드가 낸 조문 근거를 이 도구가 내린 법인 판정에 맞춘다(findings 342)."""
        적용, 미적용 = list(r["적용 조문"]), [dict(m) for m in r["미적용 조문"]]
        고침 = {}
        if 주택:
            고침["지방세법 §13의3"] = "법인 취득 — 세대 주택 수를 세지 않는다"
            고침["지방세법 §13의2④"] = "법인 취득 — 조정대상지역 여부를 묻지 않는다"
            if 예외:
                고침["지방세법 §13의2①"] = "시행령 §28의2 %s 예외로 법인 주택 중과(12%%)에서 빠진다" % 예외정보["호"]
                미적용 = [m for m in 미적용 if m["표기"] != "지방세법 시행령 §28의2"]
                if "지방세법 시행령 §28의2" not in 적용:
                    적용.append("지방세법 시행령 §28의2")
            elif standard_value is None and heavy_exception_item is None:
                고침["지방세법 시행령 §28의2"] = "판정 불가 — 시가표준액(standard_value)을 받지 못했다"
            else:
                고침["지방세법 시행령 §28의2"] = "예외에 해당하지 않는다" + (
                    " — %s" % 예외정보["사유"] if 예외정보.get("사유") else " — 시가표준액이 기준액을 넘거나 정비구역 등 제외 사유")
        if 대도시 is None:
            고침["지방세법 §13②"] = "판정 불가 — %s" % 사유
        elif 대도시 is False:
            고침["지방세법 §13②"] = "대도시 중과 아님 — %s" % 사유
        for m in 미적용:
            if m["표기"] in 고침:
                m["사유"] = 고침[m["표기"]]
        return 적용, 미적용

    out = {"납세의무자": "법인", "취득가액": acquisition_price, "취득일": acquire_date, "부동산": property_kind,
           "법인주택중과": bool(주택 and not 예외) if 주택 else None, "주택중과_예외": 예외정보,
           "대도시중과": 대도시, "대도시중과_사유": 사유}
    if 소재지판정 is not None:
        out["대도시_소재지판정"] = 소재지판정
    if 업종정보 is not None:
        out["대도시중과_제외업종"] = 업종정보
    if 대도시 is None:
        아님, 중과 = 계산(False), 계산(True)
        같음 = _acq_parts(아님) == _acq_parts(중과)
        if 같음:                                   # 법인 주택 12%는 대도시 여부와 무관하다
            r = 아님
            out["대도시중과_사유"] = 사유 + " — 다만 이 취득은 어느 쪽이든 세액이 같다"
            out.update(_acq_parts(r))
        else:
            r = 중과
            out.update({"적용세율": None, "세율근거": None, "취득세": None, "지방교육세": None, "농어촌특별세": None,
                        "총납부세액": None,
                        "경우별_세액": {"대도시 중과 아님": _acq_parts(아님), "대도시 중과": _acq_parts(중과)}})
            notes.append("대도시 중과 여부를 정하지 못해 세액을 하나로 내지 않았다 — 경우별_세액의 두 값 가운데 어느 쪽인지는 "
                         "대도시중과_사유에 적힌 사실로 갈린다. 둘 중 하나를 골라 답하지 않는다")
            적용, 미적용 = 근거맞춤(아님)
            out.update({"적용 조문": 적용, "미적용 조문": 미적용,"값 출처": dict(아님["값 출처"], **출처)})
            out["주의"] = notes
            out["다루지 않는 것"] = ACQUISITION_NOT_COVERED
            return out
    else:
        r = 계산(bool(대도시))
        out.update(_acq_parts(r))
    if 주택 and 예외 and 대도시 and not excluded_business:
        notes.append("시행령 §28의2는 '법 §13의2①을 적용할 때'의 예외다. 대도시 중과(§13②)는 괄호에서 주택에 §13의2①1호 '세율'을 쓰라고만 하므로 "
                     "문언대로 12%를 적용했다 — 시가표준액 기준 이하 주택이 대도시 중과에서도 빠지는지는 공식 해석례를 확인하지 못했다")
    if 주택 and exclusive_area is None:
        notes.append("exclusive_area 가 없어 농어촌특별세를 과세로 계산했다 — 전용 85㎡ 이하 주택이면 농어촌특별세가 없다")
    if 주택 and not 예외:
        notes.append("법인의 주택 취득은 주택 수·조정대상지역과 무관하게 12%다(§13의2①1호)")
    적용, 미적용 = 근거맞춤(r)
    out.update({"적용 조문": 적용, "미적용 조문": 미적용, "값 출처": dict(r["값 출처"], **출처)})
    out["주의"] = notes
    out["다루지 않는 것"] = ACQUISITION_NOT_COVERED
    return out
