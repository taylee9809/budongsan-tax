"""세금엔진 2층 — 법정 상수 조회기. 검증되지 않은 연도면 계산을 거부한다.

설계 의도(2026-08-30):
  server.py가 세율표를 하드코딩하지 않은 원래 이유는 "잘못된 값을 내장하면
  그럴듯하지만 틀린 계산이 나올 위험"이었다. 그 우려는 **스테일된 값이 조용히
  통과하는 것**이 문제이지 내장 자체가 문제가 아니다. 그래서 여기서는 값을
  내장하되(1층 data/tax_params.json), 조회 시 연도를 필수로 받고 그 연도가
  검증되지 않았으면 예외를 던진다. 스테일된 표는 틀린 답을 주는 대신 멈춘다.

  이 규약이 깨지는 유일한 경로는 호출자가 값을 직접 넘기는 것이다. calc_* 는
  명시 인자가 오면 그것을 우선하되, 어디서 온 값인지 결과에 표시한다.

사용:
    from tax_params import get_param, get_brackets, ParamNotVerified
    ratio = get_param("종부세.주택.공정시장가액비율", 2026)   # -> 0.6
    table = get_brackets("종부세.주택.세율표.2주택이하", 2026)
    get_param("종부세.주택.공정시장가액비율", 2031)           # -> ParamNotVerified
"""
import json
from pathlib import Path

PARAMS_PATH = Path(__file__).resolve().parent / "data" / "tax_params.json"


class TaxParamError(LookupError):
    """상수표 조회 실패의 공통 부모."""


class ParamNotFound(TaxParamError):
    """표에 그런 키가 없다 — 아직 이관되지 않은 세목일 수 있다."""


class ParamNotVerified(TaxParamError):
    """키는 있으나 그 연도가 검증되지 않았다. 계산을 진행하면 안 된다."""


_cache = None


def _load():
    global _cache
    if _cache is None:
        raw = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
        _cache = {row["키"]: row for row in raw.get("params", [])}
    return _cache


def reload_params():
    """표를 고친 뒤 프로세스 재시작 없이 다시 읽는다(테스트·감수용)."""
    global _cache
    _cache = None
    return _load()


def available_keys():
    return sorted(_load())


def get_row(key, year):
    """검증된 상수 행 전체(값 + 근거 + MST)를 돌려준다."""
    table = _load()
    row = table.get(key)
    if row is None:
        raise ParamNotFound(
            "상수표에 '%s' 키가 없습니다. 아직 이관되지 않은 항목이면 "
            "data/tax_params.json에 근거조문과 함께 추가하십시오. "
            "사용 가능한 키: %s" % (key, ", ".join(available_keys()))
        )
    years = row.get("검증연도") or []
    if year in years:
        return row
    # 미래 연도는 원리적으로 검증할 수 없다(그 해 법령이 아직 없다). 그렇다고 미래
    # 시나리오 계산을 막으면 상담이 성립하지 않으므로, '현행유지' 표시가 있는 행에
    # 한해 현행값을 쓰되 추정임을 결과에 드러낸다. 과거 미검증 연도는 그대로 거부한다
    # — 과거는 확인할 수 있는데 안 한 것이라 성격이 다르다.
    if years and year > max(years) and row.get("현행유지"):
        return dict(row, 추정=True)
    raise ParamNotVerified(
        "'%s'는 %s년 값이 검증되지 않았습니다(검증된 연도: %s). "
        "법제처 원문으로 %s년 시행 조문을 확인해 상수표에 행을 추가하기 전에는 "
        "계산하지 않습니다 — 근거: %s"
        % (key, year, years or "없음", year, row.get("근거", "미기재"))
    )


def get_param(key, year):
    return get_row(key, year)["값"]


def get_brackets(key, year):
    """누진세율표를 calc_* 가 받는 [{upto, rate, deduction}] 형태로 돌려준다."""
    value = get_param(key, year)
    if not isinstance(value, list):
        raise TaxParamError("'%s'는 세율표가 아닙니다(형식: %s)"
                            % (key, type(value).__name__))
    return [dict(b) for b in value]


