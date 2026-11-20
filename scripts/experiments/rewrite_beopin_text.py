# -*- coding: utf-8 -*-
"""법인세 조문 노드 가운데 원문이 현행 본문과 글자 대조되지 않는 것(줄이거나 풀어 쓴 것)을 법제처 본문 그대로 다시 옮긴다 (2026-11-19, findings 239).

노드가 가리키는 단위(조·항·호·목)의 현행 본문을 law.go.kr 에서 뽑아, 노드에 적혀 있던 원문과 견준다.
  · 겹침 = 옛 원문의 조각(줄인 자리에서 끊은 것)이 그 단위 본문과 4자 이상 이어져 겹치는 비율
  · 숫자 = 옛 원문에 나온 숫자가 그 단위 본문(같은 조 전체까지 넓혀서)에 있는지
둘 다 통과한 노드만 원문을 바꾼다(겹침 0.8 이상 · 숫자 모두 있음). 나머지는 손대지 않고 목록으로 낸다 — 사람이 읽어야 한다.
하위 호·목에 따로 노드가 있으면 그 단위의 문장만 옮기고 "[각 호 생략]"·"[각 목 생략]"을 붙인다. 하위 단위 가운데 일부만 노드가 있고
나머지는 이 노드가 직접 다루는 경우(법인세법 §93 7호 — 가목은 이 노드, 나목은 따로)는 이 도구가 가리지 못한다 — 호·목 점검
(scripts/node_coverage.py)에 '노드 없는 형제'로 잡히므로 그때 소스에서 직접 적는다.
원문만 바꾼다. 노드의 계산(함수 본문)·비고·id 는 건드리지 않는다.

실행: python scripts/experiments/rewrite_beopin_text.py            대조만(표를 출력)
      python scripts/experiments/rewrite_beopin_text.py --write    통과한 노드의 원문을 소스에 쓴다
      … --report <경로>   노드별 결과를 JSON 으로
"""
import ast
import difflib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_beopin_text as chk  # noqa: E402
import law_web  # noqa: E402
from tax_nodes import engine  # noqa: E402

항기호 = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
길이한도 = 1500
_태그 = chk._태그


def _깨끗(s: str) -> str:
    return re.sub(r"\s+", " ", _태그.sub("", s)).strip()


def 단위표(이름: str) -> dict:
    """{("55의2", 시행일자 또는 ""): 조문 dict} — ""는 현행 판, 시행일자는 장래 시행 판."""
    out = {}
    for u in law_web.parse_text(law_web.fetch(이름)["text"])["단위"]:
        if u.get("조문여부") != "조문" or u.get("삭제"):
            continue
        키 = str(u["조문번호"]) + ("의%d" % u["가지번호"] if u.get("가지번호") else "")
        out.setdefault((키, "" if u.get("판") in (None, "현행") else u.get("시행일자", "")), u)
    return out


def _호글(ho: dict) -> str:
    s = "%s. %s" % (ho["번호"], ho["내용"])
    for m in ho.get("목", []):
        s += " %s. %s" % (m["번호"], m["내용"])
    return s


def 단위본문(art: dict, 항: str, 호: str, 목: str, 자식노드있음: bool) -> tuple:
    """(그 단위의 본문, 넓힌 본문). 못 찾으면 (None, 사유)."""
    hangs = art.get("항", [])
    if not 항 and not 호:
        몸 = " ".join(([h["번호"] and 항기호[int(h["번호"]) - 1] or ""] and
                      ((항기호[int(h["번호"]) - 1] + " " if h["번호"] else "") + h["내용"] + "".join(" " + _호글(x) for x in h["호"])))
                     for h in hangs)
        return _깨끗(몸), _깨끗(art["본문"])
    if 항:
        hs = [h for h in hangs if h["번호"] == str(항)]
    else:
        hs = [h for h in hangs if h["번호"] == ""] or hangs[:1]
    if not hs:
        return None, "항 없음"
    h = hs[0]
    if not 호:
        own = (항기호[int(항) - 1] + " " if 항 else "") + h["내용"]
        full = own + "".join(" " + _호글(x) for x in h["호"])
        return _깨끗(own if (자식노드있음 or len(full) > 길이한도) and h["호"] else full) + (
            " [각 호 생략]" if (자식노드있음 or len(full) > 길이한도) and h["호"] else ""), _깨끗(full)
    hos = [x for x in h["호"] if x["번호"] == str(호)]
    if not hos:
        return None, "호 없음"
    ho = hos[0]
    if not 목:
        own = "%s. %s" % (ho["번호"], ho["내용"])
        full = _호글(ho)
        줄임 = (자식노드있음 or len(full) > 길이한도) and ho.get("목")
        return _깨끗(own if 줄임 else full) + (" [각 목 생략]" if 줄임 else ""), _깨끗(full)
    ms = [m for m in ho.get("목", []) if m["번호"] == 목]
    if not ms:
        return None, "목 없음"
    return _깨끗("%s. %s" % (목, ms[0]["내용"])), _깨끗("%s. %s" % (목, ms[0]["내용"]))


