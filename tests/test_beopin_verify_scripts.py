"""법인세 조문 노드(tax_nodes/beopin_*.py)의 조문값 자체 검증 스크립트가 불일치 0 인지 (2026-11-19).

scripts/experiments/verify_beopin_*.py 는 조문 산식을 손으로 적용한 기대값과 노드 값을 맞대는 스크립트다(원본 저장소에서 2026-10-16 작성,
통일 때 판정이 갈린 항목만 원문 근거로 기대값을 고쳤다 — data/verification/findings.jsonl 230~). 마지막 줄 "[…] N건 — 불일치 M" 을 읽는다.
"""
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
스크립트 = sorted((ROOT / "scripts" / "experiments").glob("verify_beopin_*.py"))


def test_all_four_scripts_are_present():
    assert [p.name for p in 스크립트] == ["verify_beopin_imdae.py", "verify_beopin_jasan.py", "verify_beopin_oeguk.py", "verify_beopin_toji.py"]


@pytest.mark.parametrize("path", 스크립트, ids=[p.stem for p in 스크립트])
def test_script_reports_zero_mismatch(path):
    r = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
    마지막 = (r.stdout.strip().splitlines() or [""])[-1]
    m = re.search(r"(\d+)건 — 불일치 (\d+)", 마지막)
    assert m, r.stdout[-2000:] + r.stderr[-2000:]
    assert int(m.group(1)) >= 200 and int(m.group(2)) == 0 and r.returncode == 0, r.stdout[-3000:]


def test_edition_table_lists_only_registered_nodes():
    # tax_nodes/beopin_pan.py — 현행 본문과 대조된 노드 목록. 목록의 id 는 전부 등록된 법인세 노드여야 하고, 그 노드의 mst 는 현행 판 번호여야 한다.
    from tax_nodes import beopin_pan, engine
    engine.모두올림()
    노드 = engine.전체()
    assert beopin_pan.대조 and not [i for i in beopin_pan.대조 if i not in 노드]
    for nid in beopin_pan.대조:
        assert 노드[nid].mst == beopin_pan.현행[노드[nid].법령], nid


def test_no_duplicate_corporate_modules():
    # 통일 뒤에는 공개판 모듈(beobin·beobin_bisaeop)과 대기 폴더가 없어야 한다 — 같은 조문의 노드가 두 벌 올라오지 않게.
    assert not (ROOT / "tax_nodes" / "beobin.py").exists() and not (ROOT / "tax_nodes" / "beobin_bisaeop.py").exists()
    assert not (ROOT / "incoming_private").exists()
