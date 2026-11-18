"""law.go.kr 웹 본문 경로(scripts/law_web.py)와 그 위의 감사·판 대조 — 네트워크 없이 고정 자료로 시험한다.

고정 자료(tests/fixtures/law_web_*.txt)는 2026-11-18 law.go.kr 본문의 작은 발췌다(전문 아님).
웹 파서 전체의 회귀 대조(27개 법령의 조문 목록)는 CONTRIBUTING.md '5. 조문 목록을 다시 만든다' 참조.
"""
import json
import pathlib
import sys
from types import SimpleNamespace as N

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import coverage_audit  # noqa: E402
import law_web  # noqa: E402
import node_coverage  # noqa: E402
import node_mst_check  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def _doc(name):
    return law_web.to_api_doc(law_web.parse_text((FIX / name).read_text(encoding="utf-8")), mst="1")


def _arts(parsed):
    return [u for u in parsed["단위"] if u["조문여부"] == "조문"]


# ───────── 머리줄·태그 ─────────

def test_header_line():
    h = law_web.parse_header("지방세법 시행령 [시행 2026. 10. 1.] [대통령령 제36736호, 2026. 9. 30., 일부개정]")
    assert h == {"시행일자": "20261001", "공포번호": "대통령령 제36736호", "공포일자": "20260930", "제개정구분": "일부개정"}
    assert law_web.parse_header("머리줄 없음") == {}


def test_tag_dates_skip_effective_date_notes():
    s = "② … <개정 2013. 3. 23., 2021. 12. 31.> [본조신설 2010. 9. 20.] [시행일: 2027. 1. 1.] 제88조"
    assert law_web.tag_dates(s) == ["20130323", "20211231", "20100920"]
    assert law_web.tag_dates("3. 삭제 <2010. 12. 30.>") == ["20101230"]


# ───────── 본문 파서: 실제 발췌 ─────────

def test_articles_chapters_and_addenda_cutoff():
    p = law_web.parse_text((FIX / "law_web_jibangse_yeong.txt").read_text(encoding="utf-8"))
    assert p["법령명"] == "지방세법 시행령" and p["시행일자"] == "20261001" and p["공포번호"] == "대통령령 제36736호"
    rows = coverage_audit.articles(law_web.to_api_doc(p))
    got = [(r["조문번호"], r["가지번호"], r["조문제목"], r["장"], r["절"]) for r in rows]
    assert got == [
        (1, 0, "목적", "제1장 총칙", ""),
        (2, 0, "토지 및 주택의 시가표준액", "제1장 총칙", ""),
        (3, 0, "공시되지 아니한 공동주택가격의 산정가액", "제1장 총칙", ""),
        (4, 0, "건축물 등의 시가표준액 산정기준", "제1장 총칙", ""),
        (11, 2, "비조합원용 부동산의 취득", "제2장 취득세", "제1절 통칙"),
    ]      # 부칙의 제1조·제2조는 본문 조문이 아니다
    assert all(r["시행일자"] == "20261001" for r in rows)


