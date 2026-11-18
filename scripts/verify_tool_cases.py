# -*- coding: utf-8 -*-
"""도구 단위 검증 케이스 실행기 — data/verification/cases.jsonl 을 공개 도구에 그대로 넣어 기대값과 대조한다.

케이스 한 줄은 CONTRIBUTING.md 1절 형식이다(tool · input_json · expected_key · expected_json).
도구는 tax_overrides.py(대체 도구) → tax_judgment.py(판정기) → tax_server.py → 호스팅 전용 모듈 순으로 찾는다. 이 저장소에 없는
도구의 케이스는 '도구없음'으로 세고 실패로 치지 않는다 — 비공개 통합 서버 쪽 케이스가 섞여 있다.

실행: py scripts/verify_tool_cases.py [--tool 이름] [--case AQ-23] [--strict]
  --strict  불일치가 있으면 종료코드 1 (기본은 0 — 실패 케이스를 먼저 올리는 기여 방식을 막지 않는다)
마지막 줄: "[도구 케이스] N건 — 불일치 M · 회색지대 G · 도구없음 K"
"""
from __future__ import annotations

import argparse
import inspect
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = ROOT / "data" / "verification" / "cases.jsonl"


def _tools() -> dict:
    import tax_judgment
    import tax_server
    found = {t.name: t.fn for t in tax_server.mcp._tool_manager.list_tools()}
    # 판정 도구는 래퍼가 아니라 판정기(tax_judgment)를 직접 부른다 — 케이스 입력이 판정기 인자 기준이다.
    found.update({n: f for n, f in vars(tax_judgment).items()
                  if inspect.isfunction(f) and (n.startswith(("judge_", "count_", "calc_")))})
    try:  # 호스팅 서버에만 붙는 도구(생성 파일 밖)
        import corporate_tax
        found.update({n: getattr(corporate_tax, n) for n in getattr(corporate_tax, "TOOLS", ())})
    except ImportError:
        pass
    try:
        import building_property_tax
        found.update({n: getattr(building_property_tax, n) for n in getattr(building_property_tax, "TOOLS", ())})
    except ImportError:
        pass
    try:  # 증여 예시·추정 도구(상증법 §35·§44·§45)
        import gift_presumption
        found.update({n: getattr(gift_presumption, n) for n in getattr(gift_presumption, "TOOLS", ())})
    except ImportError:
        pass
    try:  # 생성 도구의 고친 판(호스팅 서버가 같은 이름으로 대체한다) — 판정기·생성 도구보다 우선
        import tax_overrides
        found.update(tax_overrides.OVERRIDES)
    except ImportError:
        pass
    return {k: v for k, v in found.items() if not inspect.iscoroutinefunction(v)}


def _same(exp, got) -> bool:
    if isinstance(exp, bool) or isinstance(got, bool):
        return exp is got
    if isinstance(exp, (int, float)) and isinstance(got, (int, float)):
        return abs(float(exp) - float(got)) < 1e-9
    return exp == got


def run(only_tool: str = "", only_case: str = "") -> tuple[int, list, int, list]:
    tools = _tools()
    total, bad, missing, gray = 0, [], 0, []
    for line in CASES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        if not c.get("활성", 1):
            continue
        if only_tool and c["tool"] != only_tool or only_case and c["case_id"] != only_case:
            continue
        fn = tools.get(c["tool"])
        if fn is None:
            missing += 1
            continue
        total += 1
        exp = json.loads(c["expected_json"])
        try:
            res = fn(**json.loads(c["input_json"]))
            got = res.get(c["expected_key"], "<키 없음>") if isinstance(res, dict) else res
        except Exception as e:  # noqa: BLE001 — 예외도 불일치로 기록
            got = "예외 %s: %s" % (type(e).__name__, e)
        if not _same(exp, got):
            # 회색지대(사실판단으로 갈린 재결례)는 기계 판정과 어긋나도 불일치로 세지 않는다 — 따로 적는다.
            (gray if c.get("회색지대") else bad).append(
                {"case_id": c["case_id"], "tool": c["tool"], "키": c["expected_key"],
                 "기대": exp, "실제": got, "사유": c.get("expected_사유", "")})
    return total, bad, missing, gray


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", default="")
    ap.add_argument("--case", default="")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    total, bad, missing, gray = run(a.tool, a.case)
    for b in bad:
        print("DIFF %s (%s) %s — 기대 %s · 실제 %s\n     근거: %s" % (
            b["case_id"], b["tool"], b["키"], json.dumps(b["기대"], ensure_ascii=False),
            json.dumps(b["실제"], ensure_ascii=False, default=str)[:200], b["사유"]))
    for g in gray:
        print("회색지대 %s (%s) — 기대 %s · 실제 %s" % (g["case_id"], g["tool"], g["기대"], g["실제"]))
    print("[도구 케이스] %d건 — 불일치 %d · 회색지대 %d · 도구없음 %d" % (total, len(bad), len(gray), missing))
    return 1 if (bad and a.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
