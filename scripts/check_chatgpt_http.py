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
]


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
        assert health == {"status": "ok", "tools": 39, "law_lookup": False}, health
        assert (await http.get(root + "/.well-known/openai-apps-challenge")).text == "synthetic-domain-check"
        invalid_host = await http.post(root + "/mcp", headers={"Host": "untrusted.invalid"}, json={})
        assert invalid_host.status_code == 421, invalid_host.text
        async with streamable_http_client(root + "/mcp", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                names = {t.name for t in tools}
                assert len(names) == 39 and "search_law" not in names
                assert all(t.annotations and t.annotations.readOnlyHint for t in tools)
                results = []
                for name, arguments in CASES:
                    result = await client.call_tool(name, arguments)
                    assert not result.isError, (name, result)
                    results.append({"tool": name, "arguments": arguments,
                                    "result": result.model_dump(mode="json")})
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
