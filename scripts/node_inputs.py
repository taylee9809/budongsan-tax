"""노드가 읽는 사실 키·산출·소스를 보여 준다 — 판례 케이스를 만들 때 입력 이름을 확인하는 도구.

실행: py -3 scripts/node_inputs.py <노드id 또는 법령|조> [...]
  예) py -3 scripts/node_inputs.py 소득세법시행령-155-1
      py -3 scripts/node_inputs.py "소득세법 시행령|155"
"""
from __future__ import annotations

import importlib
import inspect
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv) -> int:
    for line in (ROOT / "scripts" / "node_coverage.py").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("import tax_nodes."):
            importlib.import_module(line.split()[1])
    from tax_nodes.engine import 전체, _산출표
    N = 전체()
    for q in argv:
        if "|" in q:
            law, jo = q.split("|", 1)
            ids = [i for i, n in N.items() if n.법령 == law and str(n.조) == jo]
        else:
            ids = [q] if q in N else [i for i in N if i.startswith(q)]
        if not ids:
            print("== %s: 노드 없음" % q)
            continue
        for i in ids:
            n = N[i]
            src = inspect.getsource(n.fn)
            facts = sorted(set(re.findall(r'사실값\(\s*"([^"]+)"', src)))
            vals = sorted(set(re.findall(r'(?<!사실)값\(\s*"([^"]+)"', src)))
            print("== %s  [%s §%s%s%s] 세목=%r  모듈=%s" % (i, n.법령, n.조, ("①②③④⑤⑥⑦⑧⑨⑩"[int(n.항) - 1] if str(n.항).isdigit() and 0 < int(n.항) <= 10 else (" " + str(n.항) + "항" if n.항 else "")),
                                                      (" %s호" % n.호) if n.호 else "", n.세목, n.fn.__module__))
            print("   제목: %s" % n.제목)
            print("   산출: %s   필요: %s   우선순위: %s" % (list(n.산출), list(n.필요 or ()), n.우선순위))
            print("   사실 입력: %s" % facts)
            print("   다른 산출 의존: %s" % [(v, _산출표.get(v, [])[:3]) for v in vals])
            if n.시행일 or n.종료일:
                print("   시행일 %s 종료일 %s" % (n.시행일, n.종료일))
            if n.비고:
                print("   비고: %s" % n.비고)
            print("   " + "\n   ".join(src.splitlines()[:80]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
