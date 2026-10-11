# ChatGPT 연결 준비

배포된 서버의 실제 연결 값과 다음 단계는 [CHATGPT_CONNECT.md](CHATGPT_CONNECT.md)를 참고한다.

생성된 `tax_server.py`는 수정하지 않고 `tax_http.py`를 원격 연결 진입점으로 쓴다.
이 문서와 템플릿은 준비물이다. 인터넷 배포·ChatGPT 연결·심사 승인은 각각 따로 확인한다.

## 로컬 확인

```sh
pip install . 'mcp>=1.26,<2' pytest
python scripts/check_chatgpt_http.py
```

실제 HTTP 연결에서 initialize, tools/list, 예시 5개 호출, 잘못된 호출 3개 거부,
Host 검증, 도메인 확인 응답을 검사한다. `dist/chatgpt-http-check.json`에 결과를 남긴다.
이 검사는 LLM의 질문 이해·도구 선택이나 세법 정확도 검증을 대신하지 않는다.

## 호스팅

Docker 사용: `Dockerfile.chatgpt`. 시작 명령: `python tax_http.py`.
헬스 체크: `/healthz`. ChatGPT에 넣을 주소: 실제 HTTPS 도메인의 `/mcp`.

- `HOST=0.0.0.0`, `PORT`: 호스팅이 지정한 포트.
- `PUBLIC_BASE_URL`: 경로 없는 실제 HTTPS 주소. Render는 `RENDER_EXTERNAL_HOSTNAME` 자동 사용.
- `LAW_OC`: 선택. 없으면 실패하는 법령 검색 4개를 숨기고 로컬 계산·판정 39개를 제공한다.
- `OPENAI_APPS_CHALLENGE`: 제출 화면이 발급한 정확한 도메인 확인 문자열. 발급 전에는 설정하지 않는다.

공개 계산 서비스라 별도 고객 로그인을 요구하지 않는다. 접근 로그는 기본 비활성화하며
어댑터는 대화·도구 인자를 저장하지 않는다. 기존 계산 코드의 오류 로그와 호스팅 제공자의
접속·오류 로그 보관 정책은 별도 확인해야 한다. 운영자가 선택할 개인정보처리방침에 반영한다.

`render.yaml`은 무료 시험용 설정이다. 계정 연결 및 서비스 생성 후 실제 주소를 확인한다.
무료 인스턴스는 유휴 시 중단되므로 고객용 상시 서비스·심사 운영용으로 완료 처리하지 않는다.
유료 플랜 변경은 비용 확인 후 별도로 결정한다. GitHub 계정을 Render에 연결해야 CI 통과 후
자동 배포가 가능하다. 공개 저장소 URL만으로 생성한 서비스는 자동 배포가 지원되지 않는다.

## 플러그인 패키지

`plugin/manifest.template.json`과 `plugin/review-cases.json`을 검토한다.
게시자 이름은 OpenAI에서 본인/사업자 확인한 이름을 사용한다. 카테고리는 제출 화면에서 확인한다.
정상 대화 5개·지원하지 않는 요청 3개는 작성된 평가 시나리오이며, 아직 ChatGPT에서 실행하지 않았다.

다음 실제 값이 있어야 제출용 ZIP을 만든다:

- 고정 HTTPS MCP 주소
- 확인된 게시자 이름
- 서비스 소개·고객지원·개인정보처리방침·이용약관 페이지 주소
- ChatGPT에서 직접 실행한 데모 녹화의 공개 또는 리뷰어 접근 가능한 주소

```sh
python scripts/build_chatgpt_plugin.py --help
```

빌더는 위 값을 필수 인자로 받고 `dist/budongsan-tax-chatgpt.zip`을 만든다.
존재하지 않는 정책 페이지나 가짜 데모 주소로 제출하지 않는다.

## 실제 연결 및 제출 순서

1. HTTPS 배포 후 외부에서 initialize/tools/list/call을 다시 검증한다.
2. ChatGPT Plugins → Add custom MCP server에서 실제 `/mcp` 주소를 연결한다.
3. 시험 대화를 실행해 입력 확인·도구 선택·결과 설명을 검토하고 녹화한다.
4. 게시자 신원 확인, 실제 정책 페이지, 도메인 확인을 완료한다.
5. ZIP 업로드, 도구 검사, 심사 요청을 진행한다. 약관 동의와 신원 확인은 게시자가 직접 한다.
6. 승인 후 공개하고 플랫폼에서 발급된 실제 설치 링크를 확인한다.

공식 문서:
- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.openai.com/plugins/deploy/submission
- https://developers.openai.com/plugins/deploy/app-review
- https://render.com/docs/blueprint-spec
- https://render.com/docs/free