def 견줌(옛: str, 단위: str, 넓힌: str, 조전체: str) -> dict:
    조각 = chk.조각들(옛)
    대상 = chk.정규(넓힌)
    tot = sum(len(f) for f in 조각) or 1
    cov = 0
    for f in 조각:
        sm = difflib.SequenceMatcher(None, f, 대상, autojunk=False)
        cov += sum(b.size for b in sm.get_matching_blocks() if b.size >= 4)
    숫자 = set(re.findall(r"\d+(?:[.,]\d+)*", re.sub(r"\[[^\]]*\]", "", 옛)))
    조숫자 = set(re.findall(r"\d+(?:[.,]\d+)*", 조전체))
    return {"겹침": round(cov / tot, 3), "없는숫자": sorted(숫자 - 조숫자)}


_법, _영, _규 = "법인세법", "법인세법 시행령", "법인세법 시행규칙"
#: 여러 단위를 한 노드가 함께 다루는 것 — 사람이 읽고 그 노드가 계산에 쓰는 단위를 적었다(2026-11-19). (법령, 조, 항, 호, 목, 하위 포함 여부)
묶음 = {
    # 법인세법-50-3 은 다른 법령(시행령 §86⑥)을 함께 적는다 — 대조 스크립트가 한 조만 보므로 소스에서 대괄호 주석으로 적었다(여기서 다루지 않는다).
    "법인세법-58-3": [(_법, "58", "3", "", "", True), (_법, "58", "2", "", "", True)],
    "법인세법-91-5": [(_법, "91", "5", "", "", True), (_법, "91", "1", "", "", True)],
    "법인세법시행규칙-26-5": [(_규, "26", "5", "", "", True)],
    "법인세법시행규칙-46-1": [(_규, "46", "1", "", "", True), (_규, "46", "3", "", "", True), (_규, "46", "4", "", "", True), (_규, "46", "10", "", "", True)],
    "법인세법시행령-11-9-가": [(_영, "11", "", "9", "", False), (_영, "11", "", "9", "가", True)],
    "법인세법시행령-132-16": [(_영, "132", "16", "", "", True)],
    "법인세법시행령-132-17": [(_영, "132", "17", "", "", True)],
    "법인세법시행령-132-3": [(_영, "132", "3", "", "", False), (_영, "132", "4", "", "", True)],
    "법인세법시행령-132-9": [(_영, "132", "9", "", "", True), (_영, "132", "15", "", "", True)],
    "법인세법시행령-72-2-4": [(_영, "72", "2", h, "", True) for h in ("3의2", "4", "4의2", "5", "5의2")],
    "법인세법시행령-72-2-8": [(_영, "72", "2", h, "", True) for h in ("5의3", "6", "7", "8")],
    "법인세법시행령-88-1-9": [(_영, "88", "1", h, "", True) for h in ("2", "3의2", "4", "5", "7의2", "8", "8의2", "9")],
}


def _소스위치() -> dict:
    """{(모듈 파일, 원문 문자열): [원문 상수 AST 노드…]} — beopin 모듈의 노드(…, 원문="…") 호출에서.

    노드 id 는 식(_법ID + "-16-1")으로 적혀 있어 소스에서 id 로 찾지 못한다 — 등록된 노드의 원문 문자열로 찾는다.
    """
    out = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, "tax_nodes"))):
        if not (fn.startswith("beopin_") and fn.endswith(".py")) or fn == "beopin_pan.py":
            continue
        path = os.path.join(ROOT, "tax_nodes", fn)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("노드", "_노드"):
                for kw in node.keywords:
                    if kw.arg == "원문" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        out.setdefault((path, kw.value.value), []).append(kw.value)
    return out


