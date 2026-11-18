# -*- coding: utf-8 -*-
"""law.go.kr 웹 본문을 정본으로 쓰는 경로 — 법제처 Open API 키(LAW_OC)가 없는 환경용.

scripts/coverage_audit.py(--source web), scripts/law_watch.py(--source web), scripts/node_mst_check.py 가 같이 쓴다.

하는 일
  fetch(법령명)          현행 본문을 받아 텍스트로 만든다(디스크 캐시 data/law_cache/web_*.json, gitignore 됨)
  fetch(법령명, mst=…)   특정 판(법령일련번호)의 본문
  parse_text(텍스트)     "제N조(제목)" · "①" · "1." · "가." 표지로 조문 목록(번호·가지번호·제목·장·절)과 항·호·목을 뽑는다
  to_api_doc(파싱결과)   법제처 lawService JSON 과 같은 모양으로 바꾼다 — coverage_audit.articles()/law_subunits() 가
                         API 응답과 웹 본문을 같은 코드로 읽게 하려는 것이다

받는 방법
  1) https://www.law.go.kr/법령/<띄어쓰기 없는 법령명> 에서 법령일련번호(lsiSeq)와 머리줄
     "[시행 2026. 10. 1.] [대통령령 제36736호, 2026. 9. 30., 일부개정]" 을 읽고
  2) https://www.law.go.kr/LSW/lsInfoR.do 에 lsiSeq·efYd 를 POST 해 본문 HTML 을 받는다(브라우저가 하는 요청과 같다).
  표준 라이브러리(urllib)만 쓴다. 이 길이 막히면(자바스크립트 필수로 바뀌는 등) fetch(..., browser=True) 가
  Playwright 로 같은 페이지를 열어 같은 HTML 을 얻는다 — Playwright 는 그 함수 안에서만 import 한다.

파서가 다루는 것
  목차(본문 앞의 장 제목·"부칙" 줄), 부칙(본문 뒤 — 거기서 끊는다), 삭제 조문("제5조 삭제", "제10조부터 제12조까지 삭제"),
  "제N조의M", 호의 가지번호("1의2."), 제목 없는 조문, 표·그림이 낀 조문("[표]"·"[그림]" 줄은 구조로 읽지 않는다),
  장·절 헤더(편·관은 따라가지 않는다 — API 경로의 articles() 와 같다).
  조·호·목 번호는 앞 형제보다 커야 새 단위로 본다(본문 줄이 우연히 "제3조 …"나 "2026. 1. 1."로 시작해도 속지 않는다).

확인하지 못한 것
  이 파서는 2026-11-18 현재 law.go.kr 화면 구조에 맞춘 것이다. 법제처 Open API 실응답과 직접 대조하지는 못했다(키 없음) —
  대신 API 로 만들어 둔 조문 목록(data/coverage/coverage_audit.json, 27개 법령)과 법령별로 대조했다.
"""
from __future__ import annotations

import datetime
import html as _html
import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "law_cache"
BASE = "https://www.law.go.kr"
UA = "Mozilla/5.0 (compatible; budongsan-tax-coverage/1.0)"
#: 요청 사이 간격(초) — 캐시에 없는 것만 받는다
PAUSE = 1.5

항기호 = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿"
목순서 = ("가나다라마바사아자차카타파하" "거너더러머버서어저처커터퍼허" "고노도로모보소오조초코토포호"
       "구누두루무부수우주추쿠투푸후" "그느드르므브스으즈츠크트프흐" "기니디리미비시이지치키티피히")

_last_request = [0.0]


class 웹조회실패(RuntimeError):
    pass


# ───────────────────────── 받기 ─────────────────────────

def _http(url: str, data: dict | None = None) -> str:
    wait = PAUSE - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Referer": BASE + "/"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                _last_request[0] = time.time()
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:  # 네트워크·HTTP 오류 — 잠깐 쉬고 다시
            last = exc
            time.sleep(3 * (attempt + 1))
    raise 웹조회실패("%s 요청 실패: %s %s" % (url, type(last).__name__, last))


