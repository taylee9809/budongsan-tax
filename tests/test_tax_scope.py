"""범위 안내(get_tax_scope) — 표가 실제 등록 도구·커버리지 감사 범위와 어긋나지 않는지.

도구가 늘거나 이름이 바뀌면 여기서 깨진다. 그때 tax_scope.TOOL_TABLE 을 고친다.
"""
import importlib
import inspect
import re
import sys
from pathlib import Path

import pytest

import tax_http
import tax_scope
import tax_server
from tax_scope import CORPORATE_FLOW, NOT_COVERED, TOOL_TABLE, TOPICS, get_tax_scope

ROOT = Path(__file__).resolve().parents[1]
#: 호스팅 서버에만 붙는 도구 모듈 — 각 모듈의 TOOLS 가 도구 이름이다.
HOSTED_MODULES = ("acquisition_checklist", "building_property_tax", "corporate_tax", "tax_scope")


def _registered() -> set:
    names = {t.name for t in tax_server.mcp._tool_manager.list_tools()}
    names |= {t.name for t in tax_http.make_server()._tool_manager.list_tools()}
    return names


def _hosted_module_tools() -> set:
    out = set()
    for m in HOSTED_MODULES:
        mod = importlib.import_module(m)
        tools = getattr(mod, "TOOLS", None) or tuple(
            n for n, f in vars(mod).items() if inspect.isfunction(f) and n.startswith("get_") and f.__module__ == m)
        for n in tools:
            assert callable(getattr(mod, n)), (m, n)
            out.add(n)
    return out


def test_table_lists_exactly_the_existing_tools():
    """표의 도구 = 등록된 도구(tax_server.mcp, tax_http.make_server()) ∪ 호스팅 모듈의 TOOLS. 한쪽에만 있으면 실패한다."""
    existing = _registered() | _hosted_module_tools()
    assert set(TOOL_TABLE) - existing == set(), "표에 있는데 없는 도구"
    assert existing - set(TOOL_TABLE) == set(), "등록됐는데 표에 없는 도구 — tax_scope.TOOL_TABLE 에 더한다"


def test_every_tool_has_known_topic_and_owner():
    for name, (topic, owner, desc) in TOOL_TABLE.items():
        assert topic in TOPICS, name
        assert owner in ("개인", "법인", "공통"), name
        assert desc.strip()


def test_tool_names_in_text_exist():
    """흐름·원칙·설명 문장 안의 도구 이름도 표에 있어야 한다."""
    text = repr(CORPORATE_FLOW) + repr(NOT_COVERED) + repr(tax_scope.CITATION_RULES)
    mentioned = set(re.findall(r"\b(?:calc|judge|get|count|search|screen|estimate|format)_[a-z0-9_]+\b", text))
    assert mentioned <= set(TOOL_TABLE), mentioned - set(TOOL_TABLE)
    for step in CORPORATE_FLOW:
        for name in step["도구"]:
            assert TOOL_TABLE[name][1] in ("법인", "공통"), "법인 흐름에 개인 전용 도구: %s" % name


def _audit():
    sys.path.insert(0, str(ROOT / "scripts"))
    return importlib.import_module("coverage_audit")


def test_not_covered_chapters_match_coverage_audit():
    """'다루지 않는다'고 적은 장은 coverage_audit.OUT_OF_SCOPE 에 있어야 하고, 지방세법의 범위밖 장은 전부 표에 있어야 한다."""
    audit = _audit()
    listed = {}
    for item in NOT_COVERED:
        for law, chapters in item.get("범위밖_장", {}).items():
            for ch in chapters:
                assert ch in audit.OUT_OF_SCOPE[law], (item["항목"], law, ch)
                listed.setdefault(law, set()).add(ch)
    for law in ("지방세법", "지방세법 시행령"):
        assert listed[law] == set(audit.OUT_OF_SCOPE[law]), law


def test_corporate_tax_scope_matches_scope_only():
    audit = _audit()
    item = next(i for i in NOT_COVERED if "범위_조문" in i)
    assert set(item["범위_조문"]["법인세법"]) == audit.SCOPE_ONLY["법인세법"]
    for art in item["범위_조문"]["법인세법"]:
        n, _, sub = art.partition("의")
        assert ("제%s조" % n + ("의%s" % sub if sub else "")) in item["법령"], art


def test_not_covered_items_cite_no_article_outside_verified_field():
    """다루지 않는 항목의 법령·답하는_법에는 조문 번호(§·제N조)가 없다 — 장까지만. 설명과 확인한_조문은 원문에서 확인한 것만."""
    for item in NOT_COVERED:
        assert "§" not in item["법령"], item["항목"]
        assert "§" not in item["답하는_법"], item["항목"]
        if "범위_조문" not in item:
            assert not re.search(r"제\d+조", item["법령"]), item["항목"]
    cited = set(re.findall(r"§\s*([0-9]+(?:의[0-9]+)?)", " ".join(i["설명"] + i.get("확인한_조문", "") for i in NOT_COVERED)))
    assert cited == {"74", "103의20", "103의31"}      # 원문 대조한 것만 — 늘리려면 원문을 보고 여기도 고친다


def test_named_gaps_are_listed():
    names = " ".join(i["항목"] for i in NOT_COVERED)
    for kw in ("주민세", "부가가치세", "배당", "과세표준", "지역자원시설세"):
        assert kw in names


