"""외부 API 키가 에러 메시지·로그로 새는 것을 막는다.

2026-09-19 실측 2건: ① 건축HUB 503 때 MCP 도구 에러 메시지에 serviceKey가 든 URL이 그대로 실렸다(httpx.HTTPStatusError
문자열에 요청 URL이 들어간다) — 베타 로그·고객 채팅으로 나갈 수 있는 경로. ② httpx INFO 로그가 요청 URL을 찍어
배치 출력에 JUSO confmKey·VWorld key가 남았다.

install()을 프로세스 시작 시 한 번 부른다: raise_for_status가 던지는 예외 문자열에서 키 파라미터 값을 가리고,
httpx·httpcore 로거를 WARNING으로 올린다. 예외 객체의 request.url 자체는 바꾸지 않는다(재시도 로직이 쓸 수 있다).
"""
from __future__ import annotations

import logging
import re

import httpx

# 공공데이터포털 serviceKey · JUSO confmKey · VWorld key · 법제처 OC · 서울열린데이터(경로형은 아래 _PATH_KEY) 등
_KEY_PARAM = re.compile(r"(?i)\b(serviceKey|service_key|confmKey|crtfc_key|apiKey|api_key|authKey|key|OC|token)=([^&\s'\"]+)")
_PATH_KEY = re.compile(r"(openapi\.seoul\.go\.kr(?::\d+)?/)([^/\s]+)(/)")
_installed = False


def redact(text: str) -> str:
    text = _KEY_PARAM.sub(lambda m: f"{m.group(1)}=***", text or "")
    return _PATH_KEY.sub(r"\1***\3", text)


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    original = httpx.Response.raise_for_status

    def raise_for_status(self):  # type: ignore[no-untyped-def]
        try:
            return original(self)
        except httpx.HTTPStatusError as e:
            raise httpx.HTTPStatusError(redact(str(e)), request=e.request, response=e.response) from None

    httpx.Response.raise_for_status = raise_for_status  # type: ignore[method-assign]
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
