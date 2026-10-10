# -*- coding: utf-8 -*-
"""korea-realestate 세금 판정·계산 MCP 서버 (공개판).

이 파일은 scripts/extract_tax_server.py 가 server.py(비공개 통합 서버, git d74a04a)에서
세금 도구와 그 의존 정의만 AST로 뽑아 생성한 것이다. 손으로 고치지 말고 생성기를 다시 돌린다.
도구 43개. 법령·재결례 조회 도구는 .env의 LAW_OC(법제처 Open API 키, 무료)가 있을 때만 동작한다.
"""
import os

import httpx

from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

import tax_params

import http_redact

http_redact.install()   # 에러 메시지·로그에서 API 키를 가린다 — 도구 에러가 고객 채팅·베타 로그로 나간다

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

LAW_OC = os.environ.get("LAW_OC", "")

LAW_SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"

LAW_SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"

SERVER_INSTRUCTIONS = 'Korean real estate tax engine. Computes and judges 취득세 (acquisition tax), 재산세 (property tax), 종합부동산세 (comprehensive holding tax), 양도소득세 (capital gains tax), 주택임대소득세 (rental income tax), 증여세·상속세 (gift/inheritance tax on real estate) and 재건축부담금 (reconstruction levy) under Korean law. Every result lists the statute articles applied, the articles considered but not applied (with reasons), and the provenance grade of each input. Use judge_* tools first to settle facts (household, home count, exemptions), then calc_* tools for amounts. Not tax advice; results are one reading of the statute.'

mcp = FastMCP("budongsan-tax", instructions=SERVER_INSTRUCTIONS)

