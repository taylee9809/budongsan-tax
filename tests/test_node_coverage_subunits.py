"""호·목 점검 — 조 단위 집계가 가리는 구멍을 찾는가 (2026-11-17, findings 42)."""
import json
import pathlib
import sys
from types import SimpleNamespace as N

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import coverage_audit  # noqa: E402
import node_coverage  # noqa: E402


def _node(조, 항="", 호="", 목="", 법령="지방세법", 원문=""):
    return N(법령=법령, 조=조, 항=항, 호=호, 목=목, 원문=원문)


def _run(nodes, subunits=None, dispositions=None):
    return node_coverage.subunit_gaps({str(i): n for i, n in enumerate(nodes)}, subunits or {}, dispositions or {})


def _names(sub):
    return [g["표기"] for g in sub["미처리"]]


SUB_111 = {"지방세법": {"111": [
    {"항": "1", "호": "1", "요지": "토지"}, {"항": "1", "호": "1", "목": "가", "요지": "종합합산과세대상"},
    {"항": "1", "호": "2", "요지": "건축물"}, {"항": "1", "호": "3", "요지": "주택"},
    {"항": "1", "호": "3", "목": "가", "삭제": True, "요지": "삭제"}, {"항": "1", "호": "3", "목": "나", "요지": "그 밖의 주택"},
    {"항": "1", "호": "4", "요지": "선박"},
]}}


def test_sibling_gap_found_from_numbers_alone():
    # 1호·3호 노드만 있고 2호가 없다 — 원문 구조가 없어도 사이 구멍은 보인다
    sub = _run([_node("111", "1", "1"), _node("111", "1", "3")])
    assert _names(sub) == ["지방세법 §111①2호"]
    assert sub["미처리"][0]["출처"] == "번호추정"


def test_statute_structure_shows_trailing_siblings_and_skips_deleted():
    sub = _run([_node("111", "1", "1", "가"), _node("111", "1", "3", "나")], SUB_111)
    assert _names(sub) == ["지방세법 §111①2호", "지방세법 §111①4호"]      # 맨 뒤 4호까지 보인다
    assert [g["표기"] for g in sub["처리"]] == ["지방세법 §111①3호가목"]     # 원문 '삭제'
    assert sub["정본부모"] == 3


def test_article_level_node_alone_is_not_checked():
    # 조·항 단위 노드 하나가 각 호를 통째로 담은 조문은 점검 대상이 아니다
    assert _run([_node("28의2", 원문="1. 저가주택 2. 공공주택")], SUB_111)["점검부모"] == 0


def test_parent_text_that_quotes_the_clause_counts_as_covered():
    nodes = [_node("106", "1", 원문="다음 각 호에 따라 구분한다. 1. 종합합산과세대상: … 2. 별도합산"), _node("106", "1", "2")]
    sub = _run(nodes)
    assert _names(sub) == []
    assert sub["처리"][0]["처리"] == "상위노드"
    # 부모 원문에 그 호가 없으면 구멍이다 — "제1호" 같은 인용은 호 본문이 아니다
    nodes = [_node("111", "1", 원문="다음 각 호의 표준세율을 적용한다. 제2호는 따로 정한다."), _node("111", "1", "1"), _node("111", "1", "3")]
    assert _names(_run(nodes)) == ["지방세법 §111①2호"]


def test_disposition_needs_known_kind_and_reason():
    nodes = [_node("111", "1", "1"), _node("111", "1", "3")]
    ok = {"지방세법 §111①2호": {"처리": "범위밖", "사유": "시험"}}
    sub = _run(nodes, dispositions=ok)
    assert _names(sub) == [] and sub["처리"][0]["사유"] == "시험"
    for bad in ({"처리": "모름", "사유": "x"}, {"처리": "범위밖", "사유": ""}):
        with pytest.raises(ValueError):
            _run(nodes, dispositions={"지방세법 §111①2호": bad})


def test_stale_disposition_is_reported():
    sub = _run([_node("111", "1", "1"), _node("111", "1", "2")],
               dispositions={"_설명": "x", "지방세법 §111①9호": {"처리": "범위밖", "사유": "옛 항목"}})
    assert sub["묵은처리"] == ["지방세법 §111①9호"]


def test_clause_without_paragraph_is_written_with_a_space():
    sub = _run([_node("88", "", "6", 법령="소득세법"), _node("88", "", "8", 법령="소득세법")])
    assert "소득세법 §88 7호" in _names(sub)


def test_audit_reads_paragraph_clause_item_structure():
    unit = {"조문여부": "조문", "조문번호": "111", "항": [
        {"항번호": "①", "호": [
            {"호번호": "1.", "호내용": "1. 토지", "목": [{"목번호": "가.", "목내용": "가. 종합합산과세대상"}]},
            {"호번호": "2.", "호내용": "2. 건축물", "목": {"목번호": "가.", "목내용": [["가. 골프장"]]}},     # 원소 하나는 dict
            {"호번호": "3의2.", "호내용": "3의2. 삭제 <2023. 3. 14.>"}]},
        {"항번호": "②", "항내용": "② 호가 없는 항"}]}
    rows = coverage_audit.subunits_of(unit)
    assert [(r["항"], r["호"], r.get("목", "")) for r in rows] == [("1", "1", ""), ("1", "1", "가"), ("1", "2", ""), ("1", "2", "가"), ("1", "3의2", "")]
    assert rows[-1]["삭제"] is True and rows[0]["요지"] == "토지"
    # 항 없이 호가 바로 오는 조문
    assert coverage_audit.subunits_of({"항": {"호": {"호번호": "6.", "호내용": "6. 1세대란"}}}) == [{"항": "", "호": "6", "요지": "1세대란"}]
    doc = {"법령": {"조문": {"조문단위": [unit, {"조문여부": "전문", "조문내용": "제9장 재산세"}]}}}
    assert list(coverage_audit.law_subunits(doc)) == ["111"]


def test_repo_data_is_consistent():
    """저장소 정본: §111①2호(건축물)는 노드가 없으므로 전환 대기에 떠 있어야 하고, 처리 파일에 묵은 항목이 없어야 한다."""
    nodes = node_coverage._load_nodes()
    sub = node_coverage.subunit_gaps(
        nodes, json.loads(node_coverage.SUBUNITS.read_text(encoding="utf-8")),
        json.loads(node_coverage.DISPOSITIONS.read_text(encoding="utf-8")))
    assert sub["묵은처리"] == []
    has_building_nodes = any(n.법령 == "지방세법" and n.조 == "111" and str(n.호) == "2" for n in nodes.values())
    assert ("지방세법 §111①2호" in _names(sub)) is (not has_building_nodes)
