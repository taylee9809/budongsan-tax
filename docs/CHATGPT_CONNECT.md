# 내 ChatGPT에 연결하기

현재 배포 주소: https://budongsan-tax-793377969551.asia-northeast3.run.app

## 입력할 값

| 항목 | 값 |
| --- | --- |
| 이름 | Budongsan Tax |
| 설명 | 한국 부동산 세금 계산 및 요건 판정 도구 |
| MCP URL | `https://budongsan-tax-793377969551.asia-northeast3.run.app/mcp` |
| 인증 | None / 인증 없음 |

1. https://chatgpt.com/plugins 에서 `+` → **Add custom MCP server**를 선택한다.
2. 위 값을 입력하고 표시된 연결 안내를 확인한다.
3. **Create as a plugin**을 누르고 도구 목록을 확인한다. LAW_OC 설정 기준 52개다(법령·해석례·조례 조회 4개 포함, 없으면 48개).
4. 생성된 플러그인을 설치한다.
5. 새 대화에서 `@`로 **Budongsan Tax**를 선택한 다음 아래 예시를 보낸다.

계정 및 워크스페이스 정책에 따라 메뉴 이용 가능 여부가 달라진다.
이 연결은 본인 계정 테스트이며 공식 디렉터리 공개 심사와는 별도다.

## 첫 테스트

> 가상 예시야. 2026년 주택 유상취득 5억원, 전용 84㎡, 개인 일반세율 적용이 확인됐고 중과·감면·조례 조정은 없어. 취득세와 부가세를 계산하고 입력 조건을 함께 적어줘.

실제 `calc_acquisition_tax` 호출 여부와 입력값을 확인한다.
다음에는 `plugin/review-cases.json`의 정상 5개 / 미지원·정보부족 3개 대화를 실행한다.
실행한 도구, 입력값, 응답, 오류를 기록한다. 아직 ChatGPT 대화 실행 결과는 없다.

## 대체 도구

지금 대체 도구는 없다(`tax_overrides.py`의 `OVERRIDES`가 비어 있다). 2026-11-19에 아래 입력을 생성기 원본의 래퍼에 넣고 `tax_server.py`를 다시 만들어, 생성 도구가 이 입력을 직접 받는다(`estimate_reconstruction_levy`의 개발비용 항목 입력 포함, 9개 도구 33개 인자). 공개 저장소의 판정기·조문 노드에 새 입력이 생겨 생성 래퍼가 넘기지 못하게 되면 같은 이름의 고친 판을 `OVERRIDES`에 두어 호스팅 서버에서 대체한다 — `scripts/wrapper_gaps.py`와 `tests/test_tax_overrides.py`가 그 틈을 잡는다.

| 도구 | 원본에 되돌려 넣은 입력 |
|---|---|
| `judge_transfer_reliefs` | 토지거래허가 사실(한시 배제 나목), 보유 목록으로 중과 판정 |
| `count_heavy_homes` | 양도 주택을 지정하면 같은 목록으로 중과 대상·가산세율 판정 |
| `judge_temporary_two_homes` | 조정대상지역 공고일(영 §155①1호 대괄호, 2026-09-30 개정) |
| `judge_acquisition_homes_and_rate` | 종전 주택등의 조정대상지역 여부, 신규 주택 계약일·계약금 지급일(영 §28의5①, 2026-09-30 개정) |
| `judge_155_special` | 양도일 현재 세대 주택 수 |
| `judge_156_3_from_portfolio` | 분양권 완공 여부, 그 밖의 주택 수 직접 지정 |
| `calc_attached_land_limit` | 멸실된 상속주택의 정착면적·양도일 |
| `calc_property_tax` | 지방세특례제한법 경감과의 비교(지방세법 §111의2④) |

`judge_jongbu_one_home_status`는 인자를 더하지 않았다 — 2026-09-30 개정의 조정대상지역 2년 판정 입력은 `other_homes` 원소의 키라 생성 도구로도 닿고, 그 키를 호스팅 설명에 적었다. 인자별 뜻과 근거 조문, 원본 래퍼에 되돌려 넣을 목록은 `docs/WRAPPER_GAPS.md`(`python scripts/wrapper_gaps.py`가 만든다)에 있다. `calc_jongbu_tax`(공제 0원·법인 거부)와 `calc_acquisition_tax`(§13의2는 주택 유상취득만)는 2026-11-18 생성기 원본에서 고쳐 다시 생성했으므로 대체하지 않는다.

## 확인된 범위

2026-10-12 00:42 KST 공개 HTTPS 검증:

- `/healthz`: HTTP 200, `status=ok`, `tools=48`, `law_lookup=false`.
- MCP 초기화와 도구 목록 조회 성공.
- 취득세, 재산세, 증여세, 부수토지 면적, 가족 간 대여금 예시 호출 성공.
- 음수 취득가액 입력 거부 확인.
- 로컬 검증 기록: `dist/render-public-check.json` (Git에는 포함하지 않음).

이는 통신 및 예시 실행 검증이다. 세법 정확성 전체 검증이나 ChatGPT의 도구 선택 검증은 아니다.

## 공개 제출에 남은 것

- 게시자: OpenAI 본인 인증을 마친 이름을 제출 시점에 입력 / 고객지원: 서비스 전용 메일(Cloud Run 환경변수 SUPPORT_EMAIL).
- 실제 운영 내용을 반영한 공개 개인정보처리방침·이용약관·소개/지원 페이지.
- ChatGPT에서 실행한 데모와 대화 검증 결과.
- 게시자 신원 확인 및 제출 포털의 도메인 확인 절차.
- 제출 ZIP 생성, 자동 검사, 심사, 승인 후 공개.

현재 `plugin/mcp.json`은 실제 연결 주소를 담은 설정 파일이다. 단독 제출 ZIP은 아니다.
신원 정보·정책·데모 주소가 준비되면 `scripts/build_chatgpt_plugin.py`로 제출 ZIP을 만든다.
게시자 설정은 `plugin/publisher.json`, 정책 본문은 `policy_pages.py`(/privacy, /terms)에 있다.

공식 OpenAI 문서 (2026-10-12 확인):
- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.openai.com/plugins/deploy/submission
