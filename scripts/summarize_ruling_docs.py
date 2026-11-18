# -*- coding: utf-8 -*-
"""docs/RULING_LINKS.md · docs/RULING_CASES.md 를 저장소 안의 자료만으로 다시 만든다 (2026-11-18).

두 문서는 원래 scripts/link_rulings.py · scripts/summarize_node_cases.py 가 만들었는데 그 스크립트가 저장소에 없다.
이 스크립트는 그 둘의 '요약' 부분만 대신한다.

  python scripts/summarize_ruling_docs.py            # 두 문서를 다시 쓴다
  python scripts/summarize_ruling_docs.py --check    # 쓰지 않고, 지금 문서와 다르면 1 로 끝난다

읽는 것
  data/verification/rulings.jsonl        판례 색인
  data/verification/ruling_links.jsonl   판례가 인용한 조문 ↔ 현행 조문 ↔ 실행 노드 연결 (link_rulings.py 의 산출물)
  data/verification/node_cases/*.jsonl   판례 회귀 케이스
  tax_nodes/*.py                         '판례 회귀 …' 비고

하지 못하는 것 — 새 판례의 조문 연결
  인용 조문을 뽑아 현행 조문에 붙이는 일(현행일치·번호이동·구법 판정)은 판례 본문과 조문 연혁이 있어야 하고,
  그 규칙은 없어진 link_rulings.py 에만 있었다. 그래서 ruling_links.jsonl 에 없는 판례(색인에만 있는 건)는
  '연결 미생성'으로 세어 문서에 적기만 한다. RULING_LINKS.md 의 표는 ruling_links.jsonl 에 든 판례만의 통계다.

대조(2026-11-18): 종전 RULING_LINKS.md 의 수치(1318·1020·772·200, 상태별·기관별 건수)는 ruling_links.jsonl 에서 그대로 다시 나온다.
조문별 상위표는 한 줄(소득세법 시행령 §154: 종전 239, 지금 238)만 다르다 — 종전 문서가 만들어진 뒤 연결 파일이 한 번 더 바뀐 것으로 보인다.
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
VER = ROOT / "data" / "verification"
DOCS = ROOT / "docs"
NOTE_MAX = 85          # 종전 문서의 비고 한 줄 길이


def _jsonl(p: pathlib.Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _table(head, rows, nums: int = 1) -> list[str]:
    """nums: 오른쪽 정렬할 끝 열의 수."""
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * (len(head) - nums) + "---:|" * nums]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return out


def _by_count(counter, n=None):
    """건수 내림차순, 같은 건수는 처음 나온 순서(파이썬 정렬은 안정적이다)."""
    items = sorted(counter.items(), key=lambda kv: -kv[1])
    return items[:n] if n else items


def links_md() -> str:
    links = _jsonl(VER / "ruling_links.jsonl")
    색인 = {r["rid"] for r in _jsonl(VER / "rulings.jsonl")}
    상태, 기관 = collections.Counter(), collections.Counter()
    조문 = collections.defaultdict(set)
    for r in links:
        if r["연결노드"]:
            기관[r["기관"]] += 1
        for c in r["인용조문"]:
            상태[c["상태"]] += 1
            if c["노드"]:
                조문[(c["법령"], c["현행조"])].add(r["rid"])
    미생성 = 색인 - {r["rid"] for r in links}
    out = ["# 판례 ↔ 실행 노드 연결", "",
           "판례·심판례·예규가 인용한 조문을 현행 조문 제목과 대조해 실행 노드에 붙인 결과(`data/verification/ruling_links.jsonl`)의 요약이다. "
           "`scripts/summarize_ruling_docs.py`가 생성한다. 손으로 고치지 않는다.", "",
           "연결 파일을 만든 `scripts/link_rulings.py`는 저장소에 없다. 그 뒤 색인에 더해진 판례 %d건은 조문 연결이 만들어지지 않아 "
           "아래 표에 들지 않는다(회귀 케이스는 `docs/RULING_CASES.md`에 센다)." % len(미생성), ""]
    out += _table(("항목", "값"), [("판례 전체", len(links)),
                                  ("인용 조문이 1개 이상인 판례", sum(1 for r in links if r["인용조문"])),
                                  ("실행 노드에 연결된 판례", sum(1 for r in links if r["연결노드"])),
                                  ("판례가 붙은 조문(현행)", len(조문)),
                                  ("색인에만 있고 연결이 없는 판례", len(미생성))])
    out += ["", "## 인용 조문 연결 상태", ""] + _table(("상태", "건수"), _by_count(상태))
    out += ["", "## 연결된 판례의 기관", ""] + _table(("기관", "판례 수"), _by_count(기관))
    top = _by_count({k: len(v) for k, v in 조문.items()}, 40)
    out += ["", "## 판례가 많이 붙은 조문 (상위 40)", ""]
    out += _table(("법령", "조", "판례 수"), [(법, "§" + 조, n) for (법, 조), n in top])
    return "\n".join(out) + "\n"


def _node_notes() -> list[str]:
    seen, out = set(), []
    for p in sorted((ROOT / "tax_nodes").glob("*.py")):
        for line in p.read_text(encoding="utf-8").splitlines():
            i = line.find("판례 회귀")
            if i < 0:
                continue
            text = line[i:].split('"')[0][:NOTE_MAX].strip()      # 문자열 리터럴이 끝나는 따옴표까지
            key = (p.name, text)
            if key not in seen:
                seen.add(key)
                out.append("- %s: %s" % (p.name, text))
    return sorted(out)


def cases_md(run: bool = True) -> str:
    색인 = _jsonl(VER / "rulings.jsonl")
    links = _jsonl(VER / "ruling_links.jsonl")
    cases = [c for f in sorted((VER / "node_cases").glob("*.jsonl")) for c in _jsonl(f)]
    활성 = [c for c in cases if c.get("활성", True)]
    비활성 = [c for c in cases if not c.get("활성", True)]
    판례건 = [c for c in cases if c.get("rid")]
    불일치 = None
    if run:
        import verify_node_cases as v
        v._load_all()
        불일치 = sum(1 for c in 활성 if not v.run_case(c)[0])
    기관_검토, 기관_활성 = collections.defaultdict(set), collections.defaultdict(set)
    for c in 판례건:
        기관_검토[c.get("기관", "")].add(c["rid"])
        if c.get("활성", True):
            기관_활성[c.get("기관", "")].add(c["rid"])
    사유 = collections.Counter((c.get("제외사유") or "미기재").split(":")[0].strip() for c in 비활성)
    노드 = collections.Counter(n for c in 활성 for n in c.get("노드", []))
    out = ["# 판례 회귀 케이스", "",
           "판례·심판례·예규·해석·상담의 사실관계를 실행 노드 입력으로, 결론을 기대값으로 옮긴 회귀 케이스다. "
           "`scripts/summarize_ruling_docs.py`가 생성한다. 실행은 `scripts/verify_node_cases.py`, 벤치는 `docs/BENCH.md`의 '판례 회귀' 행.", ""]
    out += _table(("항목", "값"), [
        ("수집 판례", len(색인)),
        ("현행 노드에 자동 연결된 판례", sum(1 for r in links if r["연결노드"])),
        ("검토한 판례(케이스 기록 있음)", len({c["rid"] for c in 판례건})),
        ("활성 케이스가 있는 판례", len({c["rid"] for c in 판례건 if c.get("활성", True)})),
        ("활성 케이스", len(활성)),
        ("그중 판례 없는 설계 대조 케이스", sum(1 for c in 활성 if not c.get("rid"))),
        ("비활성 기록", len(비활성)),
        ("활성 케이스 불일치", "미실행" if 불일치 is None else 불일치),
        ("케이스가 시험하는 노드", len(노드))])
    out += ["", "## 기관별", ""]
    out += _table(("기관", "검토 판례", "활성 케이스 있는 판례"),
                  [(k, len(v), len(기관_활성.get(k, ()))) for k, v in sorted(기관_검토.items(), key=lambda kv: -len(kv[1]))], nums=2)
    out += ["", "## 비활성 사유", ""]
    out += _table(("사유", "건수"), _by_count(사유))
    out += ["", "사유 정의: 구법(판례 당시 규정이 바뀌어 현행 노드가 표현 못함) · 사실판단(증거·사실인정만 다툼) · 쟁점-노드밖(해당 법리의 노드 없음) · "
            "연결오류(자동 연결이 쟁점과 무관) · 정보부족 · 판례충돌(상급심 결론 우선) · 해석충돌(문언과 다른 확장해석).", ""]
    out += ["## 케이스가 많은 노드 (상위 30)", ""] + _table(("노드", "활성 케이스"), _by_count(노드, 30))
    out += ["", "## 판례 회귀로 고친 노드", "",
            "케이스 메모나 노드 비고에 '판례 회귀 R… 보정'이 있는 건. 노드 비고 전체 목록: `grep -rn \"판례 회귀 R\" tax_nodes/`.", ""]
    out += _node_notes()
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    diff = 0
    for name, text in (("RULING_LINKS.md", links_md()), ("RULING_CASES.md", cases_md())):
        p = DOCS / name
        if check:
            same = p.exists() and p.read_text(encoding="utf-8") == text
            print("%s: %s" % (name, "같음" if same else "다름"))
            diff += not same
        else:
            p.write_text(text, encoding="utf-8")
            print("%s: %d줄" % (name, text.count("\n")))
    return 1 if diff else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