@pytest.mark.parametrize("topic", ["주민세", "부가가치세", "배당", "지역자원시설세", "이월결손금"])
def test_uncovered_topic_returns_no_tool_and_refusal_guidance(topic):
    r = get_tax_scope(topic, "법인")
    assert r["다루는_것"] == []
    assert r["다루지_않는_것"] and all("인용하지 말고" in i["답하는_법"] for i in r["다루지_않는_것"])


def test_corporate_owner_gets_flow_with_commonly_missed_items():
    r = get_tax_scope(owner="법인")
    flow = r["법인_흐름"]
    assert [s["단계"][:1] for s in flow] == ["1", "2", "3", "4"]
    assert flow[0]["도구"] == ["calc_corporate_acquisition_tax"]
    assert "calc_corporate_jongbu_tax" in flow[1]["도구"] and "calc_building_property_tax" in flow[1]["도구"]
    assert flow[2]["도구"][-1] == "calc_corporate_property_sale_tax"
    missed = " ".join(m for s in flow for m in s["흔히_빠뜨리는_것"])
    for kw in ("6월 1일", "종합부동산세", "대도시 법인 중과", "토지등 양도소득 추가과세", "저가주택 중과 예외"):
        assert kw in missed, kw
    tools = {t["도구"] for c in r["다루는_것"] for t in c["도구"]}
    assert not tools & {"calc_transfer_tax", "calc_jongbu_tax", "calc_acquisition_tax"}     # 개인 전용은 법인에게 안 보인다


def test_individual_owner_has_no_corporate_flow_or_tools():
    r = get_tax_scope(owner="개인")
    assert "법인_흐름" not in r
    tools = {t["도구"] for c in r["다루는_것"] for t in c["도구"]}
    assert "calc_jongbu_tax" in tools and "calc_corporate_jongbu_tax" not in tools


@pytest.mark.parametrize("topic,tool", [
    ("종부세", "calc_corporate_jongbu_tax"), ("취득세", "calc_corporate_acquisition_tax"),
    ("재산세", "calc_building_property_tax"), ("매도", "calc_corporate_property_sale_tax"),
    ("유지비", "calc_corporate_jongbu_tax"),
])
def test_topic_alias_routes_to_tool(topic, tool):
    r = get_tax_scope(topic, "법인")
    assert tool in {t["도구"] for c in r["다루는_것"] for t in c["도구"]}


def test_maintenance_cost_question_lists_uncovered_parts():
    """실제로 틀렸던 질문('법인 연간 유지비') — 재산세·종부세 도구와 함께 주민세·지역자원시설세·토지분이 '다루지 않는 것'으로 나온다."""
    r = get_tax_scope("유지비", "법인")
    names = " ".join(i["항목"] for i in r["다루지_않는_것"])
    for kw in ("주민세", "지역자원시설세", "토지 재산세", "기장"):
        assert kw in names


def test_unknown_topic_and_bad_owner():
    r = get_tax_scope("우주세")
    assert r["찾지_못함"] is True and "인용하지 않는다" in r["안내"]
    with pytest.raises(ValueError):
        get_tax_scope(owner="외국법인")


def test_docstring_shape_for_hosting():
    doc = get_tax_scope.__doc__.strip().splitlines()[0]
    assert doc.isascii() and "does not cover" in doc


# ── docs/QUESTION_CASES.md — 문서에 적은 도구 이름과 기대 금액이 실제와 맞는지 ─────────────────
def _doc() -> str:
    return (ROOT / "docs" / "QUESTION_CASES.md").read_text(encoding="utf-8")


def test_question_cases_name_only_existing_tools():
    mentioned = set(re.findall(r"`((?:calc|judge|get|count|search|screen|estimate|format)_[a-z0-9_]+)", _doc()))
    assert mentioned and mentioned <= set(TOOL_TABLE), mentioned - set(TOOL_TABLE)


def test_question_cases_amounts_reproduce():
    from corporate_tax import (calc_corporate_acquisition_tax as acq, calc_corporate_jongbu_tax as jongbu,
                               calc_corporate_property_sale_tax as sale)
    doc = _doc()

    def won(n):
        s = format(n, ",") + "원"
        assert s in doc, s

    r = jongbu(2026, 600_000_000, 1, prev_year_official_price=580_000_000)                      # Q1
    won(r["종합부동산세"]), won(r["농어촌특별세"])
    r = acq(500_000_000, "2026-03-02", "주택", exclusive_area=59, standard_value=350_000_000, in_capital_area=True)   # Q2
    won(r["취득세"]), won(r["지방교육세"]), won(r["총납부세액"])
    r = sale(2026, [{"라벨": "A", "종류": "주택", "양도금액": 500_000_000, "장부가액": 400_000_000}], taxable_base=100_000_000)  # Q3
    won(r["세액합계"]), won(r["토지등양도소득_법인세"])
    r = jongbu(2026, 600_000_000, 3)                                                            # Q6
    won(r["산출세액"]), won(r["농어촌특별세"])
    r = acq(1_000_000_000, "2026-03-02", "주택외", property_in_metro=True, metro_office_date="2025-06-01")            # Q7
    won(r["취득세"]), won(r["지방교육세"]), won(r["총납부세액"])
    r = acq(90_000_000, "2026-03-02", "주택", property_in_metro=False, exclusive_area=59, standard_value=80_000_000,
            in_capital_area=True)                                                               # Q8
    won(r["취득세"]), won(r["지방교육세"])
