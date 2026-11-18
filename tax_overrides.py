# -*- coding: utf-8 -*-
"""생성 서버(tax_server.py) 도구의 고친 판 — 같은 이름으로 대체한다.

tax_server.py 는 비공개 생성기가 만드는 파일이라 이 저장소에서 손으로 고치지 않는다. 그 안의 도구 넷에 결함이 있다
(data/verification/findings.jsonl 88·95·97·98). 여기의 함수는 이름과 기존 인자를 그대로 두고 필요한 인자만 더한
판이다. 계산은 새로 짜지 않는다 — tax_server 의 원래 함수, 판정기(tax_judgment), 조문 노드(tax_nodes)를 부르고
결함이 있는 입구만 바로잡는다.

  calc_jongbu_tax        공제 0원을 값으로 받는다(None 이 미지정). 법인(is_corporation)은 계산하지 않고 이유를 돌려준다.
  calc_acquisition_tax   §13의2① 유형(heavy_type)을 주택 유상취득이 아닌 물건에 주면 계산하지 않고 이유를 돌려준다.
                         가산세율을 직접 넘긴 호출에는 지방교육세 경고를 붙인다(금액은 그대로).
  judge_transfer_reliefs 판정기가 받는 한시 배제 나목 인자(토지거래허가·6개월 지역·소재지)를 넘긴다.
  count_heavy_homes      양도 주택을 지정하면 주택 목록으로 중과 대상·가산세율까지 본다(조문 노드 중과세율_판정).

대체 목록은 OVERRIDES 한 곳이다. 호스팅 서버(tax_http.make_server), stdio 진입점(tax_full), 케이스 실행기
(scripts/verify_tool_cases.py)가 이 표를 읽는다. 대체 도구의 인자가 원래 도구 인자의 상위집합인지는
tests/test_tax_overrides.py 가 지킨다 — 생성기가 인자를 바꾸면 깨진다.

조문 근거(법제처 원문 2026-11-18 대조 — 지방세법 법률 제21308호 시행 2026-07-01, 종합부동산세법 법률 제21224호 시행 2026-01-01)
  지방세법 §13의2①  "주택(…)을 유상거래를 원인으로 취득하는 경우로서 다음 각 호의 어느 하나에 해당하는 경우에는 …"
  지방세법 §13②     "… 제11조제1항의 표준세율의 100분의 300에서 중과기준세율의 100분의 200을 뺀 세율 …"
  지방세법 §151①1호 가목 "제13조제2항ㆍ제3항ㆍ제6항 또는 제7항에 해당하는 경우: 이 호 각 목 외의 부분 본문의 계산방법으로
                     산출한 지방교육세액의 100분의 300. 다만, 법인이 제11조제1항제8호에 따른 주택을 취득하는 경우에는 나목을 적용한다."
  종합부동산세법 §8①2호 "제9조제2항제3호 각 목의 세율이 적용되는 법인 또는 법인으로 보는 단체: 0원"
  종합부동산세법 §9②3호 "가. 2주택 이하를 소유한 경우: 1천분의 27  나. 3주택 이상을 소유한 경우: 1천분의 50"
  종합부동산세법 §10 단서 "납세의무자가 법인 또는 법인으로 보는 단체로서 제9조제2항제3호 각 목의 세율이 적용되는 경우는 그러하지 아니하다."
"""
from __future__ import annotations

import types

import tax_judgment as _tj
import tax_params
import tax_server as _ts

#: 원래 도구와 기본값이 달라진 인자. 그 밖의 기존 인자는 이름·순서·기본값이 원래 도구와 같아야 한다(테스트가 대조).
CHANGED_DEFAULTS = {"calc_jongbu_tax": {"basic_deduction": None}}


def _거부(사유: str, 근거: str, **더) -> dict:
    """계산하지 않았다는 결과. 금액 키를 넣지 않는다 — 금액처럼 읽힐 값이 없어야 한다."""
    return dict({"계산불가": True, "사유": 사유, "근거": 근거}, **더)


# ───────────────────────────────────────────────────────────── 종합부동산세
class _공제0원:
    """tax_params 대역 — 기본공제 표만 0원으로 돌려준다.

    원래 함수는 `if not basic_deduction:` 으로 0을 미지정으로 읽고 표에서 9억·12억을 가져온다. 같은 코드를 그대로
    돌리되 그 표만 0원으로 읽히게 해서 '공제 0원'을 계산한다. 전역 tax_params 는 건드리지 않는다.
    """

    def __getattr__(self, name):
        return getattr(tax_params, name)

    @staticmethod
    def get_param(key, year, *a, **k):
        v = tax_params.get_param(key, year, *a, **k)
        return {x: 0 for x in v} if key == "종부세.주택.기본공제" else v