def test_paragraph_clause_item_structure_from_text():
    sub = coverage_audit.law_subunits(_doc("law_web_jibangse_yeong.txt"))
    rows = sub["4"]
    keys = [(r["항"], r["호"], r.get("목", "")) for r in rows]
    assert keys[:7] == [("1", "1", ""), ("1", "1", "가"), ("1", "1", "나"), ("1", "1의2", ""),
                        ("1", "1의2", "가"), ("1", "1의2", "나"), ("1", "1의2", "다")]
    assert [k[1] for k in keys if not k[2]] == ["1", "1의2", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
    assert rows[0]["요지"].startswith("오피스텔:") and len(rows[0]["요지"]) <= coverage_audit.요지길이
    assert "11의2" not in sub and "1" not in sub      # 호가 없는 조문은 싣지 않는다
    # 삭제된 항(③~⑩ "삭제")은 호가 없으니 구조에 나타나지 않는다
    assert {r["항"] for r in rows} == {"1"}


def test_figure_line_is_not_structure():
    p = law_web.parse_text((FIX / "law_web_jibangse_yeong.txt").read_text(encoding="utf-8"))
    art = [a for a in _arts(p) if (a["조문번호"], a["가지번호"]) == (11, 2)][0]
    assert "[그림]" in art["본문"] and len(art["항"]) == 1 and art["항"][0]["호"] == []


def test_future_version_is_kept_apart_and_toc_is_skipped():
    p = law_web.parse_text((FIX / "law_web_future_articles.txt").read_text(encoding="utf-8"))
    arts = _arts(p)
    # 목차의 "제1장 총칙"·"부칙" 줄에 속지 않는다: 본문은 제87조부터, 부칙에서 끊는다
    assert [(a["조문번호"], a["가지번호"], a["판"], a["삭제"]) for a in arts] == [
        (87, 0, "현행", False), (88, 0, "현행", True), (88, 0, "장래", False)]
    cur88, fut88 = arts[1], arts[2]
    assert "가상자산" not in cur88["본문"]                 # 장래 시행분이 현행 조문 본문에 섞이지 않는다
    assert fut88["시행일자"] == "20270101" and fut88["장래"]["대상"] == "제88조"
    assert [h["번호"] for h in fut88["항"]] == ["1", "2", "3", "4", "5", "6"]
    # 제87조: 호의 가지번호(1의2), 삭제된 목
    a87 = arts[0]
    hos = a87["항"][0]["호"]
    assert [o["번호"] for o in hos] == ["1", "1의2", "2", "3"]
    assert [(k["번호"], k["삭제"]) for k in hos[0]["목"]] == [("가", False), ("나", True), ("다", False), ("라", True)]


def test_new_chapter_not_yet_in_force():
    # 새로 생긴 장(시행 전)은 한 번만 실린다: 장 이름에서 [시행일 …]을 떼고, 조문 시행일자에 그 날짜를 적는다
    p = law_web.parse_text((FIX / "law_web_new_chapter.txt").read_text(encoding="utf-8"))
    arts = _arts(p)
    assert [(a["조문번호"], a["가지번호"], a["판"], a["장"], a["시행일자"]) for a in arts] == [
        (23, 0, "현행", "제4장 토지거래허가구역 등", "20240517"),
        (23, 2, "장래", "제4장의2 불공정거래 행위", "20261217")]
    assert [o["번호"] for o in arts[1]["항"][0]["호"]] == ["1", "2", "3"]


def test_pick_versions_prefers_current_unless_deleted():
    doc = _doc("law_web_future_articles.txt")
    rows = coverage_audit.articles(doc)
    # 현행이 삭제인 제88조는 장래 시행분을 쓴다(없어진 조문이 아니라 곧 생기는 조문이다)
    assert [(r["조문번호"], r["가지번호"], r["조문제목"], r["시행일자"]) for r in rows] == [
        (87, 0, "기타소득의 필요경비계산", "20261001"),
        (88, 0, "가상자산에 대한 기타소득금액의 계산 등", "20270101")]
    unit = [u for u in doc["법령"]["조문"]["조문단위"] if u.get("조문번호") == "88"][0]
    assert unit["웹_판"] == "장래" and unit["웹_다른판"]["삭제"] is True


# ───────── 본문 파서: 까다로운 꼴(손으로 만든 줄) ─────────

TRICKY = """시험법
[시행 2026. 1. 1.] [법률 제1호, 2025. 12. 31., 제정]
제1편 총칙
제1장 통칙 <개정 2020. 1. 1.>
제1조 이 법은 제목 없는 조문을 시험한다.
제2조 삭제 <2019. 1. 1.>
제3조부터 제5조까지 삭제 <2019. 1. 1.>
제6조(범위(괄호 안 괄호)) 다음 각 호와 같다.
1. 첫째
2026. 1. 1. 이후 취득분부터 적용한다는 문단은 호가 아니다
2. 둘째
가. 가목
제3조 및 제4조에 따른다는 문단은 조문 머리가 아니다
나. 나목
1) 세목은 구조로 읽지 않는다
[표] 1. 표 안의 번호 | 2. 는 호가 아니다
4.「띄어쓰기 없는 호」
제1절 세부
제6조의2(가지번호) ① 항
② 삭제 <2021. 1. 1.>
㉑ 스물한째 항
1. 호
제7조(끝)
[제8조로 이동 <2016. 3. 21.>]
부칙 <법률 제1호, 2025. 12. 31.>
제1조(시행일) 이 법은 공포한 날부터 시행한다.
"""


def test_tricky_shapes():
    p = law_web.parse_text(TRICKY)
    arts = _arts(p)
    assert [(a["조문번호"], a["가지번호"], a["조문제목"], a["삭제"]) for a in arts] == [
        (1, 0, "", False), (2, 0, "", True), (3, 0, "", True), (6, 0, "범위(괄호 안 괄호)", False),
        (6, 2, "가지번호", False), (7, 0, "끝", False)]
    a6 = arts[3]
    hos = a6["항"][0]["호"]
    assert [o["번호"] for o in hos] == ["1", "2", "4"]            # "2026. 1. 1." 문단, 표 안의 "1."은 호가 아니다
    assert [k["번호"] for k in hos[1]["목"]] == ["가", "나"]        # "제3조 및 …" 문단에 끊기지 않는다
    assert "적용한다는 문단" in hos[0]["내용"]
    # 장·절: 편은 따라가지 않는다. 절은 다음 장에서 비워진다
    assert arts[0]["장"] == "제1장 통칙" and arts[0]["절"] == "" and arts[4]["절"] == "제1절 세부"
    a62 = arts[4]
    assert [h["번호"] for h in a62["항"]] == ["1", "2", "21"]
    # API 모양으로 바꾸면 기존 함수가 그대로 읽는다 — 삭제 조문은 빠지고, ㉑항의 호는 21항으로 간다
    doc = law_web.to_api_doc(p)
    assert [(r["조문번호"], r["가지번호"]) for r in coverage_audit.articles(doc)] == [(1, 0), (6, 0), (6, 2), (7, 0)]
    sub = coverage_audit.law_subunits(doc)
    assert [(r["항"], r["호"], r.get("목", "")) for r in sub["6"]] == [("", "1", ""), ("", "2", ""), ("", "2", "가"), ("", "2", "나"), ("", "4", "")]
    assert sub["6의2"] == [{"항": "21", "호": "1", "요지": "호"}]


# ───────── HTML → 텍스트 ─────────

HTML = """<html><body>
<input type="hidden" id="lsNm" name="lsNm" value="시험법 시행령" />
<input type="hidden" id="lsiSeq" name="lsiSeq" value="123456" /><input type="hidden" id="lsId" value="009999" />
<div class="ct_sub"> <span>[시행 2026. 10. 1.] [대통령령 제1호, 2026. 9. 30., 일부개정]<a href="#">입법예고안</a></span></div>
<script>var x = "<p>스크립트 안의 p 는 본문이 아니다</p>";</script>
<div id="conScroll">
 <div class="pgroup"><p class="gtit"> 제1장 총칙 </p></div>
 <div class="pgroup"><ul class="lawico01"><li><img alt="조문체계도버튼" src="/LSW/assets/btn-pan.svg" /></li></ul>
  <div class="lawcon">
   <p class="pty1_p4"> <input type="checkbox" value="1:0" /> <span class="bl"><label> 제1조(계산식) </label></span> ① <a class="link">법</a> 제1조에 따른 금액은 다음 계산식에 따른다. <span class="sfon">&lt;개정 2026. 9. 30.&gt;</span><br />
     <img alt="가액 = A × B" src="/LSW/flDownload.do?flSeq=1" /> </p>
   <p class="pty1_de2h">1. 첫째 호 </p>
   <p class="pty1_de3">가. 가목 <span class="sfon"></span></p>
   <table><tr><td><p>1. 표 안</p></td><td>100분의 10</td></tr></table>
   <p class="pty1_de2"> <span class="sfon">[본조신설 2020. 1. 1.]</span> </p>
   <p></p>
  </div></div>
 <div id="arDivArea"><div class="pgroup"><p class="pty3"> <a class="nun"><label><span class="bl"> 부 칙</span></label> <span class="sfon">&lt;대통령령 제1호, 2026. 9. 30.&gt;</span></a></p>
   <p class="pty3_dep1"><span class="bl">제1조(시행일)</span> 이 영은 공포한 날부터 시행한다.</p></div></div>
</div></body></html>"""


def test_html_to_text_and_parse():
    text = law_web.html_to_text(HTML)
    lines = text.split("\n")
    assert lines[0] == "시험법 시행령"
    assert lines[1] == "[시행 2026. 10. 1.] [대통령령 제1호, 2026. 9. 30., 일부개정]"
    assert lines[2] == "제1장 총칙"
    assert lines[3].startswith("제1조(계산식) ① 법 제1조에 따른 금액은") and "[그림] 가액 = A × B" in lines[3]
    assert "<개정 2026. 9. 30.>" in lines[3]
    assert "조문체계도버튼" not in text and "스크립트" not in text
    assert "[표] 1. 표 안 100분의 10" in lines
    assert any(ln.startswith("부 칙 <대통령령 제1호") for ln in lines)
    p = law_web.parse_text(text)
    arts = _arts(p)
    assert len(arts) == 1 and arts[0]["장"] == "제1장 총칙" and arts[0]["개정일"] == ["20260930", "20200101"]
    assert [o["번호"] for o in arts[0]["항"][0]["호"]] == ["1"]         # 표 안의 "1."은 호가 아니다


# ───────── 받기: 캐시와 실패 ─────────

def test_fetch_uses_cache_and_browser_path_fails_kindly(tmp_path, monkeypatch):
    monkeypatch.setattr(law_web, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(law_web, "PAUSE", 0)
    calls = []

    def fake_http(url, data=None):
        calls.append((url, data))
        if data is None:
            return ('<input type="hidden" id="lsiSeq" value="123456" /> var efYd = \'20260101\'; '
                    '<p class="subTit">[시행 2026. 10. 1.] [대통령령 제1호, 2026. 9. 30., 일부개정]</p>')
        return HTML

    monkeypatch.setattr(law_web, "_http", fake_http)
    law = law_web.fetch("시험법 시행령")
    assert law["MST"] == "123456" and law["법령ID"] == "009999" and law["시행일자"] == "20261001"
    # 시행일은 스크립트 변수(첫 시행일)가 아니라 화면 머리줄에서 읽어 보낸다
    assert calls[1][1]["lsiSeq"] == "123456" and calls[1][1]["efYd"] == "20261001"
    assert law_web.fetch("시험법 시행령") == law and len(calls) == 2          # 두 번째는 캐시
    assert law_web.current_meta("시험법 시행령") == {"mst": "123456", "공포일자": "20260930", "시행일자": "20261001", "제개정구분": "일부개정"}
    with pytest.raises(law_web.웹조회실패, match="다른 법령"):
        law_web.fetch("없는법")
    # Playwright 가 없으면 브라우저 경로만 안내와 함께 실패한다
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(law_web.웹조회실패, match="Playwright"):
        law_web.fetch("시험법 시행령", refresh=True, browser=True)


# ───────── 감사: 앞선 목록과의 차이, 손 보충, 직렬화 ─────────

def _row(n, sub, title, ch="제1장", sec="", ef=""):
    return {"조문번호": n, "가지번호": sub, "조문제목": title, "장": ch, "절": sec, "시행일자": ef}


def test_diff_articles():
    old = [_row(1, 0, "목적"), _row(7, 0, "신고·납부 등"), _row(8, 0, "옛 제목"), _row(9, 0, "없어질 조문")]
    new = [_row(1, 0, "목적"), _row(7, 0, "신고ㆍ납부 등"), _row(8, 0, "새 제목"), _row(8, 2, "신설", ef="20270101")]
    assert coverage_audit.diff_articles(old, new) == ["~ §8 새 제목 ← 옛 제목", "+ §8의2 신설 (시행 20270101)", "- §9 없어질 조문"]


def test_supplement_fills_only_unread_paragraphs():
    sub = {"농어촌특별세법": {"5": [{"항": "2", "호": "1", "요지": "읽힌 호"}]}}
    sup = {"_설명": "x", "농어촌특별세법": {"5": {"확인": "판", "단위": [
        {"항": "1", "호": "1", "요지": "표 속의 호"}, {"항": "2", "호": "9", "요지": "쓰이지 않아야 한다"}]}}}
    assert coverage_audit.apply_supplement(sub, sup) == [("농어촌특별세법", "5", "1")]
    assert [(u["항"], u["호"], u.get("출처", "")) for u in sub["농어촌특별세법"]["5"]] == [("1", "1", "손보충"), ("2", "1", "")]


def test_dump_subunits_roundtrip():
    data = {"_meta": {"설명": "x"}, "나법": {"1": [{"항": "1", "호": "1", "요지": '따옴표 " 포함'}]}, "가법": {"2의3": []}}
    text = coverage_audit.dump_subunits(data)
    assert json.loads(text) == data
    assert text.count("\n") < 12          # 조문 하나가 한 줄


# ───────── 요약표 밖 ─────────

def test_outside_counts_shows_what_the_summary_drops():
    def node(law, jo):
        return N(법령=law, 조=jo, 항="", 호="", 목="", id="%s-%s" % (law, jo), 원문="")

    def a(n, title, kind, covered=False, out="", ch="제3장 거주자의 양도소득에 대한 납세의무"):
        return {"조문번호": n, "가지번호": 0, "조문제목": title, "장": ch, "절": "", "분류": kind, "covered": covered,
                "부동산도메인": True, "범위밖": out}

    audit = {"소득세법": {"조문": [a(95, "양도소득금액", "세액영향", True), a(97, "양도소득의 필요경비 계산", "미분류", True),
                                a(100, "양도차익의 산정", "미분류", False), a(104, "세율", "세액영향", True),
                                a(127, "원천징수의무", "절차", out="제5장 원천징수", ch="제5장 원천징수"),
                                a(12, "비과세소득", "세액영향", True, ch="제2장 거주자의 종합소득")]}}
    nodes = {str(i): n for i, n in enumerate([node("소득세법", "95"), node("소득세법", "97"), node("소득세법", "127"), node("소득세법", "12")])}
    rep = node_coverage.build(audit, nodes)
    assert rep["요약"]["양도세"]["세액영향조문"] == 2 and rep["요약"]["양도세"]["전환대기(코퍼스有)"] == 1
    out = node_coverage.outside_counts(rep)
    assert sorted((x[1], x[3]) for x in out["노드있음"]) == [("12", "세목표에 없는 법령·장"), ("127", "범위밖: 제5장 원천징수"), ("97", "분류 '미분류'")]
    assert [(x[0], x[2], x[4], x[5]) for x in out["노드없음"]] == [("양도세", "100", "미분류", False)]
    text = "\n".join(node_coverage.render_outside(out))
    assert "소득세법 §100 양도차익의 산정 (미분류)" in text and "실행 노드는 있는데 표에 안 잡히는 조문: **3개**" in text


# ───────── 판 대조 ─────────

def test_mst_classification_and_recent_changes():
    cur = {"MST": "290815", "법령ID": "005077"}
    c = node_mst_check.classify
    assert [c(x, cur) for x in ("290815", "287223", "005077", "003963", "", "소득세법 현행")] == [
        "현행", "옛 판", "법령ID", "알 수 없는 번호", "미기재", "글로 적음"]
    assert node_mst_check.base_law("지방세법 시행령 부칙(대통령령 제30939호, 2020.8.12.)") == "지방세법 시행령"
    arts = node_mst_check.articles_of({"text": (FIX / "law_web_future_articles.txt").read_text(encoding="utf-8")})
    assert arts["88"]["삭제"] is False and arts["88"]["장래"]["시행일자"] == "20270101"
    recent = node_mst_check.changed_since(arts, "20250101")
    assert recent["88"]["날짜"] == ["20250228"]
    assert "4" in recent["88"]["항"] and "3" not in recent["88"]["항"]         # ④ <신설 2025. 2. 28.>, ③은 태그 없음
    assert "87" not in node_mst_check.changed_since(arts, "20260301")


def test_mst_check_reports_changed_articles(monkeypatch):
    old_text = "시험법\n[시행 2026. 1. 1.] [법률 제1호, 2025. 12. 31., 일부개정]\n제1조(목적) 옛 문장\n제2조(세율) ① 100분의 1\n제3조(그대로) 같다\n"
    new_text = ("시험법\n[시행 2026. 10. 1.] [법률 제2호, 2026. 9. 30., 일부개정]\n제1조(목적) 옛 문장\n"
                "제2조(세율) ① 100분의 2 <개정 2026. 9. 30.>\n② 새 항 <신설 2026. 9. 30.>\n제3조(그대로) 같다\n")

    def fake_fetch(name, mst=None, refresh=False, browser=False):
        if name != "시험법":
            raise law_web.웹조회실패("없음")
        t = old_text if mst == "100" else new_text
        return dict(law_web.parse_header(t), 법령명="시험법", MST=mst or "200", 법령ID="000001", text=t)

    def node(jo, 항, mst):
        return N(법령="시험법", 조=jo, 항=항, 호="", 목="", mst=mst, id="시험법-%s-%s-%s" % (jo, 항, mst))

    nodes = [node("1", "", "100"), node("2", "1", "100"), node("3", "", "200"), node("2", "", "000001"), node("9", "", "")]
    monkeypatch.setattr(law_web, "fetch", fake_fetch)
    monkeypatch.setattr(node_mst_check, "load_nodes", lambda: {n.id: n for n in nodes})
    monkeypatch.setattr(node_mst_check, "param_msts", lambda: {("시험법", "100"): ["키1"]})
    res = node_mst_check.check(since="20260101", log=lambda *_: None)
    table = {r["인용"]: r for r in res["표"]}
    assert table["100"]["구분"] == "옛 판" and table["100"]["달라진조문"] == 1 and table["100"]["상수"] == 1
    assert table["100"]["옛공포"] == "20251231" and table["200"]["구분"] == "현행" and table["000001"]["구분"] == "법령ID"
    (c,) = res["달라진조문"]
    assert (c["조"], c["변화"], c["날짜"], c["항"]) == ("2", "본문 다름", ["20260930"], ["1", "2"])
    # 판을 알 수 없는 노드: 최근 개정 태그가 붙은 조문, 현행에 없는 조문
    assert sorted((u["조"], u["변화"]) for u in res["기준없음"]) == [("2", "개정 태그"), ("9", "현행 본문에 없음(삭제·이동)")]
    text = node_mst_check.render(res)
    assert "§2 세율 — 본문 다름; 개정 2026-09-30; 개정 태그가 붙은 항: 1·2 — 노드가 옮긴 항과 겹침(1)" in text


# ───────── 저장소 산출물 ─────────

def test_repo_outputs_have_the_shape_both_paths_share():
    audit = json.loads((ROOT / "data" / "coverage" / "coverage_audit.json").read_text(encoding="utf-8"))
    from law_watch import TRACKED_LAWS
    assert set(TRACKED_LAWS) <= set(audit)                      # 법인세법·법인세법 시행령 포함 전부
    keys = {"조문번호", "가지번호", "조문제목", "장", "절", "시행일자", "covered", "분류", "부동산도메인", "범위밖"}
    for law, info in audit.items():
        assert "error" not in info, law
        assert all(set(r) == keys for r in info["조문"]), law
        assert len({(r["조문번호"], r["가지번호"]) for r in info["조문"]}) == len(info["조문"]), law   # 장래 시행분이 겹쳐 실리지 않는다
    # 법인세는 SCOPE_ONLY 조문만 범위 안이다
    inside = {coverage_audit._jo(r) for r in audit["법인세법"]["조문"] if not r["범위밖"]}
    assert inside == coverage_audit.SCOPE_ONLY["법인세법"]
    sub = json.loads((ROOT / "data" / "coverage" / "subunits.json").read_text(encoding="utf-8"))
    for law, arts in sub.items():
        if law == "_meta":
            continue
        assert sub["_meta"]["법령"][law]["MST"], law
        for jo, rows in arts.items():
            assert rows and all(r.get("호") for r in rows), (law, jo)
    # 지방세법 §111①: 1(토지)·2(건축물)·3(주택)호가 원문 구조에 있다
    assert [r["호"] for r in sub["지방세법"]["111"] if r["항"] == "1" and not r.get("목")][:3] == ["1", "2", "3"]
