# -*- coding: utf-8 -*-
"""검증 정본(JSONL) ↔ 검증 DB 동기화.

  py scripts/verification_sync.py --export    # DB → data/verification/*.jsonl  (커밋 전 필수)
  py scripts/verification_sync.py --rebuild   # JSONL → DB 재생성 (클론 직후·정본 수정 후)
  py scripts/verification_sync.py --check     # 재생성 후 export 결과가 정본과 같은지 왕복 검사
  py scripts/verification_sync.py --check-hierarchy  # 정답지 우선순위 위반 스캔 (S4 등급강등 등)

정본은 `data/verification/*.jsonl` — git이 추적하는 증거다. 줄 단위로 diff가 찍혀서
"어느 커밋에서 어떤 케이스·결과·발견이 바뀌었나"가 그대로 보인다.
`data/tax_cases.db`는 여기서 만들어지는 조회용 파생물이라 git에 넣지 않는다.

재결례 '이유' 전문은 정본에 넣지 않고 sha256만 남긴다. 부피의 90%인데 공개 API에서
다시 받을 수 있고, 해시가 있으면 "우리가 검증한 텍스트가 그거였다"는 증명된다.
본문 캐시가 없으면 --rebuild가 '본문없음' 건수를 알려준다 → scripts/fetch_rulings.py 로 재수집.
"""
import argparse
import filecmp
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tax_case_store as store  # noqa: E402


def _check() -> int:
    """정본 → DB → 정본 왕복이 바이트 동일한지 확인한다."""
    src = store.VERIF_DIR
    with tempfile.TemporaryDirectory() as tmp:
        backup = pathlib.Path(tmp) / "before"
        shutil.copytree(src, backup)
        print("rebuild:", store.import_jsonl(reset=True))
        print("export :", store.export_jsonl())
        diff = []
        for f in sorted(backup.glob("*.jsonl")):
            if not filecmp.cmp(f, src / f.name, shallow=False):
                diff.append(f.name)
        if diff:
            print("왕복 불일치:", ", ".join(diff))
            return 1
        print("왕복 일치 — 정본과 DB가 같은 내용입니다")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--export", action="store_true")
    g.add_argument("--rebuild", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--check-hierarchy", action="store_true")
    a = ap.parse_args()

    if a.export:
        print(store.export_jsonl())
    elif a.rebuild:
        print(store.import_jsonl(reset=True))
        print(store.stats())
    elif a.check_hierarchy:
        violations = store.check_source_hierarchy()
        if violations:
            print(f"위반 {len(violations)}건:")
            for v in violations:
                print(f"  [{v['유형']}] {v.get('case_id') or ''} {v.get('tool') or ''} — {v['설명']}")
            return 1
        print("정답지 우선순위 위반 없음")
    else:
        return _check()
    return 0


if __name__ == "__main__":
    sys.exit(main())
