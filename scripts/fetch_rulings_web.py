# -*- coding: utf-8 -*-
"""정답지 수집기(웹) — 키 없이 www.law.go.kr 화면에서 해석례·재결례 본문을 받아 data/rulings/ 에 보관.

scripts/fetch_rulings.py 는 법제처 DRF(OC 키)와 국세법령정보시스템을 쓴다. 둘 다 못 쓰는 환경
(키 없음, taxlaw.nts.go.kr 차단)에서 쓰는 대체 통로다. 2026-11-18 실측.

  python scripts/fetch_rulings_web.py search decc "2025인3865"          # 목록만 본다
  python scripts/fetch_rulings_web.py search cgm  "대도시 중과" 60
  python scripts/fetch_rulings_web.py get    decc 2076151 360101        # 본문 1건 보관
  python scripts/fetch_rulings_web.py get    cgm  428310  350104
  python scripts/fetch_rulings_web.py get    expc 331837
  python scripts/fetch_rulings_web.py collect decc "비사업용 토지" 10   # 검색 → 앞 N건 보관
  python scripts/fetch_rulings_web.py index-lines ttSpecialDecc_2076151.json ...   # rulings.jsonl 줄 출력

화면(국가법령정보센터 > 판례·해석례 등) — 모두 서버 렌더링이라 GET 한 번으로 끝난다. 로그인·캡차 없음.
처음에는 Playwright 로 화면을 따라가 경로를 찾았지만, 목록·본문 모두 스크립트 실행 없이 HTML 에 들어 있어
브라우저가 필요 없다 — 표준 라이브러리(urllib)만 쓴다.
robots.txt 는 전체 허용. 그래도 요청 사이에 1.5초를 쉰다.

  kind  목록                                   본문
  decc  /LSW/deccSc.do?query=…                 일반 행정심판: /LSW/deccInfoP.do?deccSeq=…
        (행정심판 + 특별행정심판 통합 목록)      특별행정심판: /LSW/specialDeccInfoP.do?specialDeccSeq=…&trbClsCd=…
                                               (조세심판원 trbClsCd=360101)
  cgm   /LSW/cgmExpcSc.do?query=…              /LSW/cgmExpcInfoP.do?cgmExpcDatSeq=…&ofiClsCd=…
        (중앙부처 1차 해석)                      행정안전부 350104 · 기획재정부 등: 본문 있음
                                               국세청 350105: 본문 없음 — taxlaw.nts.go.kr 로 302. 목록의 제목·요지 한 줄뿐
  expc  /LSW/expcSc.do?query=…                 /LSW/expcInfoP.do?expcSeq=…   (법제처 법령해석례)

검색 시맨틱(실측): 공백은 AND 로 보인다 — "대도시 중과 저가주택" 0건, "대도시 중과" 126건. 2토큰 이하로.
사건번호("2025인3865")를 그대로 넣으면 그 건만 나온다.

서버가 연결을 자주 끊는다(connection reset). 4번까지 다시 건다.

보관 형식은 fetch_rulings.py 와 같다(data/rulings/<target>_<rid>.json + _index.json) —
tax_case_store.load_rulings 가 그대로 읽는다. rid 는 화면의 일련번호(specialDeccSeq·cgmExpcDatSeq·expcSeq)이고
DRF 의 일련번호와 같은 공간이다(기존 색인의 2296691 = 화면 cgmExpcDatSeq 2296691).
웹 본문은 DRF 본문과 공백·줄바꿈이 달라 같은 문서라도 sha256 이 다르다 — 이미 색인에 있는 rid 는 덮어쓰지 않는다.

원문 보관 근거: 저작권법 §7 3호. MCP 런타임은 이 스크립트도 data/rulings/ 도 읽지 않는다(검증 전용).
"""
from __future__ import annotations

import html as _html
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "https://www.law.go.kr/LSW"
OUT = ROOT / "data" / "rulings"
INDEX = OUT / "_index.json"
PAUSE = 1.5
_MENU = {"decc": "menuId=7&subMenuId=53&tabMenuId=249",
         "cgm": "menuId=7&subMenuId=729&tabMenuId=733",
         "expc": "menuId=7&subMenuId=51&tabMenuId=237"}
