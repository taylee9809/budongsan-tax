"""대체 도구(tax_overrides) — 생성 도구와의 호환, 고친 동작, 호스팅 서버·stdio 진입점 등록."""
import asyncio
import inspect
import itertools

import pytest

import tax_http
import tax_judgment
import tax_overrides
import tax_server

SOURCE = {t.name: t for t in tax_server.mcp._tool_manager.list_tools()}
_EMPTY = inspect.Parameter.empty


FIXED = {"calc_jongbu_tax", "calc_acquisition_tax", "judge_transfer_reliefs", "count_heavy_homes"}


def test_overrides_name_generated_tools():
    assert set(tax_overrides.OVERRIDES) == FIXED | set(tax_overrides.PASSTHROUGH) and len(tax_overrides.OVERRIDES) == 16
    assert set(tax_overrides.OVERRIDES) <= set(SOURCE)
    assert all(fn.__name__ == name for name, fn in tax_overrides.OVERRIDES.items())


@pytest.mark.parametrize("name", sorted(tax_overrides.OVERRIDES))
def test_override_parameters_are_a_superset(name):
    """생성기가 인자를 바꾸면 여기서 깨진다 — 기존 인자는 이름·순서·기본값이 같고, 더한 인자는 모두 선택이다."""
    old = inspect.signature(SOURCE[name].fn).parameters
    new = inspect.signature(tax_overrides.OVERRIDES[name]).parameters
    assert list(new)[:len(old)] == list(old), "기존 인자의 이름·순서(위치 인자 호환)"
    changed = tax_overrides.CHANGED_DEFAULTS.get(name, {})
    for p, spec in old.items():
        if p in changed:
            assert new[p].default == changed[p] and spec.default is not _EMPTY
        else:
            assert new[p].default == spec.default, p
    for p in list(new)[len(old):]:
        assert new[p].default is not _EMPTY, "더한 인자 %s 는 기본값이 있어야 한다" % p


def test_passthrough_overrides_cover_the_judgment_signature():
    """판정기를 그대로 부르는 대체 도구는 판정기 인자를 빠짐없이 받는다 — 판정기에 인자가 늘면 따라간다."""
    judged = inspect.signature(tax_judgment.judge_transfer_reliefs).parameters
    assert set(judged) <= set(inspect.signature(tax_overrides.judge_transfer_reliefs).parameters)
    assert list(inspect.signature(tax_judgment.count_heavy_homes).parameters) == ["items", "heavy_tier"]
    for name in tax_overrides.PASSTHROUGH:
        assert (list(inspect.signature(tax_overrides.OVERRIDES[name]).parameters)
                == list(inspect.signature(getattr(tax_judgment, name)).parameters)), name


def test_no_generated_wrapper_drops_judgment_arguments_unnoticed():
    """생성 서버 래퍼가 판정기 인자를 떨어뜨리면 그 도구는 대체 목록에 있어야 한다(findings 120)."""
    import re
    dropping = set()
    for name, tool in SOURCE.items():
        for called in set(re.findall(r"_tj\.([A-Za-z_0-9]+)\(", inspect.getsource(tool.fn))):
            judged = inspect.signature(getattr(tax_judgment, called)).parameters
            mine = inspect.signature(tool.fn).parameters
            if any(p not in mine and spec.kind is spec.POSITIONAL_OR_KEYWORD for p, spec in judged.items()):
                dropping.add(name)
    assert dropping <= set(tax_overrides.OVERRIDES), dropping - set(tax_overrides.OVERRIDES)
    assert set(tax_overrides.PASSTHROUGH) <= dropping          # 생성기가 따라잡으면 목록에서 뺀다


def test_passthrough_descriptions_document_the_added_arguments():
    from hosted_descriptions import ADDED_ARGUMENTS
    assert set(ADDED_ARGUMENTS) == set(tax_overrides.PASSTHROUGH)
    tools = {t.name: t for t in tax_http.make_server()._tool_manager.list_tools()}
    for name in tax_overrides.PASSTHROUGH:
        old = inspect.signature(SOURCE[name].fn).parameters
        added = [p for p in inspect.signature(tax_overrides.OVERRIDES[name]).parameters if p not in old]
        assert added and all(p in ADDED_ARGUMENTS[name] for p in added), name
        assert ADDED_ARGUMENTS[name] in tools[name].description
        assert set(added) <= set(tools[name].parameters["properties"])
        assert not set(added) & set(tools[name].parameters.get("required", []))


