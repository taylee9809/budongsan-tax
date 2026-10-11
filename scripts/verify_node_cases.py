"""판례 회귀 케이스 실행기 — data/verification/node_cases/*.jsonl 의 케이스를 실행 노드로 돌려 판례 결론과 대조한다 (2026-10-11).

케이스 한 줄(JSON)
  case_id      "R<rid>-<n>"
  rid          판례 색인 rid (data/verification/rulings.jsonl)
  기관·의결일자·사건  판례 식별
  활성         true 면 실행, false 면 기록만(구법·사실판단 등으로 노드와 대조 불가)
  제외사유     활성 false 일 때 이유
  방식         "노드" | "함수"
    노드: 세목(실행기 세목, 예 "양도세"), 연도, 기준일(선택 "YYYYMMDD"), 사실{...}, 기대{산출이름: 값}
    함수: 함수("tax_nodes.모듈.함수명"), 인자{...}, 기대{결과 키 경로: 값}   — 경로는 "a.b.c"
  기대값 비교  숫자·문자·불은 정확히 같아야 함. dict 는 기대 dict 의 키가 실제에 모두 있고 값이 같으면 통과(부분일치).
               "__미적용__" 은 그 산출을 내는 노드가 모두 미적용(값 없음)이어야 함을 뜻한다.
  노드         이 케이스가 시험하는 노드 id 목록
  결론요지     판례 결론 인용(80자 이내), 쟁점 메모

실행: py -3 scripts/verify_node_cases.py [파일 ...]   (인자 없으면 node_cases/ 전체)
마지막 줄: "[판례 회귀] N건 — 불일치 M" (bench_nodes.py 가 읽는다)
"""
from __future__ import annotations

import importlib
import json
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_없음 = object()


def _load_all():
    for line in (ROOT / "scripts" / "node_coverage.py").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("import tax_nodes."):
            importlib.import_module(line.split()[1])


def _get(d, path):
    cur = d
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return _없음
    return cur


def _match(exp, got) -> bool:
    if isinstance(exp, str) and exp == "__미적용__":
        return got is _없음 or got is None
    if got is _없음:
        return False
    if isinstance(exp, dict) and isinstance(got, dict):
        return all(k in got and _match(v, got[k]) for k, v in exp.items())
    if isinstance(exp, bool) or isinstance(got, bool):
        return exp is got or exp == got
    if isinstance(exp, (int, float)) and isinstance(got, (int, float)):
        return abs(float(exp) - float(got)) < 1e-9
    if isinstance(exp, list) and isinstance(got, (list, tuple)):
        return len(exp) == len(got) and all(_match(a, b) for a, b in zip(exp, got))
    return exp == got


def run_case(c: dict):
    """(통과 여부, 상세) — 예외는 실패로 본다."""
    try:
        if c.get("방식", "노드") == "함수":
            modname, fn = c["함수"].rsplit(".", 1)
            res = getattr(importlib.import_module(modname), fn)(**c.get("인자", {}))
            fails = {k: {"기대": v, "실제": (None if _get(res, k) is _없음 else _get(res, k))} for k, v in c["기대"].items() if not _match(v, _get(res, k))}
            return not fails, fails
        from tax_nodes.engine import 실행
        kw = {"세목": c.get("세목", "")}
        if c.get("기준일"):
            kw["기준일"] = c["기준일"]
        ctx = 실행(dict(c.get("사실", {})), int(c["연도"]), **kw)
        fails = {}
        for k, v in c["기대"].items():
            try:
                got = ctx.값(k, _없음)
            except Exception as e:  # noqa: BLE001 — 노드 내부 오류도 실패로 기록
                got = "오류: %s" % e
            if not _match(v, got):
                fails[k] = {"기대": v, "실제": None if got is _없음 else got}
        return not fails, fails
    except Exception as e:  # noqa: BLE001
        return False, {"예외": "%s: %s" % (type(e).__name__, e), "위치": traceback.format_exc().splitlines()[-3:]}


def main(argv) -> int:
    _load_all()
    files = [pathlib.Path(a) for a in argv] or sorted((ROOT / "data" / "verification" / "node_cases").glob("*.jsonl"))
    total = bad = inactive = 0
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            c = json.loads(line)
            if not c.get("활성", True):
                inactive += 1
                continue
            total += 1
            ok, detail = run_case(c)
            if not ok:
                bad += 1
                print("DIFF %s (%s:%d) %s" % (c.get("case_id"), f.name, i, json.dumps(detail, ensure_ascii=False, default=str)[:600]))
    print("비활성(구법·사실판단 등) %d건" % inactive)
    print("[판례 회귀] %d건 — 불일치 %d" % (total, bad))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