def cite(key, year):
    """결과에 붙일 근거 문자열. 어떤 값이 어디서 왔는지 남기기 위한 것."""
    row = get_row(key, year)
    base = "%s (MST %s, 확인 %s)" % (row.get("근거", "?"), row.get("MST", "?"),
                                    row.get("확인일", "?"))
    if row.get("추정"):
        # 미래 연도에 현행값을 끌어다 쓴 경우 — 반드시 결과에 드러나야 한다.
        return base + " ⚠️%d년 값은 미검증, 현행법 기준 추정(검증연도 %s)" % (
            year, row.get("검증연도"))
    return base


def property_tax_base_cap(prev_year_price, current_price, year,
                          fair_market_ratio=None):
    """재산세 주택 과세표준상한액을 계산한다 (지방세법 §110③ + 영 §109의2).

    2026-08-30 사고의 직접 원인이 이 산식의 부재였다. 상수는 상한율 하나뿐이고
    나머지는 산식이므로 표가 아니라 코드로 둔다.

    영 §109의2①은 '직전 연도 과세표준 상당액'을 직전연도 시가표준액에
    **과세기준일 현재(=당해연도)** 공정시장가액비율을 곱한 값으로 정의한다.
    직전연도의 실제 과세표준이 아니므로 연쇄 재귀가 없다.

    Args:
        prev_year_price: 직전 연도 시가표준액(공시가격). 없으면 당해 값을 쓴다.
        current_price: 과세기준일 당시 시가표준액
        year: 과세연도 (상한율·공정비율 조회에 쓰인다)
        fair_market_ratio: 공정시장가액비율. 생략하면 일반(비1세대1주택) 값을 쓴다.

    Returns:
        과세표준상한액(원). 이 값과 제1항 과세표준 중 작은 쪽이 과세표준이 된다.
    """
    rate = get_param("재산세.주택.과세표준상한율", year)
    if fair_market_ratio is None:
        fair_market_ratio = get_param("재산세.주택.공정시장가액비율.일반", year)
    base_price = prev_year_price if prev_year_price else current_price
    prev_equiv = base_price * fair_market_ratio          # 직전연도 과세표준 상당액
    current_base = current_price * fair_market_ratio     # 당해 시가표준액 기준 과세표준
    return int(prev_equiv + current_base * rate)


def apply_brackets(base, brackets):
    """누진세율표를 적용한다. [{upto, rate, deduction}] 형식."""
    for b in brackets:
        if b["upto"] is None or base <= b["upto"]:
            return max(int(base * b["rate"]) - int(b.get("deduction", 0)), 0)
    last = brackets[-1]
    return max(int(base * last["rate"]) - int(last.get("deduction", 0)), 0)


def property_tax_standard_amount(taxable_base, year):
    """주택을 합산하여 재산세 표준세율로 계산한 재산세 상당액 (§4의3 분모)."""
    return apply_brackets(taxable_base,
                          get_brackets("재산세.주택.표준세율표", year))


def jongbu_property_tax_credit(jongbu_taxable_base, property_tax_charged,
                               property_tax_taxable_base, year):
    """종부세에서 공제할 재산세액 (종합부동산세법 시행령 §4의3①).

    ⚠️ 2026-08-30 사고 지점. 원문 산식은

        부과된 재산세액 합계
          × [(종부세 과세표준 × 재산세 공정시장가액비율) × 재산세 표준세율]
          ÷ [주택 합산 재산세 표준세율 계산액]

    인데, 분자 안쪽의 **재산세 공정시장가액비율(§109①2호)을 빠뜨리고** 종부세
    과세표준에 재산세율을 바로 곱하면 공제액이 크게 과대계산된다. 이 조문은
    코퍼스에 노드가 있었는데도 사람이 기억으로 산식을 재현하다 틀렸다 —
    조문 커버리지(3층)로는 못 막는 유형이라 산식을 코드로 내린다.

    Args:
        jongbu_taxable_base: 법 §8① 주택분 종부세 과세표준
        property_tax_charged: 지방세법 §112①1호에 따라 부과된 주택분 재산세액 합계
        property_tax_taxable_base: 재산세 과세표준(§110③ 상한 적용 후)
        year: 과세연도
    """
    fmr = get_param("재산세.주택.공정시장가액비율.일반", year)
    numerator = apply_brackets(int(jongbu_taxable_base * fmr),
                               get_brackets("재산세.주택.표준세율표", year))
    denominator = property_tax_standard_amount(property_tax_taxable_base, year)
    if denominator <= 0:
        return 0
    return int(property_tax_charged * numerator / denominator)


