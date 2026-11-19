# -*- coding: utf-8 -*-
"""PR #7 리뷰(2026-11-19)에서 나온 세액 오판·보안 지적을 공개 도구의 기대값으로 고정한다.

도구는 MCP 가 부르는 함수(tax_server·corporate_tax)를 그대로 부른다 — 판정기만 맞고 래퍼가 틀리는 일을 막는다.
tax_server.py 는 생성 파일이다. 여기서 깨지는 항목 가운데 법령 API 주소(HTTPS)와 calc_transfer_tax 의 basic_deduction 은
비공개 원본(server.py)에도 같은 수정이 들어가야 한다 — 원본을 고치지 않고 다시 생성하면 이 테스트가 깨진다.
"""
import asyncio
import inspect
import json
import pathlib

import pytest

import acquisition_checklist
import corporate_tax
import tax_judgment
import tax_server
import usage_log

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _home(label, std=500_000_000, **more):
    return dict({"종류": "주택", "시가표준액": std, "수도권": True, "라벨": label}, **more)


# ───────────────────────────────────────── 1. 취득세 일시적 2주택 — 종전 주택등 1개 요건(영 §28의5①)
def test_temporary_two_homes_needs_exactly_one_prior_home():
    kw = dict(in_adjusted_area=True, acquire_date="2026-03-02", prev_disposal_date="2027-03-02")
    two = tax_server.judge_acquisition_homes_and_rate([_home("A"), _home("신규", 700_000_000)], **kw)
    assert two["산입_주택수"] == 2 and two["일시적2주택"] is True and two["중과여부"] is False

    three = tax_server.judge_acquisition_homes_and_rate(
        [_home("A"), _home("B", 600_000_000), _home("신규", 700_000_000)], **kw)
    assert three["산입_주택수"] == 3
    assert three["일시적2주택"] is False
    assert three["중과여부"] is True and three["취득세율"] == 0.12
    assert three["일시적2주택_판정"]["종전주택등_1개요건"] is False


def test_rate_matrix_ignores_temporary_flag_outside_two_homes():
    r = tax_judgment.judge_acquisition_rate(3, True, temporary_two_homes=True)
    assert r["취득세율"] == 0.12 and r["중과여부"] is True
    r = tax_judgment.judge_acquisition_rate(2, True, temporary_two_homes=True)
    assert r["중과여부"] is False


# ───────────────────────────────────────── 2. 가격 누락은 0원이 아니다
def test_heavy_home_count_pending_when_local_price_missing():
    r = tax_server.count_heavy_homes([{"라벨": "서울", "기준시가": 900_000_000}, {"라벨": "지방", "지방소재": True}])
    assert r["중과판정_주택수"] is None
    assert r["중과판정_주택수_범위"] == [1, 2]
    assert r["확인필요"] == ["items[1].기준시가"]
    # 값을 주면 종전대로 확정된다
    low = tax_server.count_heavy_homes([{"라벨": "서울", "기준시가": 900_000_000},
                                        {"라벨": "지방", "지방소재": True, "기준시가": 250_000_000}])
    assert low["중과판정_주택수"] == 1 and "확인필요" not in low
    high = tax_server.count_heavy_homes([{"라벨": "서울", "기준시가": 900_000_000},
                                         {"라벨": "지방", "지방소재": True, "기준시가": 350_000_000}])
    assert high["중과판정_주택수"] == 2


def test_heavy_home_node_does_not_exclude_unpriced_local_home():
    from tax_nodes.setdae_jutaeksu import 중과판정_주택수
    r = 중과판정_주택수([{"라벨": "서울", "기준시가": 900_000_000}, {"라벨": "지방", "지방소재": True}])
    assert r["중과판정_주택수"] == 2 and "지방" not in r["불산입"]


def test_jongbu_low_price_home_pending_when_official_price_missing():
    r = tax_server.judge_jongbu_one_home_status([{"유형": "지방저가", "소재요건충족": True}], "2026-06-01")
    assert r["1세대1주택자_간주"] is None
    assert r["확인필요"] == ["other_homes[0].공시가격"]
    ok = tax_server.judge_jongbu_one_home_status(
        [{"유형": "지방저가", "소재요건충족": True, "공시가격": 390_000_000}], "2026-06-01")
    assert ok["1세대1주택자_간주"] is True
    over = tax_server.judge_jongbu_one_home_status(
        [{"유형": "지방저가", "소재요건충족": True, "공시가격": 410_000_000}], "2026-06-01")
    assert over["1세대1주택자_간주"] is False
    # 다른 주택이 이미 탈락이면 보류가 아니라 탈락이다
    mixed = tax_server.judge_jongbu_one_home_status(
        [{"유형": "지방저가", "소재요건충족": True}, {"유형": "일반"}], "2026-06-01")
    assert mixed["1세대1주택자_간주"] is False


