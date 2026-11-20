# -*- coding: utf-8 -*-
"""국세청 예규 본문 캐시를 복원한다 — data/verification/nts_bodies.jsonl → data/rulings/ntsCgmExpc_*.json

왜 필요한가: `data/rulings/` 는 .gitignore 라 새 복제본에는 본문이 없다. 그리고 국세청 본문
(taxlaw.nts.go.kr)은 **국내 망에서만** 받힌다 — 클라우드 세션에서는 443 이 TLS 인사에 응답하지 않는다
(scripts/fetch_rulings_web.py 머리말의 양쪽 실측). 그래서 국내 망 PC 가 한 번 받아 이 꾸러미로 올려 두고,
어느 컴퓨터·어느 세션이든 이것으로 캐시를 되살린다.

  python scripts/restore_nts_bodies.py            # 복원하고 rulings.jsonl 의 본문sha256 과 대조
  python scripts/restore_nts_bodies.py --force    # 이미 있는 파일도 다시 쓴다

새로 받은 본문을 꾸러미에 더하려면(국내 망에서):
  python scripts/fetch_rulings.py ntsCgmExpc '"<검색어>"'   또는  nts_detail(<ntstDcmId>)
  python scripts/restore_nts_bodies.py --pack               # data/rulings/ → 꾸러미로 다시 묶는다
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BUNDLE = ROOT / "data" / "verification" / "nts_bodies.jsonl"
INDEX = ROOT / "data" / "verification" / "rulings.jsonl"
OUT = ROOT / "data" / "rulings"


def _lines(p: pathlib.Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def pack() -> int:
    rows = []
    for p in sorted(OUT.glob("ntsCgmExpc_*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))["CgmExpcService"]
        rows.append({"rid": p.stem.split("_", 1)[1], **d})
    BUNDLE.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
                      encoding="utf-8")
    print(f"꾸러미 {len(rows)}건 다시 묶음: {BUNDLE}")
    return len(rows)


def restore(force: bool = False) -> int:
    if not BUNDLE.exists():
        print(f"꾸러미가 없다: {BUNDLE}")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    idx = {r["rid"]: r for r in _lines(INDEX)} if INDEX.exists() else {}
    n = skip = bad = 0
    for row in _lines(BUNDLE):
        rid = row.pop("rid")
        p = OUT / f"ntsCgmExpc_{rid}.json"
        if p.exists() and not force:
            skip += 1
        else:
            p.write_text(json.dumps({"CgmExpcService": row}, ensure_ascii=False, indent=1), encoding="utf-8")
            n += 1
        want = (idx.get(rid) or {}).get("본문sha256")
        got = hashlib.sha256((row.get("이유") or "").encode("utf-8")).hexdigest()
        if want and want != got:
            print(f"  ⚠ {rid}: 본문sha256 다름 (색인 {want[:12]}… ≠ 꾸러미 {got[:12]}…)")
            bad += 1
    print(f"복원 {n}건 · 이미 있어 건너뜀 {skip}건 · sha256 불일치 {bad}건 → {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--pack" in sys.argv:
        pack()
        raise SystemExit(0)
    raise SystemExit(restore("--force" in sys.argv))