def _공제0원_판(fn):
    g = dict(fn.__globals__, tax_params=_공제0원())
    f = types.FunctionType(fn.__code__, g, fn.__name__, fn.__defaults__, fn.__closure__)
    f.__kwdefaults__ = fn.__kwdefaults__
    return f


_jongbu_공제0원 = _공제0원_판(_ts.calc_jongbu_tax)

_법인_거부사유 = (
    "법인(법인으로 보는 단체 포함)의 주택분 종합부동산세는 이 계산으로 내지 않는다. 법인은 공제금액이 0원이고"
    "(종합부동산세법 §8①2호) 세율이 2주택 이하 2.7%, 3주택 이상 5%의 단일세율이며(§9②3호) 세 부담 상한이 없다(§10 단서). "
    "공익법인등·공공주택사업자 등은 다시 개인과 같은 세율·공제 9억원이다(§9②1·2호, §8①3호). 이 계산은 그 구분에 필요한 사실"
    "(법인의 종류, 공익목적 사용 여부)을 받지 않고, 개인의 누진세율·1세대 1주택 공제·세 부담 상한을 전제로 한다. "
    "법인 전용 종합부동산세 계산(법인 종류와 주택 수를 받는다)을 쓴다.")


def calc_jongbu_tax(
    total_official_price: int,
    year: int,
    prev_year_official_price: int = 0,
    one_home: bool = False,
    home_count: int = 1,
    age: int = 0,
    holding_years: int = 0,
    basic_deduction: int | None = None,
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
    is_corporation: bool = False,
) -> dict:
    """개인의 주택분 종합부동산세. 설명은 hosted_descriptions.DESCRIPTIONS["calc_jongbu_tax"]."""
    if is_corporation:
        return _거부(_법인_거부사유, "종합부동산세법 §8①2호 · §9② · §10 단서")
    if basic_deduction is not None and basic_deduction < 0:
        raise ValueError("basic_deduction은 0 이상이어야 합니다(미지정은 생략 또는 null)")
    rest = dict(
        prev_year_official_price=prev_year_official_price, one_home=one_home, home_count=home_count, age=age,
        holding_years=holding_years, fair_market_ratio=fair_market_ratio, tax_brackets=tax_brackets,
        property_tax_credit=property_tax_credit, age_credit_rate=age_credit_rate,
        holding_credit_rate=holding_credit_rate, credit_cap=credit_cap,
        previous_year_total_tax=previous_year_total_tax, burden_cap_ratio=burden_cap_ratio,
        current_year_property_tax=current_year_property_tax, rural_special_tax_rate=rural_special_tax_rate)
    if basic_deduction is None or basic_deduction > 0:
        # 미지정(None)과 양수는 원래 함수 그대로다 — 원래 함수에서 0은 '표에서 읽어라'였다.
        return _ts.calc_jongbu_tax(total_official_price, year, basic_deduction=basic_deduction or 0, **rest)
    # 여기부터 basic_deduction == 0 을 명시한 호출: 공제 0원으로 계산한다.
    if one_home:
        return _거부(
            "one_home=true(1세대 1주택자, 공제 12억원 — 종합부동산세법 §8①1호)와 basic_deduction=0(공제 0원 — §8①2호, "
            "§9②3호 세율 법인)은 함께 성립하지 않는다. 개인이면 basic_deduction 을 생략(null)한다 — 공제금액은 표에서 읽는다. "
            "법인이면 이 계산으로 내지 않는다.", "종합부동산세법 §8① 각 호")
    r = _jongbu_공제0원(total_official_price, year, **rest)
    경고 = ["공제금액 0원으로 계산했다(basic_deduction=0 명시). 공제 0원은 §9②3호 세율이 적용되는 법인뿐이다"
          "(종합부동산세법 §8①2호) — 개인이면 basic_deduction 을 생략해 9억원·12억원이 적용되게 한다."]
    if tax_brackets is None:
        경고.append("세율표(tax_brackets)를 주지 않아 개인의 누진세율(§9①)을 적용했다. 공제 0원인 법인의 세율은 "
                  "2주택 이하 2.7%·3주택 이상 5% 단일세율(§9②3호)이라 이 세액은 법인의 세액이 아니다.")
    if r.get("세부담상한 적용여부"):
        경고.append("세 부담 상한(§10 본문)이 적용돼 세액이 줄었다. §9②3호 세율 법인은 §10 단서로 상한이 없으므로 "
                  "법인이라면 이 세액은 과소하다.")
    if isinstance(r.get("값 출처"), dict):
        r["값 출처"]["기본공제"] = "호출자 지정 0원 (종합부동산세법 §8①2호에 해당하는 경우의 값)"
    r["경고"] = 경고
    return r


