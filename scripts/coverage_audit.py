"""조문 커버리지 감사 — 추적 법령의 전 조문 대비 법문 노드 반영 여부를 대조한다.

배경(2026-08-30): 종부세 계산에서 지방세법 §110③ 주택 과세표준상한제가 누락돼
세액이 틀렸다. 원인은 값이 낡아서가 아니라 **조항이 애초에 코퍼스에 없어서**였다.
검증상수 표(1층)와 연도 필수화(2층)로는 이 유형을 못 막는다 — 목록에 없는 것은
지킬 수 없기 때문이다. 이 스크립트가 3층으로, 법령 원문의 조문 목록을 정본으로 놓고
data/legal_nodes 에 노드가 있는지 역대조해 미반영 조문을 뽑는다.

산출물:
  data/coverage/coverage_audit.json  — 법령별 전 조문 + 커버 여부 + 분류
  data/coverage/coverage_gaps.md     — 미반영 '세액영향' 조문만 추린 검토용 목록

사용:
  py scripts/coverage_audit.py             # 추적 법령 전체
  py scripts/coverage_audit.py 지방세법     # 특정 법령만
환경변수: LAW_OC
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


def main():
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc:
        print("LAW_OC 환경변수가 필요합니다", file=sys.stderr)
        return 1
    targets = sys.argv[1:] or TRACKED_LAWS
    node_refs = load_node_refs()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 인자로 법령 하나만 주고 돌리는 일이 잦은데(방금 고친 조문만 확인), 그때
    # 보고서를 통째로 다시 쓰면 나머지 26개 법령의 측정치가 조용히 사라진다.
    # 2026-08-31에 실제로 한 번 날렸다 — 기존 결과를 읽어 부분 갱신으로 병합한다.
    prev_path = OUT_DIR / "coverage_audit.json"
    report = {}
    if prev_path.exists() and set(targets) != set(TRACKED_LAWS):
        try:
            report = json.loads(prev_path.read_text(encoding="utf-8"))
            print("  기존 보고서 %d개 법령을 유지하고 %d개만 갱신한다"
                  % (len(report), len(targets)))
        except (ValueError, OSError):
            report = {}
    gaps = []
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
        covered = node_refs.get(name, set())
        rows = []
        for a in articles(doc):
            key = (a["조문번호"], a["가지번호"])
            excl = [c for c in OUT_OF_SCOPE.get(name, [])
                    if a["장"].startswith(c) or a["절"].startswith(c)]
            if not excl and name.startswith(("지방세법", "지방세특례제한법")):
                excl = ["비부동산:" + k for k in OUT_OF_SCOPE_TITLE_KW if k in a["조문제목"]][:1]
            dom = any(k in a["조문제목"] for k in DOMAIN_KW)
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
                        "세목제외": n_out, "조문": rows}
        print("  %-30s 조문 %4d / 커버 %3d / 미커버 세액영향 %4d / 검토대상 %3d"
              "%s" % (name, len(rows), n_cov, n_tax, n_gap,
                      "  (세목 제외 %d)" % n_out if n_out else ""))

    (OUT_DIR / "coverage_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

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
