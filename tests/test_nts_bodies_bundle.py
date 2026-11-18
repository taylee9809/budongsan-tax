"""국세청 본문 꾸러미(data/verification/nts_bodies.jsonl)가 색인과 맞는지 — 인수인계 산출물 잠금.

`data/rulings/` 는 .gitignore 이고 국세청 본문은 국내 망에서만 받힌다(docs/HANDOFF_NTS_261118.md).
그래서 꾸러미가 유일한 전달 수단이다 — 색인의 본문sha256·본문길이와 어긋나면 복원이 깨진다.
"""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
_BUNDLE = ROOT / "data" / "verification" / "nts_bodies.jsonl"
_INDEX = ROOT / "data" / "verification" / "rulings.jsonl"


def _lines(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_bundle_matches_index():
    assert _BUNDLE.exists()
    idx = {r["rid"]: r for r in _lines(_INDEX)}
    rows = _lines(_BUNDLE)
    assert rows
    for row in rows:
        rid = row["rid"]
        assert rid in idx, f"{rid} 가 rulings.jsonl 에 없다"
        reason = row.get("이유") or ""
        assert hashlib.sha256(reason.encode("utf-8")).hexdigest() == idx[rid]["본문sha256"], rid
        assert len(reason) == idx[rid]["본문길이"], rid
        assert idx[rid]["target"] == "ntsCgmExpc"


def test_cases_bodies_present():
    """rulings4_nts_honin.jsonl 의 케이스는 꾸러미에 본문이 있어야 한다(다른 컴퓨터에서 읽으려면)."""
    rids = {r["rid"] for r in _lines(_BUNDLE)}
    cases = _lines(ROOT / "data" / "verification" / "node_cases" / "rulings4_nts_honin.jsonl")
    assert cases
    missing = [c["case_id"] for c in cases if c["rid"] not in rids]
    assert not missing, missing
