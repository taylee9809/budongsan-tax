"""건축물분 재산세 도구 — 호스팅 서버에 붙인다(tax_http.py). 생성 파일 tax_server.py 는 건드리지 않는다.

계산은 전부 조문 노드(tax_nodes/jaesan_geonchuk.py + 주택분과 함께 쓰는 tax_nodes/jaesan.py)가 한다.
이 파일은 도구 입출력만 맡는다. 세율·비율은 data/tax_params.json 에서 과세연도로 읽고,
검증되지 않은 연도는 계산을 거부한다.
"""
from __future__ import annotations

TOOLS = ("calc_building_property_tax",)

#: 결과에 항상 붙이는 범위 고지 — 도구가 답하지 않는 것을 모델이 지어내지 않게 한다.
NOT_COVERED = [
    "건축물 시가표준액 산정(지방세법 §4②) — standard_value 는 호출자가 준 값을 그대로 쓴다. 지방자치단체가 결정·고시한다.",
    "부속토지의 재산세 — 토지는 따로 과세된다(별도합산·분리과세·종합합산, 지방세법 §106·§111①1호·§113). 이 도구는 건축물만 계산한다.",
    "주택 — 주택과 그 부속토지는 calc_property_tax 로 계산한다. 주거용 오피스텔처럼 주택으로 과세되는지의 판단(§104 3호, §106②)도 하지 않는다.",
    "소방분 지역자원시설세(지방세법 §146③) — 건축물 재산세 고지서에 함께 나오지만 계산하지 않는다.",
    "골프장·고급오락장 해당 여부(§13⑤, 시행령 §28), 시행규칙 별표 2 공장 업종 해당 여부, 과밀억제권역·주거지역·조례 지정 지역 여부 — 입력을 그대로 믿는다.",
    "비과세(§109)·감면(지방세특례제한법·감면조례), 직전 연도 재산세액 상당액의 재계산(시행령 §118 2호 나·다목) — 호출자가 계산해 넣는다.",
    "납기(§115)·분할납부(§118)·소액 징수면제(§119)와 세액의 끝수 처리 — 원 미만만 버린다.",
]

_USE = ("일반", "골프장", "고급오락장", "공장")
_FACTORY_KEYS = {
    "연면적": "공장_연면적", "별표2업종": "공장_별표2업종", "시지역": "공장_시지역", "주거지역등": "공장_주거지역등",
    "과밀억제권역": "공장_과밀억제권역", "산업단지등": "공장_산업단지등", "신설증설": "공장_신설증설",
    "도시형공장": "공장_도시형공장", "중과제외목": "공장_중과제외목", "기산일": "공장_기산일",
}


