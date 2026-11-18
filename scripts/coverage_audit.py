"""조문 커버리지 감사 — 추적 법령의 전 조문 대비 법문 노드 반영 여부를 대조한다.

배경(2026-08-30): 종부세 계산에서 지방세법 §110③ 주택 과세표준상한제가 누락돼
세액이 틀렸다. 원인은 값이 낡아서가 아니라 **조항이 애초에 코퍼스에 없어서**였다.
검증상수 표(1층)와 연도 필수화(2층)로는 이 유형을 못 막는다 — 목록에 없는 것은
지킬 수 없기 때문이다. 이 스크립트가 3층으로, 법령 원문의 조문 목록을 정본으로 놓고
data/legal_nodes 에 노드가 있는지 역대조해 미반영 조문을 뽑는다.

산출물:
  data/coverage/coverage_audit.json  — 법령별 전 조문 + 커버 여부 + 분류
  data/coverage/coverage_gaps.md     — 미반영 '세액영향' 조문만 추린 검토용 목록
  data/coverage/subunits.json        — 조문별 항·호·목 구조(2026-11-17). 조 단위 대조는 "§111에 노드가 있다"만
                                       보고 ①항 2호(건축물)가 빠진 것을 못 봤다. node_coverage.py 가 이 구조를
                                       형제 목록으로 써서 호·목 누락을 센다.

사용:
  py scripts/coverage_audit.py                       # 추적 법령 전체 (법제처 Open API — 환경변수 LAW_OC 필요)
  py scripts/coverage_audit.py 지방세법               # 특정 법령만
  py scripts/coverage_audit.py --source web          # 키 없이: law.go.kr 웹 본문을 정본으로 (scripts/law_web.py)
  py scripts/coverage_audit.py --source web 지방세법
  --refresh   웹 캐시(data/law_cache/web_*.json)를 버리고 다시 받는다
  --browser   웹 경로를 HTTP 대신 Playwright 로(HTTP 가 막혔을 때만 — Playwright 필요)

두 경로 (2026-11-18)
  api  lawService JSON(조문단위 → 항 → 호 → 목)을 읽는다.
  web  law.go.kr 본문 텍스트를 "제N조(제목)"·"①"·"1."·"가." 표지로 나눠 **같은 모양의 문서**로 만든 뒤
       같은 articles()/law_subunits() 로 읽는다. 그래서 산출물의 모양은 경로와 무관하다.
  차이: 시행일이 아직 오지 않은 개정 조문은 웹 경로가 현행 본문을 쓰고(현행이 삭제·없음이면 장래분을 쓰고
       시행일자에 그 날짜를 적는다), API 경로는 법제처가 주는 대로 쓴다. 2026-11 대조에서 API 로 만든 옛 목록은
       소득세법 §118의10 등 7개 조문에 장래(2027-01-01 시행) 제목을 싣고 있었다.
  확인하지 못한 것: API 경로의 subunits_of()/law_subunits() 는 가상 응답으로만 시험했다 — 이 저장소의
       subunits.json 은 웹 경로로 만든 것이다. 키가 생기면 한 법령을 두 경로로 돌려 subunits 가 같은지 볼 것.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODES_DIR = ROOT / "data" / "legal_nodes"
CACHE_DIR = ROOT / "data" / "law_cache"
OUT_DIR = ROOT / "data" / "coverage"
SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"

sys.path.insert(0, str(ROOT / "scripts"))
from law_watch import TRACKED_LAWS  # 추적 대상은 한 곳에서만 관리한다

# 근거링크에 쓰인 약칭 -> 법제처 정식 법령명. 노드를 쓰는 사람이 약칭을 쓰므로
# 대조 전에 정규화가 필요하다. 새 약칭이 생기면 여기에 추가할 것.
ABBREV = {
    "종부세법": "종합부동산세법",
    "상증세법": "상속세 및 증여세법",
    "도시정비법": "도시 및 주거환경정비법",
    "재초환법": "재건축초과이익 환수에 관한 법률",
    "재건축초과이익 환수에 관한 법": "재건축초과이익 환수에 관한 법률",
    "지특법": "지방세특례제한법",
    "조특법": "조세특례제한법",
    "부동산 거래신고 등에 관한 법": "부동산 거래신고 등에 관한 법률",
}

# 조 단위 감사 대상은 아니지만 실행 노드가 인용하는 법령 — 호·목 점검(subunits.json)의 형제 목록용으로만 받는다.
# 웹 경로에서만 쓴다(추적 법령 전체를 돌릴 때). 노드가 새 법령을 인용하기 시작하면 여기에 더한다.
SUBUNIT_ONLY_LAWS = ["국세기본법", "국세기본법 시행령", "지방세기본법", "지방세법 시행규칙",
                     "지방세특례제한법 시행령", "조세특례제한법 시행규칙"]

# 세액을 좌우하는 조문인지 제목으로 1차 분류한다. 절차 조문까지 전부 검토 목록에
# 올리면 사람이 못 본다 — 우선순위를 나누기 위한 것이지 배제가 아니다.
TAX_KW = ["과세표준", "세율", "세액", "공제", "감면", "비과세", "면제", "산출", "상한",
          "비율", "특례", "중과", "과세대상", "납세의무", "과세기준", "합산", "평가",
          "가액", "범위", "제외", "추징", "부과", "표준"]
PROC_KW = ["신고", "납부", "징수", "가산세", "경정", "환급", "서류", "신청", "통지",
           "고지", "제척", "위임", "벌칙", "과태료", "장부", "기장", "조사", "정의",
           "목적", "협의", "이의", "심사", "송달", "결정"]
# 조특법·지특법은 농어촌·중소기업·연구개발 감면까지 수백 조문을 담고 있어, 세액영향
# 분류만으로는 검토 목록이 1,600건을 넘어 사람이 볼 수 없다. 부동산 도메인 조문만
# 1차 검토 대상으로 좁힌다 — 나머지는 audit.json에 그대로 남으므로 배제가 아니다.
DOMAIN_KW = ["주택", "토지", "부동산", "양도", "취득", "재산세", "임대", "조합",
             "상속", "증여", "건축물", "거주", "세대", "농지", "분양", "정비사업",
             "종합부동산"]

# 세목 축 필터 (2026-08-30). 지방세법 한 법에 취득세·재산세·지방소득세·자동차세·
# 주민세가 다 들어 있어 제목 키워드로는 세목을 못 가른다. 법령 원문의 장(章) 구조가
# 곧 세목 구분이므로 그걸 쓴다 — 추측이 아니라 원문 구조다.
#
# 포함 목록이 아니라 **제외 목록**으로 둔다. 새 장이 생겼을 때 조용히 빠지는 것보다
# 조용히 들어오는 편이 안전하기 때문이다. 제외 건수는 보고서에 그대로 표시한다.
OUT_OF_SCOPE = {
    "지방세법": ["제4장 레저세", "제5장 담배소비세", "제6장 지방소비세",
               "제7장 주민세", "제8장 지방소득세", "제10장 자동차세",
               "제11장 지역자원시설세"],
    "지방세법 시행령": ["제4장 레저세", "제5장 담배소비세", "제6장 지방소비세",
                   "제7장 주민세", "제8장 지방소득세", "제10장 자동차세",
                   "제11장 지역자원시설세"],
    "지방세특례제한법": ["제3장 지방소득세 특례"],
    # 원천징수(근로·이자·배당 중심)와 보칙은 부동산 세목 상담에서 쓰지 않는다.
    # 제4장 비거주자는 남긴다 — 비거주자의 국내 부동산 양도가 실제 상담 대상이다.
    "소득세법": ["제5장 원천징수", "제6장 보칙"],
    "소득세법 시행령": ["제5장 원천징수", "제6장 보칙"],
}


# 조문 제목으로 거르는 범위밖 — 부동산 세금 엔진이 다루지 않는 과세물건(차량·선박·항공기·기계장비 등).
# 장 단위 OUT_OF_SCOPE로는 못 거르는, 취득세 장 안의 비부동산 조문용이다. 2026-10-10.
# 조특법·조특법 시행령은 연구개발·고용·투자세액공제·저축·간접국세·관세 등 양도세와 무관한 특례가 대부분이다. 양도세·부동산(종부세·증여세 포함) 관련
# 조문만 세목 범위 안에 두고, 코퍼스에 없는 나머지 조문은 "비양도·비부동산"으로 범위밖 표시한다 (2026-10-10). 코퍼스에 이미 있는 조문은 건드리지 않는다.
IN_SCOPE_ARTICLES = {
    "조세특례제한법": set(["3", "69의3", "69의4", "70의2", "71", "83", "85의2", "85의5", "85의8", "85의9", "97", "97의2", "97의6", "97의7", "97의8", "97의9", "98의2", "98의3", "98의4", "98의5", "98의6", "98의7", "98의8", "99", "99의2", "99의14", "104의13", "104의19", "104의20", "128", "132", "141", "146"]),
    "조세특례제한법 시행령": set(["40", "66의2", "66의3", "66의4", "67의2", "68", "73", "74", "78", "79의3", "79의6", "79의8", "79의9", "79의10", "97", "97의2", "97의3", "97의4", "97의5", "97의6", "97의7", "97의8", "97의9", "98", "98의2", "98의3", "98의4", "98의5", "98의6", "98의7", "99", "99의2", "99의3", "104의11", "104의12", "104의18", "134", "137"]),
}

# 법인세법은 부동산 양도에 닿는 조문만 본다 (2026-11-17). 여기 적힌 조문 밖은 "법인세 일반"으로 범위밖 표시한다.
# 익금·손금·감가상각·합병·연결납세까지 검토 목록에 오르면 사람이 못 본다 — 배제가 아니라 audit.json 에 범위밖으로 남는다.
SCOPE_ONLY = {
    "법인세법": {"55", "55의2", "60의2"},
    "법인세법 시행령": {"42", "92의2", "92의3", "92의4", "92의5", "92의6", "92의7", "92의8", "92의9", "92의10",
                   "92의11", "97의4"},
}

OUT_OF_SCOPE_TITLE_KW = ["차량", "자동차", "선박", "항공기", "기계장비", "농기계", "이륜", "무선국", "이동통신", "해운항만", "항공운송",
                         "철도시설", "광업", "주유소", "도시가스", "별정우체국", "해양오염", "경형자동차", "교환자동차", "노후경유", "중고자동차",
                         "운송사업", "교통안전", "물류단지", "도시첨단물류", "장애인용 자동차"]


def chapter_of(text):
    """'제9장 재산세 <개정 …>' → '제9장 재산세'"""
    return re.sub(r"\s*<[^>]*>", "", re.sub(r"\s+", " ", text)).strip()

_LAW_TOKEN = re.compile(
    r"(?P<full>[가-힣][가-힣\s]*?(?:법률|법))\s*(?P<var>시행규칙|시행령)?"
    r"|(?P<bare>시행규칙|시행령|영|규칙|법)(?=\s*§)"
    r"|§\s*(?P<art>\d+)(?:의\s*(?P<sub>\d+))?"
)


def canon(name):
    return ABBREV.get(name.strip(), name.strip())


def parse_refs(text):
    """근거링크 문자열에서 (정식법령명, 조문번호, 가지번호) 집합을 뽑는다.

    "소득세법 §64의2③ + 영 §122의2③" 처럼 뒤에 '영'만 나오면 직전 본법의
    시행령을 가리키므로, 왼쪽에서 오른쪽으로 읽으며 현재 법령 문맥을 들고 간다.
    """
    refs = set()
    base = None      # 본법 정식명 (예: 소득세법)
    variant = ""     # "", "시행령", "시행규칙"
    for m in _LAW_TOKEN.finditer(text):
        if m.group("full"):
            base = canon(m.group("full"))
            variant = m.group("var") or ""
        elif m.group("bare"):
            b = m.group("bare")
            # "…시행령 §160 (법 §95③ 위임)" 처럼 뒤에 맨 '법 §'이 나오면 본법으로 되돌린다.
            # 이걸 시행령으로 귀속시키면 본법 커버리지가 통째로 0으로 잡힌다.
            if b == "법":
                variant = ""
            elif b in ("시행규칙", "규칙"):
                variant = "시행규칙"
            else:
                variant = "시행령"
        elif m.group("art") and base:
            full = (base + " " + variant).strip()
            refs.add((full, int(m.group("art")), int(m.group("sub") or 0)))
    return refs


def load_node_refs():
    """법문 노드 전체에서 법령별로 참조된 조문 집합을 모은다."""
    by_law = {}
    for path in sorted(NODES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        nodes = data.get("nodes", []) if isinstance(data, dict) else data
        if not isinstance(nodes, list):
            continue
        for node in nodes:
            if not isinstance(node, dict):
                continue
            # 판례 태그 노드(사건번호 보유)는 법문 노드가 아니므로 건너뛴다
            if "사건번호" in node:
                continue
            blob = " ".join(str(node.get(k, ""))
                            for k in ("근거링크", "규칙", "메모", "비고", "변수"))
            for law, art, sub in parse_refs(blob):
                by_law.setdefault(law, set()).add((art, sub))
    return by_law


def _get(url, params):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "coverage-audit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fetch_law(name, oc):
    """법령명으로 현행 MST를 찾아 조문 전문을 받아온다(디스크 캐시)."""
    cache = CACHE_DIR / (re.sub(r"[^가-힣A-Za-z0-9]", "_", name) + ".json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    raw = _get(SEARCH_URL, {"OC": oc, "target": "law", "type": "JSON",
                            "query": name, "display": "20"})
    hits = json.loads(raw).get("LawSearch", {}).get("law", [])
    if isinstance(hits, dict):
        hits = [hits]
    mst = None
    for h in hits:
        if (h.get("법령명한글") or "").strip() == name:
            mst = h.get("법령일련번호")
            break
    if not mst:
        return None
    time.sleep(0.3)
    doc = json.loads(_get(SERVICE_URL, {"OC": oc, "target": "law",
                                        "type": "JSON", "MST": mst}))
    cache.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return doc


def articles(doc):
    """조문단위에서 본문 조문만(부칙·삭제 제외) 뽑는다."""
    units = doc.get("법령", {}).get("조문", {}).get("조문단위", [])
    if isinstance(units, dict):
        units = [units]
    out = []
    chapter = section = ""
    for u in units:
        # 장/절 헤더는 조문단위 배열에 조문여부!="조문"으로 섞여 있다. 순서대로 읽으며
        # 현재 장·절을 들고 가면 각 조문이 어느 세목인지 원문 구조 그대로 알 수 있다.
        if u.get("조문여부") != "조문":
            head = chapter_of(u.get("조문내용") or "")
            if re.match(r"제\d+장", head):
                chapter, section = head, ""
            elif re.match(r"제\d+절", head):
                section = head
            continue
        title = (u.get("조문제목") or "").strip()
        body = u.get("조문내용") or ""
        if not title and "삭제" in body[:40]:
            continue
        try:
            num = int(u.get("조문번호"))
        except (TypeError, ValueError):
            continue
        out.append({"조문번호": num,
                    "가지번호": int(u.get("조문가지번호") or 0),
                    "조문제목": title,
                    "장": chapter,
                    "절": section,
                    "시행일자": u.get("조문시행일자", "")})
    return out


# ㉑ 이상도 있다(소득세법 시행령 §155 는 ㉕항까지) — 20개만 두면 21항 이하의 호가 "항 없음"으로 뭉친다
_항기호 = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿"


#: subunits.json 의 요지 길이. 전 조문으로 넓히면서 60 → 40 (파일 크기 — 요지는 사람이 알아보는 용도일 뿐이다)
요지길이 = 40


def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _flat(x):
    """조문 내용은 문자열이거나 (표가 낀 경우) 중첩 리스트로 온다."""
    if isinstance(x, list):
        return " ".join(_flat(i) for i in x)
    return str(x or "")


def subunits_of(unit):
    """조문단위 하나에서 항·호·목 구조를 뽑는다 → [{"항","호","목"?,"삭제"?,"요지"}].

    법제처 lawService JSON은 조문단위 아래 항(항번호 ①…) → 호(호번호 "1." "1의2.") → 목(목번호 "가.")으로
    내려가고, 원소가 하나면 리스트가 아니라 dict 로 온다. 항 없이 호가 바로 오는 조문은 항번호가 비어 있다.
    호가 없는 항은 싣지 않는다(형제 비교 대상이 아니다).
    """
    out = []
    for hang in _as_list(unit.get("항")):
        if not isinstance(hang, dict):
            continue
        mark = (hang.get("항번호") or "").strip()
        h = str(_항기호.index(mark[0]) + 1) if mark and mark[0] in _항기호 else ""
        for ho in _as_list(hang.get("호")):
            if not isinstance(ho, dict):
                continue
            m = re.match(r"\s*(\d+)(?:의\s*(\d+))?", ho.get("호번호") or "")
            if not m:
                continue
            ho_no = m.group(1) + ("의" + m.group(2) if m.group(2) else "")
            body = re.sub(r"^\s*\d+(의\d+)?\.\s*", "", _flat(ho.get("호내용")).strip())
            row = {"항": h, "호": ho_no}
            if body.startswith("삭제"):
                row["삭제"] = True
            row["요지"] = re.sub(r"\s+", " ", body)[:요지길이]
            out.append(row)
            for mok in _as_list(ho.get("목")):
                if not isinstance(mok, dict):
                    continue
                mm = re.match(r"\s*([가-힣])", mok.get("목번호") or "")       # 하 다음은 거·너…, 고·노…(조특법 §7)
                if not mm:
                    continue
                mbody = re.sub(r"^\s*[가-힣]\.\s*", "", _flat(mok.get("목내용")).strip())
                mrow = {"항": h, "호": ho_no, "목": mm.group(1)}
                if mbody.startswith("삭제"):
                    mrow["삭제"] = True
                mrow["요지"] = re.sub(r"\s+", " ", mbody)[:요지길이]
                out.append(mrow)
    return out


def law_subunits(doc):
    """법령 문서 전체 → {조: [하위 단위]} (호가 있는 조문만)."""
    units = doc.get("법령", {}).get("조문", {}).get("조문단위", [])
    if isinstance(units, dict):
        units = [units]
    out = {}
    for u in units:
        if u.get("조문여부") != "조문":
            continue
        try:
            num = int(u.get("조문번호"))
        except (TypeError, ValueError):
            continue
        sub = int(u.get("조문가지번호") or 0)
        rows = subunits_of(u)
        if rows:
            out["%d%s" % (num, ("의%d" % sub) if sub else "")] = rows
    return out


def classify(title):
    tax = any(k in title for k in TAX_KW)
    proc = any(k in title for k in PROC_KW)
    if tax and not proc:
        return "세액영향"
    if tax and proc:
        return "혼합"
    if proc:
        return "절차"
    return "미분류"


def _jo(r):
    return "%d%s" % (r["조문번호"], ("의%d" % r["가지번호"]) if r["가지번호"] else "")


def dump_subunits(subunits):
    """subunits.json 직렬화 — 조문 하나가 한 줄(diff 가 조문 단위로 보이고, 들여쓰기 없는 만큼 작다)."""
    out = ["{", '"_meta": %s' % json.dumps(subunits.get("_meta", {}), ensure_ascii=False, indent=1)]
    for law in sorted(k for k in subunits if k != "_meta"):
        arts = subunits[law]
        lines = [" %s: %s" % (json.dumps(jo, ensure_ascii=False), json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
                 for jo, rows in arts.items()]
        out[-1] += ","
        out.append("%s: {\n%s\n}" % (json.dumps(law, ensure_ascii=False), ",\n".join(lines)))
    out.append("}")
    return "\n".join(out) + "\n"


def _node_articles():
    """실행 노드가 있는 조문 {법령: {조}} — 범위밖 조문이라도 노드가 있으면 호·목 구조를 싣기 위한 것.

    tax_nodes 를 못 읽는 환경이면 빈 dict(그때는 범위밖 조문의 구조가 빠지고, 호·목 점검이 번호 추정으로 물러난다).
    """
    try:
        sys.path.insert(0, str(ROOT))
        import node_coverage
        out = {}
        for n in node_coverage._load_nodes().values():
            out.setdefault(n.법령, set()).add(str(n.조))
        return out
    except Exception as exc:  # noqa: BLE001
        print("  (실행 노드를 읽지 못했다 — 범위밖 조문의 호·목 구조는 싣지 않는다: %s)" % exc)
        return {}


def apply_supplement(subunits, supplement):
    """손 보충(표 이미지 속의 호)을 끼운다 — 같은 (조, 항) 아래 읽힌 호가 없을 때만. 끼운 (법령, 조, 항) 목록을 돌려준다."""
    added = []
    for law, arts in supplement.items():
        if law.startswith("_"):
            continue
        for jo, item in arts.items():
            have = subunits.setdefault(law, {}).setdefault(jo, [])
            for hang in sorted({u.get("항", "") for u in item["단위"]}):
                if any(u.get("항", "") == hang for u in have):
                    continue                     # 파서가 읽었다 — 보충은 쓰지 않는다
                have.extend(dict(u, 출처="손보충") for u in item["단위"] if u.get("항", "") == hang)
                added.append((law, jo, hang))
            have.sort(key=lambda u: (int(u["항"]) if str(u.get("항", "")).isdigit() else 0))
    return added


def _law_meta(doc):
    info = doc.get("법령", {}).get("기본정보", {})
    meta = {"시행": str(info.get("시행일자", "")), "공포번호": str(info.get("공포번호", "")),
            "공포일": str(info.get("공포일자", "")), "MST": str(info.get("법령일련번호", "") or "")}
    if doc.get("출처") == "web":
        meta["출처"] = "web"
        meta["조회일"] = str(info.get("조회일", ""))
    return meta


def diff_articles(old_rows, new_rows):
    """앞선 감사의 조문 목록과 새 목록의 차이 → 사람이 읽을 줄들(신설·삭제·제목 변경·장절 이동)."""
    def key(r):
        return (r["조문번호"], r["가지번호"])

    def name(r):
        return "§%d%s %s" % (r["조문번호"], ("의%d" % r["가지번호"]) if r["가지번호"] else "", r["조문제목"])

    def norm(x):
        return (x or "").replace("·", "ㆍ")      # 가운뎃점 문자만 다른 것은 차이로 치지 않는다

    old, new = {key(r): r for r in old_rows}, {key(r): r for r in new_rows}
    out = []
    for k in sorted(set(old) | set(new)):
        o, n = old.get(k), new.get(k)
        if o is None:
            out.append("+ %s (시행 %s)" % (name(n), n.get("시행일자", "")))
        elif n is None:
            out.append("- %s" % name(o))
        elif norm(o["조문제목"]) != norm(n["조문제목"]):
            out.append("~ %s ← %s" % (name(n), o["조문제목"]))
        elif norm(o.get("장")) != norm(n.get("장")) or norm(o.get("절")) != norm(n.get("절")):
            out.append("~ %s 장·절 이동: %s %s ← %s %s" % (name(n), n.get("장"), n.get("절"), o.get("장"), o.get("절")))
    return out


def main():
    args = sys.argv[1:]
    source = "api"
    if "--source" in args:
        i = args.index("--source")
        source = args[i + 1] if i + 1 < len(args) else ""
        del args[i:i + 2]
    refresh, browser = "--refresh" in args, "--browser" in args
    args = [a for a in args if a not in ("--refresh", "--browser")]
    if source not in ("api", "web"):
        print("--source 는 api 또는 web", file=sys.stderr)
        return 1
    oc = os.environ.get("LAW_OC", "").strip()
    if source == "api" and not oc:
        print("LAW_OC 환경변수가 필요합니다 (키 없이 돌리려면 --source web)", file=sys.stderr)
        return 1
    if source == "web":
        import law_web

        def fetch_law(name, _oc):          # noqa: F811 — API 경로와 같은 모양의 문서를 돌려준다
            return law_web.fetch_doc(name, refresh=refresh, browser=browser)
    else:
        fetch_law = globals()["fetch_law"]
    targets = args or TRACKED_LAWS
    node_refs = load_node_refs()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 인자로 법령 하나만 주고 돌리는 일이 잦은데(방금 고친 조문만 확인), 그때
    # 보고서를 통째로 다시 쓰면 나머지 26개 법령의 측정치가 조용히 사라진다.
    # 2026-08-31에 실제로 한 번 날렸다 — 기존 결과를 읽어 부분 갱신으로 병합한다.
    prev_path = OUT_DIR / "coverage_audit.json"
    report = {}
    previous = {}
    if prev_path.exists():
        try:
            previous = json.loads(prev_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            previous = {}
    if previous and set(targets) != set(TRACKED_LAWS):
        report = dict(previous)
        print("  기존 보고서 %d개 법령을 유지하고 %d개만 갱신한다"
              % (len(report), len(targets)))
    changed = []
    node_articles = _node_articles()
    gaps = []
    sub_path = OUT_DIR / "subunits.json"
    try:
        subunits = json.loads(sub_path.read_text(encoding="utf-8")) if sub_path.exists() else {}
    except (ValueError, OSError):
        subunits = {}
    for name in targets:
        try:
            doc = fetch_law(name, oc)
        except Exception as exc:
            report[name] = {"error": str(exc)}
            print("  !! " + name + ": " + str(exc))
            continue
        if doc is None:
            report[name] = {"error": "법령 조회 실패"}
            print("  !! " + name + ": 조회 실패")
            continue
        got_subunits = law_subunits(doc)
        covered = node_refs.get(name, set())
        rows = []
        for a in articles(doc):
            key = (a["조문번호"], a["가지번호"])
            excl = [c for c in OUT_OF_SCOPE.get(name, [])
                    if a["장"].startswith(c) or a["절"].startswith(c)]
            if not excl and name.startswith(("지방세법", "지방세특례제한법")):
                excl = ["비부동산:" + k for k in OUT_OF_SCOPE_TITLE_KW if k in a["조문제목"]][:1]
            # 2026-10-11 조특법 비양도 조문까지 노드화(jotuk_gita_1~8) — 범위밖 표시 해제. 빈 칸이 있으면 미착수로 드러나게 한다.
            if False and not excl and name in IN_SCOPE_ARTICLES and key not in covered:
                _k = "%d%s" % (a["조문번호"], ("의%d" % a["가지번호"]) if a["가지번호"] else "")
                if _k not in IN_SCOPE_ARTICLES[name]:
                    excl = ["비양도·비부동산: 법인세·소득세·간접세 특례"]
            if not excl and name in SCOPE_ONLY:
                _k = "%d%s" % (a["조문번호"], ("의%d" % a["가지번호"]) if a["가지번호"] else "")
                if _k not in SCOPE_ONLY[name]:
                    excl = ["법인세 일반: 부동산 양도 밖"]
            dom = any(k in a["조문제목"] for k in DOMAIN_KW) or (name in SCOPE_ONLY and not excl)
            row = dict(a, covered=key in covered, 분류=classify(a["조문제목"]),
                       부동산도메인=dom, 범위밖=(excl[0] if excl else ""))
            rows.append(row)
            if (not row["covered"] and row["분류"] in ("세액영향", "혼합")
                    and dom and not excl):
                gaps.append(dict(row, 법령=name))
        n_cov = sum(1 for r in rows if r["covered"])
        n_tax = sum(1 for r in rows
                    if not r["covered"] and r["분류"] in ("세액영향", "혼합"))
        n_out = sum(1 for r in rows if not r["covered"]
                    and r["분류"] in ("세액영향", "혼합") and r["부동산도메인"]
                    and r["범위밖"])
        n_gap = sum(1 for r in rows if not r["covered"]
                    and r["분류"] in ("세액영향", "혼합") and r["부동산도메인"]
                    and not r["범위밖"])
        report[name] = {"조문수": len(rows), "커버": n_cov,
                        "미커버_세액영향": n_tax, "미커버_부동산": n_gap,
                        "세목제외": n_out, "판": _law_meta(doc), "조문": rows}
        # 항·호·목 구조 — 이번에 받은 법령분만 바꿔 쓴다(다른 법령분은 그대로 둔다).
        # 범위밖 조문(레저세·법인세 일반 등)은 싣지 않는다: 전부 실으면 3 MB 를 넘고, 그 조문에는 노드를 두지 않는다.
        # 다만 실행 노드가 이미 있는 조문은 범위밖이어도 싣는다(지방세법 §103의20 법인지방소득세 등).
        outside = {_jo(r) for r in rows if r["범위밖"]} - node_articles.get(name, set())
        got_subunits = {k: v for k, v in got_subunits.items() if k not in outside}
        if got_subunits:
            subunits[name] = got_subunits
            subunits.setdefault("_meta", {}).setdefault("법령", {})[name] = _law_meta(doc)
        if isinstance(previous.get(name), dict) and "조문" in previous[name]:
            d = diff_articles(previous[name]["조문"], rows)
            if d:
                changed.append((name, d))
        print("  %-30s 조문 %4d / 커버 %3d / 미커버 세액영향 %4d / 검토대상 %3d"
              "%s" % (name, len(rows), n_cov, n_tax, n_gap,
                      "  (세목 제외 %d)" % n_out if n_out else ""))

    # 호·목 구조만 필요한 법령(노드가 인용하지만 조 단위 감사 대상은 아닌 것) — 웹 경로로 전체를 돌릴 때만
    if source == "web" and not args:
        for name in SUBUNIT_ONLY_LAWS:
            try:
                doc = fetch_law(name, oc)
            except Exception as exc:
                print("  !! (호·목 구조만) " + name + ": " + str(exc))
                continue
            got = law_subunits(doc)
            if got:
                subunits[name] = got
                subunits.setdefault("_meta", {}).setdefault("법령", {})[name] = _law_meta(doc)
                print("  %-30s 호·목 구조만 — 호가 있는 조문 %d" % (name, len(got)))

    sup_path = OUT_DIR / "subunits_supplement.json"
    if sup_path.exists():
        for law, jo, hang in apply_supplement(subunits, json.loads(sup_path.read_text(encoding="utf-8"))):
            print("  손 보충: %s §%s %s항의 호 (표 이미지라 본문에서 읽지 못함)" % (law, jo, hang or "-"))

    (OUT_DIR / "coverage_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    meta = subunits.setdefault("_meta", {})
    meta["설명"] = ("법령 원문의 항·호·목 구조(호가 있는 조문 전부). scripts/node_coverage.py 의 호·목 점검이 형제 목록으로 쓴다. "
                  "손으로 고치지 않는다 — scripts/coverage_audit.py 가 만든다.")
    meta["출처"] = ("law.go.kr 웹 본문(scripts/law_web.py), scripts/coverage_audit.py --source web 생성" if source == "web"
                  else "법제처 lawService(조문단위 → 항 → 호 → 목), scripts/coverage_audit.py 생성")
    if changed:
        print("\n앞선 감사와 달라진 조문 목록 (+ 신설, - 없어짐, ~ 제목·장절 변경)")
        for name, d in changed:
            print("  " + name)
            for line in d:
                print("    " + line)
    sub_path.write_text(dump_subunits(subunits), encoding="utf-8")

    # gaps는 이번에 돌린 법령분만 쌓였다. 유지된 법령은 저장된 조문 행에서 되살린다.
    fresh = set(targets)
    for law, v in report.items():
        if law in fresh or not isinstance(v, dict) or "조문" not in v:
            continue
        for r in v["조문"]:
            if (not r.get("covered") and r.get("분류") in ("세액영향", "혼합")
                    and r.get("부동산도메인") and not r.get("범위밖")):
                gaps.append(dict(r, 법령=law))
    order = {law: i for i, law in enumerate(TRACKED_LAWS)}
    gaps.sort(key=lambda g: (order.get(g["법령"], 999), g["조문번호"], g["가지번호"]))

    total_refs = sum(len(v) for v in node_refs.values())
    lines = ["# 미반영 조문 — 부동산 도메인 세액영향 후보 (1차 검토 대상)", "",
             "법문 노드가 참조 중인 조문: %d개" % total_refs, ""]
    # 세목 축으로 제외한 건수를 먼저 밝힌다 — 목록이 짧아진 이유가 "다 봤다"로
    # 읽히면 안 되기 때문이다(조용한 축소 금지).
    dropped = [(law, v["세목제외"]) for law, v in report.items()
               if v.get("세목제외")]
    if dropped:
        lines.append("## 세목 축으로 제외된 조문 (검토 대상 아님)")
        lines.append("")
        for law, n in dropped:
            lines.append("- %s: %d건 — %s"
                         % (law, n, ", ".join(OUT_OF_SCOPE.get(law, []))))
        lines.append("")
        lines.append("전문은 coverage_audit.json의 `범위밖` 필드로 남아 있다.")
        lines.append("")

    cur_law = cur_ch = None
    for g in gaps:
        if g["법령"] != cur_law:
            cur_law, cur_ch = g["법령"], None
            lines.append("")
            lines.append("## " + cur_law)
        head = " · ".join(x for x in (g["장"], g["절"]) if x)
        if head != cur_ch:
            cur_ch = head
            lines.append("")
            lines.append("### " + (head or "(장 구분 없음)"))
            lines.append("")
        num = "§%d" % g["조문번호"]
        if g["가지번호"]:
            num += "의%d" % g["가지번호"]
        lines.append("- [ ] %s %s  (%s)" % (num, g["조문제목"], g["분류"]))
    (OUT_DIR / "coverage_gaps.md").write_text("\n".join(lines), encoding="utf-8")

    print("\n미반영 세액영향 조문 총 %d건 -> data/coverage/coverage_gaps.md" % len(gaps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
