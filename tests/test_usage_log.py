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
    assert rec["args"] == ["acquisition_price"]  # 이름은 남고
    text = json.dumps(rec)
    assert "987654321" not in text and "Seoul" not in text and "user-x" not in text  # 값은 안 남는다


def test_args_keeps_names_only(monkeypatch):
    logged = []
    monkeypatch.setattr(usage_log, "emit", logged.append)
    body = json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {
        "name": "calc_transfer_tax", "arguments": {
            "transfer_price": 1_500_000_000,     # 값 → 이름만 남아야 한다
            "homes": 2,
            "address": "",                        # 빈 값 → 채우지 않은 것으로 본다
            "note": None,                         # null → 제외
            "owners": [],                         # 빈 목록 → 제외
            "서울시 강남구 1-2": "비밀",            # 식별자 모양이 아니면 버린다
            "nested": {"birth": "900101"},        # 중첩 안쪽은 들여다보지 않는다
        }}}).encode()
    _run(_fake_app({"content": []}), body)
    (rec,) = logged
    assert rec["args"] == ["homes", "nested", "transfer_price"]
    text = json.dumps(rec, ensure_ascii=False)
    for leaked in ("1500000000", "900101", "강남구", "비밀", "birth"):
        assert leaked not in text


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


def test_error_detail_names_fields_without_values(monkeypatch):
    """검증 실패 이유는 '항목:오류종류'만 남고, 오류 문구에 섞인 입력값은 남지 않는다."""
    logged = []
    monkeypatch.setattr(usage_log, "emit", logged.append)
    # FastMCP가 실제로 돌려주는 인수 검증 오류 문구 형태
    text = ("Error executing tool calc_transfer_tax: 3 validation errors for calc_transfer_taxArguments\n"
            "purchase_price\n  Input should be a valid integer, unable to parse string as an integer "
            "[type=int_parsing, input_value='987654321원', input_type=str]\n"
            "    For further information visit https://errors.pydantic.dev/2.14/v/int_parsing\n"
            "sale_price\n  Field required [type=missing, input_value={'purchase_price': '987654321원', "
            "'주소': '서울시 강남구'}, input_type=dict]\n"
            "    For further information visit https://errors.pydantic.dev/2.14/v/missing\n"
            "items.0.강남구\n  Field required [type=missing, input_value={}, input_type=dict]\n")
    call = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "calc_transfer_tax", "arguments": {"purchase_price": "987654321원", "sale_prise": 1}}}).encode()
    _run(_fake_app({"content": [{"type": "text", "text": text}], "isError": True}), call)
    (rec,) = logged
    assert rec["error"] == "tool_error"
    assert rec["error_detail"] == ["purchase_price:int_parsing", "sale_price:missing", "items.0.?:missing"]
    assert rec["args"] == ["purchase_price", "sale_prise"]  # 오타 난 인수 이름도 보인다
    dumped = json.dumps(rec, ensure_ascii=False)
    for leaked in ("987654321", "강남구", "input_value"):
        assert leaked not in dumped


def test_error_detail_for_exception_and_success(monkeypatch):
    logged = []
    monkeypatch.setattr(usage_log, "emit", logged.append)
    call = json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                       "params": {"name": "x", "arguments": {}}}).encode()
    _run(_fake_app({"content": [{"type": "text", "text": "Error executing tool x: 주민번호 900101"}],
                    "isError": True}), call)
    assert logged[-1]["error_detail"] == ["exception"] and "900101" not in json.dumps(logged[-1])
    _run(_fake_app({"content": []}), call)
    assert "error_detail" not in logged[-1]
