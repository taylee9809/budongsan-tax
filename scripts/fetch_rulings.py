# -*- coding: utf-8 -*-
"""정답지 수집기 — 법제처 DRF에서 해석례·재결례 본문을 받아 data/rulings/에 보관.

  py scripts/fetch_rulings.py ttSpecialDecc "일시적2주택" 60
  py scripts/fetch_rulings.py ntsCgmExpc '"상생임대"'
  py scripts/fetch_rulings.py --load          # 수집분을 검증 DB에 적재만

target: ttSpecialDecc(조세심판원) | ntsCgmExpc(국세청해석) | moisCgmExpc(행안부) | expc(법령해석례)
      | prec(법원 판례 — S5, 대법원 한정 curt 필터. 상세는 ID=판례일련번호로 JSON 완결, 2026-08-24 개통)

검색 시맨틱 주의: 조세심판원은 공백=AND라 토큰 3개 이상이면 0건이 흔하다. 2토큰 이하로 쪼갤 것.
국세청·행안부는 공백=OR라 따옴표 구문으로 질의한다.
청구번호는 검색결과에만 있고 상세에는 비어 있어 _index.json으로 병합해 둔다.

원문 보관 근거: 저작권법 §7 3호 — schema_tax_cases.sql 헤더 참조.
MCP 런타임은 이 스크립트도 data/rulings/도 읽지 않는다 (검증 전용).
"""
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OC = os.environ.get("LAW_OC", "1356")  # 법제처 공동활용 신청 ID — .env로 덮어쓸 수 있게
BASE = "https://www.law.go.kr/DRF"
OUT = ROOT / "data" / "rulings"
INDEX = OUT / "_index.json"
ITEM_KEYS = ("decc", "cgmExpc", "expc", "prec")  # 소스별 결과 배열 키가 다르다
ID_KEYS = ("특별행정심판재결례일련번호", "법령해석일련번호", "법령해석례일련번호",
           "판례일련번호")  # "id"는 순번이라 쓰면 안 된다
NUM_KEYS = ("청구번호", "안건번호", "사건번호")
NAME_KEYS = ("사건명", "안건명")


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _first(d: dict, keys) -> str:
    return next((str(d[k]) for k in keys if d.get(k)), "")


def search(target: str, query: str, display: int = 50, page: int = 1) -> list[dict]:
    # search=2 는 본문검색. 빠뜨리면 제목검색(itmNm)으로 떨어져 0건이 되기 쉽다 — 2026-08-23 실측.
    url = (f"{BASE}/lawSearch.do?OC={OC}&target={target}&type=JSON&search=2"
           f"&query={urllib.parse.quote(query)}&display={display}&page={page}")
    if target == "prec":
        # S5는 대법원 판례만 수집(하급심 배제 — 확정 결론만 정답지로). curt 필터 2026-08-24 실측.
        url += "&curt=" + urllib.parse.quote("대법원")
    root = list(_get(url).values())[0]
    items = next((root[k] for k in ITEM_KEYS if k in root), [])
    if isinstance(items, dict):
        items = [items]
    print(f"total={root.get('totalCnt')} fetched={len(items)}")
    return [i for i in items if isinstance(i, dict)]


def detail(target: str, rid: str) -> dict:
    p = OUT / f"{target}_{rid}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    d = _get(f"{BASE}/lawService.do?OC={OC}&target={target}&ID={rid}&type=JSON")
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    time.sleep(0.4)
    return d


# ── 국세청 예규(S1) — 국세법령정보시스템 직접 수집 ────────────────────────────
# 법제처 DRF는 국세청 예규의 검색만 주고 본문 API가 없다(lawService.do가 오류 HTML 반환).
# 본문은 taxlaw.nts.go.kr 이 화면 렌더링에 쓰는 내부 액션 엔드포인트에서 그대로 받는다.
#
#   POST https://taxlaw.nts.go.kr/action.do   (application/x-www-form-urlencoded)
#     actionId=ASIQTB002PR01
#     paramData={"dcmDVO":{"ntstDcmId":"010000000000564680"}}
#
# 2026-08-23 실측: 쿠키·CSRF·세션 불필요, 순수 HTTP로 동작. paramData가 dcmDVO로 한 겹
# 감싸여 있어야 한다(안 감싸면 status=ERROR). robots.txt는 /is/USEISA001M.do·
# /is/USEISA003M.do 둘만 막으므로 이 경로는 허용 범위.
#
# 응답 구조: data.ASIQTB002PR01
#   .dcmDVO.ntstDcmTtl        안건명
#   .dcmDVO.ntstDcmGistCntn   요지
#   .dcmDVO.ntstDcmCntn       회신 본문
#   .dcmDVO.ntstDcmDscmCntn   문서번호(서면-2022-부동산-1656)
#   .dcmDVO.ntstDcmRplyCntn   회신번호(부동산납세과-3753)
#   .dcmDVO.ntstDcmRgtDt      등록일 YYYYMMDD
#   .dcmHwpEditorDVOList[].dcmFleByte   HWP 변환 HTML 전문 — "1. 사실관계"가 여기 있다
TAXLAW = "https://taxlaw.nts.go.kr"
NTS_ACTION = "ASIQTB002PR01"
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t ]+")


