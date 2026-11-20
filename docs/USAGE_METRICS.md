# 사용량 확인

`tax_http.py`는 `/mcp`의 `tools/call`마다 stdout에 한 줄 JSON을 남긴다(`usage_log.py`). Cloud Run이 이를 Cloud Logging `jsonPayload`로 수집한다(보관 30일).

```json
{"event":"tool_call","ts":"…","tool":"calc_transfer_tax","ok":true,"error":null,"ms":12,"user":"b38b7cbb8156d072","session":"2d59cf3ade9e4e70"}
```

- `user`/`session`: ChatGPT가 보내는 `_meta["openai/subject"]`·`_meta["openai/session"]`을 `USAGE_SALT`로 다시 해시한 값. ChatGPT 외 클라이언트는 `-`.
- `args`: 값이 채워진 인수의 **이름만**(예: `["article_id"]`). 인수 이름을 잘못 보낸 실패도 여기서 보인다.
- `error_detail`(실패 시에만): 실패 이유를 값 없이 요약. 인수 검증 실패면 `"항목:오류종류"`(예: `"article:missing"`, `"year:int_parsing"`), 도구 내부 예외면 `"exception"`. 오류 문구 원문에는 입력값이 섞여 있어 저장하지 않는다.
- 입력값·결과·위치·IP는 남기지 않는다. 끄려면 `USAGE_LOG=0`.
- Cloud Run 환경변수에 `USAGE_SALT`를 임의의 긴 문자열로 설정한다(바꾸면 사용자 연속성이 끊긴다).

## 보기

빠른 확인(Logs Explorer):

```
resource.type="cloud_run_revision"
jsonPayload.event="tool_call"
```

집계 리포트(고유 사용자, 사용자당 호출·대화·사용일수, 재방문율, 일별 활성/신규, 도구별 실패율, 실패 내역(이유·보낸 항목 이름)):

```
gcloud logging read 'resource.type="cloud_run_revision" AND jsonPayload.event="tool_call"' --freshness=30d --format=json --project=PROJECT > usage.json
py scripts/usage_report.py usage.json
```

30일보다 오래 보려면 Cloud Logging 싱크로 BigQuery에 보낸다.
