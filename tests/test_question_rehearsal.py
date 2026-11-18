"""scripts/question_rehearsal.py 의 대조 로직 — 조문 인용 뽑기, 도구 결과와의 대조, 세율·금액, 채점표 읽기."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import question_rehearsal as qr  # noqa: E402


def cites(text):
    return [(c["법령"], c["조"], c["항"]) for c in qr.extract_citations(text)]


@pytest.fixture(scope="module")
def questions():
    return qr.parse_questions(qr.CASES_MD.read_text(encoding="utf-8"))


# ── 조문 인용 뽑기 ──

def test_law_name_carries_over_within_a_line():
    assert cites("지방세법 §111①3호·§112①2호·§151①6호") == [
        ("지방세법", "111", 1), ("지방세법", "112", 1), ("지방세법", "151", 1)]


def test_law_name_does_not_carry_across_lines():
    assert cites("지방세법 §13②\n§16⑤") == [("지방세법", "13", 2), (None, "16", 5)]


def test_decree_after_a_law_is_that_laws_decree():
    assert cites("종합부동산세법 §8①, §9②, 시행령 §2의4①·§4의3①, 농어촌특별세법 §5①8호") == [
        ("종합부동산세법", "8", 1), ("종합부동산세법", "9", 2),
        ("종합부동산세법 시행령", "2의4", 1), ("종합부동산세법 시행령", "4의3", 1), ("농어촌특별세법", "5", 1)]


def test_decree_without_a_law_is_unknown_decree():
    assert cites("시행령 §27③") == [("?시행령", "27", 3)]


def test_je_jo_form_and_same_law():
    assert cites("지방세법 제13조의2 제1항, 같은 법 시행령 제28조의2 에 따라") == [
        ("지방세법", "13의2", 1), ("지방세법 시행령", "28의2", None)]


def test_bare_beop_goes_back_to_the_statute():
    assert cites("소득세법 시행령 §167의3①, 법 §104⑦") == [("소득세법 시행령", "167의3", 1), ("소득세법", "104", 7)]


def test_aliases_and_spacing():
    assert cites("종부세법 §9②") == [("종합부동산세법", "9", 2)]
    assert cites("지방세법시행령 §28의2") == [("지방세법 시행령", "28의2", None)]
    assert cites("법인세법 § 55의2 ①") == [("법인세법", "55의2", 1)]


def test_node_id_form():
    assert cites("노드 종부세법-9-2 · 지방세법시행령-28의2 · 법인세법-55의2-1") == [
        ("종합부동산세법", "9", 2), ("지방세법 시행령", "28의2", None), ("법인세법", "55의2", 1)]


def test_paragraph_or_item_alone_is_not_a_citation():
    assert cites("제2항 제3호에 따라 100분의 20, 2026년 6월 1일, 제7장 주민세") == []


def test_unknown_law_names_are_not_invented():
    # 목록에 없는 말("계산방법")이 법령으로 읽히지 않는다 — 조문은 법령 불명으로 남는다
    assert cites("계산방법 §3") == [(None, "3", None)]


# ── 도구 결과와 대조 ──

TOOL_RESULT = json.dumps({
    "적용 조문": ["종합부동산세법 §8① — 법인 공제 0원", "종합부동산세법 §9② — 1천분의 27", "시행령 §2의4①"],
    "값 출처": {"세율": "종부세법-9-2", "농특세": "농어촌특별세법 §5①8호"},
    "미적용 조문": [{"조문": "지방세법 §111①3호", "이유": "재산세는 따로"}],
    "세율": 0.027, "산출세액": 9720000,
}, ensure_ascii=False)


def verdicts(answer, texts=(TOOL_RESULT,)):
    return {(r["법령"], r["조"], r["항"]): r["판정"] for r in qr.check_citations(answer, list(texts))["인용"]}


def test_cited_article_present_in_tool_result():
    v = verdicts("종합부동산세법 제9조 제2항에 따라 2.7%, 농어촌특별세법 §5")
    assert v == {("종합부동산세법", "9", 2): "있음", ("농어촌특별세법", "5", None): "있음"}


def test_article_absent_from_tool_result_is_flagged():
    report = qr.check_citations("종합부동산세법 §10 에 따라 상한이 없고, 지방세법 §74 의 주민세", [TOOL_RESULT])
    assert report["없음"] == ["종합부동산세법 §10", "지방세법 §74"]


def test_paragraph_mismatch_is_a_warning_not_a_miss():
    v = verdicts("종합부동산세법 §9①")
    assert v == {("종합부동산세법", "9", 1): "항_불일치"}


def test_right_number_wrong_law():
    v = verdicts("소득세법 §9②")
    assert v == {("소득세법", "9", 2): "법령_불일치"}


def test_number_without_law_name():
    v = verdicts("§8① 에 따라 공제가 없습니다")
    assert v == {(None, "8", 1): "법령_불명"}


def test_bare_decree_matches_any_decree_in_results():
    assert verdicts("시행령 §2의4①") == {("?시행령", "2의4", 1): "있음"}
    assert verdicts("시행령 §9") == {("?시행령", "9", None): "법령_불일치"}


def test_tool_result_that_abbreviates_the_law_name_still_matches():
    # 결과의 "시행령 §2의4①" 은 앞 문자열(종합부동산세법 §9②)의 법령을 이어받지 않는다 — 법령 이름이 줄어든 조로 남고,
    # 답이 어느 시행령이라고 적었든 조 번호가 같으면 있는 것으로 본다. 본법으로 적으면 맞지 않는다.
    assert verdicts("종합부동산세법 시행령 §2의4①") == {("종합부동산세법 시행령", "2의4", 1): "있음"}
    assert verdicts("종합부동산세법 §2의4①") == {("종합부동산세법", "2의4", 1): "법령_불일치"}
    # "영 §154①" 처럼 법령이 아예 없는 표기
    assert verdicts("소득세법 시행령 §154①", ['{"근거": "영 §154①·⑤"}']) == {("소득세법 시행령", "154", 1): "있음"}


def test_description_only_citation_is_separated():
    report = qr.check_citations("지방세법 시행령 §26① 과 소득세법 §999", [TOOL_RESULT],
                                surface_text="대도시 중과 제외 업종(지방세법 시행령 §26①)")
    assert report["설명에만_있음"] == ["지방세법 시행령 §26①"] and report["없음"] == ["소득세법 §999"]


def test_forbidden_and_conditional_tools(questions):
    by = {q["id"]: q for q in questions}
    assert by["Q13"]["금지_도구"] == ["calc_corporate_jongbu_tax"] and by["Q13"]["기대_도구"] == ["calc_jongbu_tax"]
    row = qr.check_answer(by["Q13"], "답", [{"tool": "calc_corporate_jongbu_tax", "arguments": {}, "isError": False, "text": "{}"}])
    assert row["금지_도구_호출"] == ["calc_corporate_jongbu_tax"]


def test_first_turn_is_checked_against_first_turn_calls_only(tmp_path, questions):
    qdir = tmp_path / "Q1"
    qdir.mkdir()
    lines = [{"tool": "get_tax_scope", "arguments": {}, "isError": False, "text": "종합부동산세법 §9②", "turn": 1},
             {"tool": "calc_corporate_jongbu_tax", "arguments": {}, "isError": False, "text": "종합부동산세법 §8①", "turn": 2}]
    (qdir / "calls.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")
    (qdir / "turn1.md").write_text("종합부동산세법 §9②, §8①", encoding="utf-8")
    (qdir / "answer.md").write_text("종합부동산세법 §9②, §8①", encoding="utf-8")
    first, final = qr.check_run(tmp_path, questions)
    assert first["조문_없음"] == ["종합부동산세법 §8①"] and final["조문_없음"] == []


def test_plain_text_tool_result():
    v = verdicts("지방세법 §13의2①", ["ERROR 가 아닌 평문 결과: 지방세법 §13의2① 1호"])
    assert v == {("지방세법", "13의2", 1): "있음"}


def test_no_tool_calls_means_every_citation_is_missing():
    assert qr.check_citations("지방세법 §78, §81", [])["없음"] == ["지방세법 §78", "지방세법 §81"]


# ── 세율·금액 ──

def test_rates():
    assert qr.extract_rates("2.7% · 1천분의 50 · 100분의 20 · 12 % · 0.4%") == {2.7, 5.0, 20.0, 12.0, 0.4}
    assert 2.7 in qr.tool_rates([TOOL_RESULT])            # 0.027 과 "1천분의 27"


def test_amounts():
    assert qr.extract_amounts("9,360,000원, 9억 3,600만원, 5억원, 3천만원, 6억 2천만 원, 1억5천만원, 900원") == {
        9_360_000, 936_000_000, 500_000_000, 30_000_000, 620_000_000, 150_000_000}


def test_amounts_from_tool_results_and_arguments():
    got = qr.tool_amounts([TOOL_RESULT, "합계 1,872,000 원"], [{"total_official_price": 600000000, "year": 2026}])
    assert {9_720_000, 1_872_000, 600_000_000} <= got and 2026 not in got


# ── 한 질문 대조 ──

def test_check_answer_flags_personal_tool_for_company_question():
    q = {"id": "Q1", "법인_질문": True, "기대_도구": ["calc_corporate_jongbu_tax", "get_tax_scope"]}
    calls = [{"tool": "calc_jongbu_tax", "arguments": {"total_official_price": 600000000}, "isError": False, "text": TOOL_RESULT}]
    answer = "종합부동산세는 9,720,000원(2.7%)이고 주민세 균등분은 지방세법 §78 에 따라 62,500원입니다. 세율 3%."
    row = qr.check_answer(q, answer, calls)
    assert row["법인에_개인용_도구"] == ["calc_jongbu_tax"]
    assert row["기대_도구_중_안_부른_것"] == ["calc_corporate_jongbu_tax", "get_tax_scope"]
    assert row["조문_없음"] == ["지방세법 §78"]
    assert row["세율_확인_필요"] == [3.0]
    assert row["금액_확인_필요"] == [62_500]
    assert row["균등분"] is True


def test_check_answer_errored_call_gives_no_citations():
    q = {"id": "Q13", "법인_질문": False, "기대_도구": []}
    calls = [{"tool": "calc_jongbu_tax", "arguments": {}, "isError": True, "text": "종합부동산세법 §9①"}]
    row = qr.check_answer(q, "종합부동산세법 §9①", calls)
    assert row["조문_없음"] == ["종합부동산세법 §9①"] and row["오류난_호출"] == ["calc_jongbu_tax"]
    assert row["법인에_개인용_도구"] == []


def test_amount_given_by_user_is_not_flagged():
    q = {"id": "Q2", "법인_질문": True, "기대_도구": []}
    row = qr.check_answer(q, "취득가액 5억원 기준입니다", [], known_text="2026-03-02 취득, 5억, 전용 59㎡")
    assert row["금액_확인_필요"] == [500_000_000]          # "5억"에 '원'이 없으면 금액으로 읽지 않는다
    row = qr.check_answer(q, "취득가액 5억원 기준입니다", [], known_text="취득가액 5억원")
    assert row["금액_확인_필요"] == []


# ── 채점표 읽기 ──

def test_question_sheet_parses(questions):
    assert [q["id"] for q in questions] == ["Q%d" % i for i in range(1, 16)]
    by = {q["id"]: q for q in questions}
    assert by["Q1"]["법인_질문"] and by["Q11"]["법인_질문"] and not by["Q13"]["법인_질문"]
    assert "calc_corporate_jongbu_tax" in by["Q1"]["기대_도구"]
    assert by["Q14"]["기대_도구"] == ["get_acquisition_tax_checklist"]
    assert all(q["질문"] for q in questions)


def test_expected_tools_are_registered_names(questions):
    """채점표가 적은 도구 이름이 실제 등록된 이름이다 — 이름이 바뀌면 채점표를 고쳐야 한다."""
    import tax_scope
    known = set(tax_scope.TOOL_TABLE)
    for q in questions:
        assert set(q["기대_도구"]) <= known, (q["id"], set(q["기대_도구"]) - known)


def test_check_run_reads_a_run_directory(tmp_path, questions):
    qdir = tmp_path / "Q1"
    qdir.mkdir()
    (qdir / "calls.jsonl").write_text(json.dumps(
        {"tool": "calc_corporate_jongbu_tax", "arguments": {}, "isError": False, "text": TOOL_RESULT}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (qdir / "answer.md").write_text("종합부동산세법 §9② 2.7% 로 9,720,000원, 지방세법 §74", encoding="utf-8")
    rows = qr.check_run(tmp_path, questions)
    assert len(rows) == 1 and rows[0]["id"] == "Q1" and rows[0]["파일"] == "answer.md"
    assert rows[0]["조문_없음"] == ["지방세법 §74"] and rows[0]["금액_확인_필요"] == []


def test_surface_markdown_lists_every_tool():
    surface = {"server": "s", "instructions": "INSTR", "tools": [
        {"name": "a_tool", "title": None, "description": "does a", "inputSchema": {"type": "object"}},
        {"name": "b_tool", "title": None, "description": "does b", "inputSchema": {"type": "object"}}]}
    text = qr.surface_markdown(surface)
    assert "INSTR" in text and "### a_tool" in text and "### b_tool" in text and "Tools (2)" in text