# ───────────────────────────────────────────────────────────────── 취득세
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
    rate_special: str = "",
) -> dict:
    """취득세·지방교육세·농어촌특별세. 설명은 hosted_descriptions.DESCRIPTIONS["calc_acquisition_tax"]."""
    args = (acquisition_price, year, acquisition_type, heavy_type, exclusive_area, standard_rate,
            heavy_surcharge_rate, ordinance_adjustment_rate, local_education_tax_rate,
            rural_special_tax_rate, rate_special)
    if (acquisition_price > 0 and heavy_type and acquisition_type != "주택유상"
            and not (rate_special and rate_special != "없음")
            and heavy_type in tax_params.get_param("취득세.중과.중과기준세율배수", year)):
        # 값 오류(가액 0 이하, 모르는 heavy_type, rate_special 과 동시 지정)는 원래 함수가 그대로 ValueError 로 거부한다.
        return _거부(
            "heavy_type=%r 은 지방세법 §13의2① 각 호의 유형이고, 그 항은 주택을 유상거래로 취득하는 경우에만 적용된다. "
            "acquisition_type=%r 은 주택 유상취득이 아니라 그 세율(8%%·12%%)을 적용할 수 없다. 주택(공유지분·부속토지만 취득해도 "
            "주택)을 매매 등으로 취득하는 것이면 acquisition_type=\"주택유상\"으로, 주택이 아니면 heavy_type 을 비우고 계산한다. "
            "주택이 아닌 부동산을 법인이 대도시에서 취득해 붙는 중과(§13②)는 다른 조문이고 이 계산이 다루지 않는다 — "
            "법인 전용 취득세 계산을 쓴다. 조정대상지역 주택의 무상취득 중과(§13의2②)도 이 인자로 지정할 수 없다."
            % (heavy_type, acquisition_type),
            "지방세법 §13의2① 각 호 외의 부분 — \"주택(…)을 유상거래를 원인으로 취득하는 경우로서 …\"",
            입력={"acquisition_type": acquisition_type, "heavy_type": heavy_type})
    r = _ts.calc_acquisition_tax(*args)
    if heavy_surcharge_rate > 0 and not heavy_type and not r.get("세율의 특례"):
        경고 = _가산세율_경고(acquisition_price, year, acquisition_type, heavy_surcharge_rate,
                         r["세율 내역"]["표준세율"], local_education_tax_rate, rural_special_tax_rate, r["지방교육세"])
        if 경고:
            r["경고"] = 경고
    return r


def _가산세율_경고(가액, year, 유형, 가산, 표준, 교육세율_입력, 농특세율_입력, 교육세) -> list[str]:
    """가산세율(heavy_surcharge_rate)을 직접 넘긴 호출 — 부가세목이 가산 사유를 모르고 계산됐음을 알린다."""
    out = []
    중과기준 = tax_params.get_param("취득세.중과기준세율", year)
    if 교육세율_입력 < 0:
        # §13② 세율 = 표준세율×300% − 중과기준세율×200% → 가산분 = 2×(표준세율 − 중과기준세율)
        if 유형 != "주택유상" and abs(가산 - 2 * (표준 - 중과기준)) < 1e-9:
            정당 = int(가액 * round(max(표준 - 중과기준, 0.0) * 0.2 * 3, 6))
            out.append(
                "표준세율 %.1f%% + 가산 %.1f%% 는 대도시 법인 중과(지방세법 §13② — 표준세율의 300%%에서 중과기준세율의 200%%를 뺀 세율)와 "
                "같은 세율이다. 그 중과라면 지방교육세는 본문 산출액의 100분의 300(§151①1호가목)이어서 %s원인데, 이 결과의 지방교육세 "
                "%s원은 본문 세율로 계산한 값이다(이 계산은 가산 사유를 입력받지 않는다). 금액은 바꾸지 않았다. "
                "대도시 중과에 해당하는지(설립·설치·전입 5년, 중과 제외 업종)는 법인 전용 취득세 계산이 판정한다."
                % (표준 * 100, 가산 * 100, format(정당, ","), format(교육세, ",")))
        else:
            out.append(
                "heavy_surcharge_rate 를 직접 넘겼다. 지방교육세는 가산 사유를 모르는 채 본문 세율((표준세율−2%)×20%, 주택 유상은 "
                "세율×50%×20%)로 계산했다 — 지방세법 §13②·③·⑥·⑦에 해당하면 본문 산출액의 300%(§151①1호가목), §13의2에 해당하면 "
                "0.4%(나목)라서 다를 수 있다. 금액은 바꾸지 않았다."
                + ("" if 농특세율_입력 >= 0 else " 농어촌특별세도 가산을 반영하지 않고 표준세율 2% 치환분(농어촌특별세법 §5①6호)만 계산했다."))
    return out