def main() -> int:
    engine.모두올림()
    N = engine.전체()
    _, 맞음, 안맞음 = chk.대조()
    표 = {이름: 단위표(이름) for 이름 in chk.법령들}
    ids = set(N)
    위치 = _소스위치()
    결과, 바꿀, 대체 = [], {}, {}
    for nid in 안맞음:
        n = N[nid]
        # 노드에 시행일이 적혀 있으면(장래 시행 조문) 그 시행일의 판에서 찾는다
        art = 표.get(n.법령, {}).get((n.조, n.시행일 or "")) or 표.get(n.법령, {}).get((n.조, ""))
        row = {"id": nid, "표기": n.표기, "옛": n.원문}
        if not art:
            row["판정"] = "조 없음"
            결과.append(row)
            continue
        자식 = any(i != nid and i.startswith(nid + "-") for i in ids)
        if nid in 묶음:
            글 = []
            for 법령, 조, 항, 호, 목, 하위 in 묶음[nid]:
                a2 = 표[법령].get((조, n.시행일 or "")) or 표[법령][(조, "")]
                u, full = 단위본문(a2, 항, 호, 목, False)
                if u is None:
                    raise SystemExit("%s: 묶음 단위 %s §%s %s %s %s — %s" % (nid, 법령, 조, 항, 호, 목, full))
                own = u if not 하위 else full
                if not 하위:      # 하위 호·목을 뺀 그 단위의 문장만
                    own = re.sub(r" \[각 [호목] 생략\]$", "", 단위본문(a2, 항, 호, 목, True)[0])
                글.append(re.sub(r"삭제 ?$", "삭제", own))
            단위 = " / ".join(글)
            넓힌 = 단위
        else:
            단위, 넓힌 = 단위본문(art, n.항, n.호, n.목, 자식)
        if 단위 is None:
            row["판정"] = 넓힌
            결과.append(row)
            continue
        row.update(견줌(n.원문, 단위, 넓힌, _깨끗(art["본문"])))
        row["새"] = 단위
        if 단위 is None:
            row["판정"] = 넓힌
            결과.append(row)
            continue
        path = os.path.join(ROOT, *n.fn.__module__.split(".")) + ".py"
        후보 = 위치.get((path, n.원문), [])
        src = (path, 후보[0]) if len(후보) == 1 else None
        if not src:
            # 표에서 만들어 내는 노드(호 번호 + 요지) — 소스에 원문 상수가 없다. 단위는 id 로 정해지므로 본문을 대체표에 싣는다.
            row["판정"] = "대체표"
            대체[nid] = 단위
        elif nid in 묶음 or (row["겹침"] >= 0.8 and not row["없는숫자"]):
            row["판정"] = "바꿈(묶음 — 사람이 읽음)" if nid in 묶음 else "바꿈"
            바꿀[nid] = (src, 단위)
        else:
            row["판정"] = "사람이 읽을 것"
        결과.append(row)
    import collections
    print("대조 안 되던 노드 %d개 —" % len(안맞음), dict(collections.Counter(r["판정"] for r in 결과)))
    if "--report" in sys.argv:
        with open(sys.argv[sys.argv.index("--report") + 1], "w", encoding="utf-8") as f:
            json.dump(결과, f, ensure_ascii=False, indent=1)
    if "--write" in sys.argv:
        경로 = os.path.join(ROOT, "tax_nodes", "beopin_wonmun.py")
        try:
            from tax_nodes import beopin_wonmun
            기존 = dict(beopin_wonmun.현행원문)
        except ImportError:
            기존 = {}
        기존.update(대체)
        with open(경로, "w", encoding="utf-8") as f:
            f.write('"""법인세 조문 노드의 원문 대체표 — scripts/experiments/rewrite_beopin_text.py --write 가 쓴다. 손으로 고치지 않는다.\n\n'
                    "호 번호와 요지를 적은 표에서 만들어 내는 노드는 소스에 원문 상수가 없다. 그 노드가 가리키는 호·목의 법제처 현행 본문을\n"
                    '여기에 싣고, 각 모듈의 노드 등록 래퍼가 등록할 때 원문을 이 본문으로 바꾼다. 계산은 건드리지 않는다.\n"""\n')
            f.write("현행원문 = {\n")
            for k in sorted(기존):
                f.write("    %s: %s,\n" % (json.dumps(k, ensure_ascii=False), json.dumps(기존[k], ensure_ascii=False)))
            f.write("}\n\n\ndef 원문(nid: str, 기본: str) -> str:\n"
                    '    """대체표에 있으면 법제처 본문, 없으면 소스에 적힌 원문."""\n'
                    "    return 현행원문.get(nid, 기본)\n")
        print("썼다:", os.path.relpath(경로, ROOT), len(기존))
        파일별 = {}
        for nid, ((path, const), 새) in 바꿀.items():
            파일별.setdefault(path, []).append((const, 새))
        for path, items in 파일별.items():
            lines = open(path, encoding="utf-8").read().split("\n")
            for const, 새 in sorted(items, key=lambda x: (x[0].lineno, x[0].col_offset), reverse=True):
                lit = json.dumps(새, ensure_ascii=False)
                if const.lineno == const.end_lineno:
                    ln = lines[const.lineno - 1]
                    b = ln.encode("utf-8")
                    lines[const.lineno - 1] = (b[:const.col_offset] + lit.encode("utf-8") + b[const.end_col_offset:]).decode("utf-8")
                else:
                    first = lines[const.lineno - 1].encode("utf-8")[:const.col_offset].decode("utf-8")
                    last = lines[const.end_lineno - 1].encode("utf-8")[const.end_col_offset:].decode("utf-8")
                    lines[const.lineno - 1:const.end_lineno] = [first + lit + last]
            open(path, "w", encoding="utf-8").write("\n".join(lines))
            print("썼다:", os.path.relpath(path, ROOT), len(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