def test_jongbu_low_price_node_does_not_deem_without_price():
    from tax_nodes.jongbu_setdae import 일세대일주택자_간주
    assert 일세대일주택자_간주([{"유형": "지방저가", "소재요건충족": True}], "2026-06-01")["1세대1주택자_간주"] is False
    assert 일세대일주택자_간주(
        [{"유형": "지방저가", "소재요건충족": True, "공시가격": 390_000_000}], "2026-06-01")["1세대1주택자_간주"] is True


# ───────────────────────────────────────── 3. 취득세 체크리스트 — 엔진이 받는 사실을 묻는다
def test_checklist_asks_engine_facts():
    keys = {i["항목"] for i in acquisition_checklist.get_acquisition_tax_checklist("매매")["물어볼_항목"]}
    assert {"low_price_home_zone", "inherited_home_date", "premarital_right", "officetel_details",
            "prev_home_adjusted_area"} <= keys
    plan = next(i for i in acquisition_checklist.ITEMS if i["key"] == "prev_disposal_plan")
    assert "2년" in plan["이유"] and "1개" in plan["이유"]


# ───────────────────────────────────────── 4. 매매업 비교과세 — 세율표 순서 무관
_BRACKETS_2026 = [
    {"upto": 14_000_000, "rate": 0.06, "deduction": 0},
    {"upto": 50_000_000, "rate": 0.15, "deduction": 1_260_000},
    {"upto": 88_000_000, "rate": 0.24, "deduction": 5_760_000},
    {"upto": 150_000_000, "rate": 0.35, "deduction": 15_440_000},
    {"upto": 300_000_000, "rate": 0.38, "deduction": 19_940_000},
    {"upto": 500_000_000, "rate": 0.40, "deduction": 25_940_000},
    {"upto": 1_000_000_000, "rate": 0.42, "deduction": 35_940_000},
    {"upto": None, "rate": 0.45, "deduction": 65_940_000},
]


@pytest.mark.parametrize("order", ["정상", "역순", "끝구간만_제자리"])
def test_dealer_comparative_tax_is_order_independent(order):
    br = {"정상": _BRACKETS_2026, "역순": _BRACKETS_2026[::-1],
          "끝구간만_제자리": _BRACKETS_2026[-2::-1] + _BRACKETS_2026[-1:]}[order]
    r = tax_server.calc_dealer_comparative_tax(0, 50_000_000, [], br)
    assert r["안2_나목_잔여과세표준세액"] == 6_240_000


@pytest.mark.parametrize("bad", [
    [],
    [{"upto": 14_000_000, "rate": 0.06, "deduction": 0}],                                      # 끝 구간 없음
    [{"upto": None, "rate": 0.45, "deduction": 0}, {"upto": None, "rate": 0.4, "deduction": 0}],  # 끝 구간 2개
    [{"upto": 14_000_000, "rate": 0.06}, {"upto": 14_000_000, "rate": 0.15}, {"upto": None, "rate": 0.45}],  # 상한 중복
    [{"upto": 14_000_000, "rate": 6, "deduction": 0}, {"upto": None, "rate": 0.45, "deduction": 0}],          # 세율이 %
    [{"upto": 14_000_000, "rate": 0.45, "deduction": 0}, {"upto": None, "rate": 0.06, "deduction": 0}],       # 세율 역전
])
def test_dealer_comparative_tax_rejects_malformed_brackets(bad):
    with pytest.raises(ValueError):
        tax_server.calc_dealer_comparative_tax(0, 50_000_000, [], bad)


# ───────────────────────────────────────── 5. 법인 대도시 취득 — 5년은 역법(민법 §157·§160)
@pytest.mark.parametrize("acquired, tax", [("2025-01-09", 8_000_000), ("2025-01-10", 8_000_000), ("2025-01-11", 4_000_000)])
def test_corporate_metro_five_years_is_calendar(acquired, tax):
    r = corporate_tax.calc_corporate_acquisition_tax(
        100_000_000, acquired, "주택외", property_in_metro=True, metro_office_date="2020-01-10")
    assert r["취득세"] == tax


