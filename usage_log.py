"""도구 호출 사용량 로그(ASGI 미들웨어). 입력값·결과는 남기지 않는다.

POST /mcp 의 JSON-RPC tools/call 만 골라 한 줄 JSON을 stdout에 찍는다. Cloud Run은 이 줄을
Cloud Logging의 jsonPayload로 넣으므로 별도 저장소가 필요 없다(보관 30일, 개인정보처리방침과 동일).

남기는 값: tool, ok, error, ms, user, session
- user/session: ChatGPT가 _meta["openai/subject"]·_meta["openai/session"]로 보내는 익명 ID를
  USAGE_SALT로 한 번 더 해시(앞 16자)한 값. 원본 ID·IP·위치(_meta["openai/userLocation"])는 남기지 않는다.
- ChatGPT 외 클라이언트(_meta 없음)는 user="-".
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

_SALT = os.environ.get("USAGE_SALT", "budongsan-tax")
_MAX_BODY = 1_000_000


def _h(value) -> str:
    if not value or not isinstance(value, str):
        return "-"
    return hashlib.sha256((_SALT + value).encode()).hexdigest()[:16]


def _calls(body: bytes):
    try:
        msg = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return []
    msgs = msg if isinstance(msg, list) else [msg]
    out = []
    for m in msgs:
        if isinstance(m, dict) and m.get("method") == "tools/call":
            p = m.get("params") or {}
            meta = p.get("_meta") or {}
            out.append((m.get("id"), str(p.get("name", "?"))[:64],
                        _h(meta.get("openai/subject")), _h(meta.get("openai/session"))))
    return out


def _results(body: bytes) -> dict:
    """id -> (ok, error_type). JSON 응답(json_response=True) 기준."""
    try:
        msg = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {}
    res = {}
    for m in msg if isinstance(msg, list) else [msg]:
        if not isinstance(m, dict):
            continue
        if "error" in m:
            res[m.get("id")] = (False, "rpc_error")
        elif isinstance(m.get("result"), dict) and m["result"].get("isError"):
            res[m.get("id")] = (False, "tool_error")
        else:
            res[m.get("id")] = (True, None)
    return res


def emit(record: dict) -> None:
    record = {"event": "tool_call", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **record}
    sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stdout.flush()


class UsageLogMiddleware:
    def __init__(self, app, path: str = "/mcp"):
        self.app = app
        self.path = path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path", "").rstrip("/") != self.path:
            return await self.app(scope, receive, send)

        # 요청 본문을 모아 두었다가 그대로 다시 흘려보낸다.
        chunks, more = [], True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            more = message.get("more_body", False)
        body = b"".join(chunks)
        calls = _calls(body) if len(body) <= _MAX_BODY else []
        if not calls:
            return await self.app(scope, _replay(body, receive), send)

        start = time.perf_counter()
        status, out = 500, []

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body" and sum(map(len, out)) < _MAX_BODY:
                out.append(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, _replay(body, receive), send_wrapper)
        finally:
            ms = round((time.perf_counter() - start) * 1000)
            results = _results(b"".join(out)) if status < 400 else {}
            for rid, tool, user, session in calls:
                ok, err = results.get(rid, (False, f"http_{status}") if status >= 400 else (True, None))
                try:
                    emit({"tool": tool, "ok": ok, "error": err, "ms": ms, "user": user, "session": session})
                except Exception:  # 로깅 실패가 응답을 막으면 안 된다
                    pass


def _replay(body: bytes, original):
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await original()  # 이후엔 실제 연결 끊김만 전달

    return receive
