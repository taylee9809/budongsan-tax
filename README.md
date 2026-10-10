# budongsan-tax

mcp-name: io.github.taylee9809/budongsan-tax

한국 부동산 세금을 계산하고 판정하는 엔진이다. MCP 서버로 돈다.
취득세, 재산세, 종합부동산세, 양도소득세, 주택임대소득세, 증여세와 상속세(부동산), 재건축부담금을 다룬다.

결과마다 적용한 조문, 봤지만 적용하지 않은 조문과 그 이유, 입력값의 출처 등급이 같이 나온다.

국세청, 조세심판원, 행정안전부의 공식 해석례와 재결례를 정답지로 두고 회귀 테스트를 돌린다.

세무대리가 아니다. 결과는 조문을 읽는 한 가지 방식이다. 신고와 불복은 세무사, 변호사와 하라.
정확성은 보증하지 않는다(AGPL §15, §16).

*English.* Korean real-estate tax engine and MCP server: acquisition, property, comprehensive holding,
capital gains, rental income, gift and inheritance tax, reconstruction levy. 43 tools,
350 statute nodes (one function per article or paragraph), official rulings as regression tests.
Every result carries the statute trail. Tool list with one-line descriptions: [`llms.txt`](llms.txt).

## 숫자

| | |
|---|---|
| MCP 도구 | 43 |
| 실행 노드 | 350 (조·항·호 하나가 함수 하나) |
| 전환 대기 조문 | 0 (법문 코퍼스에 있는 세액영향 조문은 전부 옮겼다) |
| 회귀 케이스 / 해석례 / 결함 기록 | 307 / 1318 / 39 |

## 구조

| 층 | 위치 | 내용 |
|---|---|---|
| 1 값 | `data/tax_params.json`, `tax_params.py` | 세율표, 비율, 상한. 연도별. 검증 안 된 연도는 돌려주지 않는다 |
| 2 법문 | `data/legal_nodes/` | 조문 원문과 시행일. 결과의 근거 필드가 여기를 가리킨다 |
| 3 판정·계산 | `tax_judgment.py`, `tax_server.py`, `entity_tax.py` | 도구 43개. 함수 하나에 조문 여러 개가 든 옛 구조 |
| 4 실행 노드 | `tax_nodes/` | 조문 하나가 함수 하나. 계산은 노드를 합성한 결과. 3층을 이걸로 바꾸는 중 |
| 검증 | `data/verification/`, `tax_case_store.py` | 케이스, 결함, 해석례 |

조문별 이관 상태는 [`docs/NODE_COVERAGE.md`](docs/NODE_COVERAGE.md)에 있다.
코퍼스에 원문이 없는 조문(미착수)은 원문을 넣는 일이 먼저다.

## 설치

```bash
pip install -r requirements.txt
cp .env.example .env      # 법령·해석례 조회 도구를 쓰려면 LAW_OC(법제처 Open API 키, 무료). 계산은 없어도 된다
python tax_server.py      # stdio MCP 서버
```

Claude Code:

```bash
claude mcp add budongsan-tax -- python /절대경로/tax_server.py
```

Claude Desktop `claude_desktop_config.json`:

```json
{"mcpServers": {"budongsan-tax": {"command": "python", "args": ["/절대경로/tax_server.py"]}}}
```

PyPI에 올라간 뒤에는 `uvx budongsan-tax` 한 줄로 뜬다. `server.json`과 `pyproject.toml`이 그 준비다.

회귀 테스트용 DB(선택):

```bash
python scripts/verification_sync.py --rebuild
python -m pytest tests
```

## 도구

이름 앞머리로 역할이 갈린다. `judge_*`는 세대, 주택 수, 비과세와 감면 요건 같은 사실을 판정한다. 먼저 돈다.
`calc_*`는 그 판정을 받아 세액을 낸다. `count_*`는 주택 수를 센다. `search_*`와 `get_*`는 법령, 조례, 해석례를
조회하는데 LAW_OC가 있어야 한다.

전체 목록과 한 줄 설명은 [`llms.txt`](llms.txt)에 있다.

## 기여

[`CONTRIBUTING.md`](CONTRIBUTING.md)를 보라. 틀린 결과 하나를 케이스 한 줄로 적어 주는 것이 가장 큰 기여다.
코드를 몰라도 된다.

## 출처와 저작권

- 법령, 시행령, 조례: 법제처 국가법령정보. 저작권법 §7 1호에 따라 보호 대상이 아니다
- 조세심판원 결정, 국세청·행안부 해석례: 저작권법 §7 2호, 3호. 발행 기관이 비식별한 원문이고, 여기서는
  숫자 패턴을 한 번 더 지운 요약만 싣는다(`scripts/sanitize_public_text.py`). 본문은 sha256만 남긴다
- 이 저장소의 코드, 노드, 케이스: AGPL-3.0-or-later

## 라이선스

GNU Affero General Public License v3.0 or later. 고쳐서 네트워크 서비스로 내놓으면 고친 소스를 같은 조건으로
공개해야 한다. 닫힌 서비스에 넣으려면 따로 문의하라.

---
생성: `scripts/package_opensource.py` (원본 git ee360cf)