def _hidden(page: str, name: str) -> str:
    m = re.search(r'<input[^>]*id="%s"[^>]*value="([^"]*)"' % name, page)
    return m.group(1) if m else ""


_머리 = re.compile(r"\[시행\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\]\s*\[([^,\]]+?),\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\s*,\s*([^\]]+?)\]")


def parse_header(text: str) -> dict:
    """"[시행 2026. 10. 1.] [대통령령 제36736호, 2026. 9. 30., 일부개정]" → 시행일자·공포번호·공포일자·제개정구분."""
    m = _머리.search(text)
    if not m:
        return {}
    return {"시행일자": "%s%02d%02d" % (m.group(1), int(m.group(2)), int(m.group(3))),
            "공포번호": m.group(4).strip(),
            "공포일자": "%s%02d%02d" % (m.group(5), int(m.group(6)), int(m.group(7))),
            "제개정구분": m.group(8).strip()}


class _본문추출(HTMLParser):
    """본문 HTML → 줄 목록. <p> 하나가 한 줄이다(조문 머리·항·호·목이 각각 <p>).

    표(<table>)는 통째로 "[표] …" 한 줄, 그림(표를 이미지로 실은 것)은 alt 를 "[그림] …"으로 싣는다.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._buf: list[str] | None = None
        self._table = 0
        self._tbuf: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "textarea"):
            self._skip += 1
        elif tag == "table":
            self._table += 1
        elif tag == "p" and not self._table:
            self._flush()
            self._buf = []
        elif tag in ("br", "td", "th", "tr"):
            self._add(" ")
        elif tag == "img" and "flDownload" in (a.get("src") or ""):
            self._add(" [그림] %s " % (a.get("alt") or ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "textarea"):
            self._skip = max(0, self._skip - 1)
        elif tag == "table":
            self._table = max(0, self._table - 1)
            if not self._table:
                t = re.sub(r"\s+", " ", "".join(self._tbuf)).strip()
                self._tbuf = []
                if t:
                    if self._buf is not None:
                        self._buf.append(" [표] %s " % t)
                    else:
                        self.lines.append("[표] " + t)
        elif tag == "p" and not self._table:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._add(data)

    def _add(self, s):
        if self._table:
            self._tbuf.append(s)
        elif self._buf is not None:
            self._buf.append(s)

    def _flush(self):
        if self._buf is not None:
            t = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if t:
                self.lines.append(t)
        self._buf = None


def html_to_text(body_html: str) -> str:
    """lsInfoR.do 본문 HTML → 텍스트(법령명 / 머리줄 / 본문 줄들). 브라우저의 innerText 와 같은 구실을 한다."""
    name = _hidden(body_html, "lsNm")
    if not name:
        m = re.search(r"<h2[^>]*>\s*(.*?)\s*</h2>", body_html, re.S)
        name = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
    m = re.search(r'class="ct_sub"[^>]*>\s*<span[^>]*>(.*?)<', body_html, re.S)
    head = _html.unescape(m.group(1)).strip() if m else ""
    i = body_html.find('id="conScroll"')
    p = _본문추출()
    p.feed(body_html[i if i >= 0 else 0:])
    p.close()
    return "\n".join([name, head] + p.lines)


def _cache_path(name: str, mst: str | None) -> Path:
    stem = re.sub(r"[^가-힣A-Za-z0-9]", "_", name)
    return CACHE_DIR / ("web_%s%s.json" % (stem, ("@" + str(mst)) if mst else ""))


def _browser_html(url: str) -> str:
    """Playwright 로 페이지를 열어 본문이 끼워진 뒤의 HTML 을 돌려준다(HTTP 경로가 막혔을 때만)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise 웹조회실패(
            "브라우저 경로에는 Playwright 가 필요합니다: pip install playwright && playwright install chromium "
            "(기본 HTTP 경로와 API 경로(LAW_OC)는 Playwright 없이 돕니다)") from exc
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        try:
            page = b.new_page()
            page.goto(url, wait_until="networkidle", timeout=180000)
            return page.content()
        finally:
            b.close()