def test_passthrough_matches_the_wrapper_when_new_arguments_are_omitted():
    cases = {
        "judge_family_loan": dict(loan_amount=200_000_000, agreed_interest_rate=0.02),
        "judge_temporary_two_homes": dict(prev_acquired="2020-03-01", new_acquired="2024-05-01", prev_sale_date="2026-03-01"),
        "judge_inherited_house_priority": dict(houses=[
            {"라벨": "가", "피상속인_소유기간_년": 20, "피상속인_거주기간_년": 5, "상속개시당시_거주": False, "기준시가": 300_000_000},
            {"라벨": "나", "피상속인_소유기간_년": 10, "피상속인_거주기간_년": 10, "상속개시당시_거주": True, "기준시가": 500_000_000}]),
        "judge_co_inherited_owner": dict(shares=[{"상속인": "갑", "지분율": 0.5, "해당주택_거주": True, "나이": 50},
                                                 {"상속인": "을", "지분율": 0.5, "해당주택_거주": False, "나이": 55}]),
    }
    for name, kw in cases.items():
        assert tax_overrides.OVERRIDES[name](**kw) == getattr(tax_server, name)(**kw), name
        assert tax_overrides.OVERRIDES[name](*kw.values()) == getattr(tax_server, name)(*kw.values()), name   # 위치 인자


def test_passthrough_new_arguments_change_the_verdict():
    two = dict(prev_acquired="2020-03-01", new_acquired="2024-05-01", prev_sale_date="2026-03-01")
    base = tax_overrides.judge_temporary_two_homes(**two)
    more = tax_overrides.judge_temporary_two_homes(**two, other_homes_at_acquisition=1)
    assert more == tax_judgment.judge_temporary_two_homes(**two, other_homes_at_acquisition=1) and more != base
    loan = tax_overrides.judge_family_loan(200_000_000, 0.02, loan_date="2014-01-01")
    assert loan == tax_judgment.judge_family_loan(200_000_000, 0.02, loan_date="2014-01-01")
    assert loan != tax_overrides.judge_family_loan(200_000_000, 0.02)
    houses = [{"라벨": "가", "피상속인_소유기간_년": 20, "피상속인_거주기간_년": 5, "상속개시당시_거주": False, "기준시가": 300_000_000},
              {"라벨": "나", "피상속인_소유기간_년": 10, "피상속인_거주기간_년": 10, "상속개시당시_거주": True, "기준시가": 500_000_000}]
    assert (tax_overrides.judge_inherited_house_priority(houses, demolished_label="가")
            == tax_judgment.judge_inherited_house_priority(houses, demolished_label="가"))


def test_hosted_server_serves_the_overrides():
    tools = {t.name: t for t in tax_http.make_server()._tool_manager.list_tools()}
    assert len(tools) == 46
    for name, fn in tax_overrides.OVERRIDES.items():
        assert tools[name].fn is fn
        assert tools[name].title == SOURCE[name].title and tools[name].annotations == SOURCE[name].annotations
        assert tools[name].description.strip() and "tax_overrides" not in tools[name].description
    assert [n for n in tools if n in SOURCE] == [n for n in SOURCE if n in tools]      # 순서도 그대로
    props = tools["calc_jongbu_tax"].parameters["properties"]
    assert props["basic_deduction"]["default"] is None and "is_corporation" in props
    assert tax_server.mcp._tool_manager.get_tool("calc_jongbu_tax").fn is tax_server.calc_jongbu_tax   # 생성 서버는 그대로


# ───────────────────────────────────────────────────────────── 종합부동산세
def test_jongbu_unspecified_and_positive_deduction_match_the_generated_tool():
    for price, prev, one, n, age, hold, ded in itertools.product(
            (500_000_000, 1_300_000_000, 3_000_000_000), (0, 1_000_000_000, 2_500_000_000), (False, True),
            (1, 3), (0, 66), (0, 12), (None, 600_000_000)):
        kw = dict(prev_year_official_price=prev, one_home=one, home_count=n, age=age, holding_years=hold)
        assert (tax_overrides.calc_jongbu_tax(price, 2026, basic_deduction=ded, **kw)
                == tax_server.calc_jongbu_tax(price, 2026, basic_deduction=ded or 0, **kw))


def test_jongbu_zero_deduction_is_zero():
    flat = [{"upto": None, "rate": 0.027, "deduction": 0}]
    r = tax_overrides.calc_jongbu_tax(600_000_000, 2026, basic_deduction=0, tax_brackets=flat)
    assert (r["공제금액"], r["과세표준"], r["종합부동산세"]) == (0, 360_000_000, 9_720_000)
    assert len(r["경고"]) == 1 and "§8①2호" in r["경고"][0]
    # 생성 도구는 같은 호출에 9억을 공제한다(finding 95) — 기록
    assert tax_server.calc_jongbu_tax(600_000_000, 2026, basic_deduction=0, tax_brackets=flat)["과세표준"] == 0
    # 공제 0원 + 직전 연도 가격 → 상한이 걸리면 그 사실을 경고한다(금액은 원래 함수의 계산)
    r = tax_overrides.calc_jongbu_tax(2_000_000_000, 2026, basic_deduction=0, prev_year_official_price=1_000_000_000)
    assert r["세부담상한 적용여부"] and any("§10 단서" in w for w in r["경고"]) and any("§9①" in w for w in r["경고"])
    assert tax_params_untouched()