def jongbu_owner_credit_rate(year, one_home=False, age=0, holding_years=0):
    """1세대 1주택자 세액공제율 (종합부동산세법 §9⑤⑥⑧). 연령률 + 보유률, 한도 적용.

    §9⑤ 후단의 합계 한도(현행 80%)까지만 중복 적용된다.
    """
    if not one_home:
        return 0.0
    rate = 0.0
    if age:
        for band in get_param("종부세.세액공제.연령", year):
            if age >= band["from_age"]:
                rate = band["rate"]
    hold = 0.0
    if holding_years:
        for band in get_param("종부세.세액공제.보유", year):
            if holding_years >= band["from_years"]:
                hold = band["rate"]
    return min(rate + hold, get_param("종부세.세액공제.합계한도", year))


def jongbu_prev_year_total_tax(prev_year_price, basic_deduction, year,
                               jongbu_brackets_key="종부세.주택.세율표.2주택이하",
                               one_home=False, age=0, holding_years=0,
                               basic_deduction_prev=None):
    """직전 연도 총세액상당액 (종합부동산세법 시행령 §5②).

    §5②1호는 재산세액상당액을 **지방세법 §110③(과세표준상한제)·§111③(조례 가감)·
    §112①2호(도시지역분)를 제외하고** 직전 연도 법령으로 산출하라고 한다. 즉
    전년도분에는 과세표준상한을 적용하지 않는다 — 당해연도(§5①1호)가 상한 적용 후
    세액인 것과 반대라서 혼동하기 쉽다.

    §5②2호는 종합부동산세액상당액을 "직전 연도의 법(법 제10조는 제외한다)을 적용하여
    산출한 금액"으로 정의하고, 괄호에서 **1세대 1주택자는 직전 연도 과세기준일 현재
    연령 및 주택 보유기간을 적용**하라고 한다. 즉 §9⑤~⑨의 고령자·장기보유 세액공제를
    직전 연도 기준으로 적용한 뒤의 금액이다.

    ⚠️ 2026-09-24 수정 — 종전에는 이 세액공제를 아예 적용하지 않아 직전 연도
    총세액상당액이 과대했고, 그 결과 세부담상한(법 §10)이 느슨해져 당해 종부세가
    과대 산출됐다. 공제 제도가 보호하려던 1세대1주택 고령·장기보유자가 손해를 보는
    방향이었다. 근거: 시행령 §5②2호 괄호 + 종합부동산세법 시행규칙 별지 제35호서식
    부표(직전연도 종합부동산세상당액 계산서) — ⑫ 종합부동산세상당액 = 산출세액 − ⑩
    공제할 재산세액 − ⑪ 1세대 1주택자 세액공제액, 작성방법 8은 "과세기준일 현재"
    기준으로 ⑪을 산정하라고 한다(직전연도 계산서이므로 직전 연도 과세기준일).

    ⚠️ 미지원: 서식 작성방법 8 가목의 '1주택의 공시가격 안분비율'(법 §8④ 간주
    1세대1주택자의 부속토지·대체취득·상속·지방저가 주택분 안분)은 반영하지 않는다.
    해당 물건이면 직전 연도 공제가 과대 → 직전 총세액 과소 → 상한이 과도하게 조인다.

    Args:
        one_home: 1세대 1주택자 여부
        age: **당해 연도** 과세기준일 현재 연령. 직전 연도분은 여기서 1을 뺀다.
        holding_years: **당해 연도** 과세기준일 현재 보유연수. 직전 연도분은 1을 뺀다.
        basic_deduction_prev: 직전 연도 §8① 공제금액. §5②2호가 "직전 연도의 법"을
            적용하라고 하므로 공제금액도 직전 연도 값이어야 한다. None이면 당해 값을
            그대로 쓴다(2025·2026은 12억/9억으로 같아 현재는 차이가 없지만, 금액이
            한 번 바뀌면 조용히 틀리는 자리다).

    직전 연도 상수로 조회하므로, 그 연도가 상수표에 없으면 ParamNotVerified가 난다.
    이것이 의도된 동작이다 — 전년도 값을 당해 값으로 대충 갈음하면 세부담상한
    적용 여부가 뒤집힐 수 있다.
    """
    prev = year - 1
    fmr_p = get_param("재산세.주택.공정시장가액비율.일반", prev)
    prop_base = int(prev_year_price * fmr_p)              # §110③ 미적용
    prop_tax = apply_brackets(prop_base,
                              get_brackets("재산세.주택.표준세율표", prev))

    fmr_j = get_param("종부세.주택.공정시장가액비율", prev)
    공제_prev = basic_deduction if basic_deduction_prev is None else basic_deduction_prev
    jb = max(int((prev_year_price - 공제_prev) * fmr_j), 0)
    jongbu = apply_brackets(jb, get_brackets(jongbu_brackets_key, prev))
    credit = jongbu_property_tax_credit(jb, prop_tax, prop_base, prev)
    after_credit = max(jongbu - credit, 0)

    # §5②2호 괄호 — 직전 연도 과세기준일 현재 연령·보유기간
    owner_rate = jongbu_owner_credit_rate(
        prev, one_home, max(age - 1, 0) if age else 0,
        max(holding_years - 1, 0) if holding_years else 0)
    jongbu_equiv = after_credit - int(after_credit * owner_rate)

    return {"재산세액상당액": prop_tax,
            "종합부동산세액상당액": jongbu_equiv,
            "직전연도 세액공제율": owner_rate,
            "총세액상당액": prop_tax + jongbu_equiv}