@mcp.tool(title='Search Korean statutes', annotations=ToolAnnotations(title='Search Korean statutes', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def search_law(query: str, target: str = "law", display: int = 20) -> dict:
    """Search Korean statutes and administrative rules on the national law database (law.go.kr). Needs LAW_OC key.

    법제처 국가법령정보에서 법령 또는 행정규칙(고시)을 검색한다.

    Args:
        query: 검색할 법령명/고시명 또는 키워드
        target: "law"(법률/시행령/시행규칙, 기본값) 또는 "admrul"(행정규칙 — 투기과열지구
                지정, 조정대상지역 지정 등 부처 고시가 여기 포함됨) 또는 "ordin"(자치법규)
        display: 결과 개수 (최대 100)

    검색 결과의 "법령일련번호"(law) 또는 "행정규칙일련번호"(admrul) 값을
    get_law_detail의 doc_id로 넘기면 조문/고시 원문 전체를 볼 수 있다.
    """
    if not LAW_OC:
        raise RuntimeError("LAW_OC가 설정되지 않았습니다 (.env 확인)")

    params = {
        "OC": LAW_OC,
        "target": target,
        "type": "JSON",
        "query": query,
        "display": display,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(LAW_SEARCH_URL, params=params)
        resp.raise_for_status()
        return resp.json()

@mcp.tool(title='Read a Korean statute', annotations=ToolAnnotations(title='Read a Korean statute', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def get_law_detail(doc_id: str, target: str = "law") -> dict:
    """Fetch the full text of a Korean statute by name or MST id, optionally one article. Needs LAW_OC key.

    법령 조문 또는 행정규칙(고시) 원문 전체를 조회한다.

    Args:
        doc_id: search_law 결과의 "법령일련번호"(target="law") 또는
                "행정규칙일련번호"(target="admrul") 값
        target: search_law에서 사용한 것과 동일하게 "law" 또는 "admrul" 지정
    """
    if not LAW_OC:
        raise RuntimeError("LAW_OC가 설정되지 않았습니다 (.env 확인)")

    # lawService.do는 target별로 일련번호 파라미터명이 다르다 — law/ordin은 MST,
    # admrul은 ID (2026-08-17 실사용 중 발견: law에 ID를 쓰면 전부 "일치하는 법령이 없습니다" 오답)
    id_param = "ID" if target == "admrul" else "MST"
    params = {
        "OC": LAW_OC,
        "target": target,
        "type": "JSON",
        id_param: doc_id,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(LAW_SERVICE_URL, params=params)
        resp.raise_for_status()
        return resp.json()

_ORDIN_TAX_LEVEL = {
    "특별시": "시세", "광역시": "시세", "특별자치시": "시세",
    "특별자치도": "도세", "도": "도세",
}

@mcp.tool(title='Local tax ordinance lookup', annotations=ToolAnnotations(title='Local tax ordinance lookup', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def get_local_tax_ordinances(sido: str, keyword: str = "취득세") -> dict:
    """Look up a Korean city/county tax ordinance (rate adjustments, local reliefs). Needs LAW_OC key.

    관할 시·도 지방세 조례에서 취득세(또는 keyword) 관련 조문을 실시간 조회한다.

    지방세법 §14가 조례로 취득세 세율을 표준세율의 50% 범위에서 가감할 수 있게
    허용하므로(탄력세율) 세액 판정 전 관할 조례 확인이 필요하다. 재산세는
    §111③(특별한 재정수요·재해 시, 해당 연도 한정)이 같은 구조. 조례는 개정이
    잦아 캐시 금지 — 호출 시점 조회 원칙(세율 하드코딩 금지 원칙의 조례 버전).

    Args:
        sido: 광역 지자체 전체 명칭 — "서울특별시", "경기도", "부산광역시" 등.
              시군구 단위가 아니라 광역 단위(취득세는 광역단체세).
        keyword: 조문에서 찾을 세목 키워드 (기본 "취득세")

    Returns:
        ordinances: 관할 지방세 조례 목록(일련번호는 get_law_detail(target="ordin")에
        바로 사용 가능), matched_articles: keyword·탄력세율 관련 조문 발췌,
        flexible_rate_found: 탄력세율 가감 조문 발견 여부(미발견 시 표준세율 적용
        판단, 단 감면 조례는 별도 검토 필요).
    """
    if not LAW_OC:
        raise RuntimeError("LAW_OC가 설정되지 않았습니다 (.env 확인)")

    level = next(
        (v for k, v in _ORDIN_TAX_LEVEL.items() if sido.endswith(k)), None
    )
    if level is None:
        raise ValueError(
            "sido는 광역 지자체 전체 명칭이어야 합니다 (예: 서울특별시·경기도·부산광역시). "
            "취득세는 광역단체세라 시군구 조례가 아니라 시·도 조례를 봅니다."
        )

    async with httpx.AsyncClient(timeout=30) as client:
        # 1) 관할 지방세 조례 검색 (기본·세율 조례 + 감면 조례)
        resp = await client.get(LAW_SEARCH_URL, params={
            "OC": LAW_OC, "target": "ordin", "type": "JSON",
            "query": f"{sido} {level} 조례", "display": 30,
        })
        resp.raise_for_status()
        root = resp.json().get("OrdinSearch", {})
        laws = root.get("law", [])
        if isinstance(laws, dict):
            laws = [laws]
        # 검색이 느슨한 매칭이라 지자체명 + '시세/도세' 명칭으로 클라이언트 필터
        ordinances = [
            {
                "자치법규명": l.get("자치법규명"),
                "자치법규일련번호": l.get("자치법규일련번호"),
                "지자체기관명": l.get("지자체기관명"),
                "시행일자": l.get("시행일자"),
            }
            for l in laws
            if l.get("지자체기관명") == sido and level in (l.get("자치법규명") or "")
        ]

        # 2) 각 조례 본문에서 keyword·탄력세율 조문 발췌
        matched_articles = []
        flexible_rate_found = False
        for o in ordinances[:6]:
            resp = await client.get(LAW_SERVICE_URL, params={
                "OC": LAW_OC, "target": "ordin", "type": "JSON",
                "MST": o["자치법규일련번호"],
            })
            resp.raise_for_status()
            body = resp.json().get("LawService", {})
            jo = body.get("조문", {})
            units = jo.get("조", []) if isinstance(jo, dict) else jo
            if isinstance(units, dict):
                units = [units]
            for u in units:
                content = u.get("조내용") or ""
                if u.get("조문여부") != "Y" or keyword not in content:
                    continue
                is_flex = ("가감" in content) or ("탄력" in content)
                flexible_rate_found = flexible_rate_found or is_flex
                matched_articles.append({
                    "조례명": o["자치법규명"],
                    "조제목": u.get("조제목"),
                    "조내용": content[:1500],
                    "탄력세율조문": is_flex,
                })

    return {
        "sido": sido,
        "관할세목레벨": level,
        "ordinances": ordinances,
        "matched_articles": matched_articles,
        "flexible_rate_found": flexible_rate_found,
        "판정안내": (
            "탄력세율 가감 조문 발견 — 표준세율 대신 조례 세율 적용 여부를 원문으로 확정할 것"
            if flexible_rate_found else
            f"{keyword} 탄력세율 가감 조문 미발견 — 지방세법 표준세율 적용으로 판단. "
            "단 감면 조례(지특법 위임)는 요건 해당 시 별도 적용 검토"
        ),
        "법적근거": "지방세법 §14(취득세 ±50% 조례 가감)·§111③(재산세, 해당 연도 한정)",
    }

@mcp.tool(title='Capital gains tax (양도소득세)', annotations=ToolAnnotations(title='Capital gains tax (양도소득세)', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def calc_transfer_tax(
    purchase_price: int,
    sale_price: int,
    holding_years: float,
    necessary_expenses: int,
    year: int,
    asset_type: str = "주택",
    tax_brackets: list[dict] | None = None,
    long_term_deduction_rate: float = -1.0,
    basic_deduction: int = 0,
    surcharge_rate: float = -1.0,
    heavy_home_count: int = 0,
) -> dict:
    """Korea capital gains tax (양도소득세) on real estate: rate, long-term holding deduction, heavy rates, surtax. Returns the statute trail.

    양도소득세를 계산한다. 세율·공제는 year로 상수표에서 읽는다.

    ⚠️ 2026-08-30 변경 — year 필수. 세율표·기본공제·중과 가산세율을
    data/tax_params.json(1층)에서 읽고, **단기세율 비교과세(§104① 후단·§104⑦ 후단)를
    코드가 수행한다.** 종전에는 "두 번 호출해서 큰 쪽을 채택하라"고 호출자에게 넘겼는데,
    그건 사람이 빠뜨리는 자리다. year가 검증 안 된 과거 연도면 계산을 거부하고,
    미래 연도는 현행법 기준 추정으로 계산하되 결과에 그렇게 표시한다.

    asset_type: "주택"(조합원입주권·분양권 포함해 단기세율이 주택등 기준) / "토지" /
    "분양권"(보유기간 무관 하한 60%) / "비사업용토지"(기본세율 +10%p).
    heavy_home_count: §104⑦ 중과 주택수(조정대상지역 기준). 2면 +20%p, 3 이상이면 +30%p.
    surcharge_rate를 직접 주면 그것이 우선한다.

    Args:
        purchase_price: 매수 가격 (원)
        sale_price: 매도 가격 (원)
        holding_years: 보유 기간 (년)
        necessary_expenses: 취득세, 중개보수 등 필요경비 (원)
        tax_brackets: [{"upto": 과세표준 상한(원, 마지막 구간은 None), "rate": 세율(0~1), "deduction": 누진공제액(원)}, ...]
                      최신 소득세법 시행령 별표에서 확인해서 넘길 것 — 하드코딩된 기본값 없음
        long_term_deduction_rate: 장기보유특별공제율 (0~1), 다주택 중과 대상이면 0으로 넘길 것
        basic_deduction: 양도소득 기본공제 (기본 250만원, 연 1회)
        surcharge_rate: 다주택자 중과세율 가산분 (0~1), 해당 없으면 0

    소득세법 §95②에 따라 §104⑦ 중과대상 주택은 장특공 자체가 배제된다(미등기와 동급) —
    surcharge_rate와 long_term_deduction_rate를 동시에 넘기는 조합은 법문상 존재하지 않으므로
    거부한다. 장특공은 보유 3년 이상만 가능(§95②).

    이 함수가 지원하지 않는 산식 — 호출자가 사전에 처리할 것:
      · 보유 2년 미만 + 중과: max(단기세율 세액, 중과세율 세액) 비교과세(§104⑦ 후단) —
        두 번 호출해서 큰 쪽을 채택
      · 고가주택(양도가액 12억 초과) 1세대1주택: 과세 양도차익 = 전체차익×(양도가액−12억)/양도가액
        (영 §160) — 안분 후의 값을 기준으로 별도 계산 필요
      · 같은 과세기간 2회 이상 양도 시 합산 비교과세(§104⑤)

    Returns:
        계산 과정이 담긴 dict (양도차익, 과세표준, 산출세액 등 단계별로 반환 — 검증 가능하도록)
    """
    # ── 1·2층 배선: 미지정 인자는 상수표(연도별)에서 읽는다 ──────────────────
    src = {}
    if surcharge_rate < 0:
        surcharge_rate = 0.0
        if heavy_home_count >= 2:
            rates = tax_params.get_param("양도세.중과.가산세율", year)
            surcharge_rate = rates["3주택이상" if heavy_home_count >= 3 else "2주택"]
            src["중과 가산세율"] = tax_params.cite("양도세.중과.가산세율", year)
    if long_term_deduction_rate < 0:
        long_term_deduction_rate = 0.0   # 판정 결과를 못 받았으면 안전하게 0
    if not basic_deduction:
        basic_deduction = tax_params.get_param("양도세.기본공제", year)
        src["기본공제"] = tax_params.cite("양도세.기본공제", year)
    if tax_brackets is None:
        key = ("양도세.비사업용토지.가산세율" if asset_type == "비사업용토지"
               else "양도세.기본세율표")
        tax_brackets = tax_params.get_brackets("양도세.기본세율표", year)
        src["세율표"] = tax_params.cite("양도세.기본세율표", year)
        if asset_type == "비사업용토지":
            add = tax_params.get_param("양도세.비사업용토지.가산세율", year)
            tax_brackets = [dict(b, rate=b["rate"] + add) for b in tax_brackets]
            src["비사업용토지 가산"] = tax_params.cite(key, year)

    if surcharge_rate > 0 and long_term_deduction_rate > 0:
        raise ValueError(
            "중과대상(surcharge_rate>0)은 장특공 배제 — 소득세법 §95②가 §104⑦ 자산을 "
            "장특공 대상에서 제외하므로 long_term_deduction_rate는 0이어야 합니다"
        )
    if holding_years < 3 and long_term_deduction_rate > 0:
        raise ValueError("장특공은 보유 3년 이상만 가능(§95②) — holding_years와 모순")

    gain = sale_price - purchase_price - necessary_expenses
    if gain <= 0:
        return {"양도차익": gain, "납부세액": 0, "비고": "양도차익 없음(손실 또는 0)"}

    long_term_deduction = int(gain * long_term_deduction_rate)
    income_after_deduction = gain - long_term_deduction
    taxable_base = max(income_after_deduction - basic_deduction, 0)

    base_rate = 0.0
    progressive_deduction = 0
    # upto=None(무한 상한) 구간은 맨 뒤로 정렬 — 앞에 오면 첫 반복에서 즉시 매칭돼
    # 모든 과세표준에 최고구간 세율이 적용되는 버그가 있었음 (2026-08-16 수정)
    for bracket in sorted(tax_brackets, key=lambda b: (b["upto"] is None, b["upto"] or 0)):
        base_rate = bracket["rate"]
        progressive_deduction = bracket["deduction"]
        if bracket["upto"] is None or taxable_base <= bracket["upto"]:
            break

    applied_rate = base_rate + surcharge_rate
    calculated_tax = max(int(taxable_base * applied_rate) - progressive_deduction, 0)

    # §104① 후단·§104⑦ 후단 — 하나의 자산이 둘 이상 세율에 해당하면 산출세액이 큰 것을
    # 적용한다. 단기보유는 누진세율이 아니라 비례세율이라 과세표준이 작을수록 단기 쪽이
    # 크게 나오는 구간이 생긴다. 종전에는 "두 번 호출해서 큰 쪽을 채택하라"고 호출자에게
    # 넘겼는데, 그게 사람이 빠뜨리는 자리라 코드로 내렸다 (2026-08-30).
    비교 = [{"근거": "기본세율%s" % ("+중과" if surcharge_rate else ""),
            "세율": applied_rate, "세액": calculated_tax}]
    short = tax_params.get_param("양도세.단기세율", year)
    주택등 = asset_type in ("주택", "조합원입주권", "분양권")
    if asset_type == "분양권":
        # 분양권은 보유기간과 무관하게 하한이 있다(§104①1호 단서)
        band = short["분양권"]
        rate = band["1년미만"] if holding_years < 1 else band["그이후"]
        비교.append({"근거": "분양권 세율", "세율": rate,
                    "세액": int(taxable_base * rate)})
    elif holding_years < 1:
        rate = short["1년미만"]["주택등" if 주택등 else "그밖"]
        비교.append({"근거": "1년 미만 단기세율", "세율": rate,
                    "세액": int(taxable_base * rate)})
    elif holding_years < 2:
        rate = short["1년이상2년미만"]["주택등" if 주택등 else "그밖"]
        비교.append({"근거": "1년 이상 2년 미만 단기세율", "세율": rate,
                    "세액": int(taxable_base * rate)})
    if len(비교) > 1:
        src["비교과세"] = "소득세법 §104① 후단·§104⑦ 후단 — 큰 세액 채택"
    채택 = max(비교, key=lambda x: x["세액"])
    calculated_tax = 채택["세액"]
    applied_rate = 채택["세율"]
    if 채택["근거"].startswith("기본세율") is False:
        progressive_deduction = 0

    local_income_tax = int(calculated_tax * 0.1)

    return {
        "양도차익": gain,
        "장기보유특별공제": long_term_deduction,
        "공제후소득금액": income_after_deduction,
        "기본공제": basic_deduction,
        "과세표준": taxable_base,
        "적용세율(기본+중과)": applied_rate,
        "누진공제": progressive_deduction,
        "양도소득세": calculated_tax,
        "지방소득세(10%)": local_income_tax,
        "총납부세액": calculated_tax + local_income_tax,
        "과세연도": year,
        "세율 비교(§104① 후단)": 비교,
        "채택": 채택["근거"],
        "값 출처": src,
    }

@mcp.tool(title='Acquisition tax (취득세)', annotations=ToolAnnotations(title='Acquisition tax (취득세)', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def calc_acquisition_tax(
    acquisition_price: int,
    year: int,
    acquisition_type: str = "주택유상",
    heavy_type: str = "",
    exclusive_area: float = 0.0,
    standard_rate: float = -1.0,
    heavy_surcharge_rate: float = -1.0,
    ordinance_adjustment_rate: float = 0.0,
    local_education_tax_rate: float = -1.0,
    rural_special_tax_rate: float = -1.0,
) -> dict:
    """Korea acquisition tax (취득세) on real estate plus local education tax and rural special tax, by year and acquisition type.

    취득세(+지방교육세+농어촌특별세)를 계산한다. 세율은 year로 상수표에서 읽는다.

    ⚠️ 2026-08-30 변경 — year 필수. 종전에는 세 세율을 전부 호출자가 계산해 넘겨야 했고,
    특히 부가세 두 개는 '취득세액×비율'이 아니라 **세율을 갈아끼워 다시 산출**하는 구조라
    사람이 재현하다 틀리기 쉬웠다(종부세 §4의3에서 실제로 낸 사고와 같은 유형). 이제
    산식을 코드가 수행한다 — tax_params.acquisition_* 참조.

    acquisition_type: "주택유상"(§11①8호 구간세율 1~3%) / "유상.농지외"(4%) / "유상.농지"(3%)
      / "상속.농지외"(2.8%) / "상속.농지"(2.3%) / "무상"(3.5%) / "무상.비영리사업자"(2.8%)
      / "원시취득"(2.8%) / "공유물분할"(2.3%)
    heavy_type: §13의2 중과 유형. "" | "법인" | "2주택조정_또는_3주택비조정"
      | "3주택이상조정_또는_4주택이상비조정". 일시적 2주택은 §13의2①2호 괄호로 제외되므로
      판정 결과가 '중과 아님'이면 빈 문자열을 넘길 것.
    exclusive_area: 전용면적(㎡). 85 이하면 농특세 비과세(농특세법 §4 11호).

    지방세법 제11조(부동산 취득의 세율)의 표준세율에, 해당하면 제13조의2(법인/다주택
    중과)의 가산세율과 제14조(조례에 따른 세율 조정, 100분의 50 범위)를 더해 실효세율을
    구성한다. calc_transfer_tax와 같은 이유로 이 함수는 세율표를 하드코딩하지 않는다 —
    조정대상지역 지정 현황, 다주택 판정 기준(일시적 2주택 등 중과 배제 사유 포함)이
    수시로 바뀌므로, 매번 search_law("지방세법")로 시행 중인 조문을 확인해서 세율을
    직접 계산한 뒤 넘길 것. 이 함수는 세율을 판단하지 않고 산식만 적용한다.

    지방교육세·농어촌특별세도 취득세 부가세목이라 함께 계산할 수 있게 인자를 뒀지만,
    두 세율도 정책적으로 바뀔 수 있어 하드코딩하지 않는다 — 생략하면 0으로 간주해
    취득세 본세만 계산한다.

    ⚠️ 두 부가세율은 '취득세액×비율'이 아니라 과세표준 대비 실효율로 넘겨야 하며,
    산식이 서로 다르다 (2026-08-17 법문 확인 — 지방세법 §151①1호, 농특세법 §5①6호):
      · 지방교육세: 일반 부동산 = (표준세율−2%)×20% (4%면 0.4%) /
        주택 유상(§11①8호 1~3%) = 취득세율×50%×20% (0.1~0.3%) /
        다주택·법인 중과(§13의2, 8·12%) = (4%−2%)×20% = 0.4% 고정 (세율 뛰어도 불변)
      · 농어촌특별세: 표준세율을 2%로 치환해 §13의2 중과 가산 구조를 유지한 채
        재계산한 취득세액×10% → 일반 0.2% / 8% 중과 0.6% / 12% 중과 1.0%.
        전용 85㎡ 이하 서민주택은 비과세(농특세법 §4 9·11호, 영 §4⑤). 취득세 감면 시
        감면세액×20%의 감면분 농특세가 별도로 붙는다(§5①1호 — 이 함수 밖에서 계산).

    Args:
        acquisition_price: 취득가액/과세표준 (원)
        standard_rate: 지방세법 제11조 표준세율 (0~1)
        heavy_surcharge_rate: 다주택·법인 등 중과기준세율 가산분 (0~1), 해당 없으면 0
        ordinance_adjustment_rate: 지방세법 제14조 조례 가감율 (-0.5~0.5), 해당 없으면 0
        local_education_tax_rate: 지방교육세율 (0~1), 미확인 시 0으로 두고 별도 계산
        rural_special_tax_rate: 농어촌특별세율 (0~1) — 전용면적 85㎡ 이하는 통상 비과세이므로
            과세대상 여부부터 확인 후 넘길 것, 미확인 시 0

    Returns:
        계산 과정이 담긴 dict (적용세율, 취득세 본세, 지방교육세, 농어촌특별세, 총납부세액)
    """
    if acquisition_price <= 0:
        raise ValueError("acquisition_price는 0보다 커야 합니다")

    # ── 1·2층 배선 ──────────────────────────────────────────────────────────
    src = {}
    is_housing_sale = acquisition_type == "주택유상"
    배수 = 0.0
    if heavy_type:
        표 = tax_params.get_param("취득세.중과.중과기준세율배수", year)
        if heavy_type not in 표:
            raise ValueError("heavy_type은 %s 중 하나여야 합니다(받은 값: %r)"
                             % (list(표), heavy_type))
        배수 = 표[heavy_type]
        src["중과 배수"] = tax_params.cite("취득세.중과.중과기준세율배수", year)

    if standard_rate < 0:
        if heavy_type:
            # §13의2는 §11①7호나목(4%)을 표준세율로 삼는다 — 주택 구간세율이 아니다
            standard_rate = tax_params.get_param("취득세.표준세율", year)["유상.농지외"]
            src["표준세율"] = "지방세법 §13의2① — §11①7호나목 4%를 표준세율로 사용"
        elif is_housing_sale:
            standard_rate = tax_params.acquisition_housing_rate(acquisition_price, year)
            src["표준세율"] = tax_params.cite("취득세.주택유상.구간", year)
        else:
            표준 = tax_params.get_param("취득세.표준세율", year)
            if acquisition_type not in 표준:
                raise ValueError("acquisition_type은 '주택유상' 또는 %s 중 하나여야 합니다"
                                 % list(표준))
            standard_rate = 표준[acquisition_type]
            src["표준세율"] = tax_params.cite("취득세.표준세율", year)
    if heavy_surcharge_rate < 0:
        heavy_surcharge_rate = (tax_params.get_param("취득세.중과기준세율", year) * 배수
                                if heavy_type else 0.0)
    if local_education_tax_rate < 0:
        local_education_tax_rate = tax_params.acquisition_local_education_rate(
            year, standard_rate, is_housing_sale=is_housing_sale,
            heavy_13_2=bool(heavy_type))
        src["지방교육세"] = tax_params.cite("취득세.지방교육세.산식", year)
    if rural_special_tax_rate < 0:
        exempt = bool(exclusive_area) and exclusive_area <= 85
        rural_special_tax_rate = tax_params.acquisition_rural_special_rate(
            year, heavy_multiplier=배수, exempt=exempt)
        src["농특세"] = tax_params.cite("농특세.취득세분.세율", year) + (
            " / 전용 85㎡ 이하 비과세(농특세법 §4 11호)" if exempt else "")

    applied_rate = standard_rate + heavy_surcharge_rate + ordinance_adjustment_rate
    acquisition_tax = int(acquisition_price * applied_rate)
    local_education_tax = int(acquisition_price * local_education_tax_rate)
    rural_special_tax = int(acquisition_price * rural_special_tax_rate)

    notes = []
    if not exclusive_area and rural_special_tax:
        notes.append("전용면적 미전달 — 85㎡ 이하 서민주택이면 농특세가 비과세됩니다"
                     "(농어촌특별세법 §4 11호). exclusive_area를 넘겨 확인하십시오")
    return {
        "취득가액": acquisition_price,
        "적용세율(표준+중과+조례)": round(applied_rate, 6),
        "취득세": acquisition_tax,
        "지방교육세": local_education_tax,
        "농어촌특별세": rural_special_tax,
        "총납부세액": acquisition_tax + local_education_tax + rural_special_tax,
        "과세연도": year,
        "세율 내역": {"표준세율": round(standard_rate, 6),
                  "중과 가산": round(heavy_surcharge_rate, 6),
                  "조례 가감": ordinance_adjustment_rate,
                  "지방교육세율": round(local_education_tax_rate, 6),
                  "농특세율": round(rural_special_tax_rate, 6)},
        "값 출처": src,
        "주의": " / ".join(notes),
    }

def _apply_brackets(taxable_base: int, tax_brackets: list[dict]) -> tuple[float, int]:
    """누진세율표에서 과세표준이 속한 구간의 (세율, 누진공제)를 찾는다.

    upto=None(무한 상한) 구간은 맨 뒤로 정렬 — calc_transfer_tax에서 2026-08-16 수정한
    구간선택 로직과 동일. 앞에 오면 첫 반복에서 즉시 매칭돼 모든 과세표준에 최고구간
    세율이 적용되는 버그가 있었다.
    """
    rate, deduction = 0.0, 0
    for bracket in sorted(tax_brackets, key=lambda b: (b["upto"] is None, b["upto"] or 0)):
        rate = bracket["rate"]
        deduction = bracket["deduction"]
        if bracket["upto"] is None or taxable_base <= bracket["upto"]:
            break
    return rate, deduction

@mcp.tool(title='Property tax (재산세)', annotations=ToolAnnotations(title='Property tax (재산세)', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def calc_property_tax(
    official_price: int,
    year: int,
    prev_year_official_price: int = 0,
    one_home: bool = False,
    fair_market_ratio: float = 0.0,
    tax_brackets: list[dict] | None = None,
    urban_area_rate: float = -1.0,
    local_education_tax_rate: float = -1.0,
    taxable_base_cap: int = 0,
) -> dict:
    """Korea property tax (재산세) on housing: fair-market ratio, base cap, one-household special rate, urban area levy, education tax.

    재산세(주택분 중심)를 계산한다. 세율·비율은 year로 상수표에서 읽는다.

    ⚠️ 2026-08-30 변경 — year가 필수가 됐고, 세율표·공정시장가액비율·도시지역분·
    지방교육세율은 data/tax_params.json(1층)에서 자동으로 읽는다. 그 연도가 검증되지
    않았으면 ParamNotVerified로 계산을 거부한다. 종전에는 호출자가 전부 넘겨야 했고
    빠뜨리면 조용히 틀렸다 — 실제로 과세표준상한제 누락으로 세액이 틀린 사고가 있었다.
    명시 인자를 주면 그것이 우선하되, 결과의 "값 출처"에 표시된다.

    산식 근거 (지방세법, 2026-08-16 원문 확인 — MST 282559):
      §110① 과세표준 = 시가표준액(주택은 공시가격) × 공정시장가액비율
             (비율은 시행령 §109 — 매년 5~6월경 개정되므로 하드코딩하지 않는다.
              참고로 2026년 기준 주택 60%, 1세대1주택은 공시가별 43~45%였음)
      §110③ 주택 과세표준상한제(2023 신설) — 직전연도 기반 상한액이 계산돼 있으면
             taxable_base_cap으로 넘기면 min()을 적용한다
      §111① 누진세율 — tax_brackets로 전달. 1세대1주택 9억 이하 특례세율(§111의2)은
             ⚠️ 2026-12-28까지 성립분만 유효한 일몰 조항이므로 적용 전 유효기간 확인
      §111③ 조례 ±50% 가감 — 호출자가 세율표에 반영해서 넘길 것
      §112  도시지역분 = 과세표준 × 0.14%(조례로 최대 0.23%) — urban_area_rate로 전달
      §122  세부담상한 150%는 주택에는 적용하지 않음(과표상한제로 대체) — 토지·건축물을
            이 함수로 계산하는 경우 상한 적용은 호출자 책임

    지방교육세는 재산세 본세(도시지역분 제외)에 대한 비율로 계산한다 — 세율은
    지방세법 §151 확인 후 전달(미확인 시 0).

    Args:
        official_price: 시가표준액/공시가격 (원)
        year: 과세연도(납세의무 성립연도). 상수표 조회 키이며 필수다.
        prev_year_official_price: 직전연도 시가표준액 — 주면 §110③ 과세표준상한액을
            자동 계산한다. 안 주면 상한제가 적용되지 않으니 주택은 사실상 필수.
        one_home: 지방세법 영 §110의2 1세대1주택 여부. 세대(배우자 포함) 기준이며
            판정 결과를 넘길 것 — 인별 1주택과 다르다.
        fair_market_ratio: 공정시장가액비율. 0이면 상수표에서 읽는다.
        tax_brackets: 세율표. None이면 상수표에서 읽는다.
        urban_area_rate: 도시지역분 세율. 음수면 상수표, 0을 명시하면 미적용 지역.
        local_education_tax_rate: 지방교육세율. 음수면 상수표에서 읽는다.
        taxable_base_cap: 과세표준상한액(원). 0이고 prev_year_official_price가 있으면
            자동 계산한다.

    Returns:
        계산 단계별 dict (검증 가능하도록) + 값 출처
    """
    if official_price <= 0:
        raise ValueError("official_price는 0보다 커야 합니다")

    src = {}
    if fair_market_ratio:
        src["공정시장가액비율"] = "호출자 지정"
    elif one_home:
        table = tax_params.get_param("재산세.주택.공정시장가액비율.1세대1주택", year)
        fair_market_ratio = next(b["rate"] for b in table
                                 if b["upto"] is None or official_price <= b["upto"])
        src["공정시장가액비율"] = tax_params.cite(
            "재산세.주택.공정시장가액비율.1세대1주택", year)
    else:
        fair_market_ratio = tax_params.get_param("재산세.주택.공정시장가액비율.일반", year)
        src["공정시장가액비율"] = tax_params.cite("재산세.주택.공정시장가액비율.일반", year)

    if tax_brackets is None:
        key = ("재산세.주택.1세대1주택특례세율표"
               if one_home and official_price <= 900_000_000
               else "재산세.주택.표준세율표")
        tax_brackets = tax_params.get_brackets(key, year)
        src["세율표"] = tax_params.cite(key, year)
    else:
        src["세율표"] = "호출자 지정"

    if urban_area_rate < 0:
        urban_area_rate = tax_params.get_param("재산세.도시지역분.세율", year)
        src["도시지역분"] = tax_params.cite("재산세.도시지역분.세율", year)
    if local_education_tax_rate < 0:
        local_education_tax_rate = tax_params.get_param("재산세.지방교육세율", year)
        src["지방교육세"] = tax_params.cite("재산세.지방교육세율", year)

    if taxable_base_cap <= 0 and prev_year_official_price > 0:
        taxable_base_cap = tax_params.property_tax_base_cap(
            prev_year_official_price, official_price, year, fair_market_ratio)
        src["과세표준상한액"] = tax_params.cite("재산세.주택.과세표준상한율", year)

    taxable_base = int(official_price * fair_market_ratio)
    cap_applied = False
    if taxable_base_cap > 0 and taxable_base > taxable_base_cap:
        taxable_base = taxable_base_cap
        cap_applied = True

    rate, deduction = _apply_brackets(taxable_base, tax_brackets)
    main_tax = max(int(taxable_base * rate) - deduction, 0)
    urban_area_tax = int(taxable_base * urban_area_rate)
    local_education_tax = int(main_tax * local_education_tax_rate)

    return {
        "시가표준액(공시가격)": official_price,
        "공정시장가액비율": fair_market_ratio,
        "과세표준": taxable_base,
        "과표상한 적용여부": cap_applied,
        "적용세율": rate,
        "누진공제": deduction,
        "재산세 본세": main_tax,
        "도시지역분": urban_area_tax,
        "지방교육세": local_education_tax,
        "총납부세액": main_tax + urban_area_tax + local_education_tax,
        "과세연도": year,
        "값 출처": src,
        "주의": ("주택인데 prev_year_official_price를 안 넘겨 과세표준상한제(지방세법 §110③)가 "
               "적용되지 않았습니다 — 공시가가 오른 해에는 세액이 과대계산됩니다"
               if taxable_base_cap <= 0 else ""),
    }

@mcp.tool(title='Comprehensive holding tax (종부세)', annotations=ToolAnnotations(title='Comprehensive holding tax (종부세)', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def calc_jongbu_tax(
    total_official_price: int,
    year: int,
    prev_year_official_price: int = 0,
    one_home: bool = False,
    home_count: int = 1,
    age: int = 0,
    holding_years: int = 0,
    basic_deduction: int = 0,
    fair_market_ratio: float = 0.0,
    tax_brackets: list[dict] | None = None,
    property_tax_credit: int = -1,
    age_credit_rate: float = -1.0,
    holding_credit_rate: float = -1.0,
    credit_cap: float = 0.0,
    previous_year_total_tax: int = 0,
    burden_cap_ratio: float = 0.0,
    current_year_property_tax: int = 0,
    rural_special_tax_rate: float = -1.0,
) -> dict:
    """Korea comprehensive real estate holding tax (종합부동산세) on housing: deductions, progressive rates, property-tax credit, age/holding credits, burden cap.

    종합부동산세(주택분)를 계산한다. 세율·공제·비율은 year로 상수표에서 읽는다.

    ⚠️ 2026-08-30 변경 — year 필수. prev_year_official_price를 주면 재산세액공제
    (영 §4의3)·당해 재산세액·직전연도 총세액상당액(영 §5②)까지 전부 코드가 계산한다.
    종전에는 이 셋을 호출자가 수기로 넘겨야 했고, 실제로 §4의3 분자에서 재산세
    공정시장가액비율을 빠뜨리고 §5②1호의 과세표준상한 배제를 놓쳐 세액이 틀렸다.
    조문이 코퍼스에 있어도 사람이 산식을 기억으로 재현하면 틀린다 — 그래서 코드로 내렸다.

    산식 근거 (종합부동산세법, 2026-08-16 원문 확인 — MST 280417):
      §8①  과세표준 = (인별 공시가격 합산 − 공제금액) × 공정시장가액비율(시행령, 60~100%)
            공제금액은 호출자가 판정해 넘긴다: 1세대1주택자 12억 / 일반 9억 / 중과세율 법인 0
            ⚠️ 1세대1주택자 여부는 §8④ 간주 4유형(부속토지만·일시적2주택·상속주택·지방저가)
            포함 — 세대 판정 트리의 출력을 쓰고, 간주 유형은 9/16~9/30 신청 요건이 있다
      §9①  누진세율 — 2주택 이하 / 3주택 이상 표가 다르므로(12억 초과분부터 분기)
            주택수 판정 후 맞는 표를 tax_brackets로 전달. 법인은 §9② 비례세율(단일 구간으로 전달)
      §9③  재산세액 공제 — 동일 과세표준분 이중과세 조정. 안분 산식은 영 §4의3①이며,
            prev_year_official_price를 주면 코드가 계산한다(수기 전달도 되나 비권장).
            ⚠️ 분자는 (종부세 과세표준 × **재산세** 공정시장가액비율) × 재산세 표준세율이다 —
            공정비율을 빠뜨리고 종부세 과세표준에 재산세율을 바로 곱하면 공제가 2배 넘게 과대계산된다
      §9⑤~⑨ 1세대1주택자 세액공제 = 산출세액 × min(연령공제율 + 보유공제율, 80%)
            연령(§9⑥): 60세 20%·65세 30%·70세 40% / 보유(§9⑧): 5년 20%·10년 40%·15년 50%
            ⚠️ §9⑦⑨ 특례분(부속토지·대체취득·상속·지방저가) 안분 제외는 미지원 —
            해당 케이스는 공제가 과대계산되므로 결과에 플래그를 띄운다
      §10  세부담상한 — 해당연도 총세액상당액(재산세+종부세)이 직전연도 총세액상당액의
            150%를 초과하면 초과분은 없는 것으로 본다. 따라서 종부세 상한 =
            직전연도 총세액상당액 × 비율 − 해당연도 재산세액.
            prev_year_official_price를 주면 아래 둘을 코드가 산출한다(권장):
              · 해당연도 재산세액 — 영 §5① 1호. §110③ 과세표준상한을 **적용한 후**의 세액
              · 직전연도 총세액상당액 — 영 §5②. 직전연도에 소유하지 않았어도 소유한 것으로
                보아 직전연도 법령으로 재계산한 의제값이며(신규취득 첫해에도 상한이 작동하는
                이유), 재산세액상당액은 §110③·§111③·§112① 2호를 **배제하고** 산출한다.
                ⚠️ 종부세액상당액은 §5②2호 괄호에 따라 **직전연도 과세기준일 현재 연령·
                보유기간으로 §9⑤ 세액공제를 적용한 뒤**의 금액이다(2026-09-24 수정 —
                종전에는 이 공제를 빼먹어 직전 총세액이 과대했고, 상한이 느슨해져 당해
                종부세가 최대 34.7% 과대 산출됐다). 근거는 시행규칙 별지 제35호서식 부표
                ⑫ = 산출세액 − ⑩ 공제할 재산세액 − ⑪ 1세대1주택자 세액공제액.
                다만 같은 서식 작성방법 8 가목의 공시가격 안분비율(§8④ 간주 1주택)은 미지원.
            ⚠️ 당해연도는 과표상한 적용 후, 직전연도는 과표상한 배제 — 방향이 반대다.
            직접 넘기려면 previous_year_total_tax·burden_cap_ratio·current_year_property_tax를
            함께 주되, 위 배제 규정을 지켰는지 확인할 것(결과에 경고가 붙는다).
    농어촌특별세는 종부세 납부세액의 비율(농특세법 확인, 통상 20%)로 계산 — 미확인 시 0.

    Returns:
        계산 단계별 dict (검증 가능하도록)
    """
    if total_official_price <= 0:
        raise ValueError("total_official_price는 0보다 커야 합니다")

    # ── 1·2층 배선: 미지정 인자는 상수표(연도별)에서 읽는다 ──────────────────
    src = {}
    if not basic_deduction:
        deds = tax_params.get_param("종부세.주택.기본공제", year)
        basic_deduction = deds["1세대1주택자" if one_home else "일반"]
        src["기본공제"] = tax_params.cite("종부세.주택.기본공제", year)
    if not fair_market_ratio:
        fair_market_ratio = tax_params.get_param("종부세.주택.공정시장가액비율", year)
        src["공정시장가액비율"] = tax_params.cite("종부세.주택.공정시장가액비율", year)
    if tax_brackets is None:
        bk = ("종부세.주택.세율표.3주택이상" if home_count >= 3
              else "종부세.주택.세율표.2주택이하")
        tax_brackets = tax_params.get_brackets(bk, year)
        src["세율표"] = tax_params.cite(bk, year)
    if not credit_cap:
        credit_cap = tax_params.get_param("종부세.세액공제.합계한도", year)
    if rural_special_tax_rate < 0:
        rural_special_tax_rate = tax_params.get_param("농특세.종부세분.세율", year)
        src["농특세율"] = tax_params.cite("농특세.종부세분.세율", year)
    if not burden_cap_ratio:
        burden_cap_ratio = tax_params.get_param("종부세.세부담상한율", year)

    # 1세대1주택자만 연령·보유 공제(§9⑥⑧). 연령/보유기간을 주면 표에서 요율을 뽑는다.
    if age_credit_rate < 0:
        age_credit_rate = 0.0
        if one_home and age:
            for band in tax_params.get_param("종부세.세액공제.연령", year):
                if age >= band["from_age"]:
                    age_credit_rate = band["rate"]
    if holding_credit_rate < 0:
        holding_credit_rate = 0.0
        if one_home and holding_years:
            for band in tax_params.get_param("종부세.세액공제.보유", year):
                if holding_years >= band["from_years"]:
                    holding_credit_rate = band["rate"]

    _base = max(int((total_official_price - basic_deduction) * fair_market_ratio), 0)
    if prev_year_official_price > 0:
        # 당해 재산세: §110③ 과세표준상한 적용 후 (영 §5①1호가 그렇게 정의한다)
        pt_ratio = tax_params.get_param("재산세.주택.공정시장가액비율.일반", year)
        cap = tax_params.property_tax_base_cap(
            prev_year_official_price, total_official_price, year, pt_ratio)
        pt_base = min(int(total_official_price * pt_ratio), cap)
        if not current_year_property_tax:
            current_year_property_tax = tax_params.apply_brackets(
                pt_base, tax_params.get_brackets("재산세.주택.표준세율표", year))
            src["당해 재산세액"] = "지방세법 §111①3호 + §110③ 과표상한 적용"
        if property_tax_credit < 0:
            property_tax_credit = tax_params.jongbu_property_tax_credit(
                _base, current_year_property_tax, pt_base, year)
            src["재산세액공제"] = "종합부동산세법 시행령 §4의3①"
        if not previous_year_total_tax:
            # §5②2호 괄호 — 1세대1주택자는 직전 연도 과세기준일 현재 연령·보유기간으로
            # §9⑤ 세액공제를 적용한 뒤의 금액이 종합부동산세액상당액이다.
            _prev = tax_params.jongbu_prev_year_total_tax(
                prev_year_official_price, basic_deduction, year,
                "종부세.주택.세율표.3주택이상" if home_count >= 3
                else "종부세.주택.세율표.2주택이하",
                one_home=one_home, age=age, holding_years=holding_years,
                # 공제금액도 "직전 연도의 법" 값이어야 한다. 호출자가 직접 지정한
                # 경우(src에 기본공제 출처가 없다)에는 그 값을 그대로 존중한다.
                basic_deduction_prev=(
                    tax_params.get_param("종부세.주택.기본공제", year - 1)[
                        "1세대1주택자" if one_home else "일반"]
                    if "기본공제" in src else None))
            previous_year_total_tax = _prev["총세액상당액"]
            src["직전연도 총세액상당액"] = (
                "종합부동산세법 시행령 §5② (§110③ 배제, 직전연도 세액공제율 %.0f%% 적용)"
                % (_prev["직전연도 세액공제율"] * 100))
    if property_tax_credit < 0:
        property_tax_credit = 0

    taxable_base = max(int((total_official_price - basic_deduction) * fair_market_ratio), 0)
    if taxable_base == 0:
        return {
            "합산 공시가격": total_official_price,
            "공제금액": basic_deduction,
            "과세표준": 0,
            "납부세액": 0,
            "비고": "과세표준 0 — 공제금액 이하라 종부세 없음",
        }

    rate, deduction = _apply_brackets(taxable_base, tax_brackets)
    gross_tax = max(int(taxable_base * rate) - deduction, 0)

    after_property_credit = max(gross_tax - property_tax_credit, 0)

    credit_rate = min(age_credit_rate + holding_credit_rate, credit_cap)
    owner_credit = int(after_property_credit * credit_rate)
    tax_after_credit = after_property_credit - owner_credit

    cap_applied = False
    cap_note = None
    if previous_year_total_tax > 0 and burden_cap_ratio > 0:
        # 법 §10: 당해 (재산세+종부세) ≤ 직전연도 상당액×비율 → 종부세 상한 = 우변 − 당해 재산세
        cap_amount = max(
            int(previous_year_total_tax * burden_cap_ratio) - current_year_property_tax, 0
        )
        if current_year_property_tax == 0:
            cap_note = (
                "⚠️ current_year_property_tax 미전달 — 당해연도 재산세를 차감하지 않은 "
                "구식 근사라 상한이 과대해 종부세가 과대계산될 수 있음"
            )
        if tax_after_credit > cap_amount:
            tax_after_credit = cap_amount
            cap_applied = True

    rural_special_tax = int(tax_after_credit * rural_special_tax_rate)

    notes = []
    if property_tax_credit == 0:
        notes.append("재산세액 공제 미반영(0) — prev_year_official_price를 넘기면 "
                     "영 §4의3① 산식으로 자동 계산됩니다. 지금은 세액이 과대계산됨")
    if not previous_year_total_tax:
        notes.append("직전연도 총세액상당액 미산출 — 세부담상한(법 §10)이 적용되지 않았습니다")
    if credit_rate > 0:
        notes.append("§9⑦⑨ 특례분(부속토지·대체취득·상속·지방저가) 안분 제외 미지원 — 해당 시 공제 과대계산")
    if cap_applied and "직전연도 총세액상당액" not in src:
        # 호출자가 직접 넘긴 전년도 값이면 영 §5② 규약(§110③·§111③·§112①2호 배제)을
        # 지켰는지 알 수 없다. 코드가 산출한 경우에는 근사가 아니므로 경고하지 않는다.
        notes.append("세부담상한 — 직전연도 총세액상당액을 호출자가 넘긴 값으로 적용했습니다. "
                     "영 §5②의 배제 규정(§110③ 과표상한·§111③ 조례·§112①2호 도시지역분)을 "
                     "지켰는지 확인하십시오")
    if cap_note:
        notes.append(cap_note)

    return {
        "합산 공시가격": total_official_price,
        "공제금액": basic_deduction,
        "공정시장가액비율": fair_market_ratio,
        "과세표준": taxable_base,
        "적용세율": rate,
        "누진공제": deduction,
        "산출세액": gross_tax,
        "재산세액 공제": property_tax_credit,
        "1세대1주택자 세액공제율(연령+보유, 한도적용)": credit_rate,
        "1세대1주택자 세액공제액": owner_credit,
        "세부담상한 적용여부": cap_applied,
        "종합부동산세": tax_after_credit,
        "농어촌특별세": rural_special_tax,
        "총납부세액": tax_after_credit + rural_special_tax,
        "당해 재산세 본세": current_year_property_tax,
        "직전연도 총세액상당액": previous_year_total_tax,
        "과세연도": year,
        "값 출처": src,
        "주의": " / ".join(notes),
    }

import tax_judgment as _tj

@mcp.tool(title='Acquisition tax home count and rate', annotations=ToolAnnotations(title='Acquisition tax home count and rate', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_acquisition_homes_and_rate(
    homes: list[dict],
    in_adjusted_area: bool,
    is_corporation: bool = False,
    exclusive_area_m2: float | None = None,
    acquire_date: str | None = None,
    prev_disposal_date: str | None = None,
    prev_disposal_kind: str = "매각",
    disposal_to_same_household: bool = False,
    new_home_for_rental: bool = False,
    is_gift: bool = False,
    gift_std_value: int = 0,
    gift_from_one_home_household_to_family: bool = False,
) -> dict:
    """Count homes for acquisition tax and decide the rate (1/8/12%), temporary two-home relief, corporate rules.

    취득세 주택수 산정 + 일시적 2주택 + 세율·부가세 실효율 판정
    (지방세법 §13의2·§151, 영 §28의2~6, 농특세법 §5).

    homes: 취득 주택 포함 세대 보유 목록. 각 원소 {"종류": 주택|조합원입주권|주택분양권|
    오피스텔|부속토지, "시가표준액": 원, "수도권": bool, "정비구역": bool, "상속개시_5년내": bool,
    "혼전분양권_배우자혼전주택": bool, "전용면적": ㎡, "취득당시가액": 원,
    "신축최초유상승계일": "YYYY-MM-DD", "라벨": str}.

    acquire_date를 반드시 넣을 것 — 비수도권 저가주택 기준이 2025-01-02를 경계로 1억↔2억으로
    갈리고(영 35477호 부칙 §2) 일시적 2주택 3년 기산의 시작점이기도 하다.

    자동 적용: 저가주택(수도권 1억/비수도권 1억→2억)·오피스텔 1억·1억 이하 부속토지(⑥5호)·
    1.10대책 소형 오피스텔(⑥8·9호, 전용 60㎡ + 수도권 6억/지방 3억)·상속 5년·혼인 완충 제외.

    일시적 2주택(영 §28의5)은 양도세 §155①과 별개다 — 1년 경과 요건이 없고 3년이며, '처분'은
    타인에게 새로운 취득이 발생하거나 멸실되는 것을 말한다. 동일 세대원 이전은 처분이 아니고
    (disposal_to_same_household=True), 상속으로 인한 이전은 처분이다. 취득 사유는 예시일 뿐이라
    임대목적 취득(new_home_for_rental)도 가능하고 신규주택 전입은 요건이 아니다.

    is_gift=True면 유상거래 매트릭스가 아니라 무상취득 트랙으로 간다 — 조정대상지역 +
    gift_std_value 3억 이상이면 12%, 1세대1주택자→배우자·직계존비속이면 제외.
    분양권 취득 주택은 잔금일이 아니라 권리 취득일 기준으로 목록을 구성할 것(영 §28의4① 후단).
    """
    return _tj.judge_acquisition_homes_and_rate(
        homes, in_adjusted_area, is_corporation, exclusive_area_m2, acquire_date,
        prev_disposal_date, prev_disposal_kind, disposal_to_same_household,
        new_home_for_rental, is_gift, gift_std_value,
        gift_from_one_home_household_to_family,
    )

@mcp.tool(title='Capital gains reliefs', annotations=ToolAnnotations(title='Capital gains reliefs', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_transfer_reliefs(
    is_one_household_one_home: bool,
    holding_years: float,
    residing_years: float,
    sale_price: int,
    adjusted_at_sale: bool = False,
    heavy_home_count: int = 1,
    sale_date: str = "",
    meets_exemption_requirements: bool = True,
    contract_date: str = "",
    deposit_received: bool = False,
    contract_months_limit: int = 4,
) -> dict:
    """Decide capital gains exemptions, heavy-rate exclusions, long-term deduction table and high-value apportionment, producing calc_transfer_tax inputs.

    양도세 비과세·중과·장특공·고가주택 안분 판정 → calc_transfer_tax 인자 생성.

    소득세법 §89·§95(표1/표2·중과 시 장특공 배제)·§104⑦·영 §159의4·§160·한시배제(영
    §167의3①12호의2)를 한 번에 판정한다. 세대·주택수(트리①②)와 비과세 요건 충족 여부는
    입력으로 받는다 — 이 함수는 그 출력을 세율·공제로 변환하는 판정 레이어.

    sale_date를 반드시 넣을 것 — 중과 가산세율이 양도일로 갈린다. 2021-06-01 이후 양도분은
    2주택 +20%p / 3주택 +30%p이고 **그 전은 +10%p / +20%p**다(법 17477호 부칙 §3).
    중과 한시배제(영 §167의3①12호의2)는 **창(窓)이다** — 2022-05-10 이후 ~ 2026-05-09까지
    양도분이고, **보유기간 2년 이상**이 대전제다. 그 기간을 넘겨 양도하더라도 2026-05-09까지
    매매계약을 체결하고 계약금을 받았다면 계약일부터 4개월(일부 지역 6개월) 내 양도까지
    배제된다 — contract_date·deposit_received·contract_months_limit로 판정한다(나·다목).
    반환의 surcharge_rate·long_term_deduction_rate를 calc_transfer_tax에 그대로 넘기고,
    과세대상_양도차익_비율(<1이면 고가주택)은 양도차익에 곱해 안분한다.
    """
    return _tj.judge_transfer_reliefs(
        is_one_household_one_home, holding_years, residing_years, sale_price,
        adjusted_at_sale, heavy_home_count, sale_date, meets_exemption_requirements,
        contract_date, deposit_received, contract_months_limit,
    )

@mcp.tool(title='Same household test', annotations=ToolAnnotations(title='Same household test', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_same_household(
    relationship: str,
    lives_together: bool = True,
    shares_livelihood: bool = True,
    age: int | None = None,
    is_married_or_was: bool = False,
    income_over_40pct_median: bool = False,
    is_minor: bool = False,
    tax_kind: str = "양도세",
    legally_divorced_but_living_together: bool = False,
    is_de_facto_marriage: bool = False,
    merged_for_parent_care: bool = False,
    descendant_age: int | None = None,
) -> dict:
    """Decide whether two people form one household (1세대) for income, acquisition or holding tax purposes.

    트리① — 본인과 특정인의 1세대 동일성 판정 (소법 §88 6호·영 §152의3 / 지방령 §28의3 / 종부령 §1의2).

    relationship: 배우자|직계존속|직계비속|직계존비속의 배우자|형제자매|기타(이모·조카 등 —
    가족 범위 밖은 세목 불문 별도 세대).

    ⚠️ 세대 정의는 세목마다 다르다 — tax_kind를 반드시 맞춰 넣을 것:
      양도세는 같은 주소 + 생계동일(실질), 취득세는 세대별 주민등록표 기준.
      사실혼 배우자는 취득세에서 명문 제외(is_de_facto_marriage).
      미혼 30세 미만 자녀는 취득세에서 주민등록을 분리해도 같은 세대이고, 별도세대가 되려면
      **직전 12개월** 소득이 중위소득 40% 이상이어야 한다(양도세는 측정기간 명문 없음).
      동거봉양 합가 별도세대 예외는 취득세가 **65세**, 양도세 §155④ 특례는 60세다
      (merged_for_parent_care·descendant_age로 취득세 판정).
    legally_divorced_but_living_together: 법률상 이혼했으나 사실상 이혼으로 보기 어려운 관계는
      배우자에 포함된다(소법 §88 6호 괄호 — 위장이혼 차단).
    """
    return _tj.judge_same_household(
        relationship, lives_together, shares_livelihood, age,
        is_married_or_was, income_over_40pct_median, is_minor, tax_kind,
        legally_divorced_but_living_together, is_de_facto_marriage,
        merged_for_parent_care, descendant_age,
    )

@mcp.tool(title='Home count for exemption', annotations=ToolAnnotations(title='Home count for exemption', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def count_transfer_homes(items: list[dict]) -> dict:
    """Count homes for the one-household-one-home capital gains exemption, applying statutory exclusions automatically.

    트리② — 1세대1주택 비과세 판정용 주택수 산정 (소법 §88·영 §155 특례 제외 자동 적용).

    items 원소: {"종류": 주택|조합원입주권|분양권|오피스텔|다가구주택|겸용주택,
    "사실상주거용": bool, "취득일": "YYYY-MM-DD"(분양권 2021 이후만 산입),
    "상속특례주택"/"공동상속_소수지분"/"농어촌주택특례"/"등록임대_거주주택특례": bool,
    "구획수": int·"일괄양도": bool(다가구), "주택연면적"·"주택외연면적": ㎡(겸용), "라벨": str}.

    다가구주택은 구획별로 각각 1주택이 원칙이고, 구획별로 양도하지 않고 하나의 매매단위로
    양도할 때만 전체가 1주택이 된다(영 §155⑮) — 일괄양도 여부가 비과세를 가르는 분기다.
    겸용주택은 주택 연면적이 주택외보다 크면 전부 주택, 적거나 같으면 주택 부분만 주택이며
    (영 §154③) 판정 기준은 공부가 아니라 **양도 당시 사용용도**다. 결과의 겸용주택_전부주택 참조.
    중과판정 주택수(영 §167의3~11)와는 별개 — 세목·용도별 주택수 분리 원칙.
    """
    return _tj.count_transfer_homes(items)

@mcp.tool(title='Temporary two-home exemption', annotations=ToolAnnotations(title='Temporary two-home exemption', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_temporary_two_homes(
    prev_acquired: str,
    new_acquired: str,
    prev_sale_date: str | None = None,
    prev_meets_exemption: bool = True,
    one_year_rule_waived: bool = False,
    prev_in_adjusted_area: bool = False,
    new_in_adjusted_area: bool = False,
    moved_in_within_1y: bool | None = None,
    moved_in_date: str | None = None,
    new_home_tenant_lease_end: str | None = None,
    new_contract_date: str | None = None,
) -> dict:
    """Temporary two-home exemption test: one-year gap, disposal deadline, move-in requirement (Income Tax Decree art. 155(1)).

    §155① 일시적 2주택 판정 — 1년 경과(§154①1~3호 해당 시 면제)·양도기한·전입요건.

    양도기한은 양도일로 갈린다: 2023.1.12 이후 양도=3년 단일, 2022.5.10~2023.1.11=조정→조정 2년,
    그 전=신규취득일 구간별 3년/2년/1년. 1년 구간(2019.12.17 이후 조정→조정 취득)은 신규주택
    취득일부터 1년 내 세대전원 이사·전입신고가 추가 요건이며, 전소유자 임대차가 남아 있으면
    종료일까지(취득일+2년 한도) 연장된다. 과거 양도분 경정청구·세무조사 상담에 필수.

    조정지역 여부는 judge_adjusted_area_at_date로 각 취득일·양도일 기준 확인 후 넣을 것.
    날짜는 YYYY-MM-DD. prev_sale_date 생략 시 현행법(3년) 데드라인만 산출. 취득세 일시적
    2주택(영 §28의5, 1년 요건 없음)과 별개라는 세목 분기 플래그 포함.
    """
    return _tj.judge_temporary_two_homes(
        prev_acquired, new_acquired, prev_sale_date, prev_meets_exemption, one_year_rule_waived,
        prev_in_adjusted_area, new_in_adjusted_area, moved_in_within_1y, moved_in_date,
        new_home_tenant_lease_end, new_contract_date,
    )

@mcp.tool(title='Special one-home cases (art. 155)', annotations=ToolAnnotations(title='Special one-home cases (art. 155)', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_155_special(
    kind: str,
    event_date: str = "",
    sale_date: str = "",
    homes_mine: int = 1,
    homes_spouse_or_parent: int = 1,
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
    designated_by_agreement: bool = False,
) -> dict:
    """Special one-home cases: marriage, caring for parents, inherited home, rural home (Income Tax Decree art. 155).

    영 §155 특례 판정 — kind: 혼인(⑤)|동거봉양(④)|상속주택(② 선순위·별도세대)|
    거주주택(⑳ 장기임대+거주 2년).

    특례기간은 **양도일 기준**으로 갈린다 — 혼인은 2024-11-12 이후 양도분 10년(그 전 5년,
    영 34990호 부칙 §2), 동거봉양은 2018-02-13 이후 양도분 10년(그 전 5년). 과거 양도분
    상담·경정청구에서는 sale_date를 반드시 넣을 것.
    1+1 판정 전에 excluded_homes_*(공동상속 §155③·농어촌 조특법 §99의4 등 특례로 주택수에서
    빠지는 주택 수)를 차감한다. 혼인 주택수는 양도일이 아니라 **혼인합가 당시** 기준이고,
    임대주택도 주택수에 든다. 2009-02-04 전 합가는 여성 직계존속 55세(parent_is_female).
    상속주택은 동거봉양 합가로 동일세대가 된 경우 merged_for_parent_care·held_before_merge로
    '합치기 이전부터 보유하던 주택'만 인정된다. §155 특례의 3중첩은 불허.
    상속·거주주택은 요건 판정 후 count_transfer_homes 입력 플래그로 연결."""
    return _tj.judge_155_special(
        kind, event_date, sale_date, homes_mine, homes_spouse_or_parent,
        parent_max_age_at_merge, separate_household_at_inheritance,
        general_home_acquired_before_inheritance, is_first_priority_inherited,
        gifted_within_2y_before_inheritance, rental_registered,
        residence_years_in_home, first_time_use,
        excluded_homes_mine, excluded_homes_spouse_or_parent, parent_is_female,
        merged_for_parent_care, held_before_merge, designated_by_agreement,
    )

@mcp.tool(title='Home count for heavy rates', annotations=ToolAnnotations(title='Home count for heavy rates', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def count_heavy_homes(items: list[dict], heavy_tier: int = 3) -> dict:
    """Count homes for heavy capital gains rates, excluding low-value provincial homes and other statutory exclusions.

    양도세 중과판정 주택수 산정 (영 §167의3~11 불산입 자동 적용 — 지방 3억 이하·§167의3①12호).

    items 원소: {"종류": 주택|조합원입주권|분양권, "기준시가": 원(입주권=종전주택가·분양권=공급가),
    "지방소재": bool, "인구감소등_12호": bool, "정비구역": bool,
    "전용면적"·"취득가액"·"취득일"·"준공일"·"아파트": 소형 신축주택(영 §167의3①12호 가목,
    2024-01-10~2027-12-31 취득·준공 + 전용 60㎡ + 수도권 6억/지방 3억 + 아파트 제외) 판정용,
    "라벨": str}.

    heavy_tier로 계열을 지정한다 — **같은 주택이라도 계열에 따라 세는 수가 달라진다.**
    2(2주택 중과, 영 §167의10)면 기준시가 1억 이하(정비구역 제외) 불산입이 추가되고,
    3(3주택 이상, 영 §167의3)에는 그 완화가 없다.
    반환 주택수를 judge_transfer_reliefs의 heavy_home_count로 연결. 비과세용 주택수와 별개.
    """
    return _tj.count_heavy_homes(items, heavy_tier)

@mcp.tool(title='Holding tax one-home status', annotations=ToolAnnotations(title='Holding tax one-home status', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_jongbu_one_home_status(other_homes: list[dict], base_date: str = "") -> dict:
    """Comprehensive holding tax: is the owner deemed a one-household-one-home holder (attached land, temporary, inherited, cheap provincial home).

    종부세 1세대1주택자 간주 4유형 판정 (법 §8④·영 §4의2 — 부속토지/일시적 3년/상속
    5년·지분40%·6억(3억)/지방저가 4억). 간주 인정 시 12억 공제·세액공제 입구, 과표 합산은
    유지·9/16~30 신청제 플래그 포함. base_date는 과세기준일(YYYY-MM-DD, 보통 매년 6/1)."""
    return _tj.judge_jongbu_one_home_status(other_homes, base_date)

@mcp.tool(title='Priority inherited home', annotations=ToolAnnotations(title='Priority inherited home', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_inherited_house_priority(houses: list[dict]) -> dict:
    """When a decedent held several homes, pick the single inherited home that gets the special treatment.

    피상속인 다주택 시 선순위 상속주택 1개 확정 (영 §155② 1~4호).

    상속주택이 2개 이상이면 순위규정에 따른 1주택만 비과세 특례 대상이다 —
    ①피상속인 소유기간 최장 ②동률 시 피상속인 거주기간 최장 ③소유·거주 모두 동률 시
    상속개시 당시 거주 ④거주사실 없고 소유기간 동률이면 기준시가 최고(동률이면 상속인 선택).
    houses 원소: {"라벨", "피상속인_소유기간_년", "피상속인_거주기간_년",
    "상속개시당시_거주": bool, "기준시가": 원}. 결과를 judge_155_special(kind="상속주택")의
    is_first_priority_inherited로 전달한다. 선순위 아닌 나머지는 주택수에 그대로 산입."""
    return _tj.judge_inherited_house_priority(houses)

@mcp.tool(title='Co-inherited home owner', annotations=ToolAnnotations(title='Co-inherited home owner', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_co_inherited_owner(shares: list[dict]) -> dict:
    """Attribute a co-inherited home to one heir under Income Tax Decree art. 155(3).

    공동상속주택의 소유자 귀속 판정 (영 §155③).

    원칙은 불산입(다른 주택 양도 시 그 거주자의 주택으로 보지 않음)이나 상속지분 최대자는
    산입하며, 최대자가 2명 이상이면 ①해당 주택 거주자 → ③최연장자 순(2호는 2008 삭제).
    shares 원소: {"상속인", "지분율": 0~1, "해당주택_거주": bool, "나이": int}.
    ⚠️ 세목별로 결론이 갈린다 — 취득세는 최대지분→거주자→연장자(지방세법 영 §28의4⑤),
    종부세는 소액지분(40%↓ 또는 지분공시가 6억·지방 3억↓)이면 기간 무관 제외(영 §4의2②)."""
    return _tj.judge_co_inherited_owner(shares)

@mcp.tool(title='Attached land limit', annotations=ToolAnnotations(title='Attached land limit', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def calc_attached_land_limit(building_footprint_m2: float, land_area_m2: float,
                             is_urban_area: bool = True, is_capital_region: bool = True,
                             urban_zone: str = "주거상업공업") -> dict:
    """Maximum land area attached to a home covered by the capital gains exemption, by zone (3x/5x/10x).

    주택 부수토지의 1세대1주택 비과세 한도 면적 (소법 §89①3호·영 §154⑦).

    비과세 범위 = 건물 정착면적(바닥면적) × 지역별 배율 — 도시지역 수도권 주거·상업·공업 3배 /
    수도권 녹지 5배 / 수도권 밖 5배, 비도시지역 10배. 초과분은 비과세에서 빠져 별도 과세되며
    비사업용 토지 해당 여부(영 §168의6~14)를 추가 판정해야 한다. urban_zone은
    주거상업공업|녹지(도시지역·수도권일 때만 구분). 수용 시엔 사업인정 고시일 전날의
    용도지역을 적용한다(2025-11-28 개정)."""
    return _tj.calc_attached_land_limit(building_footprint_m2, land_area_m2,
                                        is_urban_area, is_capital_region, urban_zone)

@mcp.tool(title='Reconstruction membership transfer', annotations=ToolAnnotations(title='Reconstruction membership transfer', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
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
    """Can a redevelopment/reconstruction association membership be transferred in a speculation zone (Urban Renewal Act art. 39).

    트리③ — 재건축·재개발 조합원 지위양도 제한 판정 (도시정비법 §39②③·영 §37①③).

    투기과열지구에서 재건축=조합설립인가 후/재개발=관리처분인가 후 양수자는 조합원 불가
    (증여 포함·상속·이혼 제외). 탈락 시 매수인은 §39③→§73 준용 손실보상 절차 대상 —
    세액 계산보다 앞선 매도가능성 선필터. in_speculation_overheated_zone은
    search_law(admrul, "투기과열지구 지정")로 거래 시점 재확인.
    transfer_notice_done=True(이전고시 후)면 제한 실효 — 단 1+1 소형 60㎡↓는
    is_one_plus_one_small로 §76①7호라목 3년 전매금지 별도 판정.
    transferor_reason: ""|세대이전|상속주택이전|해외이주|지분형주택|공공재개발양도|
    1세대1주택_소유10년_거주5년|시행령예외(decree_reason으로 §37③ 6세목 지정)."""
    return _tj.judge_reconstruction_membership_transfer(
        project_type, in_speculation_overheated_zone, association_established,
        management_disposal_approved, transfer_notice_done, transferor_reason,
        owned_years, resided_years, decree_reason, is_partial_share_transfer, is_one_plus_one_small,
    )

@mcp.tool(title='One-home exemption requirements', annotations=ToolAnnotations(title='One-home exemption requirements', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
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
    """Full one-household-one-home capital gains exemption test: holding, residence, price cap, adjusted area.

    트리④ — 1세대1주택 비과세 요건 판정 (소법 §89①3호·영 §154·§155의3).

    트리①(세대)·트리②(주택수) 출력을 입력으로 받아 보유 2년·취득당시 조정 시 거주 2년·
    배제사유·상생임대 대체·고가주택 12억 안분 비율을 판정하고, 결과를
    judge_transfer_reliefs의 meets_exemption_requirements로 연결한다.
    acquired_in_adjusted_area는 '취득 당시' 지정이력 기준(승계 입주권·분양권은 사용승인일).
    waiver_reason: ""|건설임대5년거주|수용|해외이주2년|취학근무국외|부득이1년거주.

    §154①5호(조정 공고 전 계약)는 사실 4개로 분해해서 넣는다 — 하나라도 틀리면 결론이 뒤집힌다:
      contract_before_adjusted_announce(공고 전 계약) · deposit_paid_in_full(계약금 '전액' 지급,
      일부면 배제 불가) · no_home_at_contract(계약금 지급일 세대 무주택, 유주택이면 이후
      세대분리해도 적용) · acquisition_cause(매매|분양|증여|상속|자가건설|조합가입).
      증여·상속은 same_household_succession=True(동일세대원 승계)일 때만 배제가 유지된다.
    partial_non_residence_unavoidable: 세대원 일부가 부득이 사유로 처음부터 미거주한 경우.
    sangsaeng_nonresident_contract: 비거주자가 체결한 임대차계약이면 상생임대 특례가 무효."""
    return _tj.judge_exemption_requirements(
        is_one_household_one_home, holding_years, residing_years, acquired_in_adjusted_area,
        sale_price, waiver_reason, sangsaeng_rental_ok, pre_announce_contract_no_home,
        acquisition_cause, is_usage_converted_after_contract,
        contract_before_adjusted_announce, deposit_paid_in_full, no_home_at_contract,
        same_household_succession, partial_non_residence_unavoidable,
        sangsaeng_nonresident_contract,
    )

@mcp.tool(title='Rental income tax status', annotations=ToolAnnotations(title='Rental income tax status', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
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
    """Residential rental income tax: taxable, home count, deemed rent, separate vs global taxation.

    트리⑤ — 주택임대 종합소득세 판정 (소법 §12·§14③7호·§25①·§64의2, 17차 순회 15노드).

    비과세(1주택·12억 이하·국내) → 주택수(**부부합산**, 영 §8의2③4호 — 양도세 1세대·종부세 개인별과
    다른 제5의 기준) → 총수입금액(월세+간주임대료) → 2천만원 분기 → 분리과세 14% 계산 순으로 판정한다.
    tax_year는 필수 — §25①2호 2주택 간주임대료가 **2026-01-01 시행**(부칙 제19933호 §1제1호)이고
    정기예금이자율이 연례 개정 상수라 과세연도로 답이 갈린다.
    own_homes/spouse_homes 원소: {"라벨","기준시가","전용면적","공동소유","지분율","최대지분자",
    "연임대수입","전대","국외"}. deposits 원소: {"라벨","보증금","일수","기준시가","전용면적"}.
    총수입 2천만원 초과(종합과세)는 추계경비가 국세청 고시 영역이라 '판단불가'로 정직 반환한다."""
    return _tj.judge_rental_income_tax(
        tax_year, own_homes, spouse_homes, monthly_rent_revenue, registered_rent_revenue,
        deposits, other_comprehensive_income, business_registered, revenue_before_registration,
        deposit_interest_rate, financial_income, tax_reduction,
    )

@mcp.tool(title='Separate rental income tax', annotations=ToolAnnotations(title='Separate rental income tax', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def calc_rental_income_tax(
    registered_revenue: int = 0,
    unregistered_revenue: int = 0,
    other_comprehensive_income: int | None = None,
    tax_reduction: int = 0,
) -> dict:
    """Compute the 14% separate tax on residential rental income up to 20 million won, with registered-landlord deductions.

    분리과세 주택임대소득 세액 계산 (소법 §64의2①② · 영 §122의2⑦).

    필요경비 50%(등록임대주택 60%), 추가공제 200만원(등록 400만원)은 **분리과세 주택임대소득을 제외한
    종합소득금액이 2천만원 이하일 때만** 적용된다 — other_comprehensive_income 미입력 시 공제 없이
    계산하고 플래그를 단다. 등록·미등록 혼재는 수입금액 비율로 안분(영 §122의2⑦2·3호).
    총수입 2천만원 초과는 분리과세 대상이 아니므로 오류를 반환한다."""
    return _tj.calc_rental_income_tax(
        registered_revenue, unregistered_revenue, other_comprehensive_income, tax_reduction
    )

@mcp.tool(title='Dealer vs individual seller', annotations=ToolAnnotations(title='Dealer vs individual seller', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_business_dealer_status(
    acquisitions_in_period: int = 0,
    sales_in_period: int = 0,
    has_business_registration: bool = False,
    business_purpose_advertised: bool = False,
    is_self_built_sale: bool = False,
    is_residential_resale: bool = False,
) -> dict:
    """Is the seller a real estate dealer (business income) or an individual (capital gains).

    사업자성 스크리닝 — 부동산매매업(사업소득)인지 양도소득인지 (트리⑥, P0 Q0 축).

    ⚠️소득세법에는 계속성·반복성의 임계값이 없다. 기계 판정 가능한 유일한 수치는
    부가가치세법 시행규칙 §2②2호의 **1과세기간(6개월) 중 1회 이상 취득 + 2회 이상 판매**로,
    실무가 소득세 판정에 원용하지만 직접 근거는 부가세법이므로 **스크리닝 전용**이다(단정 금지).
    구입한 주거용 건물의 재판매는 부동산매매업에 포함된다(영 §122① 단서 괄호) — '주택은 매매업이
    아니다'는 오해 지점. 결과가 갈리면 시나리오 2개(양도소득/사업소득) 병기가 출력 규약."""
    return _tj.judge_business_dealer_status(
        acquisitions_in_period, sales_in_period, has_business_registration,
        business_purpose_advertised, is_self_built_sale, is_residential_resale,
    )

@mcp.tool(title='Dealer comparative tax', annotations=ToolAnnotations(title='Dealer comparative tax', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def calc_dealer_comparative_tax(
    comprehensive_income_tax: int,
    comprehensive_tax_base: int,
    housing_trade_profits: list[dict],
    tax_brackets: list[dict],
) -> dict:
    """Comparative taxation for real estate dealers under Income Tax Act art. 64.

    소법 §64 부동산매매업자 비교과세 — 사업자 전환으로 중과세율을 피할 수 있는지 계산.

    산출세액 = max(①종합소득 산출세액, ②주택등매매차익×§104 양도세율 + (종합소득과세표준 −
    주택등매매차익)×§55 기본세율). 대상 자산은 §104①1호(분양권)·8호·10호·§104⑦ = 중과 대상.
    housing_trade_profits: [{"라벨", "매매차익", "양도세율"}] — 세율은 호출자가 확정해 넘긴다.
    tax_brackets: [{"upto", "rate", "deduction"}] — 기본세율표(하드코딩 금지 원칙).
    두 안의 차액이 그대로 의사결정 값이므로 항상 둘 다 반환한다."""
    return _tj.calc_dealer_comparative_tax(
        comprehensive_income_tax, comprehensive_tax_base, housing_trade_profits, tax_brackets
    )

@mcp.tool(title='Reconstruction levy (재건축부담금)', annotations=ToolAnnotations(title='Reconstruction levy (재건축부담금)', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
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
    """Estimate the reconstruction excess-profit levy (재건축부담금): exemptions, base, rate bands, reductions.

    재건축부담금 추정 (재초환법 §7·8·10·12·14의2·17의2 — 22차 순회).

    초과이익 = 종료시점 주택가액 − (개시시점 주택가액 + 정상주택가격상승분 + 개발비용).
    normal_rise_rate = max(국토부 고시 정기예금이자율, 시·군·구 평균주택가격상승률) — 외부 고시·
    통계이므로 호출 시점 조회값을 넘긴다(캐시 금지). 부과율은 1인당 평균이익 8천만원 이하 면제,
    이후 5천만원 폭으로 10~50%(2023-12-26 개정 — 구 수치 3천만/2천만은 오답).
    1세대1주택 장기보유 감경 6년 10%~20년 70%, 60세 이상 1주택자는 납부유예 가능.
    ⚠️판례 0건 영역이고 가액은 감정평가로 확정되므로 **반환값은 전부 추정치**다.
    또 재건축부담금은 세금이 아니라 부담금이고 1차 납부의무자는 조합(§6)."""
    return _tj.estimate_reconstruction_levy(
        end_price_total, start_price_total, member_count, normal_rise_rate, development_cost,
        start_date, end_date, management_plan_applied_date, one_home_holding_years,
        is_one_home_at_end, age_at_end,
    )

@mcp.tool(title='Relief caps and gates', annotations=ToolAnnotations(title='Relief caps and gates', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_transfer_reduction_limit(
    reductions: list[dict],
    tax_year: int,
    prior_4year_reductions: int = 0,
    prior_4year_taking_reductions: int = 0,
    contract_price_mismatch: bool = False,
    unregistered_transfer: bool = False,
) -> dict:
    """Capital gains relief gate: disqualification, annual and five-year relief caps, choose-one rules (Restriction of Special Taxation Act art. 129/133/127).

    양도세 감면 공통 게이트 — 조특법 §129 배제 → §133 종합한도 → §127⑦ 택일 (19차 순회).

    reductions 각 원소: {"조문": "69"|"70"|"77"|"77의2"|..., "감면세액": int, "라벨": str}.
    한도는 두 바스켓으로 나뉘며 서로 잠식하지 않는다 — ①§33·43·66~69·69의2~4·70·85의10:
    과세기간 1억/5개 과세기간 2억(§70 단독은 5년 1억) ②**공익수용 §77·77의2·77의3: 과세기간 2억/
    5개 과세기간 3억**(2025-03-14 신설 §133② — 종전 1억/2억 인용은 수용 건에서 오답).
    감면율이 100%여도 이 한도로 잘리므로 '전액 비과세' 안내를 막는 것이 이 함수의 역할이다.
    다운·업 계약이나 미등기양도면 감면 전면 배제(§129)."""
    return _tj.judge_transfer_reduction_limit(
        reductions, tax_year, prior_4year_reductions, prior_4year_taking_reductions,
        contract_price_mismatch, unregistered_transfer,
    )

@mcp.tool(title='Small-home landlord reduction', annotations=ToolAnnotations(title='Small-home landlord reduction', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
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
    """Small-home landlord income tax reduction (Special Taxation Act art. 96): eligibility and rate.

    조특법 §96 소형주택 임대사업자 세액감면 — 트리⑤ calc_rental_income_tax의 tax_reduction 산출.

    감면율: 1호 임대 30%(공공지원·장기일반민간임대주택 75%) / 2호 이상 20%(장기일반등 50%).
    요건(영 §96): 소법 §168 사업자등록 + 민특법 §5 등록 + 국민주택규모 85㎡ 이하 +
    **임대개시일 기준시가 6억 이하** + 임대료 증가율 5% 이하. 일몰 2028-12-31.
    기준시가 6억·85㎡는 소법 §64의2 분리과세의 등록임대주택 요건에는 없다 — 필요경비 60%·
    공제 400만원은 되는데 §96 감면은 안 되는 구간이 존재한다.
    추징: 4년(장기일반 10년) 미만 임대 시 감면세액 + 이자상당가산액."""
    return _tj.judge_small_house_rental_reduction(
        tax_year, rental_house_count, is_long_term_general, business_registered,
        minteukbeop_registered, exclusive_area_m2, published_price_at_start,
        rent_increase_rate, income_tax_before_reduction, rental_months,
    )

@mcp.tool(title='Self-cultivated farmland exemption', annotations=ToolAnnotations(title='Self-cultivated farmland exemption', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_farmland_reduction(
    farming_years_claimed: float,
    resides_within_scope: bool,
    direct_farming: bool,
    yearly_incomes: list[dict] | None = None,
    zone_converted_date: str = "",
    transfer_date: str = "",
    estimated_tax: int = 0,
) -> dict:
    """Self-cultivated farmland capital gains exemption after 8 years (Special Taxation Act art. 69).

    조특법 §69 자경농지 양도세 100% 감면 판정 (시행령 §66 요건 포함).

    ⚠️실질 관문은 8년이 아니라 소득 요건이다 — yearly_incomes([{"연도","사업소득금액","총급여액"}])의
    합계가 **3,700만원 이상인 과세기간은 경작기간에서 제외**된다(영 §66⑭, 농업·임업·부동산임대·
    농가부업소득 제외). 겸업 농민은 달력상 8년을 채워도 탈락하므로 연도별 소득자료가 필요하다.
    재촌 요건은 농지 소재 시·군·구 / 연접 시·군·구 / 직선 30km 이내(영 §66①).
    주거·상업·공업지역 편입 후 3년이 지나면 감면 배제(영 §66④).
    감면율 100%여도 §133① 한도로 잘리므로 judge_transfer_reduction_limit에 넘길 것."""
    return _tj.judge_farmland_reduction(
        farming_years_claimed, resides_within_scope, direct_farming, yearly_incomes,
        zone_converted_date, transfer_date, estimated_tax,
    )

@mcp.tool(title='Farmland substitution exemption', annotations=ToolAnnotations(title='Farmland substitution exemption', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
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
) -> dict:
    """Farmland substitution exemption (Special Taxation Act art. 70): distance, period, area and value ratios.

    조특법 §70 농지대토 양도세 100% 감면 판정 (시행령 §67 — 23차 순회).

    요건: ①종전 농지 양도일 현재 **4년 이상** 농지소재지(시군구·연접·직선 30km) 거주·경작
    ②양도일부터 1년(수용은 2년) 내 새 농지 취득 ③취득일부터 1년 내 새 농지소재지 거주·경작 개시
    ④종전+신규 **합산 경작 8년 이상** ⑤신규 농지 면적이 종전의 2/3 이상 **또는** 가액이 1/2 이상.
    자경농지(§69)와 달리 양도 시점에 8년을 채울 필요가 없고 사후 합산으로 채운다 — 대신 미달 시
    §70④⑤로 2개월 내 추징 + 이자상당액. 재촌 요건 기간도 §69(8년)와 달리 4년이라 혼동 주의.
    감면율 100%여도 §133①2호가목의 **5개 과세기간 1억원** 한도가 별도로 걸린다 —
    judge_transfer_reduction_limit에 넘겨 최종 감면세액을 확정할 것."""
    return _tj.judge_farmland_daeto(
        prior_reside_years, transfer_date, new_acquire_date, farming_start_date,
        total_farming_years, new_area_ratio, new_price_ratio, is_expropriation, estimated_tax,
    )

@mcp.tool(title='Homes excluded from the count', annotations=ToolAnnotations(title='Homes excluded from the count', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
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
) -> dict:
    """Homes excluded from the home count: rural/hometown house, depopulation-area house, unsold completed house.

    주택수 제외 특례 3형제 — 조특법 §99의4(농어촌·고향주택) / §71의2(인구감소지역) / §98의9(준공후미분양).

    kind: "농어촌주택"|"고향주택"|"인구감소지역주택"|"인구감소관심지역주택"|"준공후미분양주택".
    준공후미분양주택(§98의9·영 §98의8): 취득 2024-01-10~**2026-12-31 일몰**, 수도권 밖 소재,
    전용 85㎡ 이하·취득가액 7억 이하, 양도자가 사업주체·분양사업자·시공자, 양수자가 최초 계약자,
    사용검사일까지 분양계약이 없어 선착순 공급된 것 — exclusive_area_m2·acquisition_price·
    first_contract·seller_is_supplier로 판정한다.
    농어촌주택: 취득 2003-08-01~2028-12-31, 기준시가 3억(한옥 4억) 이하, 3년 보유,
    일반주택과 같거나 연접한 읍·면·동이면 배제(§99의4③).
    인구감소지역주택: 취득 2024-01-04~**2026-12-31 일몰**, 기준시가 수도권 밖 9억 /
    수도권 인구감소지역·인구감소관심지역 4억, 종전 주택과 같은 시·군·구면 배제(영 §68의2①).
    종부세 1세대1주택자 간주는 9/16~9/30 별도 신청 필요(§71의2②③).
    두 특례 모두 특례 주택을 **나중에** 취득해야 적용된다."""
    return _tj.judge_second_home_exclusion(
        kind, acquired_date, published_price, is_hanok, in_capital_area,
        same_or_adjacent_area, same_sigungu, holding_years, acquired_after_general_home,
        exclusive_area_m2, acquisition_price, first_contract, seller_is_supplier,
    )

@mcp.tool(title='First-home acquisition relief', annotations=ToolAnnotations(title='First-home acquisition relief', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
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
) -> dict:
    """First-time home buyer acquisition tax relief (Local Tax Special Act art. 36-3).

    지특법 §36의3 생애최초 주택 구입 취득세 감면 (2028-12-31까지).

    본인·배우자 무주택 + 취득당시가액 12억 이하 유상거래(부담부증여 제외) + 본인 거주 목적,
    미성년자 제외. 감면 한도는 **300만원**(전용 60㎡ 이하 공동주택—아파트 제외·도시형생활주택·
    구분 다가구 60㎡ 호, 인구감소지역 주택) / **200만원**(그 외) 2분류 — 2024-12-31·2025-12-31
    개정으로 생긴 구분이라 '200만원 단일'로 알려진 통설과 다르다.
    추징: 3개월 내 상시거주 미개시, 또는 3년 내 매각·증여·**임대**(전세 끼는 경로 차단)."""
    return _tj.judge_first_home_acquisition_relief(
        acquisition_price, no_home_history, is_minor, computed_tax, exclusive_area_m2,
        house_type, in_depopulation_area, acquired_date, co_owners,
    )

@mcp.tool(title='Family loan vs gift', annotations=ToolAnnotations(title='Family loan vs gift', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_family_loan(loan_amount: int, agreed_interest_rate: float = 0.0) -> dict:
    """Family loan vs gift screening: 4.6% benchmark rate and the 10 million won threshold (Inheritance and Gift Tax Act art. 41-4).

    가족 간 차용·무상대출 증여 스크리닝 (상증법 §41의4 — 적정이자율 4.6%·기준 1천만).

    연간 증여이익 = 대출금×4.6% − 실제 이자. 1천만 미만이면 과세 제외(무상 기준 약 2.17억).
    차용증·이자 실지급은 취득자금 증여추정(§45) 방어와 세트라는 플래그를 함께 반환.
    """
    return _tj.judge_family_loan(loan_amount, agreed_interest_rate)

@mcp.tool(title='Funding plan requirement', annotations=ToolAnnotations(title='Funding plan requirement', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_fund_plan_requirement(
    actual_price: int,
    in_speculation_zone: bool = False,
    in_adjusted_area: bool = False,
    in_permit_zone: bool = False,
    is_corporation: bool = False,
) -> dict:
    """Whether a home purchase must file a funding plan and supporting documents.

    주택 매수 자금조달계획서 제출·증빙 판정 (거래신고령 별표 1 — 법인 전부 / 6억↑ /
    규제지역 소재, 투기과열지구·허가구역은 증빙 첨부). 현행 서식(별지 1호의3) 항목 안내 포함."""
    return _tj.judge_fund_plan_requirement(
        actual_price, in_speculation_zone, in_adjusted_area, in_permit_zone, is_corporation
    )

@mcp.tool(title='Consultation report', annotations=ToolAnnotations(title='Consultation report', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def format_consultation_report(
    conclusion: str,
    evidences: list[dict],
    owner_qa: list[dict] | None = None,
    scenarios: list[dict] | None = None,
    dividing_issue: str = "",
    issue_grade: str = "",
) -> dict:
    """Format a consultation result as a report: conclusion, grounds mapped to sources, tailored Q&A.

    소비자용 상담 리포트 최종 양식 — 1.최종결론 / 2.근거(설명↔출처 1:1) / 3.맞춤 Q&A.

    상담의 마지막 단계. 소비자는 결론만 원하므로 결론을 맨 위에, 근거는 설명과 출처를
    1:1로 매칭(출처 없는 설명은 리포트 전체 거부), 소유자가 물었던 추가 질문들은 §3에
    답변+근거로 정리한다. 쟁점으로 세액이 갈리면 scenarios를 함께 넘겨 결론 아래
    병기(단정 금지 규약 유지 — format_consultation_output 재사용). 쟁점·질문 문구에서
    해석례 추천검색(search_tax_rulings용 쿼리)을 자동 도출해 '추천검색'으로 반환."""
    return _tj.format_consultation_report(conclusion, evidences, owner_qa, scenarios, dividing_issue, issue_grade)

@mcp.tool(title='Adjusted area on a date', annotations=ToolAnnotations(title='Adjusted area on a date', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_adjusted_area_at_date(region: str, target_date: str) -> dict:
    """Was a location an adjusted (regulated) area on a given date, from the designation history.

    '취득 당시' 조정대상지역 여부 판정 (트리④ B2 — data/adj_regions_history.json 이력 lookup).

    region 예: "서울 마포구"·"성남시 분당구". target_date: 취득일 YYYY-MM-DD(분양권·입주권
    승계취득은 사용승인일 기준). 이력은 근거 확보 구간만 수록(2025-10-16 C급·2026-07-01 A급) —
    미수록 기간·지역은 '판단불가' 반환(그럴듯한 오답 금지). 결과의 acquired_in_adjusted_area를
    judge_exemption_requirements에 연결. 과거분(2017~2025) 백필은 액션백로그 진행 중."""
    return _tj.judge_adjusted_area_at_date(region, target_date)

@mcp.tool(title='Consultation output', annotations=ToolAnnotations(title='Consultation output', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def format_consultation_output(
    scenarios: list[dict],
    dividing_issue: str = "",
    issue_grade: str = "",
    lead_threshold: int = 5_000_000,
    extra_flags: list[dict] | None = None,
) -> dict:
    """Standard output formatter for a consultation result.

    상담 결과 표준 출력 포맷터 (설계 §11 출력규약의 코드화) — 파이프라인의 마지막 단계.

    규약을 강제한다: ①단일 숫자 금지 — 쟁점 등급이 D~F(해석·사실판단)면 시나리오 2개 이상
    병기 필수(성립/불성립 양쪽 세액) ②차액 = 리드 스코어(하<500만<중<3천만<상<1억<최상) —
    차액이 클수록 전문가 상담 기대가치가 커서 매칭 우선순위 ③근거 없는 시나리오 등재 거부
    ④세무사법 안전선 문구 자동 포함(단정 금지). scenarios 원소: {"라벨", "세액", "전제",
    "근거": [판정 함수들의 근거 인용]}. 사용 순서: 트리③→①→②→④ 판정 → calc_* 계산 →
    시나리오별 세액을 이 포맷터로."""
    return _tj.format_consultation_output(scenarios, dividing_issue, issue_grade, lead_threshold, extra_flags)

def _sangjeung_progressive(tax_base: int, year: int) -> tuple[int, float]:
    """상증세 누진세율 적용 (§26, 증여세는 §56이 준용). 세율표는 1층에서 읽는다.

    2026-08-30 — 종전에는 모듈 상수 _SANGJEUNG_BRACKETS를 썼다. 값 자체는 원문과
    일치했으나 연도 게이트도 근거 표시도 없어, 개정되면 조용히 틀릴 자리였다.
    """
    for b in tax_params.get_brackets("상증세.세율표", year):
        if b["upto"] is None or tax_base <= b["upto"]:
            return max(0, int(tax_base * b["rate"] - b["deduction"])), b["rate"]
    return 0, 0.0

@mcp.tool(title='Gift tax (증여세)', annotations=ToolAnnotations(title='Gift tax (증여세)', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def calc_gift_tax(
    taxable_value: int,
    year: int,
    relationship: str = "직계존속",
    is_minor_recipient: bool = False,
    prior_gifts_10yr: int = 0,
    prior_gift_tax_paid: int = 0,
    marriage_birth_deduction: int = 0,
    generation_skip: bool = False,
    over_2b_minor_skip: bool = False,
    filing_credit_rate: float = -1.0,
) -> dict:
    """Korea gift tax (증여세) on real estate: relationship deductions, marriage/birth deduction, prior gifts, progressive rates.

    증여세를 계산한다 (상증세법 §53·§55·§56·§57 — 12차 순회까지 법문 확정 상수 사용).

    taxable_value: 증여재산 과세가액(시가 평가·부담부증여 채무 차감 후 — 평가는 별도.
    아파트 시가는 유사매매사례 요건(상증규칙 §15③: 같은 단지+면적±5%+공시가±5%)으로 판정).
    relationship(증여자 기준): 배우자|직계존속|직계비속|기타친족|타인 — 공제 6억/5천(미성년
    2천)/5천/1천/0, 10년 통산이므로 prior_gifts_10yr(같은 증여자그룹 10년 내 기증여 과세가액)를
    합산하고 기납부세액(prior_gift_tax_paid)을 공제. marriage_birth_deduction: 혼인·출산 공제
    사용액(통합한도 1억, §53의2). generation_skip: 세대생략 할증 30%(미성년+20억 초과는
    over_2b_minor_skip=True로 40%, §57 — 대습상속 제외). filing_credit_rate: 신고세액공제
    (§69 — 기한 내 신고 3%, 무신고면 0으로).

    ⚠️미지원(플래그로 안내): 이월과세(§97의2 — 수증자가 10년 내 양도 시 양도세 쪽에서 처리),
    저가양수 증여의제(§35), 창업자금·가업승계 특례세율.
    """
    공제표 = tax_params.get_param("증여세.증여재산공제", year)
    선택지 = [k for k in 공제표 if "." not in k]
    if relationship not in 선택지:
        return {"오류": f"relationship 선택지: {선택지}"}
    deduction = 공제표[relationship]
    if relationship == "직계존속" and is_minor_recipient:
        deduction = 공제표["직계존속.미성년수증자"]
    # §53의2 혼인·출산 공제는 '직계존속으로부터' 받은 증여에만 있다 (2026-10-09 조문 노드 대조에서 교정 —
    # 종전에는 배우자·기타 증여에도 공제가 들어갔다)
    marriage = 0
    if relationship == "직계존속":
        marriage = min(marriage_birth_deduction,
                       tax_params.get_param("증여세.혼인출산공제", year)["통합한도"])
    if filing_credit_rate < 0:
        filing_credit_rate = tax_params.get_param("상증세.신고세액공제율", year)

    # §47② — 10년 내 동일인 증여재산 합계가 1천만원 이상인 경우에만 가산 (같은 날 교정, 종전 무조건 합산)
    total_value = taxable_value + (prior_gifts_10yr if prior_gifts_10yr >= 10_000_000 else 0)
    tax_base = max(0, total_value - deduction - marriage)
    gross, rate = _sangjeung_progressive(tax_base, year)
    surcharge = 0
    if generation_skip:
        할증 = tax_params.get_param("상증세.세대생략할증", year)
        surcharge = int(gross * (할증["미성년20억초과"] if over_2b_minor_skip
                                 else 할증["기본"]))
    after_prior = max(0, gross + surcharge - prior_gift_tax_paid)
    filing_credit = int(after_prior * filing_credit_rate)
    final_tax = after_prior - filing_credit

    return {
        "증여재산공제": deduction, "혼인출산공제": marriage,
        "합산과세가액": total_value, "과세표준": tax_base,
        "산출세액": gross, "적용세율": rate, "세대생략할증": surcharge,
        "기납부세액공제": min(prior_gift_tax_paid, gross + surcharge),
        "신고세액공제": filing_credit, "납부세액": final_tax,
        "과세연도": year,
        "값 출처": {"세율표": tax_params.cite("상증세.세율표", year),
                 "증여재산공제": tax_params.cite("증여세.증여재산공제", year)},
        "근거": [
            {"규칙": "세율 5구간 10~50%·누진공제", "근거": "상증세법 §26·§56 (검증상수 등재)", "등급": "A"},
            {"규칙": f"증여재산공제 {relationship} {deduction:,} (10년 통산)", "근거": "상증세법 §53·§53의2", "등급": "A"},
            {"규칙": "10년 내 동일인(직계존속은 배우자 합산) 재차증여 합산 + 기납부세액 공제", "근거": "상증세법 §47②·§58", "등급": "A"},
        ],
        "플래그": [
            "과세가액 평가는 별도 — 아파트는 유사매매사례(상증규칙 §15③)·감정평가, 전매제한 물건은 감정평가 필요(외부대조 사례)",
            "부담부증여는 채무인수분을 양도세(유상)로 분리 — 이 계산기엔 무상분만 넣을 것 (§12의2 N-부담부증여)",
            "수증 부동산을 10년 내 양도하면 이월과세(소법 §97의2) — 증여취득세는 필요경비 불인정(영 §163의2)",
            "부동산 증여취득세(시가표준 3.5%, 조정지역 3억↑ 12%)는 별도 — calc_acquisition_tax",
        ],
    }

@mcp.tool(title='Inheritance tax (상속세)', annotations=ToolAnnotations(title='Inheritance tax (상속세)', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def calc_inheritance_tax(
    taxable_value: int,
    year: int,
    spouse_actual_inheritance: int = 0,
    spouse_legal_share_cap: int = 0,
    use_lump_sum_deduction: bool = True,
    cohabit_house_deduction: int = 0,
    other_deductions: int = 0,
    generation_skip_portion: float = 0.0,
    over_2b_minor_skip: bool = False,
    filing_credit_rate: float = -1.0,
) -> dict:
    """Korea inheritance tax (상속세): basic, spouse and lump-sum deductions, progressive rates (estate basis).

    상속세를 계산한다 (상증세법 §18~§26 — 9·11차 순회 법문 확정 상수 사용, 유산세 방식).

    taxable_value: 상속세 과세가액(상속재산 + 사전증여 합산 − 공과금·채무·장례비 차감 후).
    배우자공제(§19): min(실제 상속받은 금액, 법정지분 한도, 30억)이되 최소 5억 —
    spouse_actual_inheritance·spouse_legal_share_cap(법정상속분×과세가액, 모르면 0=미적용)
    입력. 배우자 단독상속은 일괄공제 불가(§21 단서) — use_lump_sum_deduction=False로.
    cohabit_house_deduction: 동거주택 상속공제(§23의2 — 직계비속 10년 동거, 100%·한도 6억).
    generation_skip_portion: 세대생략(손자녀 등) 귀속 비율 0~1 — 그 몫의 산출세액에 30%
    (미성년+20억 초과 40%) 할증(§27, 대습상속 제외).

    ⚠️미지원(플래그): 금융재산공제(§22 — 미순회)·가업/영농상속공제·단기재상속 세액공제(§30)·
    상속개시 6개월 내 양도 시 시가 평가 연동. 인적공제 개별 계산 대신 일괄 5억이 기본.
    """
    sp = tax_params.get_param("상속세.배우자공제", year)
    lump = tax_params.get_param("상속세.일괄공제", year) if use_lump_sum_deduction else 0
    spouse = 0
    if spouse_actual_inheritance > 0 or spouse_legal_share_cap > 0:
        caps = [c for c in (spouse_actual_inheritance, spouse_legal_share_cap,
                            sp["한도"]) if c > 0]
        spouse = max(sp["최소"], min(caps))
    cohabit = min(cohabit_house_deduction,
                  tax_params.get_param("상속세.동거주택공제", year)["한도"])
    if filing_credit_rate < 0:
        filing_credit_rate = tax_params.get_param("상증세.신고세액공제율", year)
    total_deduction = lump + spouse + cohabit + other_deductions

    tax_base = max(0, taxable_value - total_deduction)
    gross, rate = _sangjeung_progressive(tax_base, year)
    skip_portion = min(max(generation_skip_portion, 0.0), 1.0)
    할증 = tax_params.get_param("상증세.세대생략할증", year)
    surcharge = int(gross * skip_portion *
                    (할증["미성년20억초과"] if over_2b_minor_skip else 할증["기본"]))
    filing_credit = int((gross + surcharge) * filing_credit_rate)
    final_tax = gross + surcharge - filing_credit

    return {
        "과세연도": year,
        "값 출처": {"세율표": tax_params.cite("상증세.세율표", year),
                 "배우자공제": tax_params.cite("상속세.배우자공제", year),
                 "일괄공제": tax_params.cite("상속세.일괄공제", year)},
        "공제합계": total_deduction,
        "공제내역": {"일괄공제": lump, "배우자공제": spouse, "동거주택공제": cohabit, "기타": other_deductions},
        "과세표준": tax_base, "산출세액": gross, "적용세율": rate,
        "세대생략할증": surcharge, "신고세액공제": filing_credit, "납부세액": final_tax,
        "근거": [
            {"규칙": "세율 5구간 10~50%·누진공제 (상속·증여 동일)", "근거": "상증세법 §26 (검증상수 등재)", "등급": "A"},
            {"규칙": "일괄공제 5억(배우자 단독상속 불가)·배우자 최소 5억~최대 30억(분할·등기 요건)·동거주택 100% 한도 6억", "근거": "상증세법 §21·§19·§23의2 (검증상수 '상속공제 세트')", "등급": "A"},
            {"규칙": "세대생략 할증 30%(미성년+20억 초과 40%), 대습상속 제외", "근거": "상증세법 §27 (12차 순회 NSJ27-1)", "등급": "A"},
        ],
        "플래그": [
            "배우자공제는 상속세 신고기한 내 분할·등기 요건(§19②) — 미분할 시 5억만",
            "금융재산공제(§22)·가업상속공제 미지원(미순회) — 해당 시 과대계산됨",
            "사전증여재산(10년 내) 합산·기납부 증여세액공제는 taxable_value·other_deductions에 반영해 넣을 것(§13·§28)",
            "상속개시 6개월 내 매도 시 매도가=시가(영 §49①) — 양도세 0이지만 상속재산 평가액 상승 트레이드오프(🎭 카탈로그 사례)",
            "상속주택은 양도세 §155② 특례·취득세 무주택 상속 특례(0.8%) 별도 검토",
        ],
    }

@mcp.tool(title='Search tax rulings', annotations=ToolAnnotations(title='Search tax rulings', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def search_tax_rulings(query: str, source: str = "국세청해석", display: int = 10) -> dict:
    """Search official Korean tax rulings and tribunal decisions used as regression answers.

    세무 해석례·심판례를 검색한다 — 판정 쟁점플래그의 D·E급 근거 탐색용 (법제처 공동활용).

    source: "국세청해석"(ntsCgmExpc, 17,534건 — 예규 회신, 요건 판정의 1순위 원료) |
    "조세심판원"(ttSpecialDecc, 12,109건 — 재결례, 경정청구·가액 다툼 중심) |
    "행안부해석"(moisCgmExpc — 취득세·재산세) | "법령해석례"(expc — 법제처·기재부).

    ⚠️검색 시맨틱이 소스마다 다름(2026-08-16 실측): 조세심판원은 공백 토큰=AND,
    국세청·행안부는 공백=OR라 수치가 부풀려짐 — 국세청·행안부는 따옴표 구문 단독으로
    질의할 것(예: '\"상생임대\"'). 이 함수는 국세청·행안부에 공백 포함 쿼리가 오면 자동으로
    따옴표를 씌운다. 결과의 상세링크는 국세법령정보시스템(taxlaw) — 상담 출력에는 링크만 낸다.
    (검증용 본문 수집은 scripts/fetch_rulings.py 담당. 저작권법 §7 3호로 심판례·판결문은
    보호받지 못하는 저작물이라 보관·인용 가능 — 종전 '수집 금지' 유보는 2026-08-23 해소.)
    예규 승격 플로우: 전언 → 이 검색으로 안건번호·회신일 대조 → D급 확정.
    """
    targets = {"국세청해석": "ntsCgmExpc", "조세심판원": "ttSpecialDecc",
               "행안부해석": "moisCgmExpc", "법령해석례": "expc"}
    target = targets.get(source)
    if not target:
        raise ValueError(f"source 선택지: {list(targets)}")
    if not LAW_OC:
        raise RuntimeError("LAW_OC가 설정되지 않았습니다 (.env 확인)")

    q = query
    if target in ("ntsCgmExpc", "moisCgmExpc") and " " in q and '"' not in q:
        q = f'"{q}"'  # OR 시맨틱 소스는 구문검색 강제
    params = {"OC": LAW_OC, "target": target, "type": "JSON", "query": q,
              "search": 2, "display": display}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(LAW_SEARCH_URL, params=params)
        resp.raise_for_status()
        return resp.json()

@mcp.tool(title='Home plus pre-sale right case', annotations=ToolAnnotations(title='Home plus pre-sale right case', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
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
    """Home plus pre-sale right (분양권) one-home special case (Income Tax Decree art. 156-3).

    주택+분양권 1세대1주택 특례 판정 (영 §156의3, 규칙 §75·§75의2 — 24차 순회).

    입주권은 judge_155_special·§156의2 계열이 맡고, 이 툴은 **분양권** 전용이다.
    **판정범위는 ②③항(일시적 1주택+1분양권)뿐이다** — 상속분양권(④⑤)·동거봉양/혼인
    조합(⑥)·문화재/이농주택 조합(⑦⑧)은 미구현이며 반환 '판정범위' 필드로 고지된다.
    상속·합가·혼인이 얽힌 분양권 상담에는 이 결론을 그대로 쓰지 말 것.
    2021-01-01 이후 취득한 분양권부터 주택수에 들어가므로 그 전 취득분은
    "특례 불필요"로 돌려준다 — 탈락과 구분해서 읽을 것.

    판정 순서: ②항(분양권 취득 후 3년 내 종전주택 양도) → 안 되면 규칙 §75① 부득이한
    사유 → 그래도 안 되면 ③항(신축주택 완성 후 실입주).

    함정 셋을 코드에 박아 뒀다.
    - ②항 후단이 1년 요건을 면제하는 것은 §154① 제1호·제2호**가목**·제3호뿐이다.
      해외이주 출국(제2호나목)·국외 취학근무 출국(다목)은 면제 대상이 아니다.
    - ③항의 "완성 후 2년"은 2023-02-28 개정으로 3년이 됐는데, 기준은 시행일이 아니라
      **2023-01-12 이후 양도분**이다(부칙 §8).
    - ③항의 "종전주택 취득 1년 경과" 요건은 2022-02-15 이후 **취득한 분양권**부터다
      (부칙 §12). 양도일 기준이 아니다.

    Args:
        prior_home_acquired: 종전주택 취득일 YYYY-MM-DD
        bunyang_acquired: 분양권 취득일 YYYY-MM-DD (계약일 아님)
        sale_date: 종전주택 양도일 YYYY-MM-DD
        new_home_completed: 분양권으로 취득하는 주택의 완성일 (③항 판정에 필요)
        moved_in_date: 신축주택으로 세대전원이 이사한 날
        continuous_residence_years: 신축주택 계속거주 기간(년) — 1년 이상이어야 한다
        holding_waiver_reason: ""|건설임대5년거주|수용|해외이주2년|취학근무국외|부득이1년거주
            (judge_exemption_requirements의 waiver_reason과 같은 어휘)
        sale_delay_reason: ""|캠코매각의뢰|법원경매신청|공매진행 (규칙 §75① 열거 3가지)
        delay_state_at_3y: 분양권 취득일부터 3년이 되는 날 현재 그 상태였는지
        sold_by_that_method: 실제로 그 방법(경매·공매 등)으로 양도됐는지
        partial_move_reason: ""|취학|근무|질병|학교폭력 — 세대원 일부가 못 옮긴 사유
        other_homes: 종전주택·분양권 외에 보유한 주택 수. §156의3②은 '1주택+1분양권'
            전제라 제외 특례를 거치지 못한 주택이 남으면 이 항으로는 비과세되지 않는다
        excluded_homes: 그중 주택수 제외 특례로 빠지는 수 — 농어촌주택(조특법 §99의4)·
            인구감소지역주택(§71의2)·준공후미분양(§98의9). 제외 후 1주택이면 적용된다
        bunyang_already_completed: 양도 당시 분양권이 이미 완공돼 주택이 된 경우
    """
    return _tj.judge_156_3_special(
        prior_home_acquired, bunyang_acquired, sale_date, new_home_completed,
        moved_in_date, continuous_residence_years, holding_waiver_reason,
        sale_delay_reason, delay_state_at_3y, sold_by_that_method,
        partial_move_reason, other_homes, excluded_homes, bunyang_already_completed,
    )

import relief_catalog as _rc  # noqa: E402  (감면 색인 — 판정 아님, C등급)

@mcp.tool(title='Relief candidates to check', annotations=ToolAnnotations(title='Relief candidates to check', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def screen_relief_candidates(
    tax_types: str = "",
    situation: str = "",
    assets: str = "",
    include_expired: bool = False,
    include_decree: bool = False,
    include_corporate: bool = False,
    limit: int = 12,
) -> dict:
    """List the tax reliefs and special cases worth checking for a given situation, to avoid omissions.

    조특법·지특법 감면/특례 중 이 상담에서 검토해야 할 조문을 뽑는다 (누락 방지용).

    **판정이 아니다.** judge_*/calc_*는 A등급 법문 노드로 결론을 내지만 이 툴은
    C등급 기계추출 색인이라 "여기를 봐라"까지만 한다. 감면 누락은 고객이 세금을 더
    내는 방향이라 틀린 답보다 조용히 손해가 나므로, 상담 마무리 전에 한 번 돌려
    빠진 감면이 없는지 확인하는 용도다. 걸린 조문은 반드시 원문·판정툴로 재확인한다.

    Args:
        tax_types: 세목 쉼표 구분 — "양도소득세,취득세,재산세,종합부동산세,증여세" 등
        situation: 상담 문장 그대로 넣어도 된다. 생활어(첫집·다둥이·수용보상)를
            법령 용어 계열로 확장해 매칭한다
        assets: 자산 쉼표 구분 — "주택,농지,토지,임대주택,미분양주택,분양권·입주권" 등
        include_expired: 본문 기한이 전부 과거인 조문까지 포함(경정청구·과거 취득분 검토 시)
        include_decree: 시행령 조문까지 포함(요건 상세를 볼 때. 기본은 법 조문만)
        include_corporate: 법인·기관 전용 조문까지 포함
        limit: 최대 표시 건수
    """
    return _rc.screen(
        semok=[x.strip() for x in tax_types.split(",") if x.strip()],
        situation=situation,
        assets=[x.strip() for x in assets.split(",") if x.strip()],
        include_corporate=include_corporate,
        include_expired=include_expired,
        include_decree=include_decree,
        limit=limit,
    )

@mcp.tool(title='Home plus pre-sale right (portfolio)', annotations=ToolAnnotations(title='Home plus pre-sale right (portfolio)', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def judge_156_3_from_portfolio(
    items: list[dict],
    sale_date: str,
    new_home_completed: str = "",
    moved_in_date: str = "",
    continuous_residence_years: float = 0.0,
    holding_waiver_reason: str = "",
    sale_delay_reason: str = "",
    delay_state_at_3y: bool = False,
    sold_by_that_method: bool = False,
    partial_move_reason: str = "",
) -> dict:
    """Same as judge_156_3_special, but counts homes from a holdings list.

    보유 목록만 넣으면 §156의3 특례를 판정한다 — 주택수를 코드가 센다.

    judge_156_3_special을 직접 쓰면 other_homes·excluded_homes를 사람이 채워야 하고,
    빠뜨리면 조용히 '1주택+1분양권'으로 가정하고 답한다. **상담에서는 이 툴을 먼저
    쓸 것.** count_transfer_homes와 같은 items 규약을 받아 종전주택·분양권·나머지
    주택수를 세고, 농어촌주택·상속주택 등 제외 특례를 자동 반영한다.

    반환의 '주택수산정'에 무엇을 몇 채로 셌는지와 제외 사유가 들어 있으니, 결론보다
    그것을 먼저 확인할 것 — 목록 자체가 틀리면 판정도 틀린다.

    Args:
        items: 보유 자산 목록. 각 원소는 count_transfer_homes 규약을 따른다 —
            {"종류": "주택"|"분양권"|"조합원입주권"|"오피스텔", "취득일": "YYYY-MM-DD",
             "라벨": str, "농어촌주택특례": bool, "상속특례주택": bool, ...}.
            **양도할 주택 하나에 "양도대상": True를 표시해야 한다.**
            분양권 취득일은 청약당첨일이 아니라 분양계약일(대법원 2024두54560).
        sale_date: 종전주택 양도일 YYYY-MM-DD
        new_home_completed: 분양권으로 취득하는 주택의 완성일 (③항 판정에 필요)
        moved_in_date: 신축주택으로 세대전원이 이사한 날
        continuous_residence_years: 신축주택 계속거주 기간(년)
        holding_waiver_reason: ""|건설임대5년거주|수용|해외이주2년|취학근무국외|부득이1년거주
        sale_delay_reason: ""|캠코매각의뢰|법원경매신청|공매진행 (규칙 §75① 열거 3가지)
        delay_state_at_3y: 분양권 취득일부터 3년이 되는 날 현재 그 상태였는지
        sold_by_that_method: 실제로 그 방법으로 양도됐는지
        partial_move_reason: ""|취학|근무|질병|학교폭력
    """
    return _tj.judge_156_3_from_portfolio(
        items, sale_date,
        new_home_completed=new_home_completed,
        moved_in_date=moved_in_date,
        continuous_residence_years=continuous_residence_years,
        holding_waiver_reason=holding_waiver_reason,
        sale_delay_reason=sale_delay_reason,
        delay_state_at_3y=delay_state_at_3y,
        sold_by_that_method=sold_by_that_method,
        partial_move_reason=partial_move_reason,
    )

@mcp.tool(title='Relief catalog entry', annotations=ToolAnnotations(title='Relief catalog entry', readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def get_relief_catalog_entry(article: str) -> dict:
    """Look up one relief catalog entry by statute reference.

    감면 카탈로그 한 건 조회 — "지특법 §36의5", "조특97의3" 같은 표기를 받는다.

    screen_relief_candidates가 뽑아 준 후보의 원문 요지·감면율·기한을 다시 볼 때 쓴다.
    여기 값도 C등급 기계추출이므로 확정 근거로 인용하면 안 된다.
    """
    e = _rc.lookup(article)
    if not e:
        return {"오류": "카탈로그에 없다: %s" % article,
                "안내": "법 조문만 색인돼 있다. 시행령은 include_decree로 조회할 것"}
    return dict(e, 주의=_rc.DISCLAIMER)


def main() -> None:
    """콘솔 진입점(pyproject [project.scripts]).

    기본은 stdio. 환경변수 MCP_TRANSPORT=streamable-http 이면 HTTP 서버로 뜬다(원격 커넥터용):
    HOST(기본 0.0.0.0)·PORT(기본 8000)·MCP_PATH(기본 /mcp). 인증은 없으니 공개 배포 시 앞단에서 처리한다.
    """
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.settings.host = os.environ.get("HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "8000"))
        mcp.settings.streamable_http_path = os.environ.get("MCP_PATH", "/mcp")
        mcp.settings.stateless_http = True
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