def test_no_year_times_365_left_in_acquisition_nodes():
    src = (ROOT / "tax_nodes" / "chwideuk_gwase.py").read_text(encoding="utf-8")
    assert "* 365" not in src


# ───────────────────────────────────────── 6. 법령 API 는 HTTPS 만
def test_law_api_urls_are_https():
    assert tax_server.LAW_SEARCH_URL.startswith("https://www.law.go.kr/")
    assert tax_server.LAW_SERVICE_URL.startswith("https://www.law.go.kr/")
    for path in ("tax_server.py", "scripts/coverage_audit.py"):
        assert "http://www.law.go.kr" not in (ROOT / path).read_text(encoding="utf-8"), path


def test_law_search_does_not_follow_redirect_to_http(monkeypatch):
    """HTTPS 요청이 HTTP 로 되돌려지면(redirect) 따라가지 않고 실패한다 — 키가 평문으로 다시 나가지 않는다."""
    import httpx
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://www.law.go.kr/DRF/lawSearch.do"})

    real = httpx.AsyncClient

    def client(*a, **kw):
        assert not kw.get("follow_redirects"), "법령 API 클라이언트는 redirect 를 따라가지 않는다"
        return real(*a, transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(tax_server, "LAW_OC", "test-key")
    monkeypatch.setattr(tax_server.httpx, "AsyncClient", client)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(tax_server.search_law("지방세법"))
    assert len(seen) == 1 and seen[0].startswith("https://")


# ───────────────────────────────────────── 7. 사용량 로그 미들웨어
def _run_mw(app, chunks, headers=None, **mw):
    sent, it = [], iter(chunks)

    async def receive():
        try:
            body, more = next(it)
        except StopIteration:
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": body, "more_body": more}

    async def send(m):
        sent.append(m)

    scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": headers or []}
    asyncio.run(usage_log.UsageLogMiddleware(app, **mw)(scope, receive, send))
    return sent


def _echo_app(calls):
    async def app(scope, receive, send):
        calls.append((await receive())["body"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"jsonrpc":"2.0","id":1,"result":{"content":[]}}'})
    return app


def test_usage_log_stops_reading_oversized_body():
    reached, read = [], []

    def chunks():
        for _ in range(1000):
            read.append(1)
            yield (b"x" * 1000, True)

    sent = _run_mw(_echo_app(reached), chunks(), max_body=10_000)
    assert sent[0]["status"] == 413 and not reached
    assert len(read) <= 11          # 한도를 넘는 순간 그만 읽는다 — 전부 모은 뒤 검사하지 않는다


def test_usage_log_rejects_by_content_length_before_reading():
    reached, read = [], []

    def chunks():
        read.append(1)
        yield (b"{}", False)

    sent = _run_mw(_echo_app(reached), chunks(), headers=[(b"content-length", b"99999999")])
    assert sent[0]["status"] == 413 and not reached and not read


@pytest.mark.parametrize("params", ["x", 3, ["a"], None, {"name": {"a": 1}, "arguments": "x", "_meta": "y"}])
def test_usage_log_passes_malformed_jsonrpc_through(monkeypatch, params):
    logged, reached = [], []
    monkeypatch.setattr(usage_log, "emit", logged.append)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}).encode()
    sent = _run_mw(_echo_app(reached), [(body, False)], tools={"calc_transfer_tax": {"year"}})
    assert reached == [body] and sent[0]["status"] == 200     # 미들웨어가 500 을 내지 않고 MCP 서버로 넘긴다
    assert all(rec["tool"] == "(unknown)" and rec["args"] == [] for rec in logged)


def test_usage_log_records_only_registered_tools_and_schema_args(monkeypatch):
    logged = []
    monkeypatch.setattr(usage_log, "emit", logged.append)
    tools = {"calc_transfer_tax": {"year", "sale_price"}}

    def call(name, args):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name, "arguments": args}}).encode()
        _run_mw(_echo_app([]), [(body, False)], tools=tools)
        return logged.pop()

    rec = call("calc_transfer_tax", {"year": 2026, "sale_price": 1, "hong_gildong_900101": 1})
    assert rec["tool"] == "calc_transfer_tax" and rec["args"] == ["sale_price", "year"]
    rec = call("hong_gildong_900101", {"year": 2026})
    assert rec["tool"] == "(unknown)" and rec["args"] == []


