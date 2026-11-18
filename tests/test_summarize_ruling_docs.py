"""scripts/summarize_ruling_docs.py — docs/RULING_LINKS.md·RULING_CASES.md 재생성기 (2026-11-18).

문서가 최신인지는 여기서 강제하지 않는다(케이스 파일이 늘 때마다 깨진다 — `--check` 로 따로 본다).
형식과, 연결 파일만으로 정해지는 수치가 문서와 같은지만 본다.
"""
import importlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
gen = importlib.import_module("summarize_ruling_docs")


def test_links_doc_is_reproducible_from_link_file():
    text = gen.links_md()
    def 표(t):      # 색인 건수에 따라 바뀌는 줄(연결 미생성 건수)은 뺀다
        return [l for l in t.splitlines() if "색인에" not in l]
    assert 표(text) == 표((ROOT / "docs" / "RULING_LINKS.md").read_text(encoding="utf-8"))
    for 제목 in ("## 인용 조문 연결 상태", "## 연결된 판례의 기관", "## 판례가 많이 붙은 조문 (상위 40)"):
        assert 제목 in text
    assert len(re.findall(r"^\| [^|]+ \| §[^|]+ \| \d+ \|$", text, re.M)) == 40


def test_cases_doc_shape():
    text = gen.cases_md(run=False)
    for 제목 in ("## 기관별", "## 비활성 사유", "## 케이스가 많은 노드 (상위 30)", "## 판례 회귀로 고친 노드"):
        assert 제목 in text
    assert "| 활성 케이스 불일치 | 미실행 |" in text
    assert re.search(r"^\| 수집 판례 \| \d+ \|$", text, re.M)
