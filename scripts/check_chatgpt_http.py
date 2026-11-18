"""Exercise the hosted adapter over real HTTP using synthetic inputs; no LLM required."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES = [
    ("calc_acquisition_tax", {"acquisition_price": 500000000, "year": 2026, "exclusive_area": 84}),
    ("calc_property_tax", {"official_price": 500000000, "year": 2026, "prev_year_official_price": 480000000, "one_home": True}),
    ("calc_gift_tax", {"taxable_value": 200000000, "year": 2026, "relationship": "직계존속"}),
    ("calc_attached_land_limit", {"building_footprint_m2": 100, "land_area_m2": 400}),
    ("judge_family_loan", {"loan_amount": 200000000, "agreed_interest_rate": 0.02}),
    ("calc_corporate_property_sale_tax", {"business_year": 2026, "taxable_base": 100000000, "sales": [
        {"라벨": "주택", "종류": "주택", "양도금액": 500000000, "장부가액": 400000000}]}),
    ("calc_building_property_tax", {"year": 2026, "standard_value": 500000000}),
    ("get_tax_scope", {"owner": "법인"}),
    # 대체 도구(tax_overrides) — 더한 인자가 HTTP 로 넘어가는지
    ("calc_jongbu_tax", {"total_official_price": 600000000, "year": 2026, "basic_deduction": 0,
                         "tax_brackets": [{"upto": None, "rate": 0.027, "deduction": 0}]}),
    ("calc_jongbu_tax", {"total_official_price": 600000000, "year": 2026, "is_corporation": True}),
    ("calc_acquisition_tax", {"acquisition_price": 1000000000, "year": 2026, "acquisition_type": "유상.농지외",
                              "heavy_type": "법인"}),
    ("judge_transfer_reliefs", {"is_one_household_one_home": False, "holding_years": 5, "residing_years": 0,
                                "sale_price": 1000000000, "adjusted_at_sale": True, "heavy_home_count": 3,
                                "sale_date": "2026-08-20", "contract_date": "2026-05-01", "deposit_received": True,
                                "land_permit_target": True}),
    ("count_heavy_homes", {"items": [{"라벨": "A", "기준시가": 900000000}, {"라벨": "B", "기준시가": 80000000}],
                           "heavy_tier": 2, "sale_label": "B", "sale_date": "2026-10-01", "adjusted_at_sale": True}),
    # 2026-11-19 에 더한 대체 도구 — 새 인자를 실어 한 번씩(기대값은 tests/test_tax_overrides.py 와 케이스 OV-12~26 이 지킨다)
    ("judge_temporary_two_homes", {"prev_acquired": "2020-01-01", "new_acquired": "2026-09-01", "prev_sale_date": "2029-03-01",
                                   "prev_in_adjusted_area": True, "new_in_adjusted_area": True,
                                   "adjusted_area_notice_date": "2026-09-15"}),
    ("judge_acquisition_homes_and_rate", {"homes": [{"라벨": "종전", "종류": "주택", "시가표준액": 500000000, "수도권": True},
                                                    {"라벨": "신규", "종류": "주택", "시가표준액": 700000000, "수도권": True,
                                                     "취득대상": True}],
                                          "in_adjusted_area": True, "acquire_date": "2026-10-15", "prev_disposal_date": "2029-03-01",
                                          "prev_home_in_adjusted_area": True, "new_contract_date": "2026-08-20",
                                          "new_deposit_paid_date": "2026-08-20"}),
    ("judge_155_special", {"kind": "혼인", "event_date": "2020-05-01", "sale_date": "2026-03-01", "homes_at_sale": 3}),
    ("judge_156_3_from_portfolio", {"items": [{"라벨": "종전", "종류": "주택", "취득일": "2018-01-01", "양도대상": True},
                                              {"라벨": "분양권", "종류": "분양권", "취득일": "2022-03-01"}],
                                    "sale_date": "2024-06-01", "bunyang_already_completed": True, "other_homes": 0}),
    ("calc_attached_land_limit", {"building_footprint_m2": 150, "land_area_m2": 500,
                                  "demolished_inherited_footprint_m2": 80, "sale_date": "2026-05-01"}),
    ("calc_property_tax", {"official_price": 300000000, "year": 2026, "one_home": True, "jiteuk_relief_type": "전세사기피해자",
                           "jiteuk_relief_facts": {"전세사기피해자": True, "전세사기피해주택": True, "전용면적": 59}}),
    ("judge_jongbu_one_home_status", {"other_homes": [{"유형": "일시적신규", "신규취득일": "2026-09-01", "종전_조정대상지역": True,
                                                       "신규_조정대상지역": True}], "base_date": "2029-06-01"}),
]
# 대체 도구 결과에 있어야 하는 것 — (CASES 순번, 구조화 결과의 키, 기대값)
OVERRIDE_EXPECT = [(8, "과세표준", 360000000), (9, "계산불가", True), (10, "계산불가", True), (11, "중과여부", True)]


async def check(port):
    root = f"http://127.0.0.1:{port}"
    async with httpx.AsyncClient(trust_env=False, timeout=10) as http:
        for _ in range(100):
            try:
                response = await http.get(root + "/healthz")
                if response.status_code == 200:
                    break
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Server did not start")
        health = response.json()
        assert health == {"status": "ok", "tools": 48, "law_lookup": False}, health
        assert (await http.get(root + "/.well-known/openai-apps-challenge")).text == "synthetic-domain-check"
        invalid_host = await http.post(root + "/mcp", headers={"Host": "untrusted.invalid"}, json={})
        assert invalid_host.status_code == 421, invalid_host.text
        async with streamable_http_client(root + "/mcp", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                names = {t.name for t in tools}
                assert len(names) == 48 and "search_law" not in names and "get_acquisition_tax_checklist" in names
                assert {"calc_corporate_property_sale_tax", "judge_corporate_non_business_land", "calc_building_property_tax",
                        "calc_corporate_jongbu_tax", "calc_corporate_acquisition_tax", "get_tax_scope"} <= names
                assert all(t.annotations and t.annotations.readOnlyHint for t in tools)
                results = []
                for name, arguments in CASES:
                    result = await client.call_tool(name, arguments)
                    assert not result.isError, (name, result)
                    results.append({"tool": name, "arguments": arguments,
                                    "result": result.model_dump(mode="json")})
                import tax_overrides
                by_name = {t.name: t for t in tools}
                for name in tax_overrides.OVERRIDES:
                    assert name in by_name, name
                assert "is_corporation" in by_name["calc_jongbu_tax"].inputSchema["properties"]
                assert "sale_label" in by_name["count_heavy_homes"].inputSchema["properties"]
                assert "land_permit_target" in by_name["judge_transfer_reliefs"].inputSchema["properties"]
                def payload(index):            # 도구 결과는 dict 를 JSON 텍스트로 싣는다
                    return json.loads(results[index]["result"]["content"][0]["text"])
                for index, key, expected in OVERRIDE_EXPECT:
                    assert payload(index).get(key) == expected, (CASES[index][0], key, payload(index).get(key))
                sale = payload(12)["양도주택_중과판정"]
                assert sale["중과대상"] is False and sale["적용호"] == "법 §104⑦1호", sale
                for name, arguments in [
                    ("calc_acquisition_tax", {"acquisition_price": -1, "year": 2026}),
                    ("calc_acquisition_tax", {"acquisition_price": 500000000}),
                    ("search_law", {"query": "지방세법"}),
                ]:
                    result = await client.call_tool(name, arguments)
                    assert result.isError, (name, "must reject invalid or disabled call")
                report = {"scope": "HTTP protocol and tool execution only; not independent tax-law validation or ChatGPT dialogue testing",
                          "health": health, "positive_calls": results, "invalid_calls_rejected": 3,
                          "invalid_host_rejected": True, "domain_challenge": True}
                output = ROOT / "dist/chatgpt-http-check.json"
                output.parent.mkdir(exist_ok=True)
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({"status": "PASS", "tools": len(names), "positive_calls": len(results),
                                  "invalid_calls_rejected": 3, "report": str(output)}))


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, HOST="127.0.0.1", PORT=str(port), LAW_OC="",
               PUBLIC_BASE_URL="", RENDER_EXTERNAL_HOSTNAME="",
               OPENAI_APPS_CHALLENGE="synthetic-domain-check", PYTHONIOENCODING="utf-8")
    with tempfile.TemporaryFile(mode="w+b") as log:
        process = subprocess.Popen([sys.executable, "tax_http.py"], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            asyncio.run(check(port))
        except BaseException:
            log.seek(0)
            print(log.read().decode("utf-8", errors="replace"), file=sys.stderr)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
