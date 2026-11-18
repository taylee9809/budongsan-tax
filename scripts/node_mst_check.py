# -*- coding: utf-8 -*-
"""법령 판 대조 — 실행 노드와 검증상수가 인용한 판(MST)이 현행인지, 아니면 그 사이 본문이 달라졌는지.

노드는 `mst="287223"`처럼 원문을 확인한 판(법령일련번호)을 적어 둔다. 법령이 개정되면 현행 MST 가 바뀌는데
노드는 옛 번호를 그대로 들고 있다 — 이 스크립트가 그 차이를 표로 만들고, 판이 바뀐 법령은 "노드가 있는 조문 중
본문이 달라진 조문"을 뽑는다. **노드를 고치지는 않는다.** 목록만 낸다.

하는 일 (law.go.kr 웹 본문 — scripts/law_web.py, 키 불필요)
  1. tax_nodes 의 노드를 (법령, mst)로 묶고, data/tax_params.json 의 검증상수 MST 를 근거 법령별로 묶는다
  2. 법령마다 현행 판(MST·시행일·공포일)을 받아 대조한다. 노드의 mst 값은 네 가지다:
       현행        현행 MST 와 같다
       옛 판       다른 법령일련번호 — 그 판의 본문을 받아 현행과 조문별로 비교한다
       법령ID      "005077" 같은 법령ID(판이 아니라 법령 자체의 번호) — 어느 판을 확인했는지 알 수 없다
       알 수 없는 번호  법령ID 꼴(0으로 시작하는 6자리)인데 이 법령의 ID 가 아니다
       미기재      빈 값
  3. 옛 판을 인용한 노드의 조문 가운데 본문이 달라진 것을 적는다. 본문 비교는 공백을 뺀 조문 전체 텍스트이고,
     그 조문의 개정 태그(<개정 2026. 9. 30.> 등) 중 옛 판의 공포일 뒤의 날짜를 함께 적는다.
  4. 법령ID·미기재 노드는 기준 판이 없으므로 --since(기본 20260101) 이후 개정 태그가 붙은 조문만 따로 적는다.

사용
  py scripts/node_mst_check.py                    # data/coverage/node_mst_check.md 생성 + 요약 출력
  py scripts/node_mst_check.py --since 20250101
  py scripts/node_mst_check.py --refresh          # 웹 캐시를 버리고 다시 받는다
  py scripts/node_mst_check.py --strict           # 옛 판을 인용한 노드 조문 중 달라진 것이 있으면 종료코드 1

한계
  - 조 단위 비교다. 노드가 ①항만 옮겼는데 ③항이 바뀐 경우도 "달라짐"으로 나온다(달라진 항은 태그 날짜로 좁혀 적는다).
  - 옛 판 본문은 law.go.kr 이 그 판을 계속 실어 줄 때만 받을 수 있다. 못 받으면 태그 날짜만으로 판단하고 그렇게 적는다.
  - 별표·서식은 보지 않는다(본문 조문만).
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
sys.path.insert(0, str(ROOT / "scripts"))

import law_web  # noqa: E402

OUT = ROOT / "data" / "coverage" / "node_mst_check.md"
PARAMS = ROOT / "data" / "tax_params.json"


def base_law(name: str) -> str:
    """'지방세법 시행령 부칙(대통령령 제30939호, 2020.8.12.)' → '지방세법 시행령'"""
    return re.sub(r"\s*부칙\s*\(.*$", "", name).strip()


def norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def articles_of(law: dict) -> dict:
    """{조: {"본문", "개정일", "항": {항번호: [개정일…]}, "제목", "삭제", "장래"}} — 현행 판 기준(pick_versions)."""
    out = {}
    for u in law_web.pick_versions(law_web.parse_text(law["text"])):
        if u["조문여부"] != "조문":
            continue
        jo = "%d%s" % (u["조문번호"], ("의%d" % u["가지번호"]) if u["가지번호"] else "")
        hang = {}
        for h in u["항"]:
            dates = list(h["개정일"])
            for o in h["호"]:
                dates += o["개정일"]
                for k in o["목"]:
                    dates += k["개정일"]
            hang[h["번호"]] = dates
        out[jo] = {"본문": u["본문"], "개정일": sorted(set(u["개정일"])), "항": hang, "제목": u["조문제목"],
                   "삭제": u["삭제"], "장래": u.get("장래") or (u.get("다른판") or {}).get("장래")}
    return out


def changed_since(cur: dict, date: str) -> dict:
    """현행 조문 가운데 date(YYYYMMDD) 뒤의 개정 태그가 있는 것 → {조: {"날짜": […], "항": [항번호…]}}"""
    out = {}
    for jo, a in cur.items():
        d = [x for x in a["개정일"] if x > date]
        if d:
            out[jo] = {"날짜": d, "항": sorted(h for h, ds in a["항"].items() if any(x > date for x in ds))}
    return out


def load_nodes() -> dict:
    import node_coverage
    return node_coverage._load_nodes()


def param_msts() -> dict:
    """검증상수의 MST → {(법령, mst): [키…]}. 연혁확인(과거 판 대조 기록)은 일부러 옛 판이므로 보지 않는다."""
    import coverage_audit
    out = defaultdict(list)
    data = json.loads(PARAMS.read_text(encoding="utf-8"))
    for p in data.get("params", []):
        mst = str(p.get("MST", "")).strip()
        if not mst:
            continue
        laws = sorted({law for law, _, _ in coverage_audit.parse_refs(str(p.get("근거", "")))})
        m = re.match(r"\s*([가-힣 ]+?(?:법률|법)(?:\s*시행령|\s*시행규칙)?)\s*§", str(p.get("근거", "")))
        law = coverage_audit.canon(m.group(1)) if m else (laws[0] if laws else "?")
        out[(law, mst)].append(str(p.get("키", "")))
    return out


def classify(mst: str, cur: dict) -> str:
    if not mst:
        return "미기재"
    if mst == cur["MST"]:
        return "현행"
    if mst == cur.get("법령ID"):
        return "법령ID"
    if mst.isdigit() and len(mst) == 6 and mst.startswith("0"):
        return "알 수 없는 번호"          # 법령ID 꼴이지만 이 법령의 ID 가 아니다
    if not mst.isdigit():
        return "글로 적음"
    return "옛 판"


def check(since: str = "20260101", refresh: bool = False, log=print) -> dict:
    nodes = load_nodes()
    by_law = defaultdict(lambda: defaultdict(list))           # 법령 → mst → [노드]
    for n in nodes.values():
        by_law[base_law(n.법령)][str(n.mst or "")].append(n)
    params = param_msts()
    for (law, mst) in params:
        by_law[law].setdefault(mst, [])
    rows, details, undated, failures = [], [], [], []
    for law in sorted(by_law):
        try:
            cur = law_web.fetch(law, refresh=refresh)
        except Exception as exc:  # noqa: BLE001
            failures.append((law, str(exc)))
            log("  !! %s: %s" % (law, exc))
            continue
        cur_art = articles_of(cur)
        for mst in sorted(by_law[law]):
            ns = by_law[law][mst]
            keys = params.get((law, mst), [])
            kind = classify(mst, cur)
            row = {"법령": law, "인용": mst or "(없음)", "구분": kind, "노드": len(ns), "상수": len(keys),
                   "현행MST": cur["MST"], "현행시행": cur["시행일자"], "현행공포": cur["공포일자"], "현행공포번호": cur["공포번호"],
                   "옛시행": "", "옛공포": "", "달라진조문": None, "비고": ""}
            node_jo = defaultdict(list)                        # 조 → 노드 id
            for n in ns:
                if re.match(r"\d+(의\d+)?$", str(n.조)) and n.법령 == law:
                    node_jo[str(n.조)].append(n)
            if kind == "옛 판":
                old = None
                try:
                    old = law_web.fetch(law, mst=mst)
                except Exception as exc:  # noqa: BLE001
                    row["비고"] = "옛 판 본문을 받지 못함(%s)" % str(exc)[:60]
                if old and old["법령명"] != law:
                    row["비고"] = "이 번호는 「%s」의 판이다" % old["법령명"]
                    row["구분"] = "다른 법령의 번호"
                    old = None
                if old:
                    row["옛시행"], row["옛공포"] = old["시행일자"], old["공포일자"]
                    if old["시행일자"] > cur["시행일자"]:
                        row["비고"] = "인용한 판이 현행보다 뒤(장래 시행분)"
                    old_art = articles_of(old)
                    lo, hi = sorted((old["공포일자"], cur["공포일자"]))
                    changed = []
                    for jo in sorted(node_jo, key=lambda j: [int(x) for x in re.findall(r"\d+", j)]):
                        a, b = old_art.get(jo), cur_art.get(jo)
                        if a is None and b is None:
                            changed.append({"조": jo, "변화": "두 판 모두 본문에 없음", "날짜": [], "항": [], "노드": node_jo[jo]})
                        elif b is None:
                            changed.append({"조": jo, "변화": "현행에 없음(삭제·이동)", "날짜": [], "항": [], "노드": node_jo[jo]})
                        elif a is None:
                            changed.append({"조": jo, "변화": "옛 판에 없음", "날짜": b["개정일"][-1:], "항": [], "노드": node_jo[jo]})
                        elif b["삭제"] and not a["삭제"]:
                            changed.append({"조": jo, "변화": "현행에서 삭제", "날짜": b["개정일"][-1:], "항": [], "노드": node_jo[jo]})
                        elif norm(a["본문"]) != norm(b["본문"]):
                            later = b if old["공포일자"] <= cur["공포일자"] else a
                            dates = [x for x in later["개정일"] if lo < x <= hi]
                            hangs = sorted(h for h, ds in later["항"].items() if any(lo < x <= hi for x in ds))
                            changed.append({"조": jo, "변화": "본문 다름", "날짜": dates, "항": hangs, "노드": node_jo[jo]})
                    row["달라진조문"] = len(changed)
                    for c in changed:
                        details.append(dict(c, 법령=law, 인용=mst, 제목=(cur_art.get(c["조"]) or {}).get("제목", "")))
            if kind in ("법령ID", "알 수 없는 번호", "미기재", "글로 적음") and ns:
                recent = changed_since(cur_art, since)
                for jo in sorted(node_jo, key=lambda j: [int(x) for x in re.findall(r"\d+", j)]):
                    if jo not in cur_art or cur_art[jo]["삭제"]:
                        undated.append({"법령": law, "인용": mst or "(없음)", "조": jo, "제목": "", "변화": "현행 본문에 없음(삭제·이동)",
                                        "날짜": [], "항": [], "노드": node_jo[jo]})
                    elif jo in recent:
                        undated.append({"법령": law, "인용": mst or "(없음)", "조": jo, "제목": cur_art[jo]["제목"],
                                        "변화": "개정 태그", "날짜": recent[jo]["날짜"], "항": recent[jo]["항"], "노드": node_jo[jo]})
            rows.append(row)
    return {"표": rows, "달라진조문": details, "기준없음": undated, "실패": failures, "since": since, "노드수": len(nodes)}


def _d(s: str) -> str:
    return "%s-%s-%s" % (s[:4], s[4:6], s[6:8]) if len(s) == 8 and s.isdigit() else s


def _hang(c: dict) -> str:
    """달라진 항과, 노드가 옮긴 항이 그 안에 드는지."""
    touched = set(c["항"])
    mine = sorted({str(n.항) for n in c["노드"]})
    if not touched:
        return ""
    hit = [h for h in mine if h in touched or (h == "" and touched)]
    return "개정 태그가 붙은 항: %s%s" % (
        "·".join(h or "본문" for h in sorted(touched, key=lambda x: int(x) if x.isdigit() else 0)),
        " — 노드가 옮긴 항과 겹침(%s)" % "·".join(h or "조 단위" for h in hit) if hit else " — 노드가 옮긴 항(%s)에는 태그 없음" % "·".join(h or "조 단위" for h in mine))


def render(res: dict) -> str:
    rows = res["표"]
    out = ["# 법령 판 대조 — 노드·검증상수가 인용한 MST 와 현행", "",
           "`scripts/node_mst_check.py`가 생성하며 손으로 고치지 않는다. 원문은 law.go.kr 웹 본문(`scripts/law_web.py`)이다.", "",
           "- 실행 노드 %d개, 대조한 (법령, 인용 번호) 묶음 %d개" % (res["노드수"], len(rows)),
           "- 현행 판을 인용: 노드 %d개 · 옛 판을 인용: 노드 %d개 · 법령ID 등을 적어 판을 알 수 없음: 노드 %d개 · 미기재: 노드 %d개" % (
               sum(r["노드"] for r in rows if r["구분"] == "현행"), sum(r["노드"] for r in rows if r["구분"] == "옛 판"),
               sum(r["노드"] for r in rows if r["구분"] in ("법령ID", "알 수 없는 번호")), sum(r["노드"] for r in rows if r["구분"] == "미기재")),
           "- 옛 판을 인용한 노드의 조문 중 본문이 달라진 것: **%d개 조문**" % len(res["달라진조문"]),
           "- 판을 알 수 없는 노드의 조문 중 %s 이후 개정 태그가 붙은 것: %d개 조문" % (_d(res["since"]), len(res["기준없음"])), "",
           "## 대조 표", "",
           "| 법령 | 인용한 번호 | 구분 | 노드 | 상수 | 인용 판 시행(공포) | 현행 MST | 현행 시행(공포) | 달라진 노드 조문 | 비고 |",
           "|---|---|---|---:|---:|---|---|---|---:|---|"]
    for r in rows:
        old = "%s (%s)" % (_d(r["옛시행"]), _d(r["옛공포"])) if r["옛시행"] else ""
        out.append("| %s | %s | %s | %d | %d | %s | %s | %s (%s, %s) | %s | %s |" % (
            r["법령"], r["인용"], r["구분"], r["노드"], r["상수"], old, r["현행MST"], _d(r["현행시행"]), r["현행공포번호"],
            _d(r["현행공포"]), "" if r["달라진조문"] is None else r["달라진조문"], r["비고"]))
    if res["실패"]:
        out += ["", "웹에서 받지 못한 법령(대조하지 못함): " + "; ".join("%s — %s" % f for f in res["실패"])]
    out += ["", "구분: **현행** 현행 MST 와 같음 · **옛 판** 다른 법령일련번호 · **법령ID** 판이 아니라 법령 자체의 번호(어느 판인지 알 수 없음) · "
            "**알 수 없는 번호** 법령ID 꼴이지만 이 법령의 ID 가 아님 · **글로 적음** '소득세법 현행'처럼 번호가 아님 · **다른 법령의 번호** 그 번호가 다른 법령의 판.", "",
            "## 옛 판을 인용한 노드 — 본문이 달라진 조문 (%d)" % len(res["달라진조문"]), "",
            "인용한 판과 현행 판의 조문 전체 텍스트(공백 제외)를 비교했다. 날짜는 두 판 사이에 붙은 개정 태그다.", ""]
    cur = None
    for c in res["달라진조문"]:
        if (c["법령"], c["인용"]) != cur:
            cur = (c["법령"], c["인용"])
            out += ["", "### %s — 노드 인용 MST %s" % cur, ""]
        ids = ", ".join(sorted(n.id for n in c["노드"])[:6]) + (" 외 %d" % (len(c["노드"]) - 6) if len(c["노드"]) > 6 else "")
        tail = "; ".join(x for x in ("개정 " + ", ".join(_d(d) for d in c["날짜"]) if c["날짜"] else "", _hang(c)) if x)
        out.append("- [ ] §%s %s — %s%s — 노드: %s" % (c["조"], c["제목"], c["변화"], ("; " + tail) if tail else "", ids))
    if not res["달라진조문"]:
        out.append("없음")
    out += ["", "## 판을 알 수 없는 노드 — %s 이후 개정 태그가 붙은 조문 (%d)" % (_d(res["since"]), len(res["기준없음"])), "",
            "법령ID 나 빈 값을 적은 노드는 어느 판을 보고 옮겼는지 알 수 없어, 최근 개정 태그가 붙은 조문만 적는다. "
            "태그가 노드 작성 전의 것일 수 있다 — 원문 대조가 필요한 후보 목록이다.", ""]
    cur = None
    for c in res["기준없음"]:
        if (c["법령"], c["인용"]) != cur:
            cur = (c["법령"], c["인용"])
            out += ["", "### %s — 노드 인용 %s" % cur, ""]
        ids = ", ".join(sorted(n.id for n in c["노드"])[:6]) + (" 외 %d" % (len(c["노드"]) - 6) if len(c["노드"]) > 6 else "")
        tail = "; ".join(x for x in ("개정 " + ", ".join(_d(d) for d in c["날짜"]) if c["날짜"] else "", _hang(c)) if x)
        out.append("- [ ] §%s %s — %s%s — 노드: %s" % (c["조"], c["제목"], c["변화"], ("; " + tail) if tail else "", ids))
    if not res["기준없음"]:
        out.append("없음")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="노드·검증상수가 인용한 법령 판(MST)과 현행 판을 대조한다 (law.go.kr 웹 본문)")
    ap.add_argument("--since", default="20260101", help="판을 알 수 없는 노드에 적용할 기준일(YYYYMMDD)")
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    ap.add_argument("--refresh", action="store_true", help="웹 캐시를 버리고 다시 받는다")
    ap.add_argument("--strict", action="store_true", help="옛 판 인용 노드의 조문 중 달라진 것이 있으면 종료코드 1")
    args = ap.parse_args()
    try:
        res = check(args.since, args.refresh)
    except law_web.웹조회실패 as exc:
        print("law.go.kr 조회 실패: %s" % exc, file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(res), encoding="utf-8")
    for r in res["표"]:
        if r["구분"] != "현행":
            print("  %-26s 인용 %-10s %-8s 노드 %4d 상수 %2d → 현행 %s(%s 시행)%s" % (
                r["법령"], r["인용"], r["구분"], r["노드"], r["상수"], r["현행MST"], _d(r["현행시행"]),
                "" if r["달라진조문"] is None else " · 달라진 노드 조문 %d" % r["달라진조문"]))
    print("옛 판 인용 노드의 달라진 조문 %d · 판을 알 수 없는 노드의 최근 개정 조문 %d · 조회 실패 %d" % (
        len(res["달라진조문"]), len(res["기준없음"]), len(res["실패"])))
    print("생성:", args.out)
    return 1 if (args.strict and res["달라진조문"]) or res["실패"] else 0


if __name__ == "__main__":
    sys.exit(main())
