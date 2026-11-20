# -*- coding: utf-8 -*-
"""법인세 조문 노드(tax_nodes/beopin_*.py)의 원문을 법제처 현행 본문과 글자 단위로 대조한다 (2026-11-19).

노드 원문이 현행 조문 본문에 그대로 들어 있으면 '대조됨'으로 보고 tax_nodes/beopin_pan.py 의 대조 목록에 싣는다 — 그 노드만 mst 가 현행 판 번호가 된다.
원문을 줄여 적은 노드('…'·대괄호·' / ')는 줄인 자리에서 끊어 조각마다 본다. 풀어 쓴(요약한) 원문은 대조되지 않아 수집 당시의 법령ID 가 그대로 남는다.

실행: python scripts/experiments/check_beopin_text.py [--write]     (law.go.kr 접속 필요, 키 불필요)
  --write  대조 결과로 tax_nodes/beopin_pan.py 를 다시 쓴다. 없으면 현재 목록과의 차이만 출력한다.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import law_web  # noqa: E402
from tax_nodes import engine  # noqa: E402

법령들 = ("법인세법", "법인세법 시행령", "법인세법 시행규칙", "지방세법")
_태그 = re.compile(r"<(개정|신설|삭제)[^>]*>|\[(본조신설|전문개정|제목개정|본조제목개정|시행일)[^\]]*\]|\[종전 [^\]]*\]")
_머리 = re.compile(r"^제(\d+)조(?:의(\d+))?(?=[\(\s])")


def 정규(s: str) -> str:
    s = _태그.sub("", s)
    return re.sub(r"[\s\"“”‘’'ㆍ·․]", "", s)


def 조문들(text: str) -> dict:
    """본문 텍스트 → {"55의2": 정규화한 조문 본문}. 부칙 앞까지만 본다."""
    out, 키 = {}, None
    for ln in text.split("\n"):
        if re.match(r"^부\s*칙", ln):
            break
        m = _머리.match(ln)
        if m:
            키 = m.group(1) + ("의" + m.group(2) if m.group(2) else "")
            out.setdefault(키, "")
        if 키:
            out[키] += ln + "\n"
    return {k: 정규(v) for k, v in out.items()}


def 조각들(원문: str) -> list:
    """줄여 적은 자리(…, [ ], ' / ')에서 끊은 조각. 정규화 뒤 6자 미만은 버린다."""
    부분 = re.split(r"…|\.\.\.|\[[^\]]*\]| / ", 원문)
    return [x for x in (정규(p) for p in 부분) if len(x) >= 6]


def 대조() -> tuple:
    engine.모두올림()
    본문, 판 = {}, {}
    for 이름 in 법령들:
        r = law_web.fetch(이름)
        본문[이름], 판[이름] = 조문들(r["text"]), r["MST"]
    맞음, 안맞음 = [], []
    for nid, n in sorted(engine.전체().items()):
        if not n.fn or "beopin" not in n.fn.__module__:
            continue
        조 = 본문.get(n.법령, {}).get(n.조)
        조각 = 조각들(n.원문)
        if 조 and 조각 and all(c in 조 for c in 조각):
            맞음.append(nid)
        else:
            안맞음.append(nid)
    return 판, 맞음, 안맞음


if __name__ == "__main__":
    판, 맞음, 안맞음 = 대조()
    print("현행 판:", 판)
    print("대조됨 %d · 대조 안 됨 %d" % (len(맞음), len(안맞음)))
    경로 = os.path.join(ROOT, "tax_nodes", "beopin_pan.py")
    if "--write" in sys.argv:
        with open(경로, "w", encoding="utf-8") as f:
            f.write('"""법인세 조문 노드의 판(MST) 표 — scripts/experiments/check_beopin_text.py --write 가 쓴다. 손으로 고치지 않는다.\n\n'
                    "현행: 대조한 날 법제처 현행 본문의 법령일련번호. 대조: 원문이 그 본문에 글자 그대로 들어 있던 노드 id.\n"
                    '대조되지 않은 노드는 수집 당시의 법령ID(판을 가리키지 않는다)를 그대로 둔다.\n"""\n')
            f.write("대조일 = %r\n현행 = %r\n대조 = frozenset((\n" % (__import__("datetime").date.today().isoformat(), 판))
            for nid in 맞음:
                f.write("    %r,\n" % nid)
            f.write("))\n\n\ndef 판(법령: str, nid: str, 기본: str) -> str:\n"
                    '    """노드 id 가 대조 목록에 있으면 현행 판 번호, 아니면 기본(수집 당시 표기)."""\n'
                    "    return 현행[법령] if nid in 대조 and 법령 in 현행 else 기본\n")
        print("썼다:", 경로)
    else:
        try:
            from tax_nodes import beopin_pan
            print("목록에만 있음:", sorted(set(beopin_pan.대조) - set(맞음))[:20])
            print("새로 대조됨:", sorted(set(맞음) - set(beopin_pan.대조))[:20])
        except ImportError:
            pass
    for nid in 안맞음[:0]:
        print("  ✗", nid)