def _html_to_text(html: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", html or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", s)
    s = re.sub(r"(?i)</td>", "\t", s)
    s = _TAG.sub("", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
    s = _WS.sub(" ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def nts_detail(dcm_id: str) -> dict:
    """국세청 예규 1건의 전문을 받아 재결례와 같은 모양으로 정규화한다."""
    p = OUT / f"ntsCgmExpc_{dcm_id}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))

    body = urllib.parse.urlencode({
        "actionId": NTS_ACTION,
        "paramData": json.dumps({"dcmDVO": {"ntstDcmId": dcm_id}}, ensure_ascii=False),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{TAXLAW}/action.do", data=body,
        headers={"User-Agent": "Mozilla/5.0", "Referer": f"{TAXLAW}/qt/USEQTA002P.do",
                 "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read().decode("utf-8"))
    if res.get("status") != "SUCCESS" or not (res.get("data") or {}).get(NTS_ACTION):
        raise RuntimeError(f"{dcm_id}: {res.get('status')} {res.get('message')}")

    root = res["data"][NTS_ACTION]
    v = root.get("dcmDVO") or {}
    full = "\n\n".join(_html_to_text(h.get("dcmFleByte") or "")
                       for h in (root.get("dcmHwpEditorDVOList") or []))
    reply = (v.get("ntstDcmCntn") or "").strip()
    # rulings 테이블과 같은 스키마로 맞춘다 — '이유'에 회신 + 질의 전문을 붙인다.
    doc = {"CgmExpcService": {
        "재결청": "국세청", "청구번호": v.get("ntstDcmDscmCntn"),
        "사건번호": v.get("ntstDcmRplyCntn"), "의결일자": v.get("ntstDcmRgtDt"),
        "세목": v.get("ntstTlawClCd"), "사건명": v.get("ntstDcmTtl"),
        "재결요지": v.get("ntstDcmGistCntn"), "주문": "",
        "이유": (f"[회신]\n{reply}" + (f"\n\n[질의 전문]\n{full}" if full else "")),
        "관련법령": None, "데이터기준일시": v.get("lstAltDtm"),
    }}
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    time.sleep(0.6)
    return doc


def collect_nts(query: str, display: int = 50) -> int:
    """법제처 DRF로 검색 → ntstDcmId 추출 → 국세법령정보시스템에서 본문 수집."""
    OUT.mkdir(parents=True, exist_ok=True)
    entries, n = {}, 0
    for it in search("ntsCgmExpc", query, display):
        link = it.get("법령해석상세링크") or ""
        m = re.search(r"ntstDcmId=(\d+)", link)
        if not m:
            continue
        dcm_id = m.group(1)
        entries[dcm_id] = {
            "청구번호": it.get("안건번호", ""), "의결일자": it.get("해석일자", ""),
            "사건명": it.get("안건명", ""),
            "링크": f"{TAXLAW}/qt/USEQTA002P.do?ntstDcmId={dcm_id}",
        }
        try:
            nts_detail(dcm_id)
            n += 1
        except Exception as e:                                     # noqa: BLE001
            print(f"ERR {dcm_id}: {e}")
    _save_index(entries)
    print(f"보관 {n}건 · 인덱스 {len(entries)}건 갱신")
    return n


# ── 국세상담센터 상담사례(S4) — taxlaw 허용 경로 직접 수집 ──────────────────
# robots.txt는 /is/USEISA001M.do(통합검색)·003M(문장검색) 두 '화면'만 막는다. 상담사례
# 상세는 /is/USEISA004P.do(허용)이고, 그 화면이 쓰는 데이터 액션이 아래다(2026-08-24 실측
# — 사용자가 브라우저로 상세 URL을 확인해 준 것이 단서):
#
#   POST /action.do  actionId=ASEISA004MR01  paramData={"reqStdId":"299"}
#
# 쿠키·세션 불필요. 응답 data.ASEISA004MR01: stdTitle(질문)·answerStdContent(답변)·
# reqTpNm(상담유형)·regstDt(등록일시)·viewCnt. reqStdId는 1부터 이어지는 작은 정수 공간
# (2026-08-24 경계 실측 참조)이라 차단된 검색 화면을 전혀 쓰지 않고 전량 순회가 가능하다.
# ⚠️상담사례는 확정 결론이 아니다 — 신뢰등급 최하, 예규·심판례와 충돌 시 열위(보조 전용).
CNSL_ACTION = "ASEISA004MR01"
CNSL_TAX_PREFIXES = ("양도소득세", "상속증여세", "종합부동산세", "취득세")


def _cnsl_detail(req_std_id: int) -> dict | None:
    body = urllib.parse.urlencode({
        "actionId": CNSL_ACTION,
        "paramData": json.dumps({"reqStdId": str(req_std_id)}, ensure_ascii=False),
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{TAXLAW}/action.do", data=body,
        headers={"User-Agent": "Mozilla/5.0", "Referer": f"{TAXLAW}/is/USEISA004P.do",
                 "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=40) as r:
        res = json.loads(r.read().decode("utf-8"))
    d = (res.get("data") or {}).get(CNSL_ACTION) or {}
    return d if d.get("stdTitle") else None


def collect_cnsl(max_probe: int = 2000, start: int = 1) -> int:
    """reqStdId start..경계 전량 순회 — 부동산 세목만 보관. 경계는 연속 부재 20건으로 판정.

    보관하지 않은 ID는 재실행 시 다시 요청하게 되므로, 이어서 돌릴 땐 start를 직전 최대치+1로.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    entries, n, misses = {}, 0, 0
    i = start - 1
    while i < max_probe and misses < 20:
        i += 1
        p = OUT / f"ntsCnsl_{i}.json"
        if p.exists():
            misses = 0
            continue
        try:
            d = _cnsl_detail(i)
        except Exception as e:                                     # noqa: BLE001
            print(f"ERR {i}: {e}")
            time.sleep(2)
            continue
        if not d:
            misses += 1
            time.sleep(0.3)
            continue
        misses = 0
        tp = (d.get("reqTpNm") or "").strip()
        keep = tp.startswith(CNSL_TAX_PREFIXES) or "임대" in tp
        if keep:
            answer = _html_to_text(d.get("answerStdContent") or "")
            doc = {"CgmExpcService": {
                "재결청": "국세상담센터", "청구번호": f"세법상담-{i}",
                "사건번호": "", "의결일자": (d.get("regstDt") or "")[:8],
                "세목": tp, "사건명": (d.get("stdTitle") or "").strip(),
                "재결요지": answer[:300], "주문": "",
                "이유": f"[상담답변 — 확정 결론 아님·신뢰등급 최하]\n{answer}",
                "관련법령": None, "데이터기준일시": d.get("lstAltDtm"),
            }}
            p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
            entries[str(i)] = {"청구번호": f"세법상담-{i}", "의결일자": (d.get("regstDt") or "")[:8],
                            "사건명": (d.get("stdTitle") or "").strip(),
                            "링크": f"{TAXLAW}/is/USEISA004P.do?reqStdId={i}"}
            n += 1
        time.sleep(0.4)
    _save_index(entries)
    print(f"순회 {i}건 중 부동산 세목 보관 {n}건 · 인덱스 갱신")
    return n


def _save_index(entries: dict) -> None:
    idx = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    idx.update(entries)
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def collect(target: str, query: str, display: int = 50) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    entries, n = {}, 0
    for it in search(target, query, display):
        rid = _first(it, ID_KEYS)
        if not rid:
            continue
        entries[rid] = {
            "청구번호": _first(it, NUM_KEYS),
            "의결일자": it.get("의결일자") or it.get("회신일자") or it.get("선고일자", ""),
            "사건명": _first(it, NAME_KEYS),
            "링크": f"{BASE}/lawService.do?OC={OC}&target={target}&ID={rid}&type=HTML",
        }
        try:
            detail(target, rid)
            n += 1
        except Exception as e:                                     # noqa: BLE001
            print(f"ERR {rid}: {e}")
    _save_index(entries)
    print(f"보관 {n}건 · 인덱스 {len(entries)}건 갱신")
    return n


if __name__ == "__main__":
    import tax_case_store as store

    if "--load" not in sys.argv:
        target = sys.argv[1]
        if target == "ntsCnsl":
            # 상담사례(S4)는 검색 없이 reqStdId 전량 순회 — 인자: [max_probe] [start]
            collect_cnsl(int(sys.argv[2]) if len(sys.argv) > 2 else 2000,
                         int(sys.argv[3]) if len(sys.argv) > 3 else 1)
        else:
            query = sys.argv[2]
            disp = int(sys.argv[3]) if len(sys.argv) > 3 else 50
            # 국세청 예규는 법제처에 본문 API가 없어 국세법령정보시스템에서 직접 받는다.
            (collect_nts(query, disp) if target == "ntsCgmExpc" else collect(target, query, disp))
    store.init()
    print(store.load_rulings(), store.stats())