def tax_params_untouched():
    import tax_params
    return tax_params.get_param("종부세.주택.기본공제", 2026)["일반"] == 900_000_000


def test_jongbu_refuses_corporations_and_contradictions():
    r = tax_overrides.calc_jongbu_tax(600_000_000, 2026, is_corporation=True)
    assert r["계산불가"] is True and "§9②" in r["근거"] and not {"과세표준", "종합부동산세", "총납부세액"} & set(r)
    r = tax_overrides.calc_jongbu_tax(1_500_000_000, 2026, one_home=True, basic_deduction=0)
    assert r["계산불가"] is True and "종합부동산세" not in r
    with pytest.raises(ValueError):
        tax_overrides.calc_jongbu_tax(600_000_000, 2026, basic_deduction=-1)
    with pytest.raises(ValueError):
        tax_overrides.calc_jongbu_tax(0, 2026)


# ───────────────────────────────────────────────────────────────── 취득세
def _acq(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ValueError:
        return "ValueError"


def test_acquisition_differs_only_by_refusing_heavy_type_on_non_housing():
    kinds = ("주택유상", "유상.농지외", "유상.농지", "무상", "원시취득", "공유물분할", "상속.농지외")
    refused = 0
    for price, kind, heavy, area, special in itertools.product(
            (300_000_000, 750_000_000, 2_000_000_000), kinds,
            ("", "법인", "2주택조정_또는_3주택비조정", "3주택이상조정_또는_4주택이상비조정"), (0, 60, 100),
            ("", "재산분할", "없음")):
        old = _acq(tax_server.calc_acquisition_tax, price, 2026, kind, heavy, area, rate_special=special)
        new = _acq(tax_overrides.calc_acquisition_tax, price, 2026, kind, heavy, area, rate_special=special)
        if old != new:
            assert heavy and kind != "주택유상" and new["계산불가"] is True and "취득세" not in new, (kind, heavy, special)
            refused += 1
    assert refused
    r = tax_overrides.calc_acquisition_tax(1_000_000_000, 2026, "유상.농지외", heavy_type="법인")
    assert r["계산불가"] is True and "§13의2①" in r["근거"]
    with pytest.raises(ValueError):                      # 모르는 유형은 원래 함수가 거부한다
        tax_overrides.calc_acquisition_tax(1_000_000_000, 2026, "유상.농지외", heavy_type="없는유형")


def test_acquisition_warns_on_hand_built_surcharge_without_changing_amounts():
    args = (1_000_000_000, 2026, "유상.농지외")
    old = tax_server.calc_acquisition_tax(*args, heavy_surcharge_rate=0.04)
    new = tax_overrides.calc_acquisition_tax(*args, heavy_surcharge_rate=0.04)
    warn = new.pop("경고")
    assert new == old and new["지방교육세"] == 4_000_000
    assert len(warn) == 1 and "§13②" in warn[0] and "12,000,000원" in warn[0] and "§151①1호가목" in warn[0]
    # §13② 세율 모양이 아니면 일반 경고
    warn = tax_overrides.calc_acquisition_tax(1_000_000_000, 2026, "주택유상", heavy_surcharge_rate=0.08)["경고"]
    assert len(warn) == 1 and "§13의2" in warn[0] and "농어촌특별세" in warn[0]
    # 지방교육세율을 직접 주었거나 가산세율을 주지 않은 호출에는 경고가 없다
    assert "경고" not in tax_overrides.calc_acquisition_tax(*args, heavy_surcharge_rate=0.04, local_education_tax_rate=0.012)
    assert "경고" not in tax_overrides.calc_acquisition_tax(*args)
    assert "경고" not in tax_overrides.calc_acquisition_tax(1_000_000_000, 2026, "주택유상", heavy_type="법인")


# ───────────────────────────────────────────────────────────── 양도소득세
def test_transfer_reliefs_passes_land_permit_facts():
    base = dict(is_one_household_one_home=False, holding_years=5, residing_years=0, sale_price=1_000_000_000,
                adjusted_at_sale=True, heavy_home_count=3, sale_date="2026-08-20", contract_date="2026-05-01",
                deposit_received=True)
    assert tax_overrides.judge_transfer_reliefs(**base) == tax_server.judge_transfer_reliefs(**base)
    assert tax_overrides.judge_transfer_reliefs(**base)["중과여부"] is False            # 허가 대상 여부를 모르면 종전 판정
    assert tax_overrides.judge_transfer_reliefs(**base, land_permit_target=True)["중과여부"] is True
    r = tax_overrides.judge_transfer_reliefs(**base, land_permit_target=True, land_permit_applied_date="2026-04-20",
                                             land_permit_granted=True)
    assert r["중과여부"] is False and r == tax_judgment.judge_transfer_reliefs(
        **base, land_permit_target=True, land_permit_applied_date="2026-04-20", land_permit_granted=True)
    late = dict(base, sale_date="2026-10-20", contract_date="2026-05-08")               # 4개월(09-08) 지나고 6개월 안
    assert tax_overrides.judge_transfer_reliefs(**late, land_permit_target=False)["중과여부"] is True
    assert tax_overrides.judge_transfer_reliefs(**late, land_permit_target=False, six_month_region=True)["중과여부"] is False


A = {"라벨": "A", "종류": "주택", "기준시가": 900_000_000}
B = {"라벨": "B", "종류": "주택", "기준시가": 80_000_000}
C = {"라벨": "C", "종류": "주택", "기준시가": 500_000_000}


def test_count_heavy_homes_without_sale_label_is_the_judgment_result():
    for items, tier in (([A, B], 2), ([A, B], 3), ([A, B, C], 3), ([], 3)):
        assert tax_overrides.count_heavy_homes(items, tier) == tax_judgment.count_heavy_homes(items, tier)


def test_count_heavy_homes_judges_the_sale_home_from_the_list():
    r = tax_overrides.count_heavy_homes([A, B], 2, sale_label="B", sale_date="2026-10-01", adjusted_at_sale=True)
    p = r["양도주택_중과판정"]
    assert r["중과판정_주택수"] == 2 and p["중과대상"] is False and p["중과적용"] is False
    assert p["적용호"] == "법 §104⑦1호" and any("9호" in w for w in p["제외사유"])
    p = tax_overrides.count_heavy_homes([A, B], 2, sale_label="A", sale_date="2026-10-01",
                                        adjusted_at_sale=True)["양도주택_중과판정"]
    assert p["중과적용"] is True and p["중과가산세율"] == 0.2 and p["장기보유특별공제_배제"] is True
    # 조정대상지역 여부를 주지 않으면 대상 주택 여부까지만
    p = tax_overrides.count_heavy_homes([A, B], 2, sale_label="A", sale_date="2026-10-01")["양도주택_중과판정"]
    assert p["중과대상"] is True and p["중과적용"] is None and p["중과가산세율"] is None
    # 한시 배제 — 다목(허가 대상 아님) / 나목(허가 대상: 신청·허가가 있어야)
    kw = dict(sale_label="A", sale_date="2026-08-20", adjusted_at_sale=True, holding_years=5,
              contract_date="2026-05-01", deposit_received=True)
    f = lambda **more: tax_overrides.count_heavy_homes([A, B, C], 3, **kw, **more)["양도주택_중과판정"]
    assert f(land_permit_target=False)["중과적용"] is False
    assert f(land_permit_target=True)["중과적용"] is True and f(land_permit_target=True)["중과가산세율"] == 0.3
    assert f(land_permit_target=True, land_permit_applied_date="2026-04-20", land_permit_granted=True)["중과적용"] is False
    assert A == {"라벨": "A", "종류": "주택", "기준시가": 900_000_000}                    # 입력 목록을 고치지 않는다
    # 계열이 heavy_tier 와 다르면 플래그, 라벨이 없으면 판정하지 않는다
    r = tax_overrides.count_heavy_homes([A, B, C], 2, sale_label="A", sale_date="2026-10-01")
    assert any("계열이 다르다" in x for x in r["플래그"])
    assert tax_overrides.count_heavy_homes([A, B], 2, sale_label="Z")["양도주택_중과판정"]["판정불가"] is True


# ───────────────────────────────────────────────────────────── stdio 진입점
def test_full_stdio_entry_uses_the_hosted_assembly(monkeypatch):
    import tax_full
    seen = {}

    def fake_run(self, transport="stdio", **kw):
        seen["transport"] = transport
        seen["tools"] = {t.name: t.fn for t in self._tool_manager.list_tools()}

    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", fake_run)
    tax_full.main()
    assert seen["transport"] == "stdio" and len(seen["tools"]) == 46
    assert all(seen["tools"][n] is fn for n, fn in tax_overrides.OVERRIDES.items())
    assert "get_tax_scope" in seen["tools"]


def test_override_call_through_the_server_returns_the_refusal():
    server = tax_http.make_server()
    out = asyncio.run(server.call_tool("calc_acquisition_tax", {
        "acquisition_price": 1_000_000_000, "year": 2026, "acquisition_type": "유상.농지외", "heavy_type": "법인"}))
    structured = out[1] if isinstance(out, tuple) else out
    assert "계산불가" in str(structured)
