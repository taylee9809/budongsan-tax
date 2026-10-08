# budongsan-tax

한국 **부동산 세금** 판정·계산 엔진이자 MCP 서버. 취득세·재산세·종합부동산세·양도소득세·임대소득세·
상속세·증여세(부동산)·재건축부담금을 다룬다. 결과마다 적용 조문과 미적용 조문(사유 포함), 입력값의
출처등급이 붙는다. 국세청·조세심판원·행안부의 공식 해석례·재결례를 정답지로 회귀 검증한다.

> 이 저장소는 세무대리가 아니다. 계산 결과는 조문 해석의 한 형태이며, 신고·불복·자문은 세무사·변호사의
> 영역이다. 저장소 소유자는 결과의 정확성을 보증하지 않는다(AGPL §15·§16).

## 왜 공개하나

법령은 저작권 보호 대상이 아니고(저작권법 §7), 심판·해석례도 같다. 그런데 그것을 **실행 가능하고
검증 가능한 형태**로 옮긴 것은 한국에 공개된 적이 없다. 세금 계산기는 많지만 어느 조·항·호가 반영됐고
어느 것이 빠졌는지 셀 수 있는 계산기는 없었다. 국민이 자기 세금을 스스로 검증할 수 있어야 하고,
그 도구는 정부 구현과 독립적으로 공개 검증되어야 한다는 생각으로 연다(프랑스 OpenFisca·Catala,
미국 IRS Direct File 공개와 같은 방향).

## 구조 — 4층

| 층 | 위치 | 역할 |
|---|---|---|
| 1 값 | `data/tax_params.json`, `tax_params.py` | 세율표·비율·상한. 연도 필수. 검증된 연도만 돌려준다 |
| 2 법문 코퍼스 | `data/legal_nodes/*.json` | 조문 원문·시행일·인용 키. 결과의 "근거" 필드가 여기를 가리킨다 |
| 3 판정·계산 | `tax_judgment.py`, `tax_server.py`, `entity_tax.py` | 계산기·판정기 43종. 함수 하나에 조문 여러 개가 들어 있는 **레거시 구조** — 아래 실행 노드로 옮기는 중 |
| 4 실행 노드 | `tax_nodes/` | **조·항·호 = 함수 하나.** 계산은 노드의 합성. 미적용 조문도 사유와 함께 기록. 현재 104개 (재산세·종부세) |
| 검증 | `data/verification/`, `tax_case_store.py` | 공식 해석례 1262건을 정답지로, 회귀 케이스 286건, 결함 기록 38건 |

## 설치·MCP 연결

```bash
pip install -r requirements.txt
cp .env.example .env     # 법령 조회가 필요하면 LAW_OC 채우기 (없어도 계산은 됨)
python tax_server.py     # stdio MCP 서버
```

Claude Desktop `claude_desktop_config.json`:

```json
{"mcpServers": {"budongsan-tax": {"command": "python", "args": ["/절대경로/tax_server.py"]}}}
```

검증 DB 만들기(선택, 회귀 테스트·재결례 검색용):

```bash
python scripts/verification_sync.py --rebuild     # data/verification/*.jsonl → data/tax_cases.db
python scripts/fetch_rulings.py                   # 재결례 본문 재수집 (LAW_OC 필요)
```

## 기여 방법 — 코드보다 케이스

기여 단위는 **케이스**다. 코드를 몰라도 된다.

1. **틀린 결과를 찾았다** → `data/verification/cases.jsonl`에 한 줄 추가: 입력, 기대 결과, 근거(심판례 청구번호나 조문).
   회귀 테스트가 실패하면 유지보수자가 노드를 고친다. 이것이 1급 기여다.
2. **조문을 옮기고 싶다** → [`docs/NODE_COVERAGE.md`](docs/NODE_COVERAGE.md)의 "전환 대기" 목록에서 한 줄을 고른다.
   `tax_nodes/jaesan.py`의 노드 하나를 본떠 함수 하나로 옮기고, 관련 케이스로 회귀를 돌린다.
3. **세법이 바뀌었다** → `data/tax_params.json`에 연도를 추가하고 출처(개정 법령·시행일)를 적는다.

세무사·수험생·연구자·개발자 누구든 환영한다. 노드 이름은 조문 번호를 그대로 쓴다(`제111조의2제1항`).

## 데이터 출처와 저작권

- 법령·시행령·조례: 법제처 국가법령정보 — 저작권법 §7 1호(보호 대상 아님)
- 조세심판원 결정·국세청 해석례·행안부 해석례: 저작권법 §7 2·3호. 발행 기관이 비식별 처리한 원문이며,
  이 저장소는 추가로 숫자 패턴(계좌·전화 등)을 지운 요약만 싣는다(`scripts/sanitize_public_text.py`).
  본문 전문은 싣지 않고 sha256만 남긴다 — 공개 API에서 다시 받을 수 있다.
- 이 저장소의 코드·노드·케이스: AGPL-3.0-or-later

## 라이선스

GNU Affero General Public License v3.0 or later. 이 엔진을 고쳐 네트워크 서비스로 제공하면 고친 소스를
같은 조건으로 공개해야 한다. 닫힌 SaaS에 넣고 싶으면 별도 라이선스를 문의하라.

---
생성: `scripts/package_opensource.py` (원본 git 0c73c09)