# ───────────────────────────────────────────────────────────── 양도소득세
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
    land_permit_target: bool | None = None,
    land_permit_applied_date: str = "",
    land_permit_granted: bool = False,
    six_month_region: bool | None = None,
    location: str = "",
) -> dict:
    """양도세 비과세·중과·장특공·고가주택 안분. 설명은 hosted_descriptions.DESCRIPTIONS["judge_transfer_reliefs"]."""
    return _tj.judge_transfer_reliefs(
        is_one_household_one_home, holding_years, residing_years, sale_price,
        adjusted_at_sale, heavy_home_count, sale_date, meets_exemption_requirements,
        contract_date, deposit_received, contract_months_limit,
        land_permit_target=land_permit_target, land_permit_applied_date=land_permit_applied_date,
        land_permit_granted=land_permit_granted, six_month_region=six_month_region, location=location)


def count_heavy_homes(
    items: list[dict],
    heavy_tier: int = 3,
    sale_label: str = "",
    sale_date: str = "",
    adjusted_at_sale: bool | None = None,
    holding_years: float | None = None,
    contract_date: str = "",
    deposit_received: bool = False,
    land_permit_target: bool | None = None,
    land_permit_applied_date: str = "",
    land_permit_granted: bool = False,
    six_month_region: bool | None = None,
    location: str = "",
    household_facts: dict | None = None,
) -> dict:
    """양도세 중과 판정용 주택 수. 설명은 hosted_descriptions.DESCRIPTIONS["count_heavy_homes"]."""
    r = _tj.count_heavy_homes(items, heavy_tier)
    if not sale_label:
        return r        # 양도 주택을 지정하지 않으면 원래 도구와 결과가 같다
    대상 = [it for it in items if (it.get("라벨") or it.get("종류", "주택")) == sale_label]
    if len(대상) != 1:
        r["양도주택_중과판정"] = {
            "판정불가": True,
            "사유": "sale_label=%r 인 항목이 items 에 %d개다 — 양도하는 주택 하나에만 그 \"라벨\"을 붙인다" % (sale_label, len(대상))}
        return r
    from tax_nodes.yangdo_jungkwa_ho import 중과세율_판정
    h = dict(대상[0])
    # 한시 배제(영 §167의3①12호의2 등)는 양도 주택 항목의 사실로 읽는다 — 인자로 준 것만 덮어쓴다.
    for 키, 값, 준것 in (("보유연수", holding_years, holding_years is not None),
                      ("매매계약일", contract_date, bool(contract_date)),
                      ("계약금_수령", deposit_received, bool(deposit_received)),
                      ("토지거래허가_대상", land_permit_target, land_permit_target is not None),
                      ("토허_신청일", land_permit_applied_date, bool(land_permit_applied_date)),
                      ("토허_허가", land_permit_granted, bool(land_permit_granted)),
                      ("6개월_지역", six_month_region, six_month_region is not None),
                      ("소재지", location, bool(location))):
        if 준것:
            h[키] = 값
    사실 = {k: v for k, v in (household_facts or {}).items() if k not in ("양도주택", "보유목록", "양도일", "양도당시_조정대상지역")}
    p = 중과세율_판정(h, items, sale_date, adjusted_at_sale, **사실)
    r["양도주택_중과판정"] = p
    if p.get("가산_주택수") and p["가산_주택수"] != heavy_tier:
        r.setdefault("플래그", []).append(
            "양도주택_중과판정은 주택 목록에서 계열을 스스로 정한다(가산_주택수 %s) — heavy_tier=%s 로 센 '중과판정_주택수'와 계열이 다르다"
            % (p["가산_주택수"], heavy_tier))
    return r


#: 대체 도구 — 이름 → 고친 판 함수. 이름은 생성 서버 도구 이름과 같아야 한다.
OVERRIDES = {f.__name__: f for f in (calc_jongbu_tax, calc_acquisition_tax, judge_transfer_reliefs, count_heavy_homes)}


def replace_tools(source_tools: list, descriptions: dict | None = None) -> list:
    """생성 서버 도구 목록에서 OVERRIDES 에 있는 이름을 고친 판으로 바꾼 목록(순서 유지).

    제목·annotations 는 원래 도구 것을 물려받고, 설명은 descriptions[name](없으면 원래 도구의 설명)을 쓴다.
    목록에 없는 이름은 더하지 않는다 — 도구 수는 그대로다.
    """
    from mcp.server.fastmcp.tools import Tool
    out = []
    for t in source_tools:
        fn = OVERRIDES.get(t.name)
        out.append(t if fn is None else Tool.from_function(
            fn, name=t.name, title=t.title, annotations=t.annotations,
            description=(descriptions or {}).get(t.name) or t.description))
    return out