def calc_building_property_tax(
    year: int,
    standard_value: int,
    use: str = "일반",
    factory: dict | None = None,
    urban_area: bool = True,
    urban_area_rate: float | None = None,
    ordinance_rate: float | None = None,
    prior_year_tax: int | None = None,
    prior_year_urban_tax: int | None = None,
    prior_year_recomputed: bool = False,
) -> dict:
    """Korea property tax (재산세) on a non-residential building — shops, offices, warehouses, factories, golf course and luxury entertainment buildings (Local Tax Act art. 111(1)2, 111(2)): taxable base, rate by building class, urban area levy, 150% tax burden cap, local education tax. Returns the statute trail.

    건축물(상가·사무실·창고·공장·골프장·고급오락장용 건축물)의 재산세를 계산한다. 주택과 토지는 이 도구가 아니다.

    과세표준 = 시가표준액 × 공정시장가액비율 70%(지방세법 §110①, 시행령 §109①1호).
    세율은 지방세법 §111①2호 — 가목 골프장·고급오락장용 건축물 1천분의 40, 나목 시 지역 주거지역 등의 공장용 건축물
    1천분의 5, 다목 그 밖의 건축물 1천분의 2.5. 과밀억제권역에서 공장을 신설·증설하면 최초의 과세기준일부터 5년간
    다목 세율의 5배인 1천분의 12.5(§111②). 공장이라고 가목이 되지는 않는다 — 공장은 나목·다목·§111② 중 하나다.
    여기에 도시지역분(§112①2호, 과세표준 × 1천분의 1.4), 세 부담 상한(§122, 직전 연도 세액의 150%),
    지방교육세(§151①6호, 재산세 본세의 20% — 도시지역분 제외)를 더한다.

    Args:
        year: 과세연도(과세기준일 6월 1일이 속하는 해). 세율 조회 키이며 필수다. 검증되지 않은 연도는 계산을 거부한다.
        standard_value: 건축물 시가표준액(원) — 지방세법 §4②에 따라 지방자치단체가 결정한 값. 토지 가액은 넣지 않는다.
            공장 증설로 §111②가 걸리는 경우에는 증설한 부분의 시가표준액만 넣고 나머지는 따로 계산한다.
        use: "일반"(상가·사무실·창고 등) | "골프장" | "고급오락장" | "공장".
            골프장·고급오락장은 지방세법 §13⑤에 해당하는 것만이다(회원제 골프장, 카지노·유흥주점 등 — 판정은 호출자).
        factory: use 가 "공장"일 때의 사실. 모르는 항목은 빼면 된다 — 빠진 요건은 충족하지 않은 것으로 보고 사유를 남긴다.
            {"연면적": 생산설비를 갖춘 건축물의 연면적(㎡) — 옥외 기계장치·저장시설의 수평투영면적과 공장 경계구역 안
                       부대시설을 포함하고 식당·기숙사 등 후생복지시설은 뺀다(시행규칙 §55),
             "별표2업종": 지방세법 시행규칙 별표 2(공장의 종류)에 규정된 업종이면 True,
             "시지역": 특별시·광역시(군 제외)·특별자치시·특별자치도·시의 읍·면이 아닌 지역이면 True,
             "주거지역등": 주거지역 또는 그 지방자치단체 조례로 정하는 지역이면 True,
             "과밀억제권역": 수도권정비계획법 §6 과밀억제권역이면 True,
             "산업단지등": 산업단지·유치지역·공업지역이면 True(§111② 대상에서 빠진다),
             "신설증설": "신설" | "증설" (과밀억제권역에서 공장을 새로 짓거나 늘린 경우),
             "기산일": "YYYY-MM-DD" — 공장용으로 건축허가를 받아 지었거나 공장용으로 쓰려고 양수했으면 취득일,
                       그 밖에는 공장시설 설치를 시작한 날(시행규칙 §56②). 이 날 이후 처음 오는 6월 1일부터 5년간이다,
             "도시형공장": 산업집적활성화 및 공장설립에 관한 법률 §28 도시형 공장이면 True(§111② 대상에서 빠진다),
             "중과제외목": 시행규칙 §7②2호 각 목에 해당하면 그 목 — "가" 포괄 승계취득 · "나" 같은 권역 안 이전 ·
                          "다" 업종 변경 · "라" 철거 후 1년 내 같은 규모 재축 · "마" 권역 편입 전 승인·허가 ·
                          "바" 부동산 취득 후 5년 지나 신설·증설}
        urban_area: 재산세 도시지역분 적용대상 지역(도시지역 중 지방의회 의결로 고시한 지역, §112①)이면 True.
            동(洞) 지역 건축물은 대부분 해당한다. 아니면 False.
        urban_area_rate: 조례로 달리 정한 도시지역분 세율(§112②, 1천분의 2.3 이하). 생략하면 1천분의 1.4.
        ordinance_rate: 조례로 가감한 그 해의 건축물 세율(§111③, 표준세율의 50%~150%). 생략하면 표준세율.
        prior_year_tax: 직전 연도에 이 건축물에 과세된 재산세 본세(도시지역분·지방교육세 제외, 원). 주면 세 부담 상한
            150%(§122)를 적용한다. 생략하면 상한을 계산하지 않고 그 사실을 결과에 적는다.
            신축·증축했거나 용도변경으로 세율이 달라졌으면 직전 연도에도 올해 현황·세율이었다고 보고 다시 계산한
            세액을 넣고(시행령 §118 2호 나·다목) prior_year_recomputed 를 True 로 한다.
        prior_year_urban_tax: 직전 연도 도시지역분 세액(원). 상한은 본세와 도시지역분에 각각 건다(§122 괄호).
        prior_year_recomputed: prior_year_tax 가 실제 과세된 세액이 아니라 다시 계산한 상당액이면 True.

    Returns:
        과세표준, 세율구분·적용세율, 재산세 본세·도시지역분·지방교육세·총납부세액, 세부담상한 내역,
        적용 조문, 미적용 조문(사유 포함), 값 출처, 주의, 다루지 않는 것.
    """
    import tax_params
    from tax_nodes import jaesan_geonchuk

    if standard_value is None or standard_value <= 0:
        raise ValueError("standard_value(건축물 시가표준액)는 0보다 커야 합니다")
    if use not in _USE:
        raise ValueError("use 는 %s 중 하나입니다 (지방세법 §111①2호)" % " | ".join(_USE))
    if factory and use != "공장":
        raise ValueError("factory 는 use 가 '공장'일 때만 넣습니다")
    unknown = set(factory or {}) - set(_FACTORY_KEYS)
    if unknown:
        raise ValueError("factory 에 모르는 항목이 있습니다: %s (쓸 수 있는 항목: %s)"
                         % (", ".join(sorted(unknown)), ", ".join(_FACTORY_KEYS)))
    for name, v in (("prior_year_tax", prior_year_tax), ("prior_year_urban_tax", prior_year_urban_tax)):
        if v is not None and v <= 0:
            raise ValueError("%s 는 0보다 커야 합니다 — 직전 연도 세액이 없으면 생략하고, 신축이면 "
                             "시행령 §118 2호나목으로 계산한 상당액을 넣습니다" % name)
    if urban_area_rate is not None:
        if not urban_area:
            raise ValueError("urban_area 가 False 이면 urban_area_rate 를 넣지 않습니다")
        cap = tax_params.get_param("재산세.도시지역분.조례상한", year)
        if not 0 < urban_area_rate <= cap:
            raise ValueError("urban_area_rate 는 0 초과 %s 이하입니다 (지방세법 §112② — 1천분의 2.3)" % cap)

    facts = {_FACTORY_KEYS[k]: v for k, v in (factory or {}).items()}
    facts["도시지역분세율"] = (urban_area_rate if urban_area_rate is not None else None) if urban_area else 0
    facts["조례_가감세율"] = ordinance_rate
    facts["직전연도_법령적용세액" if prior_year_recomputed else "직전연도_과세세액"] = prior_year_tax
    facts["직전연도_도시지역분_세액상당액"] = prior_year_urban_tax

    r = jaesan_geonchuk.재산세_건축물(standard_value, year, 용도=use, **facts)
    r.pop("근거표", None)

    notes = []
    cap_detail = r["세부담상한"]
    if cap_detail is None:
        notes.append("직전 연도 세액(prior_year_tax)이 없어 세 부담 상한(§122, 직전 연도의 150%)을 계산하지 않았다 — "
                     "산출세액이 직전 연도 세액의 1.5배를 넘으면 실제 고지액은 이 결과보다 적다")
    else:
        if cap_detail["제1호"]["상한적용"] is None:
            notes.append("직전 연도 본세(prior_year_tax)가 없어 본세에는 세 부담 상한을 걸지 않았다")
        if r["도시지역분(산출세액)"] and cap_detail["제2호"]["상한적용"] is None:
            notes.append("직전 연도 도시지역분 세액(prior_year_urban_tax)이 없어 도시지역분에는 세 부담 상한을 걸지 않았다")
    if use == "공장" and r["세율구분"] == "다목":
        notes.append("공장이지만 나목(주거지역 등 1천분의 5)·§111②(과밀억제권역 신설·증설 1천분의 12.5) 요건이 확인되지 않아 "
                     "다목 1천분의 2.5로 계산했다 — 미적용 조문의 사유를 확인할 것")
    if r["세율구분"] == "§111②" and (factory or {}).get("신설증설") == "증설":
        notes.append("증설이면 §111② 세율은 증설한 부분의 공장용 건축물에만 걸린다(시행규칙 §7②1호가목) — "
                     "standard_value 가 증설 부분의 시가표준액인지 확인할 것")
    if ordinance_rate is not None and not r["조례가감 적용여부"]:
        notes.append("ordinance_rate 를 적용하지 않았다 — §111② 세율은 '제1항의 표준세율'이 아니어서 조례 가감(§111③) 대상인지 "
                     "법문으로 확정하지 못했다")
    if use in ("골프장", "고급오락장"):
        notes.append("가목 1천분의 40은 지방세법 §13⑤에 해당하는 골프장·고급오락장용 건축물에만 적용된다 — 해당 여부는 입력을 그대로 믿었다")
    if not urban_area:
        notes.append("도시지역분 적용대상 지역이 아니라고 보고 도시지역분을 계산하지 않았다")
    notes.append("건축물분만이다 — 부속토지 재산세와 소방분 지역자원시설세는 따로 나온다")

    return {
        "과세연도": year,
        "과세기준일": r["과세기준일"],
        "시가표준액": r["시가표준액"],
        "공정시장가액비율": r["공정시장가액비율"],
        "과세표준": r["과세표준"],
        "세율구분": r["세율구분"],
        "표준세율": r["표준세율"],
        "적용세율": r["적용세율"],
        "조례가감 적용여부": r["조례가감 적용여부"],
        "재산세 본세(산출세액)": r["재산세 본세(산출세액)"],
        "도시지역분(산출세액)": r["도시지역분(산출세액)"],
        "세부담상한": cap_detail,
        "재산세 본세": r["재산세 본세"],
        "도시지역분": r["도시지역분"],
        "지방교육세": r["지방교육세"],
        "총납부세액": r["총납부세액"],
        "최초과세기준일": r["최초과세기준일"],
        "적용 조문": r["적용 조문"],
        "미적용 조문": r["미적용 조문"],
        "값 출처": r["값 출처"],
        "주의": notes,
        "다루지 않는 것": NOT_COVERED,
    }