def acquisition_housing_rate(price, year):
    """주택 유상거래 취득세 표준세율 (지방세법 §11①8호).

    6억 이하 1% / 6억 초과 9억 이하는 계산식 / 9억 초과 3%.
    계산식: (취득당시가액 × 2 ÷ 3억원 − 3) × 1/100, 소수점 다섯째자리에서
    반올림하여 넷째자리까지. 반올림 자리수까지 조문에 명시돼 있어 그대로 따른다.
    """
    band = get_param("취득세.주택유상.구간", year)
    if price <= band["하한가액"]:
        return band["하한세율"]
    if price > band["상한가액"]:
        return band["상한세율"]
    return round((price * 2 / 300_000_000 - 3) / 100, 4)


def acquisition_local_education_rate(year, standard_rate, is_housing_sale=False,
                                     heavy_13_2=False, heavy_13_multiplier=1.0):
    """취득세분 지방교육세의 실효세율 (지방세법 §151①1호).

    ⚠️ '취득세액 × 비율'이 아니라 **세율을 갈아끼워 다시 산출**하는 구조다.
    그래서 §13의2 중과로 취득세율이 8·12%로 뛰어도 지방교육세는 0.4%로 고정된다.
    이 사실은 종전에 독스트링 산문으로만 적혀 있었고, 사람이 매번 재현해야 했다.

    Args:
        standard_rate: 적용된 §11①(또는 §12) 표준세율
        is_housing_sale: §11①8호 주택 유상거래인지 (그러면 세율×50%×20%)
        heavy_13_2: §13의2(다주택·법인 유상 중과) 대상인지
        heavy_13_multiplier: §13②③⑥⑦(대도시 법인 등) 해당 시 3.0
    """
    base = get_param("취득세.중과기준세율", year)
    if heavy_13_2:
        # 나목 — §11①7호나목 세율에서 중과기준세율을 뺀 세율로 산출
        일반유상 = get_param("취득세.표준세율", year)["유상.농지외"]
        return (일반유상 - base) * 0.2
    if is_housing_sale:
        return standard_rate * 0.5 * 0.2
    return max(standard_rate - base, 0) * 0.2 * heavy_13_multiplier


def acquisition_rural_special_rate(year, heavy_multiplier=0.0, exempt=False):
    """취득세분 농어촌특별세의 실효세율 (농어촌특별세법 §5①6호).

    지방세법 §11·§12의 **표준세율을 100분의 2로 치환하여** 산출한 취득세액의 10%.
    중과 구조는 유지되므로 배수만큼 더한다 — 일반 0.2% / 8% 중과 0.6% / 12% 중과 1.0%.

    Args:
        heavy_multiplier: §13의2 중과기준세율 배수(2.0 또는 4.0). 중과 아니면 0.
        exempt: 전용 85㎡ 이하 서민주택 등 비과세 대상(농특세법 §4 11호)이면 True
    """
    if exempt:
        return 0.0
    p = get_param("농특세.취득세분.세율", year)
    치환 = p["표준세율치환"]
    return (치환 + 치환 * heavy_multiplier) * p["세율"]
