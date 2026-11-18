# 기여 안내

기여 단위는 케이스다. 코드는 그다음이다.

## 1. 틀린 결과를 찾았다

`data/verification/cases.jsonl`에 한 줄을 더한다. 필드는 이렇다.

```json
{"case_id": "JB-15", "tool": "judge_jongbu_one_home_status",
 "input_json": "{\"other_homes\": [{\"유형\": \"상속\", \"상속개시일\": \"2022-01-01\", \"지분율\": 1.0, \"지분공시가\": 700000000, \"수도권\": true}], \"base_date\": \"2027-06-01\"}",
 "expected_key": "1세대1주택자_간주", "expected_json": "false",
 "expected_사유": "상속개시 5년 경과, 지분 40% 초과, 지분공시가 6억 초과",
 "rid": null, "분류": "설계통제군", "사실요약": "2027 귀속, 2022-01-01 상속개시, 단독상속 수도권 7억."}
```

- `tool` 은 `tax_server.py`의 도구 이름
- `expected_key` 는 결과 dict에서 비교할 키, `expected_json` 은 기대값(JSON)
- 근거가 심판례나 해석례면 `rid`에 청구번호나 문서번호를 적는다. 조문이면 `expected_사유`에 조·항·호를 적는다
- 경험치나 관행은 근거가 아니다. 원문이 있어야 한다

그다음 `python scripts/verify_tool_cases.py --case JB-15` 로 그 케이스를 돌려 본다(`--tool 이름`은 도구 하나, 인자 없이 전체).
`python scripts/verification_sync.py --rebuild` 로 DB를 다시 만들고 `python -m pytest tests` 를 돌린다.
실패하면 그대로 PR을 올려도 된다. 고치는 건 유지보수자 몫이다.

## 2. 조문을 노드로 옮기고 싶다

`docs/NODE_COVERAGE.md`에서 아직 노드가 없는 조문을 고른다. 노드 하나는 이렇게 생겼다.

```python
@노드(
    id="지방세법-114",
    법령="지방세법", 조="114", 제목="과세기준일", mst="282559",
    원문="재산세의 과세기준일은 매년 6월 1일로 한다.",
    산출=("과세기준일",),
)
def 제114조(ctx):
    return "%04d0601" % ctx.연도
```

규칙은 네 가지다.

- 함수 하나가 조문 하나. 항이나 호가 갈리면 노드도 가른다
- `원문`은 법제처 원문을 그대로 옮긴다. 요약하지 않는다
- 적용되지 않으면 값 대신 `미적용("사유")`를 돌려준다. 기록에 남는다
- 이름은 조문 번호를 그대로 쓴다(`제111조의2제1항`)

`tax_nodes/jaesan.py`가 가장 짧은 본보기다. 옮긴 뒤 관련 케이스로 회귀를 돌린다.

항 아래 호를 일부만 옮기면 `python scripts/node_coverage.py` 의 '호·목 점검'에 나머지 호가 전환 대기로 뜬다.
형제 호·목의 목록은 `data/coverage/subunits.json`(법령 원문의 항·호·목 구조, 범위 안 조문 전부)에서 읽는다.
옮기지 않아도 되는 호(삭제, 부동산이 아닌 과세대상 등)는 `data/coverage/subunit_dispositions.json`에 처리와 사유를 적는다.
판단이 서지 않으면 적지 않는다. 전환 대기로 남는 것이 맞다.
`mst=`에는 원문을 확인한 판의 법령일련번호(law.go.kr 주소의 `lsiSeq`, 예 `290815`)를 적는다. `005077` 같은 법령ID는 판을 가리키지 않는다.
기존 판정기(`tax_judgment.py`)가 있는 조문이면 `scripts/experiments/verify_*_nodes.py`처럼 격자 대조를 붙인다.

## 3. 세법이 바뀌었다

`data/tax_params.json`의 해당 키에 연도를 더하고, `근거`에 개정 법령 번호와 시행일을 적는다.
연도를 안 적은 값은 엔진이 거부한다. 그게 의도다.

## 4. 원문이 코퍼스에 없다

`data/legal_nodes/*.json` 형식으로 조문 원문을 넣는다. 법제처 수집본에서 옮기고 MST(법령 일련번호)와 시행일을 붙인다.
이 작업이 끝나야 2번이 가능하다.

## 5. 조문 목록을 다시 만든다 (법령이 개정됐다, 추적 법령을 더했다)

커버리지는 두 단계로 센다. 순서대로 돌린다.

```
python scripts/coverage_audit.py --source web     # 추적 법령 전 조문 → data/coverage/coverage_audit.json · coverage_gaps.md · subunits.json
python scripts/node_coverage.py                   # 실행 노드 역대조 → docs/NODE_COVERAGE.md
python scripts/node_mst_check.py                  # 노드·검증상수가 인용한 판(MST)과 현행 대조 → data/coverage/node_mst_check.md
```

- `--source web`은 키 없이 law.go.kr 웹 본문을 받는다(`scripts/law_web.py`, 캐시 `data/law_cache/web_*.json`은 저장소에 넣지 않는다. 다시 받으려면 `--refresh`).
  법제처 Open API 키가 있으면 `LAW_OC=… python scripts/coverage_audit.py`(`--source` 없이)로 같은 모양의 결과가 나온다.
- 웹 경로는 본문 텍스트를 "제N조(제목)"·"①"·"1."·"가." 표지로 나눈다. 돌릴 때마다 앞선 `coverage_audit.json`과 달라진 조문(신설·없어짐·제목 변경)을 출력하니,
  그 목록이 실제 개정과 맞는지 본다. 설명되지 않는 차이는 파서 문제다. 2026-11-18 대조: API로 만든 27개 법령 목록과 조문 번호·장·절이 전부 일치했고,
  차이는 그 뒤의 신설 조문(조세특례제한법 4개, 부동산 거래신고 등에 관한 법률 4개), 장래 시행분의 제목(소득세법·시행령 7개), 가운뎃점 문자(6개)뿐이었다.
- 시행일이 아직 오지 않은 개정 조문은 현행 본문을 쓴다. 현행이 삭제이거나 없는 조문만 장래분을 싣고 `시행일자`에 그 날짜를 적는다.
- 호가 표 이미지로 실린 조문(농어촌특별세법 §5①)은 본문에서 읽히지 않는다. `data/coverage/subunits_supplement.json`에 손으로 옮기고 확인한 판을 적는다.
- `subunits.json`에는 범위 밖 조문(레저세, 법인세 일반 등)을 싣지 않는다. 그런 조문에 호 단위 노드를 두면 `node_coverage.py`가 번호만으로 형제를 추정하고 그렇게 표시한다.
- API 경로의 항·호·목 읽기(`subunits_of`)는 실제 응답으로 검증하지 못했다(가상 응답 시험뿐). 키가 생기면 한 법령을 두 경로로 돌려 `subunits.json`이 같은지 본다.
- 세목별 요약표는 조문 제목 키워드로 '세액영향'이라 분류된 조문만 센다. 그 밖의 조문은 `docs/NODE_COVERAGE.md`의 '요약표에 들지 않는 조문'에 따로 나온다.
- `node_mst_check.py`는 목록만 낸다. 달라진 조문의 노드는 원문을 다시 대조해 고치고 `mst`를 현행 번호로 바꾼다.

## 하지 않는 것

- 경매·공매 데이터, 매물, 가액 추정, 대출, 리포트는 이 저장소 밖이다
- 특정 납세자의 신고를 대신하는 기능은 넣지 않는다

라이선스는 AGPL-3.0-or-later다. 기여한 코드와 케이스도 같은 라이선스다.
