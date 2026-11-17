# -*- coding: utf-8 -*-
"""실행 노드 커버리지 — "어느 조문이 아직 실행 노드(tax_nodes)로 옮겨지지 않았나"를 목록으로 만든다.

층이 둘이다.
  법문 코퍼스  data/legal_nodes/*.json  — 조문 원문·인용용. coverage_audit.py가 "코퍼스에 있나"를 센다.
  실행 노드    tax_nodes/*.py           — 조·항·호 = 함수 하나. 계산이 실제로 지나가는 노드.
이 스크립트는 둘째 층을 센다. coverage_audit.json(법령별 전 조문 + 세액영향 분류)을 정본으로 놓고
등록된 실행 노드를 역대조해서, 세액에 영향을 주는데 실행 노드가 없는 조문을 "전환 대기"로 뽑는다.
공개 저장소에서는 이 목록이 기여 메뉴다 — 한 줄이 조문 하나, 가져가서 노드 하나로 옮기면 끝.

호·목 점검 (2026-11-17)
  위 집계는 조(條) 단위다. 지방세법 §111은 ①항 1호(토지)·3호(주택) 노드만 있어도 "실행 노드 있음"이 되어
  2호(건축물)가 비어 있는 것이 재산세 30/30 뒤에 가려졌다. 그래서 한 단계 더 내려가 센다:
  같은 항(또는 호) 아래에 호(또는 목) 단위 노드가 하나라도 있으면, 그 형제 호·목은 전부 노드가 있거나
  "왜 없어도 되는지"가 data/coverage/subunit_dispositions.json 에 적혀 있어야 한다.
  형제 목록의 정본은 data/coverage/subunits.json(법제처 원문의 항·호·목 구조)이다. 그 파일에 없는 조문은
  노드 번호만으로 사이 구멍(1·3호는 있는데 2호가 없음)을 찾는다 — 이때 맨 뒤 형제는 못 본다.
  조·항 단위 노드 하나가 각 호를 통째로 담은 조문은 점검하지 않는다(쪼갠 조문만 본다).

사용
  py scripts/node_coverage.py                 # docs/NODE_COVERAGE.md 생성
  py scripts/node_coverage.py --strict        # 처리 안 된 호·목 구멍이 있으면 종료코드 1
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
SUBUNITS = ROOT / "data" / "coverage" / "subunits.json"
DISPOSITIONS = ROOT / "data" / "coverage" / "subunit_dispositions.json"
_항기호 = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_목순서 = "가나다라마바사아자차카타파하"
#: 처리 구분 — 구멍으로 세지 않는 사유. 이 밖의 값은 거부한다.
처리구분 = ("삭제", "범위밖", "상위노드", "다른노드")

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
    # 법인의 부동산 양도 (2026-11-17). coverage_audit.py 의 SCOPE_ONLY 조문만 범위 안이다.
    "법인세(부동산 양도)": [("법인세법", None), ("법인세법 시행령", None)],
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
    import tax_nodes.chwideuk_gwase  # noqa: F401
    import tax_nodes.jiteuk_chwideuk  # noqa: F401
    import tax_nodes.jiteuk_entity  # noqa: F401
    import tax_nodes.yangdo_sodeuk_rest  # noqa: F401
    import tax_nodes.yangdo_jotuk_rest  # noqa: F401
    import tax_nodes.sangjeung_rest  # noqa: F401
    import tax_nodes.sangjeung_pyeongga  # noqa: F401
    import tax_nodes.jaesan_rest  # noqa: F401
    import tax_nodes.jongbu_rest  # noqa: F401
    import tax_nodes.jaegeonchuk_rest  # noqa: F401
    import tax_nodes.jotuk_gita_1  # noqa: F401
    import tax_nodes.jotuk_gita_2  # noqa: F401
    import tax_nodes.jotuk_gita_3  # noqa: F401
    import tax_nodes.jotuk_gita_4  # noqa: F401
    import tax_nodes.jotuk_gita_5  # noqa: F401
    import tax_nodes.jotuk_gita_6  # noqa: F401
    import tax_nodes.jotuk_gita_7  # noqa: F401
    import tax_nodes.jotuk_gita_8  # noqa: F401
    import tax_nodes.gibon_jeolcha  # noqa: F401
    import tax_nodes.yangdo_gigan  # noqa: F401
    import tax_nodes.chwideuk_saryeo  # noqa: F401
    import tax_nodes.sangjeung_boyu_rest  # noqa: F401
    import tax_nodes.yangdo_gita_a  # noqa: F401
    import tax_nodes.yangdo_gita_b  # noqa: F401
    import tax_nodes.sangjeung_gasanse  # noqa: F401
    import tax_nodes.chwideuk_gasanse  # noqa: F401
    import tax_nodes.beobin  # noqa: F401
    import tax_nodes.jaesan_geonchuk  # noqa: F401
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
                             "미착수(코퍼스無)": tot - corp,
                             "감사없음": [law for law, _ in laws if law not in audit]}
    return report


def _호키(h: str):
    m = re.match(r"(\d+)(?:의(\d+))?$", str(h))
    return (int(m.group(1)), int(m.group(2) or 0)) if m else None


def _표기(법령: str, 조: str, 항: str, 호: str = "", 목: str = "") -> str:
    s = "%s §%s" % (법령, 조)
    if 항:
        i = int(항) if str(항).isdigit() else 0
        s += _항기호[i - 1] if 1 <= i <= len(_항기호) else "제%s항" % 항
    if 호:
        s += "%s%s호" % ("" if 항 else " ", 호)
    if 목:
        s += "%s목" % 목
    return s


def subunit_gaps(nodes: dict, subunits: dict, dispositions: dict) -> dict:
    """같은 부모 아래 형제 호·목 가운데 실행 노드가 없는 것을 찾는다.

    nodes        등록된 실행 노드
    subunits     {법령: {조: [{"항","호","목","삭제","요지"}...]}} — 법제처 원문 구조(없으면 번호만으로 추정)
    dispositions {"표기": {"처리": 처리구분 중 하나, "사유": str}}
    반환 {"미처리": [...], "처리": [...], "점검부모": n, "정본부모": n, "묵은처리": [...]}
    """
    호있음: dict[tuple, set] = defaultdict(set)   # (법령, 조, 항) → 노드가 있는 호
    목있음: dict[tuple, set] = defaultdict(set)   # (법령, 조, 항, 호) → 노드가 있는 목
    for n in nodes.values():
        if not re.match(r"\d+(의\d+)?$", n.조):      # 부칙 등 본문 밖 조문은 형제 비교가 안 된다
            continue
        if n.호 and _호키(n.호):
            호있음[(n.법령, n.조, str(n.항))].add(str(n.호))
        if n.목:
            for m in re.split(r"[·,\s]+", n.목):       # '나·다'처럼 한 노드가 여러 목을 담은 경우
                if m in _목순서:
                    목있음[(n.법령, n.조, str(n.항), str(n.호))].add(m)
    # 부모 단위 노드의 원문 — 그 원문이 형제 호·목을 그대로 싣고 있으면 부모 노드가 담은 것으로 본다
    부모원문: dict[tuple, str] = defaultdict(str)
    for n in nodes.values():
        if not n.목:
            부모원문[(n.법령, n.조, str(n.항), str(n.호))] += " " + (n.원문 or "")

    정본: dict[tuple, list] = defaultdict(list)    # 부모 → 형제 [(이름, 삭제, 요지)]
    for 법령, 조들 in subunits.items():
        if 법령.startswith("_"):
            continue
        for 조, 단위들 in 조들.items():
            for u in 단위들:
                if u.get("목"):
                    정본[(법령, 조, u.get("항", ""), u["호"])].append((u["목"], bool(u.get("삭제")), u.get("요지", "")))
                elif u.get("호"):
                    정본[(법령, 조, u.get("항", ""))].append((u["호"], bool(u.get("삭제")), u.get("요지", "")))

    found, n_parent, n_canon = [], 0, 0
    for 부모, 있음 in sorted(list(호있음.items()) + list(목있음.items())):
        n_parent += 1
        단계 = "호" if len(부모) == 3 else "목"
        if 부모 in 정본:
            n_canon += 1
            형제 = 정본[부모]
            출처 = "원문"
        elif 단계 == "호":
            끝 = max(_호키(h)[0] for h in 있음)
            형제 = [(str(i), False, "") for i in range(1, 끝 + 1)]
            출처 = "번호추정"
        else:
            끝 = max(_목순서.index(m) for m in 있음)
            형제 = [(_목순서[i], False, "") for i in range(끝 + 1)]
            출처 = "번호추정"
        for 이름, 삭제, 요지 in 형제:
            if 이름 in 있음:
                continue
            if 단계 == "호":
                # 그 호 아래 목 단위 노드가 있으면 호는 덮인 것으로 본다
                if any(k[:3] == 부모 and k[3] == 이름 for k in 목있음):
                    continue
                표기 = _표기(부모[0], 부모[1], 부모[2], 이름)
                상위 = bool(re.search(r"(?<![\d§제의])%s\.\s" % re.escape(이름), 부모원문.get((부모[0], 부모[1], 부모[2], ""), "")))
            else:
                표기 = _표기(부모[0], 부모[1], 부모[2], 부모[3], 이름)
                상위 = bool(re.search(r"(?<![가-힣])%s\.\s" % 이름, 부모원문.get(부모, "")))
            found.append({"표기": 표기, "법령": 부모[0], "조": 부모[1], "단계": 단계, "출처": 출처, "상위원문": 상위,
                          "원문삭제": 삭제, "요지": 요지,
                          "있는형제": sorted(있음, key=lambda x: (_호키(x) or (0, 0)) if 단계 == "호" else _목순서.index(x))})

    미처리, 처리 = [], []
    쓰인 = set()
    for g in found:
        d = dispositions.get(g["표기"])
        if g["상위원문"] and not d:
            처리.append(dict(g, 처리="상위노드", 사유="상위 단위 노드의 원문에 이 %s가 실려 있다(자동 판정)" % g["단계"]))
        elif g["원문삭제"]:
            처리.append(dict(g, 처리="삭제", 사유="원문 '삭제'"))
            쓰인.add(g["표기"])
        elif d:
            if d.get("처리") not in 처리구분 or not d.get("사유"):
                raise ValueError("%s: 처리는 %s 중 하나이고 사유가 있어야 한다" % (g["표기"], "·".join(처리구분)))
            처리.append(dict(g, 처리=d["처리"], 사유=d["사유"]))
            쓰인.add(g["표기"])
        else:
            미처리.append(g)
    묵은 = sorted(k for k in dispositions if not k.startswith("_") and k not in 쓰인)
    return {"미처리": 미처리, "처리": 처리, "점검부모": n_parent, "정본부모": n_canon, "묵은처리": 묵은}


def render_subunits(sub: dict) -> list[str]:
    out = ["## 호·목 점검 — 형제는 노드가 있는데 빠진 호·목", "",
           "조 단위 집계가 가리는 구멍을 찾는다. 같은 항·호 아래 형제 가운데 일부만 노드로 옮겨져 있으면 나머지를 여기 적는다. "
           "형제 목록은 법제처 원문 구조(`data/coverage/subunits.json`)에서 읽고, 없어도 되는 사유는 "
           "`data/coverage/subunit_dispositions.json`에 적는다.", "",
           "- 점검한 부모(항·호): **%d개** — 원문 구조로 대조 %d개, 번호만으로 추정 %d개" % (
               sub["점검부모"], sub["정본부모"], sub["점검부모"] - sub["정본부모"]),
           "- 노드가 없는 형제: %d개 — 사유 있음 %d개, **전환 대기 %d개**" % (
               len(sub["미처리"]) + len(sub["처리"]), len(sub["처리"]), len(sub["미처리"])), ""]
    out += ["### 전환 대기 (%d)" % len(sub["미처리"]), ""]
    for g in sub["미처리"]:
        tail = " — %s" % g["요지"] if g["요지"] else ""
        est = " (번호 추정 — 원문 확인 필요)" if g["출처"] == "번호추정" else ""
        out.append("- [ ] %s%s%s" % (g["표기"], tail, est))
    if not sub["미처리"]:
        out.append("없음")
    out += ["", "<details><summary>사유가 적힌 것 (%d)</summary>" % len(sub["처리"]), "",
            "| 호·목 | 처리 | 사유 |", "|---|---|---|"]
    for g in sub["처리"]:
        out.append("| %s | %s | %s |" % (g["표기"], g["처리"], g["사유"].replace("|", "/")))
    out += ["", "</details>", ""]
    if sub["묵은처리"]:
        out += ["처리 파일에 있지만 지금은 구멍이 아닌 항목(노드가 생겼거나 표기가 바뀜 — 지워도 된다): "
                + ", ".join(sub["묵은처리"]), ""]
    return out


def render(report: dict, node_count: int, sub: dict | None = None) -> str:
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
        if s.get("감사없음") and not s["세액영향조문"]:
            out.append("| %s | — | — | — | — | — |" % tax)
            continue
        out.append("| %s | %d | %d | %d | %d | %d |" % (tax, s["세액영향조문"], s["코퍼스"], s["실행노드"],
                                                      s["전환대기(코퍼스有)"], s["미착수(코퍼스無)"]))
    out.append("")
    없음 = sorted({law for s in report["요약"].values() for law in s.get("감사없음", [])})
    if 없음:
        out += ["'—'는 아직 세지 못한 세목이다: %s 이(가) `data/coverage/coverage_audit.json`에 없다. "
                "`LAW_OC=… py scripts/coverage_audit.py %s` 를 돌린 뒤 이 스크립트를 다시 돌리면 채워진다." % (
                    "·".join(없음), " ".join('"%s"' % x for x in 없음)), ""]
    if sub is not None:
        out += ["위 표는 조(條) 단위다. 조 안의 호·목 누락은 아래 '호·목 점검'이 따로 센다 — "
                "**호·목 전환 대기 %d개**." % len(sub["미처리"]), ""]

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

    if sub is not None:
        out += render_subunits(sub)

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
    ap.add_argument("--strict", action="store_true", help="처리 안 된 호·목 구멍이 있으면 종료코드 1")
    args = ap.parse_args()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    nodes = _load_nodes()
    report = build(audit, nodes)
    subunits = json.loads(SUBUNITS.read_text(encoding="utf-8")) if SUBUNITS.exists() else {}
    dispositions = json.loads(DISPOSITIONS.read_text(encoding="utf-8")) if DISPOSITIONS.exists() else {}
    sub = subunit_gaps(nodes, subunits, dispositions)
    report["호목점검"] = sub
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(report, len(nodes), sub), encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for tax, s in report["요약"].items():
        if s.get("감사없음") and not s["세액영향조문"]:
            print("%-8s 조문 감사 없음 — coverage_audit.py 를 %s 에 돌려야 센다" % (tax, "·".join(s["감사없음"])))
            continue
        print("%-8s 세액영향 %3d · 코퍼스 %3d · 실행노드 %3d · 전환대기 %3d · 미착수 %3d" % (
            tax, s["세액영향조문"], s["코퍼스"], s["실행노드"], s["전환대기(코퍼스有)"], s["미착수(코퍼스無)"]))
    print("호·목 점검  부모 %d(원문 대조 %d) · 노드 없는 형제 %d · 사유 있음 %d · 전환 대기 %d" % (
        sub["점검부모"], sub["정본부모"], len(sub["미처리"]) + len(sub["처리"]), len(sub["처리"]), len(sub["미처리"])))
    for g in sub["미처리"]:
        print("  [ ] %s%s" % (g["표기"], " — " + g["요지"] if g["요지"] else ""))
    print("생성:", args.out)
    return 1 if (args.strict and sub["미처리"]) else 0


if __name__ == "__main__":
    sys.exit(main())
