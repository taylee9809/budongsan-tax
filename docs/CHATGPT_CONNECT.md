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
3. **Create as a plugin**을 누르고 도구 목록을 확인한다. LAW_OC 설정 기준 43개다(법령·해석례·조례 조회 포함).
4. 생성된 플러그인을 설치한다.
5. 새 대화에서 `@`로 **Budongsan Tax**를 선택한 다음 아래 예시를 보낸다.

계정 및 워크스페이스 정책에 따라 메뉴 이용 가능 여부가 달라진다.
이 연결은 본인 계정 테스트이며 공식 디렉터리 공개 심사와는 별도다.

## 첫 테스트

> 가상 예시야. 2026년 주택 유상취득 5억원, 전용 84㎡, 개인 일반세율 적용이 확인됐고 중과·감면·조례 조정은 없어. 취득세와 부가세를 계산하고 입력 조건을 함께 적어줘.

실제 `calc_acquisition_tax` 호출 여부와 입력값을 확인한다.
다음에는 `plugin/review-cases.json`의 정상 5개 / 미지원·정보부족 3개 대화를 실행한다.
실행한 도구, 입력값, 응답, 오류를 기록한다. 아직 ChatGPT 대화 실행 결과는 없다.

## 확인된 범위

2026-10-12 00:42 KST 공개 HTTPS 검증:

- `/healthz`: HTTP 200, `status=ok`, `tools=39`, `law_lookup=false`.
- MCP 초기화와 도구 목록 조회 성공.
- 취득세, 재산세, 증여세, 부수토지 면적, 가족 간 대여금 예시 호출 성공.
- 음수 취득가액 입력 거부 확인.
- 로컬 검증 기록: `dist/render-public-check.json` (Git에는 포함하지 않음).

이는 통신 및 예시 실행 검증이다. 세법 정확성 전체 검증이나 ChatGPT의 도구 선택 검증은 아니다.

## 공개 제출에 남은 것

- 게시자: 이태연 / 고객지원: taylee9809@gmail.com (사용자 제공, OpenAI 신원 확인 완료 여부는 미확인).
- 실제 운영 내용을 반영한 공개 개인정보처리방침·이용약관·소개/지원 페이지.
- ChatGPT에서 실행한 데모와 대화 검증 결과.
- 게시자 신원 확인 및 제출 포털의 도메인 확인 절차.
- 제출 ZIP 생성, 자동 검사, 심사, 승인 후 공개.

현재 `plugin/mcp.json`은 실제 연결 주소를 담은 설정 파일이다. 단독 제출 ZIP은 아니다.
신원 정보·정책·데모 주소가 준비되면 `scripts/build_chatgpt_plugin.py`로 제출 ZIP을 만든다.
게시자 설정은 `plugin/publisher.json`, 공표 전 정책 초안은 `docs/POLICY_DRAFTS.md`에 있다.

공식 OpenAI 문서 (2026-10-12 확인):
- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.openai.com/plugins/deploy/submission
