"""도구 호출 사용량 로그(ASGI 미들웨어). 입력값·결과는 남기지 않는다.

POST /mcp 의 JSON-RPC tools/call 만 골라 한 줄 JSON을 stdout에 찍는다. Cloud Run은 이 줄을
Cloud Logging의 jsonPayload로 넣으므로 별도 저장소가 필요 없다(보관 30일, 개인정보처리방침과 동일).

남기는 값: tool, ok, error, ms, user, session, args, (실패 시) error_detail
- user/session: ChatGPT가 _meta["openai/subject"]·_meta["openai/session"]로 보내는 익명 ID를
  USAGE_SALT로 한 번 더 해시(앞 16자)한 값. 원본 ID·IP·위치(_meta["openai/userLocation"])는 남기지 않는다.
- ChatGPT 외 클라이언트(_meta 없음)는 user="-".
- args: 값이 채워진 인수의 **이름만** 모은 목록(예: ["acquisition_price", "homes"]).
  어떤 항목을 채워서 묻는지 집계하려는 것이므로 값은 절대 담지 않는다. 중첩 객체 안쪽 이름도 보지 않는다.
  스키마에 있는 식별자 형태(ASCII) 이름만 통과시키고, 그 외(한글 키 등)는 버린다 — 값이 키 자리에
  잘못 실려 오는 경우까지 막기 위한 안전장치다. USAGE_SALT를 바꾸면 user/session 해시가 달라져
  같은 사람이 다른 사람으로 집계되므로 한번 정한 값은 바꾸지 않는다.
  미들웨어에 도구 표(tools={도구명: 인수명 집합})를 주면 등록된 도구명과 그 도구 스키마의 인수명만 남긴다 —
  등록되지 않은 도구명은 "(unknown)"으로 바꾸고 인수는 남기지 않는다(임의의 문자열이 로그에 실리지 않게).
- 본문은 읽는 도중에 크기를 잰다. _MAX_BODY(1MB)를 넘으면 더 읽지 않고 413 으로 끊는다 — 큰 요청을 통째로
  메모리에 올리지 않는다. Content-Length 가 한도를 넘으면 본문을 읽기 전에 끊는다.
- JSON-RPC 모양이 아닌 요청(params 가 객체가 아님 등)은 기록하지 않고 그대로 넘긴다 — 입력 검증은 MCP 서버의 몫이다.
- error_detail: 도구 실패 시 이유를 값 없이 요약한 목록. 인수 검증 실패면 "항목:오류종류"
  (예: "article:missing", "year:int_parsing"), 도구 내부 예외면 "exception". 오류 문구 원문은
  입력값(input_value)을 담고 있으므로 저장하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time

_SALT = os.environ.get("USAGE_SALT", "budongsan-tax")
_MAX_BODY = 1_000_000
_MAX_FIELDS = 40
# 스키마 인수 이름은 모두 ASCII 식별자다. 이 모양이 아니면 로그에 올리지 않는다.
_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,47}$")


def _h(value) -> str:
    if not value or not isinstance(value, str):
        return "-"
    return hashlib.sha256((_SALT + value).encode()).hexdigest()[:16]


def _fields(arguments) -> list:
    """채워진 인수의 이름만 정렬해 돌려준다. 값은 담지 않는다."""
    if not isinstance(arguments, dict):
        return []
    names = [
        k for k, v in arguments.items()
        if isinstance(k, str) and _FIELD_RE.match(k) and v is not None and v != "" and v != [] and v != {}
    ]
    return sorted(names)[:_MAX_FIELDS]


def _calls(body: bytes, tools: dict | None = None):
    """tools/call 만 골라 (id, 도구명, user, session, 인수명) 목록으로. 모양이 어긋난 요청은 건너뛴다(예외를 내지 않는다).

    tools 가 있으면 등록된 도구명과 그 도구 스키마의 인수명만 남긴다.
    """
    try:
        msg = json.loads(body)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return []
    msgs = msg if isinstance(msg, list) else [msg]
    out = []
    for m in msgs:
        if not (isinstance(m, dict) and m.get("method") == "tools/call"):
            continue
        p = m.get("params")
        if not isinstance(p, dict):
            continue        # params 가 객체가 아니면 기록하지 않는다 — 오류 응답은 MCP 서버가 낸다
        meta = p.get("_meta")
        meta = meta if isinstance(meta, dict) else {}
        name, args = p.get("name"), _fields(p.get("arguments"))
        if tools is not None:
            if isinstance(name, str) and name in tools:
                args = [a for a in args if a in tools[name]]
            else:
                name, args = "(unknown)", []
        elif not (isinstance(name, str) and _FIELD_RE.match(name)):
            name = "?"
        rid = m.get("id")
        if not isinstance(rid, (str, int)) or isinstance(rid, bool):
            rid = None
        out.append((rid, name[:64], _h(meta.get("openai/subject")), _h(meta.get("openai/session")), args))
    return out


_VALIDATION_RE = re.compile(r"^(\S[^\n]*)\n[ \t]+[^\n]*?\[type=([a-z_]+)", re.M)
_TYPE_RE = re.compile(r"^[a-z_]{1,40}$")


def _error_detail(result: dict) -> list:
    """실패 이유를 값 없이 요약한다 — 예: ["article:missing", "year:int_parsing"].

    오류 문구에는 input_value=… 로 사용자가 넣은 값이 그대로 들어 있으므로 문구를 저장하지 않는다.
    pydantic 인수 검증 오류에서 '항목 경로'와 '오류 종류 코드'만 뽑고, 경로 조각도
    스키마 식별자(ASCII)나 목록 순번이 아니면 '?'로 가린다. 그 밖의 실패는 종류만 남긴다.
    """
    texts = [c.get("text", "") for c in (result.get("content") or [])
             if isinstance(c, dict) and isinstance(c.get("text"), str)]
    text = "\n".join(texts)[:20000]
    if "validation error" not in text:
        return ["exception"] if text.startswith("Error executing tool") else ["unknown"]
    out = []
    for loc, kind in _VALIDATION_RE.findall(text):
        parts = [p if (_FIELD_RE.match(p) or p.isdigit()) else "?" for p in loc.strip().split(".")]
        out.append("%s:%s" % (".".join(parts)[:80], kind if _TYPE_RE.match(kind) else "?"))
    return out[:10] or ["validation"]


def _results(body: bytes) -> dict:
    """id -> (ok, error_type, error_detail). JSON 응답(json_response=True) 기준."""
    try:
        msg = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {}
    res = {}
    for m in msg if isinstance(msg, list) else [msg]:
        if not isinstance(m, dict):
            continue
        if "error" in m:
            res[m.get("id")] = (False, "rpc_error", None)
        elif isinstance(m.get("result"), dict) and m["result"].get("isError"):
            res[m.get("id")] = (False, "tool_error", _error_detail(m["result"]))
        else:
            res[m.get("id")] = (True, None, None)
    return res


def emit(record: dict) -> None:
    record = {"event": "tool_call", "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **record}
    sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stdout.flush()


async def _too_large(send):
    body = b'{"error":"request body too large"}'
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class UsageLogMiddleware:
    def __init__(self, app, path: str = "/mcp", tools: dict | None = None, max_body: int | None = None):
        """tools: {도구명: 인수명 집합} — 주면 등록된 도구명·스키마 인수명만 기록한다. max_body: 본문 한도(기본 _MAX_BODY)."""
        self.app = app
        self.path = path
        self.tools = None if tools is None else {k: frozenset(v) for k, v in tools.items()}
        self.max_body = _MAX_BODY if max_body is None else max_body

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path", "").rstrip("/") != self.path:
            return await self.app(scope, receive, send)

        # 본문 크기는 읽기 전(Content-Length)과 읽는 도중에 잰다 — 한도를 넘는 요청은 메모리에 올리지 않고 끊는다.
        for k, v in scope.get("headers") or []:
            if k.lower() == b"content-length":
                try:
                    if int(v) > self.max_body:
                        return await _too_large(send)
                except ValueError:
                    pass
        # 요청 본문을 모아 두었다가 그대로 다시 흘려보낸다.
        chunks, size, more = [], 0, True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_body:
                return await _too_large(send)
            chunks.append(chunk)
            more = message.get("more_body", False)
        body = b"".join(chunks)
        try:
            calls = _calls(body, self.tools)
        except Exception:  # 로깅 때문에 요청이 실패하면 안 된다 — 기록 없이 그대로 넘긴다
            calls = []
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
            for rid, tool, user, session, args in calls:
                ok, err, detail = results.get(
                    rid, (False, f"http_{status}", None) if status >= 400 else (True, None, None))
                record = {"tool": tool, "ok": ok, "error": err, "ms": ms, "user": user, "session": session,
                          "args": args}
                if detail:
                    record["error_detail"] = detail
                try:
                    emit(record)
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
