"""시나리오 커버리지 맵: 회귀 시나리오 · 도구 실재 · 근거 · 엔진 상수 일치 · 호스팅 등록."""
import json
import pathlib
import re

import pytest

import entity_tax
import tax_http
import tax_server
from scenario_coverage import ASSETS, CONTEXTS, ITEMS, STAGES, TAXPAYERS, get_tax_scenario_checklist

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGRESSION = [json.loads(line) for line in
              (ROOT / "data/coverage/scenario_regression.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
IDS = {i["id"] for i in ITEMS}


def _ids(result):
    return [i["id"] for i in result["검토_항목"]]


@pytest.mark.parametrize("case", REGRESSION, ids=[c["id"] for c in REGRESSION])
def test_regression_scenario(case):
    ids = set(_ids(get_tax_scenario_checklist(**case["입력"])))
    missing = set(case["필수"]) - ids
    wrong = set(case["제외"]) & ids
    assert not missing, f"{case['id']} 빠진 항목 {sorted(missing)} — {case['질문']}"
    assert not wrong, f"{case['id']} 상황에 맞지 않는 항목 {sorted(wrong)} — {case['질문']}"


def test_regression_set_is_well_formed():
    assert len(REGRESSION) >= 20
    assert len({c["id"] for c in REGRESSION}) == len(REGRESSION)
    for c in REGRESSION:
        assert (set(c["필수"]) | set(c["제외"])) <= IDS, c["id"]
        assert not set(c["필수"]) & set(c["제외"]), c["id"]
    # 맵의 모든 항목이 최소 한 시나리오에서 필수로 검증된다
    covered = set().union(*(set(c["필수"]) for c in REGRESSION))
    assert IDS <= covered, f"회귀 시나리오가 없는 항목: {sorted(IDS - covered)}"


def test_items_are_well_formed():
    assert len(IDS) == len(ITEMS)
    domains = {"taxpayer": TAXPAYERS, "assets": ASSETS, "stages": STAGES, "context": CONTEXTS}
    for item in ITEMS:
        assert re.fullmatch(r"[A-Z]+(-[A-Z0-9]+)+", item["id"])
        assert item["범위"] in {"엔진", "부분", "범위밖"}, item["id"]
        assert item["세목"] and item["쟁점"] and item["요지"], item["id"]
        assert re.search(r"§|별표", item["근거"]), f"{item['id']} 근거에 조문이 없다"
        assert set(item["조건"]) <= set(domains), item["id"]
        for key, allowed in domains.items():
            if item["조건"].get(key) is not None:
                assert set(item["조건"][key]) <= set(allowed), (item["id"], key)
        # 범위와 도구가 맞물린다: 범위밖이면 도구가 없고, 엔진·부분이면 도구가 있다
        assert (item["범위"] == "범위밖") == (not item["도구"]), item["id"]


def test_every_named_tool_exists_on_hosted_server():
    names = {t.name for t in tax_http.make_server()._tool_manager.list_tools()}
    for item in ITEMS:
        assert set(item["도구"]) <= names, (item["id"], set(item["도구"]) - names)


def test_corporate_rates_match_engine_constants():
    """맵의 법인세율·추가과세율 문구가 entity_tax 상수와 어긋나면 실패한다(한쪽만 개정되는 것 방지)."""
    by_id = {i["id"]: i for i in ITEMS}
    text = by_id["SELL-CORP-INCOME"]["요지"]
    rates = [f"{int(round(r * 100))}%" for _, r, _ in entity_tax.CORP_BRACKETS]
    assert all(r in text for r in rates), (rates, text)
    sur = by_id["SELL-CORP-SURTAX"]["요지"]
    assert f"{int(entity_tax.SURCHARGE_HOUSE * 100)}%" in sur
    assert f"비사업용 토지 {int(entity_tax.SURCHARGE_NONBIZ_LAND * 100)}%" in sur


def test_low_price_item_matches_engine_thresholds():
    import tax_judgment as tj
    text = {i["id"]: i for i in ITEMS}["ACQ-LOWPRICE"]["요지"]
    assert f"수도권 {tj.LOW_PRICE_HOME_LIMIT_CAPITAL // 100_000_000}억" in text
    assert f"비수도권 {tj.LOW_PRICE_HOME_LIMIT_NONCAPITAL // 100_000_000}억" in text


def test_auction_corporation_case_flags_out_of_scope_items():
    r = get_tax_scenario_checklist("법인", ["주택"], ["취득", "보유", "양도"], ["경매·공매", "단기매매"])
    assert {"SELL-CORP-SURTAX", "SELL-CORP-INCOME", "HOLD-JUMIN"} <= set(r["범위밖_항목"])
    assert {"HOLD-JONGBU-CORP", "ACQ-LOWPRICE", "SELL-CORP-SURTAX"} <= set(r["함정_항목"])
    # 단계 순서: 취득 → 보유 → 양도
    order = [i["id"] for i in r["검토_항목"]]
    assert order.index("ACQ-CORP-HOME") < order.index("HOLD-JONGBU-CORP") < order.index("SELL-CORP-SURTAX")


def test_string_inputs_and_defaults():
    r = get_tax_scenario_checklist("개인", "주택, 분양권·입주권", "취득/양도")
    assert r["조건"]["assets"] == ["주택", "분양권·입주권"]
    assert r["조건"]["stages"] == ["취득", "양도"]
    assert get_tax_scenario_checklist()["조건"]["stages"] == ["취득", "보유", "양도"]


@pytest.mark.parametrize("kwargs", [
    {"taxpayer": "조합"}, {"assets": ["아파트"]}, {"stages": ["매도"]}, {"context": ["급매"]},
])
def test_invalid_inputs_rejected(kwargs):
    with pytest.raises(ValueError):
        get_tax_scenario_checklist(**kwargs)


def test_registered_on_hosted_server_only():
    server = tax_http.make_server()
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    tool = tools["get_tax_scenario_checklist"]
    assert tool.annotations.readOnlyHint and not tool.annotations.openWorldHint
    assert "get_tax_scenario_checklist" in server.instructions
    assert "범위밖" in server.instructions
    stdio = {t.name for t in tax_server.mcp._tool_manager.list_tools()}
    assert "get_tax_scenario_checklist" not in stdio  # 생성 파일은 건드리지 않는다