_LIST = {"decc": "deccSc.do", "cgm": "cgmExpcSc.do", "expc": "expcSc.do"}
TRB_조세심판원 = "360101"
OFI = {"350104": ("moisCgmExpc", "행정안전부"), "350105": ("ntsCgmExpc", "국세청"),
       "350101": ("moefCgmExpc", "기획재정부")}
_last = [0.0]


class 본문없음(RuntimeError):
    """본문 화면이 없거나 외부 사이트로 넘어간다(국세청 등)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _get(url: str) -> str:
    wait = PAUSE - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko"})
            with _opener.open(req, timeout=60) as r:
                _last[0] = time.time()
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            _last[0] = time.time()
            if e.code in (301, 302, 303, 307):
                raise 본문없음(f"외부로 넘어감: {(e.headers.get('Location') or '')[:80]}") from None
            if e.code == 404:
                raise 본문없음("404") from None
            err = e
        except Exception as e:                                     # noqa: BLE001 — 연결 끊김은 다시 건다
            err = e
        time.sleep(3 + 2 * attempt)
    raise RuntimeError(f"{url}: {err}")


def _text(fragment: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", fragment or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", s)
    s = re.sub(r"(?i)</td>", "\t", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t\r]+", " ", s)
    s = re.sub(r" ?\n ?", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


# ── 목록 ────────────────────────────────────────────────────────────────────
_ROW = re.compile(r'onclick="([^"]*?(?:allDeccView|deccView|specialDeccView|cgmExpcView|expcView|showExternalLink)'
                  r'\([^"]*)"[^>]*>(.*?)</a>', re.S)


def search(kind: str, query: str, outmax: int = 30, pg: int = 1) -> dict:
    """{"총": N, "rows": [{seq, cls, 제목, 표시, 요지, 본문가능, 외부링크}]} — 요지는 목록의 둘째 줄."""
    url = (f"{BASE}/{_LIST[kind]}?{_MENU[kind]}&query={urllib.parse.quote(query)}"
           f"&outmax={outmax}&pg={pg}")
    page = _get(url)
    m = re.search(r"총 <span>([\d,]+)</span>건", page)
    rows, by_key = [], {}
    for m2 in _ROW.finditer(page):
        call = _html.unescape(m2.group(1))
        args = re.findall(r"'([^']*)'", call)
        label = _text(m2.group(2)).replace("\n", " ")
        ext = call.startswith("showExternalLink") or "showExternalLink(" in call
        if ext:
            cls, _, seq = (args[1] if len(args) > 1 else ",").partition(",")
            link = args[2] if len(args) > 2 else ""
        else:
            seq = args[0] if args else ""
            cls = args[1] if len(args) > 1 and args[1] not in ("Y", "N") else ""
            link = ""
        key = (seq, cls)
        if key in by_key:
            by_key[key]["요지"] = label
            continue
        t = re.match(r"(.*)\[([^\[\]]*)\]\s*$", label)
        row = {"seq": seq, "cls": cls, "제목": (t.group(1) if t else label).strip(),
               "표시": (t.group(2) if t else "").strip(), "요지": "",
               "본문가능": not ext, "외부링크": link}
        by_key[key] = row
        rows.append(row)
    return {"총": int(m.group(1).replace(",", "")) if m else None, "rows": rows}


# ── 본문 ────────────────────────────────────────────────────────────────────
def _hidden(page: str, name: str) -> str:
    m = re.search(r'<input[^>]*id="%s"[^>]*value="([^"]*)"' % re.escape(name), page)
    return _html.unescape(m.group(1)) if m else ""


def _sections(page: str) -> dict:
    i = page.find('id="conScroll02"')
    if i < 0:
        i = page.find('id="conScroll"')
    j = page.find('<input type="hidden" id="f', i)
    body = page[i:j if j > 0 else len(page)]
    out = {}
    parts = re.split(r'<h4[^>]*>\s*【([^】]*)】\s*</h4>', body)
    for name, frag in zip(parts[1::2], parts[2::2]):
        out[name.strip()] = _text(frag)
    return out


def _collected(page: str) -> str:
    m = re.search(r"※\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", page)
    return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))) if m else ""


def _source_link(page: str) -> str:
    m = re.search(r'class="cont_subtit">\s*<p>.*?<a href="([^"]+)"', page, re.S)
    return _html.unescape(m.group(1)) if m else ""


def detail_url(kind: str, seq: str, cls: str = "") -> str:
    if kind == "decc":
        if cls:
            return f"{BASE}/specialDeccInfoP.do?specialDeccSeq={seq}&trbClsCd={cls}"
        return f"{BASE}/deccInfoP.do?deccSeq={seq}"
    if kind == "cgm":
        return f"{BASE}/cgmExpcInfoP.do?cgmExpcDatSeq={seq}&ofiClsCd={cls}"
    return f"{BASE}/expcInfoP.do?expcSeq={seq}"


def target_of(kind: str, cls: str = "") -> str:
    if kind == "decc":
        return "ttSpecialDecc" if cls == TRB_조세심판원 else ("specialDecc" + cls if cls else "decc")
    if kind == "cgm":
        return OFI.get(cls, ("cgmExpc" + cls, ""))[0]
    return "expc"


def detail(kind: str, seq: str, cls: str = "", force: bool = False) -> tuple[str, dict]:
    """본문 1건을 받아 (파일명, 문서) 를 돌려준다. 캐시가 있으면 그것을 쓴다."""
    target = target_of(kind, cls)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{target}_{seq}.json"
    if p.exists() and not force:
        return p.name, json.loads(p.read_text(encoding="utf-8"))
    url = detail_url(kind, seq, cls)
    page = _get(url)
    sec = _sections(page)
    if not sec:
        raise 본문없음(f"{url}: 본문 구획(【…】)이 없다")
    head = re.search(r'<div class="ct_sub[^"]*">\s*<span>\s*\[(.*?)\]\s*</span>', page, re.S)
    head = _text(head.group(1)) if head else ""
    # head 예: "조세심판원 조심 2025인3865 (2025. 12. 22)" · "행정안전부 부동산세제과-2742, 2022. 8. 24." · "법제처 24-0772, 2024. 11. 26., 민원인"
    _d = re.search(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", head)
    head_date = "%s%02d%02d" % (_d.group(1), int(_d.group(2)), int(_d.group(3))) if _d else ""
    head_num = (head.split(" ", 1) + [""])[1].split(",")[0].strip()
    if re.match(r"\d{4}\.", head_num):
        head_num = ""
    title = _text((re.search(r'<div id="conTop".*?<h2>(.*?)</h2>', page, re.S) or [0, ""])[1])
    기준 = _collected(page)
    if kind == "decc":
        org = head.split(" ")[0] if head else ""
        doc = {"SpecialDeccService" if cls else "DeccService": {
            "재결청": org, "청구번호": _hidden(page, "specialDeccNo") or _hidden(page, "deccNo"),
            "의결일자": _hidden(page, "rlsYd") or head_date, "세목": sec.get("세목", ""), "사건명": title,
            "재결요지": sec.get("재결요지", ""), "주문": sec.get("주문", ""),
            "청구취지": sec.get("청구취지", ""), "이유": sec.get("이유", ""),
            "관련법령": sec.get("관련법령") or None, "데이터기준일시": 기준,
            "수집경로": url, "원출처": _source_link(page)}}
        num = doc[next(iter(doc))]["청구번호"]
        if target not in ("ttSpecialDecc",):
            doc = doc[next(iter(doc))]          # tax_case_store 가 모르는 target 은 한 겹으로 둔다
    else:
        q, a, why = sec.get("질의요지", ""), sec.get("회답", ""), sec.get("이유", "")
        # tax_case_store._reason_of 는 '이유'가 있으면 그것만 본문으로 삼는다 — 질의·회답을 함께 넣어 둔다.
        body = "\n\n".join(x for x in ((f"[질의요지]\n{q}" if q else ""), (f"[회답]\n{a}" if a else ""),
                                       (f"[이유]\n{why}" if why else "")) if x)
        num = _hidden(page, "cgmExpcNo") or _hidden(page, "expcNo") or head_num
        inner = {"해석기관명": (OFI.get(cls, ("", head.split(" ")[0].rstrip(",")))[1] if kind == "cgm" else "법제처"),
                 "안건번호": num, "해석일자": _hidden(page, "cgmExpcYd") or _hidden(page, "expcYd") or head_date,
                 "안건명": title, "질의요지": q, "회답": a, "이유": body,
                 "관련법령": sec.get("관련법령") or None, "데이터기준일시": 기준,
                 "수집경로": url, "원출처": _source_link(page)}
        key = {"moisCgmExpc": "CgmExpcService", "expc": "ExpcService"}.get(target)
        doc = {key: inner} if key else inner
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    idx = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    idx[str(seq)] = {"청구번호": num, "사건명": title, "링크": url,
                     "의결일자": (doc.get(next(iter(doc))) if isinstance(doc.get(next(iter(doc))), dict) else doc)
                     .get("의결일자") or inner_date(doc)}
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    return p.name, doc


def inner_date(doc: dict) -> str:
    d = doc.get(next(iter(doc))) if isinstance(doc.get(next(iter(doc))), dict) else doc
    return d.get("해석일자") or ""


def index_line(filename: str) -> dict:
    """캐시 파일 1건을 data/verification/rulings.jsonl 의 한 줄로 — tax_case_store.load_rulings·export_jsonl 과 같은 규칙."""
    import tax_case_store as store

    p = OUT / filename
    target, rid = p.stem.split("_", 1)
    doc = json.loads(p.read_text(encoding="utf-8"))
    d = doc.get(store._SERVICE_KEY.get(target, ""), doc)
    meta = (json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}).get(rid, {})
    reason = store._reason_of(d)
    return {
        "rid": rid, "source_file": p.name, "target": target, "관련법령": d.get("관련법령"),
        "기관": d.get("재결청") or d.get("해석기관명") or d.get("법원명") or store._AGENCY.get(target, ""),
        "데이터기준일시": store._iso(d.get("데이터기준일시")),
        "링크": meta.get("링크") or d.get("수집경로"),
        "본문sha256": store._sha(reason), "본문길이": len(reason),
        "사건명": d.get("사건명") or d.get("안건명") or meta.get("사건명"),
        "사건번호": (d.get("사건번호") or "").strip(),
        "세목": d.get("세목") or d.get("관련법령") or d.get("참조조문"),
        "의결일자": store._iso(d.get("의결일자") or d.get("해석일자") or d.get("선고일자") or meta.get("의결일자")),
        "재결요지": d.get("재결요지") or d.get("질의요지") or d.get("판결요지") or d.get("판시사항"),
        "주문": (d.get("주문") or "").strip(),
        "청구번호": (meta.get("청구번호") or d.get("청구번호") or d.get("안건번호") or d.get("사건번호") or "").strip(),
    }


def collect(kind: str, query: str, n: int = 10) -> list[str]:
    files = []
    res = search(kind, query, outmax=max(15, min(150, n)))
    print(f"total={res['총']} listed={len(res['rows'])}")
    for row in res["rows"][:n]:
        if not row["본문가능"]:
            print(f"SKIP(본문 없음) {row['표시']} — {row['제목'][:50]}")
            continue
        try:
            name, _ = detail(kind, row["seq"], row["cls"])
            files.append(name)
            print(f"OK {name} {row['표시']}")
        except Exception as e:                                     # noqa: BLE001
            print(f"ERR {row['seq']}: {e}")
    return files


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "search":
        res = search(argv[2], argv[3], int(argv[4]) if len(argv) > 4 else 30)
        print(f"총 {res['총']}건")
        for r in res["rows"]:
            print(f"{'  ' if r['본문가능'] else '✗ '}{r['seq']:>8} {r['cls']:>6} [{r['표시']}] {r['제목'][:90]}")
            if r["요지"]:
                print(f"{'':19}└ {r['요지'][:160]}")
    elif cmd == "get":
        name, _ = detail(argv[2], argv[3], argv[4] if len(argv) > 4 else "")
        print(name)
    elif cmd == "collect":
        collect(argv[2], argv[3], int(argv[4]) if len(argv) > 4 else 10)
    elif cmd == "index-lines":
        for f in argv[2:]:
            print(json.dumps(index_line(f), ensure_ascii=False, sort_keys=True))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
