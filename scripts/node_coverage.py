# -*- coding: utf-8 -*-
"""실행 노드 커버리지 — "어느 조문이 아직 실행 노드(tax_nodes)로 옮겨지지 않았나"를 목록으로 만든다.

층이 둘이다.
  법문 코퍼스  data/legal_nodes/*.json  — 조문 원문·인용용. coverage_audit.py가 "코퍼스에 있나"를 센다.
  실행 노드    tax_nodes/*.py           — 조·항·호 = 함수 하나. 계산이 실제로 지나가는 노드.
이 스크립트는 둘째 층을 센다. coverage_audit.json(법령별 전 조문 + 세액영향 분류)을 정본으로 놓고
등록된 실행 노드를 역대조해서, 세액에 영향을 주는데 실행 노드가 없는 조문을 "전환 대기"로 뽑는다.
공개 저장소에서는 이 목록이 기여 메뉴다 — 한 줄이 조문 하나, 가져가서 노드 하나로 옮기면 끝.

사용
  py scripts/node_coverage.py                 # docs/NODE_COVERAGE.md 생성
  py scripts/node_coverage.py --out <path>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

AUDIT = ROOT / "data" / "coverage" / "coverage_audit.json"

# 세목 → [(법령, 장 필터)]. 장 필터가 있으면 '장' 문자열에 그 말이 들어간 조문만 그 세목으로 센다.
# 지방세법은 취득세·재산세가 한 법 안에 있고 소득세법은 종합소득과 양도소득이 한 법이라 장으로 갈라야
# "취득세 미착수 218"처럼 다른 세목 조문이 섞여 부풀지 않는다. None이면 그 법령 전체.
TAX_LAWS = {
    "재산세": [("지방세법", "재산세"), ("지방세법 시행령", "재산세")],
    "종부세": [("종합부동산세법", None), ("종합부동산세법 시행령", None), ("농어촌특별세법", None)],
    "취득세": [("지방세법", "취득세"), ("지방세법 시행령", "취득세"), ("지방세특례제한법", None)],
    "양도세": [("소득세법", "양도소득"), ("소득세법 시행령", "양도소득"), ("소득세법 시행규칙", "양도소득"),
             ("조세특례제한법", None), ("조세특례제한법 시행령", None)],
    "상증세": [("상속세 및 증여세법", None), ("상속세 및 증여세법 시행령", None), ("상속세 및 증여세법 시행규칙", None)],
    "재건축부담금": [("재건축초과이익 환수에 관한 법률", None), ("재건축초과이익 환수에 관한 법률 시행령", None)],
}


def _rows_for(report: dict, law: str, chapter: str | None):
    for r in report["법령"].get(law, []):
        if chapter and chapter not in (r.get("장") or ""):
            continue
        yield r


def _load_nodes():
    import tax_nodes  # noqa: F401
    import tax_nodes.jaesan  # noqa: F401
    import tax_nodes.jongbu  # noqa: F401
    import tax_nodes.chwideuk  # noqa: F401
    import tax_nodes.yangdo  # noqa: F401
    import tax_nodes.sangjeung  # noqa: F401
    import tax_nodes.jaegeonchuk  # noqa: F401
    import tax_nodes.yangdo_gammyeon  # noqa: F401
    import tax_nodes.yangdo_teukrye  # noqa: F401
    import tax_nodes.setdae_jutaeksu  # noqa: F401
    import tax_nodes.yangdo_bunyang  # noqa: F401
    import tax_nodes.yangdo_suyong  # noqa: F401
    import tax_nodes.jongbu_toji  # noqa: F401
    import tax_nodes.jongbu_setdae  # noqa: F401
    import tax_nodes.jaesan_toji  # noqa: F401
    import tax_nodes.yangdo_bisaeop  # noqa: F401
    import tax_nodes.yangdo_jungkwa  # noqa: F401
    import tax_nodes.yangdo_jotuk  # noqa: F401
    from tax_nodes import 전체
    return 전체()


def _article_key(조: str) -> tuple[int, int]:
    """'110' → (110, 0), '110의2' → (110, 2)"""
    m = re.match(r"(\d+)(?:의(\d+))?$", str(조))
    if not m:
        return (0, 0)
    return int(m.group(1)), int(m.group(2) or 0)


def build(audit: dict, nodes: dict) -> dict:
    by_article: dict[tuple, list] = defaultdict(list)
    for n in nodes.values():
        by_article[(n.법령,) + _article_key(n.조)].append(n)

    report = {"법령": {}, "요약": {}}
    for law, info in audit.items():
        rows = []
        for a in info["조문"]:
            key = (law, a["조문번호"], a["가지번호"])
            impl = by_article.get(key, [])
            rows.append({
                "조": "%d%s" % (a["조문번호"], ("의%d" % a["가지번호"]) if a["가지번호"] else ""),
                "제목": a["조문제목"], "장": a.get("장", ""), "분류": a.get("분류", ""),
                "부동산": bool(a.get("부동산도메인")), "코퍼스": bool(a.get("covered")),
                "범위밖": a.get("범위밖", ""),
                "실행노드": [n.id for n in impl],
                "항": sorted({(n.항, n.호) for n in impl}),
            })
        report["법령"][law] = rows

    for tax, laws in TAX_LAWS.items():
        tot = corp = impl = wait = 0
        for law, chapter in laws:
            for r in _rows_for(report, law, chapter):
                if r["범위밖"] or r["분류"] != "세액영향":
                    continue
                tot += 1
                if r["코퍼스"]:
                    corp += 1
                if r["실행노드"]:
                    impl += 1
                elif r["코퍼스"]:
                    wait += 1
        report["요약"][tax] = {"세액영향조문": tot, "코퍼스": corp, "실행노드": impl, "전환대기(코퍼스有)": wait,
                             "미착수(코퍼스無)": tot - corp}
    return report


def render(report: dict, node_count: int) -> str:
    out = ["# 실행 노드 커버리지", "",
           "조·항·호 하나가 함수 하나인 **실행 노드**가 세액영향 조문을 얼마나 덮는지 센다. "
           "`scripts/node_coverage.py`가 생성하며 손으로 고치지 않는다.", "",
           "- 등록된 실행 노드: **%d개**" % node_count,
           "- '전환 대기'는 법문 코퍼스(원문·인용)에는 있지만 실행 노드가 없는 조문이다. **기여 메뉴**가 이 목록이다: "
           "한 줄을 골라 `tax_nodes/`에 노드 하나로 옮기고, `data/verification/cases.jsonl`의 해당 케이스로 회귀를 돌린다.",
           "- '미착수'는 코퍼스에도 없는 조문이다. 먼저 원문을 `data/legal_nodes/`에 넣는 작업이 선행된다.", "",
           "## 세목별 요약", "",
           "| 세목 | 세액영향 조문 | 코퍼스 | 실행 노드 | 전환 대기 | 미착수 |",
           "|---|---:|---:|---:|---:|---:|"]
    for tax, s in report["요약"].items():
        out.append("| %s | %d | %d | %d | %d | %d |" % (tax, s["세액영향조문"], s["코퍼스"], s["실행노드"],
                                                      s["전환대기(코퍼스有)"], s["미착수(코퍼스無)"]))
    out.append("")

    out += ["## 전환 대기 — 코퍼스에 있고 실행 노드가 없는 세액영향 조문", ""]
    for tax, laws in TAX_LAWS.items():
        items = []
        for law, chapter in laws:
            for r in _rows_for(report, law, chapter):
                if r["범위밖"] or r["분류"] != "세액영향" or not r["코퍼스"] or r["실행노드"]:
                    continue
                items.append("- [ ] %s §%s %s" % (law, r["조"], r["제목"]))
        if items:
            out += ["### %s (%d)" % (tax, len(items)), ""] + items + [""]

    out += ["## 실행 노드가 있는 조문", ""]
    seen = set()
    for law, rows in report["법령"].items():
        for r in rows:
            if r["실행노드"]:
                k = (law, r["조"])
                if k in seen:
                    continue
                seen.add(k)
                hang = ", ".join(("%s항%s" % (h, (h2 + "호") if h2 else "")) if h else "본문"
                                 for h, h2 in r["항"])
                out.append("- %s §%s %s — %s" % (law, r["조"], r["제목"], hang))
    out.append("")

    out += ["## 미착수 — 코퍼스에도 없는 세액영향 조문 (원문 수록이 먼저)", ""]
    for tax, laws in TAX_LAWS.items():
        items = []
        for law, chapter in laws:
            for r in _rows_for(report, law, chapter):
                if r["범위밖"] or r["분류"] != "세액영향" or r["코퍼스"]:
                    continue
                items.append("- [ ] %s §%s %s" % (law, r["조"], r["제목"]))
        if items:
            out += ["<details><summary>%s (%d)</summary>" % (tax, len(items)), ""] + items + ["", "</details>", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "docs" / "NODE_COVERAGE.md")
    ap.add_argument("--json", type=pathlib.Path)
    args = ap.parse_args()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    nodes = _load_nodes()
    report = build(audit, nodes)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(report, len(nodes)), encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for tax, s in report["요약"].items():
        print("%-8s 세액영향 %3d · 코퍼스 %3d · 실행노드 %3d · 전환대기 %3d · 미착수 %3d" % (
            tax, s["세액영향조문"], s["코퍼스"], s["실행노드"], s["전환대기(코퍼스有)"], s["미착수(코퍼스無)"]))
    print("생성:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
