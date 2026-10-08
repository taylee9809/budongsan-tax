"""법제처 법령 변경 감시 스크립트 (GitHub Actions에서 매일 실행).

추적 대상 법령의 최신 법령일련번호(MST)·공포일자·시행일자를 법제처 공동활용 API로
조회해 scripts/law_watch_state.json 과 비교하고, 변경이 있으면 changes.md 를 생성한다.
changes.md 가 생성되면 워크플로가 GitHub 이슈를 만들어 감수자(세무사)에게 알리고,
스킬 알고리즘 반영 체크리스트를 포함시킨다.

환경변수: LAW_OC (open.law.go.kr 발급 OC 아이디)
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# 스킬(툴) 알고리즘의 근거가 되는 법령만 추적한다. 검증상수 레지스트리·법문 노드
# (data/legal_nodes)와 동기 유지할 것 — 2026-08-17 코퍼스 13~14차 순회 확장분 반영.
TRACKED_LAWS = [
    "지방세법",                # 취득세·재산세 (tax_judgment 취득 주택수·중과)
    "지방세법 시행령",         # 저가주택 수도권1억/비수도권2억 등 — 스테일 사고 이력(외부대조 ⑪)
    "소득세법",                # 양도세 본법
    "소득세법 시행령",         # §154 비과세·§155 특례·§155의3 상생임대(일몰 2026-12-31)·§167 중과
    "소득세법 시행규칙",       # §70·71 부득이 사유 위임 + §23① 간주임대료 정기예금이자율(연례 개정)
    "종합부동산세법",
    "종합부동산세법 시행령",   # 공정시장가액비율(§2의4)·1주택 간주(§4의2) — 시행령만으로 변경 가능
    "상속세 및 증여세법",      # 9차 순회 코퍼스
    "상속세 및 증여세법 시행령",
    "상속세 및 증여세법 시행규칙",  # 무상사용 2%·임대료환산 12%·유사매매 요건(§15③)
    "법인세법 시행규칙",       # §43② 적정이자율 4.6% — 상증 §41의4 4단 위임 사슬의 말단
    "농어촌특별세법",          # 취득 부가세 축
    "농어촌특별세법 시행령",
    "도시 및 주거환경정비법",  # §39 조합원 지위양도(트리③)·§76 1+1 전매제한
    "도시 및 주거환경정비법 시행령",  # §37 소유10년·거주5년 + §37③ 예외
    "부동산 거래신고 등에 관한 법률",
    "부동산 거래신고 등에 관한 법률 시행령",  # 별표 1 자금조달계획서 제출기준
    "부동산 거래신고 등에 관한 법률 시행규칙",  # 별지 1호의3 서식
    "조세특례제한법",          # 감면 계열 — 일몰·연장이 매년 반복(§96 임대·§69 자경·§77 수용·§99의4·§71의2)
    "조세특례제한법 시행령",   # §66⑭ 자경 소득 3,700만원·§68의2 인구감소지역 가액·§96 임대 6억
    "지방세특례제한법",        # §36의3 생애최초 취득세 감면 한도 200/300만원 + 지방소득세 감면 대응 조문
    "재건축초과이익 환수에 관한 법률",  # §12 부과율(2023-12-26 완화)·§14의2 1세대1주택 감경·§8② 10년 상한
    "재건축초과이익 환수에 관한 법률 시행령",
    "부가가치세법 시행규칙",   # §2②2호 부동산매매업 반복거래 기준(1과세기간 1취득·2판매) — 사업자성 스크리닝
    "공인중개사법 시행규칙",
    "주택임대차보호법",
    "주택임대차보호법 시행령",  # §10·11 최우선변제 소액보증금 — 대출 모듈 방공제 상수(NL-방공제-상수)
]

STATE_PATH = Path(__file__).parent / "law_watch_state.json"
CHANGES_PATH = Path("changes.md")
API = "https://www.law.go.kr/DRF/lawSearch.do"


def fetch_current(oc: str, name: str) -> tuple[dict | None, str]:
    """법령명 정확 일치 항목의 현행 메타데이터를 반환한다.

    (결과, 실패사유)를 돌려준다. 조회 자체가 막힌 것과 "그런 법령이 없다"를
    호출자가 구분할 수 있어야 해서 사유를 같이 넘긴다 — 법제처 OC는 등록된
    IP/도메인에서만 동작해서, 실행 환경이 바뀌면 통째로 막히는 일이 생긴다.
    """
    params = {"OC": oc, "target": "law", "type": "JSON", "query": name, "display": 20}
    url = API + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            body = r.read().decode("utf-8", errors="replace")
    except Exception as e:  # 네트워크·HTTP 오류
        return None, f"요청 실패: {type(e).__name__} {e}"

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None, f"JSON 아님(에러 페이지 추정): {body[:200]}"

    if "LawSearch" not in data:
        # 법제처는 인증 실패 시에도 200 + JSON으로 응답한다.
        return None, f"API 거부: {data.get('msg') or data.get('result') or data}"

    laws = data["LawSearch"].get("law", [])
    if isinstance(laws, dict):
        laws = [laws]
    for law in laws:
        if law.get("법령명한글") == name and law.get("현행연혁코드") == "현행":
            return {
                "mst": law.get("법령일련번호"),
                "공포일자": law.get("공포일자"),
                "시행일자": law.get("시행일자"),
                "제개정구분": law.get("제개정구분명"),
            }, ""
    return None, "검색 결과에 정확히 일치하는 현행 법령 없음"


def main() -> int:
    oc = os.environ.get("LAW_OC")
    if not oc:
        print("LAW_OC 환경변수가 없습니다.", file=sys.stderr)
        return 1

    state = json.loads(STATE_PATH.read_text("utf-8")) if STATE_PATH.exists() else {}
    changes: list[str] = []
    failures: list[str] = []

    for name in TRACKED_LAWS:
        cur, reason = fetch_current(oc, name)
        if cur is None:
            print(f"[실패] {name} — {reason}", file=sys.stderr)
            failures.append(name)
            continue
        prev = state.get(name)
        if prev != cur:
            if prev is None:
                changes.append(f"- **{name}**: 추적 시작 (MST {cur['mst']}, 시행 {cur['시행일자']})")
            else:
                changes.append(
                    f"- **{name}**: {prev['시행일자']} → {cur['시행일자']} "
                    f"({cur['제개정구분']}, 공포 {cur['공포일자']}, MST {prev['mst']} → {cur['mst']})"
                )
            state[name] = cur

    if changes:
        CHANGES_PATH.write_text(
            "## 법령 변경 감지\n\n" + "\n".join(changes) + "\n\n"
            "### 감수·반영 체크리스트\n"
            "- [ ] 세무사 감수: 개정 내용이 세액 산정에 영향을 주는지 판단\n"
            "- [ ] 영향 있는 스킬(툴) 식별 (스킬 레지스트리 대조)\n"
            "- [ ] 해당 스킬 알고리즘에 시행일 분기 추가 (기존 로직 덮어쓰기 금지)\n"
            "- [ ] 골든 테스트 케이스 추가·갱신\n"
            "- [ ] CHANGELOG에 세액 변경 여부 명시 후 MINOR 릴리스\n",
            "utf-8",
        )
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
        print(f"변경 {len(changes)}건 감지 → changes.md 생성")
    else:
        print("변경 없음")

    # 조회에 실패한 법령이 하나라도 있으면 개정을 놓칠 수 있다. "변경 없음"과
    # 구분되도록 잡을 실패시켜야 함 — 조용한 성공이 제일 위험하다.
    if failures:
        print(f"\n조회 실패 {len(failures)}건: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
