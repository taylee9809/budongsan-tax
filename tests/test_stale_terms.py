"""사용자에게 나가는 문구에 폐지·개명된 세법 용어가 없는지.

대상: 호스팅 도구 설명, 서버 instructions, 체크리스트·시나리오 표, README·docs.
조문 원문 코퍼스(data/legal_nodes)와 재결례(data/verification)는 당시 법령을 그대로 옮긴 것이라 제외한다.
"""
import pathlib
import re

import pytest

import acquisition_checklist
import scenario_coverage
import tax_http

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 폐지 용어 자체를 설명하는 문서 — 여기서는 옛 명칭을 일부러 적는다.
DOCS_ABOUT_STALE_TERMS = {"SCENARIO_COVERAGE.md"}

# (패턴, 현행 표현, 근거)
STALE = [
    (r"균등분\s*주민세|주민세\s*균등분|법인\s*균등분", "주민세 사업소분(기본세액)", "지방세법 2020-12-29 개정, 2021-01-01 시행"),
    (r"재산분\s*주민세|주민세\s*재산분", "주민세 사업소분(연면적분)", "같은 개정"),
    (r"종업원할\s*주민세|주민세\s*종업원할", "주민세 종업원분", "같은 개정"),
    (r"소득할\s*주민세|주민세\s*소득할", "지방소득세", "지방세법 2010-03-31 개정"),
    (r"법인세분\s*지방소득세", "법인지방소득세", "지방세법 2014-01-01 개정(독립세 전환)"),
]


def _texts():
    server = tax_http.make_server()
    yield "instructions", server.instructions
    for t in server._tool_manager.list_tools():
        yield f"tool:{t.name}", t.description or ""
    for item in acquisition_checklist.ITEMS:
        yield f"acq:{item['key']}", " ".join(str(v) for v in item.values())
    for item in scenario_coverage.ITEMS:
        yield f"scenario:{item['id']}", " ".join(str(item[k]) for k in ("세목", "쟁점", "요지", "근거"))
    docs = [p for p in sorted((ROOT / "docs").glob("*.md")) if p.name not in DOCS_ABOUT_STALE_TERMS]
    for path in [ROOT / "README.md", ROOT / "README-EN.md", ROOT / "llms.txt", *docs]:
        yield str(path.relative_to(ROOT)), path.read_text(encoding="utf-8")


@pytest.mark.parametrize("pattern,current,basis", STALE, ids=[c for _, c, _ in STALE])
def test_no_stale_term(pattern, current, basis):
    hits = [where for where, text in _texts() if re.search(pattern, text)]
    assert not hits, f"폐지 용어 /{pattern}/ → '{current}' ({basis}) : {hits}"