def fetch(name: str, mst: str | None = None, refresh: bool = False, browser: bool = False) -> dict:
    """법령 본문을 받는다 → {"법령명","MST","법령ID","시행일자","공포일자","공포번호","제개정구분","조회일","text"}.

    mst 를 주면 그 판(연혁 포함), 안 주면 현행. 캐시가 있으면 캐시를 쓴다(refresh=True 면 다시 받는다).
    """
    cache = _cache_path(name, mst)
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    if mst:
        url = BASE + "/LSW/lsInfoP.do?lsiSeq=%s" % urllib.parse.quote(str(mst))
    else:
        url = BASE + "/" + urllib.parse.quote("법령") + "/" + urllib.parse.quote(name.replace(" ", ""))
    if browser:
        body = _browser_html(url)
        seq = _hidden(body, "lsiSeq")
    else:
        land = _http(url)
        seq = _hidden(land, "lsiSeq")
        if not seq:
            raise 웹조회실패("%s: 법령일련번호(lsiSeq)를 찾지 못했다 — 법령명이 정확한지 확인(%s)" % (name, url))
        # 시행일은 화면 머리줄에서 읽는다. 페이지 스크립트의 efYd 변수는 같은 공포분의 첫 시행일이라
        # (지방세법: 변수 20260101, 머리줄 2026. 7. 1.) 그걸 보내면 7월 1일 시행분이 빠진 본문이 온다.
        m = re.search(r'class="subTit"[^>]*>([^<]*)<', land)
        ef = parse_header(m.group(1) if m else land).get("시행일자", "")
        if not ef:
            m = re.search(r"var\s+efYd\s*=\s*'(\d{8})'", land)
            ef = m.group(1) if m else ""
        if not ef:
            raise 웹조회실패("%s: 시행일자를 찾지 못했다(%s)" % (name, url))
        body = _http(BASE + "/LSW/lsInfoR.do", {"lsiSeq": seq, "efYd": ef, "efYn": "Y", "chrClsCd": "010202",
                                                   "nwJoYnInfo": "Y", "ancYnChk": "0", "netPrivateYn": "N"})
    text = html_to_text(body)
    got = text.split("\n", 1)[0].strip()
    head = parse_header(text)
    if not head or "제1조" not in text:
        raise 웹조회실패("%s: 본문을 읽지 못했다(머리줄·제1조 없음)" % name)
    if not mst and got != name:
        raise 웹조회실패("%s: 다른 법령이 열렸다(%s)" % (name, got))
    out = dict(head, 법령명=got, MST=seq or str(mst or ""), 법령ID=_hidden(body, "lsId"),
               조회일=datetime.date.today().isoformat(), text=text)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


# ───────────────────────── 읽기 ─────────────────────────