# ───────────────────────────────────────── 그 밖의 지적
def test_transfer_tax_basic_deduction_zero_is_zero():
    kw = dict(purchase_price=500_000_000, sale_price=700_000_000, holding_years=1.0, necessary_expenses=0, year=2026)
    default = tax_server.calc_transfer_tax(**kw)
    zero = tax_server.calc_transfer_tax(basic_deduction=0, **kw)
    assert default["기본공제"] == 2_500_000 and zero["기본공제"] == 0
    assert inspect.signature(tax_server.calc_transfer_tax).parameters["basic_deduction"].default is None
    with pytest.raises(ValueError):
        tax_server.calc_transfer_tax(basic_deduction=-1, **kw)


def test_155_special_is_pending_until_prior_home_is_sold():
    kw = dict(prev_acquired="2020-01-01", new_acquired="2026-03-02")
    r = tax_server.judge_temporary_two_homes(**kw)
    assert r["특례충족"] is None and r["양도기한내"] is None and r["양도데드라인"] == "2029-03-02"
    assert tax_server.judge_temporary_two_homes(prev_sale_date="2029-03-02", **kw)["특례충족"] is True
    assert tax_server.judge_temporary_two_homes(prev_sale_date="2029-03-03", **kw)["특례충족"] is False
    # 다른 요건이 이미 탈락이면 양도일이 없어도 탈락이다
    assert tax_server.judge_temporary_two_homes(prev_meets_exemption=False, **kw)["특례충족"] is False


def test_ruling_verifier_strict_fails_only_on_new_mismatch(tmp_path, capsys):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import verify_node_cases as v
    from tests import test_rulings3_cases as t3, test_rulings4_cases as t4, test_rulings6_cases as t6
    known = set(t3._알려진_불일치) | set(t4._알려진_불일치) | set(t6._알려진_불일치)
    assert set(v.알려진_불일치) <= known                    # 스크립트가 봐주는 불일치는 테스트에도 알려진 것이어야 한다
    assert v.main(["--strict"]) == 0                       # 알려진 불일치만 있으면 통과
    bad = tmp_path / "new.jsonl"
    bad.write_text(json.dumps({"case_id": "NEW-1", "방식": "함수", "함수": "tax_judgment._add_years",
                               "인자": {"d": "x", "years": 1}, "기대": {"없는키": 1}}, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    assert v.main(["--strict", str(bad)]) == 1             # 새 불일치는 실패
    assert v.main([str(bad)]) == 0                         # --strict 없이는 종전대로 0
    capsys.readouterr()


def test_sangsaeng_pre_acquisition_lease_is_pending_with_both_readings():
    """상생임대 — 취득 전 체결·취득과 동시에 개시한 임대차: 예규(불충족)와 조심 2026서2935(충족)가 갈린다. 확정하지 않는다."""
    from tax_nodes.yangdo_gigan import _상생판정
    from datetime import date
    first = {"임차인": "A", "계약일": "2021-01-20", "개시일": "2021-03-16", "종료일": "2023-03-15", "보증금": 400_000_000}
    second = {"임차인": "B", "계약일": "2023-02-10", "개시일": "2023-03-16", "종료일": "2025-03-15", "보증금": 420_000_000}
    r = _상생판정([first, second], date(2021, 3, 16), date(2025, 7, 8), "20250708")
    assert r["충족"] is None
    assert r["해석충돌"]["예규"]["충족"] is False and r["해석충돌"]["심판례"]["충족"] is True
    # 전 소유자의 임차인을 승계한 계약(취득 전 개시)은 다툼 없이 직전임대차계약이 아니다 — 보류가 아니라 탈락
    inherited = dict(first, 개시일="2021-02-01")
    assert _상생판정([inherited, second], date(2021, 3, 16), date(2025, 7, 8), "20250708")["충족"] is False
    # 취득 후 체결한 계약이면 종전대로 충족
    after = dict(first, 계약일="2021-03-16")
    assert _상생판정([after, second], date(2021, 3, 16), date(2025, 7, 8), "20250708")["충족"] is True
