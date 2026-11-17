import asyncio
import json

import usage_log


def _run(app, body: bytes):
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(m):
        sent.append(m)

    scope = {"type": "http", "method": "POST", "path": "/mcp"}
    asyncio.run(usage_log.UsageLogMiddleware(app)(scope, receive, send))
    return sent


def _fake_app(result):
    async def app(scope, receive, send):
        req = json.loads((await receive())["body"])
        payload = json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}).encode()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": payload})
    return app


def test_logs_hashed_ids_without_arguments(monkeypatch):
    logged = []
    monkeypatch.setattr(usage_log, "emit", logged.append)
    body = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {
        "name": "calc_acquisition_tax", "arguments": {"acquisition_price": 987654321},
        "_meta": {"openai/subject": "v1/user-x", "openai/session": "s-1",
                  "openai/userLocation": {"city": "Seoul"}}}}).encode()
    sent = _run(_fake_app({"content": []}), body)
    assert sent[-1]["type"] == "http.response.body"
    (rec,) = logged
    assert rec["tool"] == "calc_acquisition_tax" and rec["ok"] is True
    assert rec["user"] == usage_log._h("v1/user-x") and rec["user"] != "v1/user-x"
    text = json.dumps(rec)
    assert "987654321" not in text and "Seoul" not in text and "user-x" not in text


def test_tool_error_and_non_tool_calls(monkeypatch):
    logged = []
    monkeypatch.setattr(usage_log, "emit", logged.append)
    call = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "x", "arguments": {}}}).encode()
    _run(_fake_app({"content": [], "isError": True}), call)
    assert logged[-1]["ok"] is False and logged[-1]["error"] == "tool_error" and logged[-1]["user"] == "-"
    n = len(logged)
    _run(_fake_app({}), json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode())
    assert len(logged) == n
