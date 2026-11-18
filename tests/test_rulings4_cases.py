"""분업 4차 '판례 회귀' 묶음 (2026-11-18) — data/verification/node_cases/rulings4_*.jsonl 의 형식과 결과.

본문은 www.law.go.kr 웹 화면에서 읽었다(scripts/fetch_rulings_web.py) — 법제처 법령해석례.
국세청 예규 본문(taxlaw.nts.go.kr)은 이 환경에서 받지 못해 케이스가 없다. 여기서는
1. 케이스 줄이 scripts/verify_node_cases.py 머리말의 형식에 맞는지,
2. rid 가 판례 색인(data/verification/rulings.jsonl)에 있는지, 노드 id 가 등록돼 있는지,
3. 활성 케이스가 판례 결론과 같은 결과를 내는지 본다.
판례와 노드가 갈리는 건은 _알려진_불일치 에 적어 둔다 — 고쳐지면 xfail 이 풀려 통과로 바뀐다(strict 아님).
"""
import importlib
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
verify_node_cases = importlib.import_module("verify_node_cases")

_DIR = ROOT / "data" / "verification" / "node_cases"
_FILES = sorted(_DIR.glob("rulings4_*.jsonl"))
_CASES = [(f.name, json.loads(l)) for f in _FILES for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
_IDS = [c["case_id"] for _, c in _CASES]
_알려진_불일치: dict = {}     # R315626-1(findings 150)은 2026-11-18 노드를 고쳐 통과한다
_제외사유 = ("구법", "사실판단", "정보부족", "쟁점-노드밖", "연결오류", "판례충돌", "해석충돌")


def test_files_exist_and_ids_unique():
    assert _FILES, "rulings4_*.jsonl 이 없다"
    assert len(_IDS) == len(set(_IDS))
    다른 = {json.loads(l)["case_id"] for f in _DIR.glob("*.jsonl") if not f.name.startswith("rulings4_")
          for l in f.read_text(encoding="utf-8").splitlines() if l.strip()}
    assert not (set(_IDS) & 다른), sorted(set(_IDS) & 다른)


@pytest.mark.parametrize("name, case", _CASES, ids=_IDS)
def test_case_shape(name, case):
    assert re.fullmatch(r"R%s-\d+[a-z]?" % re.escape(case["rid"]), case["case_id"])
    for k in ("기관", "의결일자", "사건", "결론요지", "노드", "메모"):
        assert k in case, k
    assert re.fullmatch(r"\d{8}", case["의결일자"])
    assert 0 < len(case["결론요지"]) <= 80
    assert isinstance(case["활성"], bool)
    if case["활성"]:
        assert case["방식"] in ("노드", "함수")
        assert case["기대"]
        if case["방식"] == "노드":
            assert case["세목"] and isinstance(case["연도"], int) and isinstance(case["사실"], dict)
        else:
            assert "." in case["함수"] and isinstance(case["인자"], dict)
    else:
        assert case["제외사유"].split(":")[0] in _제외사유


def test_rids_are_indexed_and_nodes_registered():
    색인 = {json.loads(l)["rid"] for l in (ROOT / "data" / "verification" / "rulings.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    assert not ({c["rid"] for _, c in _CASES} - 색인)
    verify_node_cases._load_all()
    from tax_nodes import engine
    없는 = {n for _, c in _CASES for n in c["노드"] if n not in engine._등록부}
    assert not 없는, sorted(없는)


@pytest.mark.parametrize("name, case", [(n, c) for n, c in _CASES if c["활성"]], ids=[c["case_id"] for _, c in _CASES if c["활성"]])
def test_active_case_matches_ruling(name, case):
    verify_node_cases._load_all()
    ok, detail = verify_node_cases.run_case(case)
    if case["case_id"] in _알려진_불일치:
        if not ok:
            pytest.xfail(_알려진_불일치[case["case_id"]])
        return
    assert ok, detail