_조머리 = re.compile(r"^제(\d+)조(?:의(\d+))?")
_편장 = re.compile(r"^제\d+(?:편|장|절|관)(?:의\d+)?(?:\s|$)")
_호머리 = re.compile(r"^(\d+)(?:의(\d+))?\.(?!\d)")       # "4.「식품위생법」"처럼 띄어쓰기 없는 호도 있다
_목머리 = re.compile(r"^([%s])\.(?![가-힣]\.)" % 목순서)
_날짜머리 = re.compile(r"^\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.")      # "2026. 1. 1. 이후 …"로 시작하는 문단은 호가 아니다
_부칙 = re.compile(r"^부\s*칙\s*(?:<|$)")
_태그 = re.compile(r"[<\[]\s*([^<>\[\]]*?\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.[^<>\[\]]*)[>\]]")
_날짜 = re.compile(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.")
_시행일 = re.compile(r"\[시행일\s*:?\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*\]")


def tag_dates(s: str) -> list[str]:
    """줄에 붙은 개정 태그(<개정 …>, <신설 …>, [본조신설 …], [전문개정 …], 삭제 <…>)의 날짜들 → ['20260930', …]."""
    out = []
    for m in _태그.finditer(s):
        if "시행일" in m.group(1) or "유효" in m.group(1):
            continue
        for d in _날짜.finditer(m.group(1)):
            out.append("%s%02d%02d" % (d.group(1), int(d.group(2)), int(d.group(3))))
    return out


def _title(rest: str) -> tuple[str, str]:
    """"(제목(괄호 포함)) 본문" → (제목, 본문). 제목이 없으면 ("", rest)."""
    if not rest.startswith("("):
        return "", rest.strip()
    depth = 0
    for i, ch in enumerate(rest):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return rest[1:i].strip(), rest[i + 1:].strip()
    return rest[1:].strip(), ""


def _article_head(ln: str, last: tuple) -> tuple | None:
    """조문 머리 줄이면 (키, 범위끝키|None, 제목, 본문, 삭제) — 아니면 None.

    조건: 뒤가 "(제목)"·" 본문"·" 삭제"·"부터 제M조까지 삭제"이고 번호가 앞 조문 이상(같으면 장래 시행분 후보).
    """
    m = _조머리.match(ln)
    if not m:
        return None
    key = (int(m.group(1)), int(m.group(2) or 0))
    rest = ln[m.end():]
    rng = re.match(r"\s*(?:부터|내지|ㆍ|및)\s*제(\d+)조(?:의(\d+))?(?:까지)?\s*삭제", rest)
    if key < last or not (rest.startswith("(") or rest.startswith(" ") or rest == "" or rng):
        return None
    title, body = _title(rest) if rest.startswith("(") else ("", rest.strip())
    deleted = bool(rng) or (not title and body.startswith("삭제"))
    return key, ((int(rng.group(1)), int(rng.group(2) or 0)) if rng else None), title, body, deleted


def _parse_body(art: dict, lines: list[str], first_body: str) -> None:
    """조문 한 덩어리의 줄들에서 항·호·목을 뽑아 art["항"]에 채운다."""
    hang = ho = mok = None
    ho_last = mok_last = None

    def new_hang(mark, body):
        nonlocal hang, ho, mok, ho_last, mok_last
        hang = {"번호": mark, "내용": body, "개정일": tag_dates(body), "호": []}
        art["항"].append(hang)
        ho = mok = ho_last = mok_last = None

    if first_body and first_body[0] in 항기호:
        new_hang(str(항기호.index(first_body[0]) + 1), first_body[1:].strip())
    elif first_body and not art["삭제"]:
        new_hang("", first_body)
    for ln in lines:
        if ln[0] in 항기호:
            new_hang(str(항기호.index(ln[0]) + 1), ln[1:].strip())
            continue
        m = _호머리.match(ln)
        if m and not _날짜머리.match(ln):
            k = (int(m.group(1)), int(m.group(2) or 0))
            if ho_last is None or k > ho_last:      # 앞 호보다 커야 호다("2026. 1. 1. …"로 시작하는 문단에 속지 않는다)
                if hang is None:
                    new_hang("", "")
                body = ln[m.end():].strip()
                ho = {"번호": m.group(1) + ("의" + m.group(2) if m.group(2) else ""), "내용": body,
                      "삭제": body.startswith("삭제"), "개정일": tag_dates(ln), "목": []}
                hang["호"].append(ho)
                ho_last, mok, mok_last = k, None, None
                continue
        m = _목머리.match(ln)
        if m and ho is not None:
            k = 목순서.index(m.group(1))
            if mok_last is None or k > mok_last:
                body = ln[m.end():].strip()
                mok = {"번호": m.group(1), "내용": body, "삭제": body.startswith("삭제"), "개정일": tag_dates(ln)}
                ho["목"].append(mok)
                mok_last = k
                continue
        # 그 밖의 줄(세목 "1)", 표·그림, [본조신설 …], 이어지는 문단)은 가장 가까운 단위의 내용에 붙인다
        tail = mok or ho or hang
        if tail is not None and not ln.startswith(("[", "<")):
            tail["내용"] += " " + ln


def parse_text(text: str) -> dict:
    """본문 텍스트 → {"법령명", 머리 정보…, "단위": [장·절 헤더와 조문]}.

    조문 = {"조문번호","가지번호","조문제목","장","절","삭제","시행일자","머리","본문","개정일":[…],
            "장래": {"시행일자","대상"} | 없음, "판": "현행"|"장래",
            "항":[{"번호":"1"|"" ,"내용","개정일","호":[{"번호":"1의2","내용","삭제","개정일","목":[{"번호":"가","내용","삭제"}]}]}]}

    law.go.kr 은 시행일이 아직 오지 않은 개정분을 현행 조문 바로 뒤에 한 번 더 싣고 끝에 "[시행일: 2027. 1. 1.] 제88조"를
    붙인다. 같은 번호가 두 번 나오면 뒤의 것을 판="장래"로 따로 둔다(현행 조문의 본문에 섞지 않는다).
    """
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    out = {"법령명": lines[0] if lines else "", "단위": []}
    out.update(parse_header(text[:3000]))
    chapter = section = ""
    last = (0, 0)
    blocks = []          # (art, 본문 줄들, 첫 줄의 본문)
    cur = None
    seen_article = False
    n = len(lines)
    i = 1
    while i < n:
        ln = lines[i]
        i += 1
        if _부칙.match(ln):
            if seen_article:
                break                      # 본문 끝 — 부칙은 읽지 않는다
            continue                       # 목차의 "부칙"
        if _편장.match(ln):
            head = re.sub(r"\s*(?:<[^>]*>|\[시행일[^\]]*\])", "", ln).strip()
            if re.match(r"제\d+장", head):
                chapter, section = head, ""
            elif re.match(r"제\d+절", head):
                section = head
            out["단위"].append({"조문여부": "전문", "내용": head})
            cur = None
            continue
        h = _article_head(ln, last)
        if h and h[0] == last:
            # 같은 번호가 또 나왔다 — 다음 조문 머리 전에 "[시행일: …]"이 있어야 장래 시행분이다
            ahead = False
            for k in range(i, n):
                if _시행일.search(lines[k]):
                    ahead = True
                    break
                if _편장.match(lines[k]) or _부칙.match(lines[k]) or _article_head(lines[k], (last[0], last[1] + 1)):
                    break
            if not ahead:
                h = None
        if h:
            key, end, title, body, deleted = h
            art = {"조문여부": "조문", "조문번호": key[0], "가지번호": key[1], "조문제목": title,
                   "장": chapter, "절": section, "삭제": deleted, "시행일자": out.get("시행일자", ""),
                   "판": "장래" if key == last else "현행", "머리": ln, "본문": ln, "개정일": tag_dates(ln), "항": []}
            out["단위"].append(art)
            cur = (art, [], body)
            blocks.append(cur)
            seen_article = True
            last = end or key
            continue
        if cur is None:
            continue                       # 머리말·목차·소관부처
        art = cur[0]
        art["본문"] += "\n" + ln
        art["개정일"] += tag_dates(ln)
        m = _시행일.search(ln)
        if m:
            target = ln[m.end():].strip()
            art["장래"] = {"시행일자": "%s%02d%02d" % (m.group(1), int(m.group(2)), int(m.group(3))), "대상": target}
            whole = "제%d조%s" % (art["조문번호"], ("의%d" % art["가지번호"]) if art["가지번호"] else "")
            if art["판"] == "장래" or target == whole:
                art["판"] = "장래"            # 조문 전체가 아직 시행 전(신설 조문이면 한 번만 나온다)
                art["시행일자"] = art["장래"]["시행일자"]
        cur[1].append(ln)
    for art, body_lines, first_body in blocks:
        _parse_body(art, body_lines, first_body)
    return out


def pick_versions(parsed: dict) -> list[dict]:
    """조문마다 한 판만 고른다 — 현행이 있으면 현행, 현행이 삭제이거나 없으면 장래 시행분.

    고른 조문에 "다른판"(쓰지 않은 판)을 달아 둔다. 장·절 헤더는 그대로 둔다.
    """
    out, at = [], {}
    for u in parsed["단위"]:
        if u["조문여부"] != "조문":
            out.append(u)
            continue
        key = (u["조문번호"], u["가지번호"])
        if key in at:
            prev = out[at[key]]
            if prev["삭제"] and not u["삭제"]:
                out[at[key]] = dict(u, 다른판=prev)
            else:
                prev["다른판"] = u
            continue
        at[key] = len(out)
        out.append(u)
    return out


def to_api_doc(parsed: dict, mst: str = "") -> dict:
    """parse_text 결과 → 법제처 lawService JSON 과 같은 모양(조문단위 → 항 → 호 → 목).

    coverage_audit.articles()/subunits_of() 가 그대로 읽는다. "웹_본문"·"웹_개정일"은 웹 경로에만 있는 덤이다.
    """
    units = []
    for u in pick_versions(parsed):
        if u["조문여부"] != "조문":
            units.append({"조문여부": "전문", "조문내용": u["내용"]})
            continue
        hangs = []
        for h in u["항"]:
            hos = []
            for o in h["호"]:
                row = {"호번호": o["번호"] + ".", "호내용": "%s. %s" % (o["번호"], o["내용"])}
                if o["목"]:
                    row["목"] = [{"목번호": k["번호"] + ".", "목내용": "%s. %s" % (k["번호"], k["내용"])} for k in o["목"]]
                hos.append(row)
            hrow = {"항번호": 항기호[int(h["번호"]) - 1] if h["번호"] else "", "항내용": h["내용"]}
            if hos:
                hrow["호"] = hos
            hangs.append(hrow)
        unit = {"조문여부": "조문", "조문번호": str(u["조문번호"]), "조문가지번호": str(u["가지번호"] or ""),
                "조문제목": u["조문제목"], "조문내용": u["머리"], "조문시행일자": u["시행일자"],
                "웹_본문": u["본문"], "웹_개정일": sorted(set(u["개정일"])), "웹_판": u["판"]}
        if u.get("장래"):
            unit["웹_장래시행"] = u["장래"]
        if u.get("다른판"):
            o = u["다른판"]
            unit["웹_다른판"] = {"판": o["판"], "조문제목": o["조문제목"], "삭제": o["삭제"], "본문": o["본문"],
                             "시행일자": o["시행일자"], "장래시행": o.get("장래")}
        if hangs:
            unit["항"] = hangs
        units.append(unit)
    info = {"법령명_한글": parsed.get("법령명", ""), "시행일자": parsed.get("시행일자", ""),
            "공포번호": parsed.get("공포번호", ""), "공포일자": parsed.get("공포일자", ""),
            "제개정구분": parsed.get("제개정구분", ""), "법령일련번호": mst}
    return {"법령": {"기본정보": info, "조문": {"조문단위": units}}, "출처": "web"}


def fetch_doc(name: str, mst: str | None = None, refresh: bool = False, browser: bool = False) -> dict:
    """받기 + 읽기 + API 모양으로 바꾸기."""
    law = fetch(name, mst=mst, refresh=refresh, browser=browser)
    doc = to_api_doc(parse_text(law["text"]), mst=law["MST"])
    doc["법령"]["기본정보"]["법령ID"] = law.get("법령ID", "")
    doc["법령"]["기본정보"]["조회일"] = law.get("조회일", "")
    return doc


def current_meta(name: str, refresh: bool = False) -> dict:
    """현행 판의 메타데이터만 — law_watch.py 의 fetch_current 와 같은 키."""
    law = fetch(name, refresh=refresh)
    return {"mst": law["MST"], "공포일자": law["공포일자"], "시행일자": law["시행일자"], "제개정구분": law["제개정구분"]}
