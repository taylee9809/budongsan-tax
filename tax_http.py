"""Hosted MCP adapter. Keep generated tax_server.py unchanged."""
import os
from urllib.parse import urlsplit

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pathlib import Path

from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

import tax_server
from hosted_descriptions import DESCRIPTIONS
from policy_pages import CONTACT, PRIVACY_HTML, SUPPORT_NAME, TERMS_HTML

REMOTE_TOOLS = {"search_law", "get_law_detail", "get_local_tax_ordinances", "search_tax_rulings"}


def make_server():
    base_url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
    if not base_url and render_host:
        base_url = "https://" + render_host
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    origins = ["http://localhost:*", "http://127.0.0.1:*"]
    if base_url:
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("PUBLIC_BASE_URL must be an HTTPS origin without a path or credentials")
        hosts.append(parsed.netloc)
        origins.append(base_url)
    # Use a separate manager so the generated stdio server keeps all its tools.
    source_tools = tax_server.mcp._tool_manager.list_tools()
    enabled = [t for t in source_tools if tax_server.LAW_OC or t.name not in REMOTE_TOOLS]
    # Directory review: descriptions say what a tool does, never which tool to call next.
    enabled = [t.model_copy(update={"description": DESCRIPTIONS[t.name]}) if t.name in DESCRIPTIONS else t
               for t in enabled]
    instructions = tax_server.SERVER_INSTRUCTIONS + (
        " Ask for missing material facts, including transaction date, household home count, "
        "area and relief conditions; never treat omitted values as confirmed zero or false. "
        "Distinguish user assumptions, statutory eligibility and arithmetic. "
        "Return the actual tool result with its limitations and citations. "
        "Do not claim to file returns, access Hometax accounts, or guarantee tax outcomes. "
        "If the user has not given the price and other material facts, ask for them first and do not "
        "call a calc_* tool with invented or illustrative values unless the user explicitly asks for an example. "
        "These tools cover Korean tax law only: for other jurisdictions, say so and do not call any tool. "
        "Only use tools present in tools/list."
    )
    server = FastMCP(
        "budongsan-tax", instructions=instructions, tools=enabled,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        streamable_http_path="/mcp", stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins),
    )

    @server.custom_route("/healthz", methods=["GET"])
    async def health(request):
        return JSONResponse({"status": "ok", "tools": len(enabled), "law_lookup": bool(tax_server.LAW_OC)})

    @server.custom_route("/", methods=["GET"])
    async def index(request):
        return PlainTextResponse(
            "Budongsan Tax\nKorean real-estate tax calculations and statutory condition checks.\n"
            "MCP endpoint: /mcp\nSource and support: https://github.com/taylee9809/budongsan-tax\n"
            f"고객지원: {CONTACT}\n지원 안내: /support\n"
            "개인정보처리방침: /privacy\n이용약관: /terms\n"
            "Calculations depend on supplied facts and the supported tax year. No tax filing service.\n"
        )

    @server.custom_route("/support", methods=["GET"])
    async def support(request):
        return PlainTextResponse(
            "Budongsan Tax 고객지원\n\n"
            f"{SUPPORT_NAME}\n이메일: {CONTACT}\n\n"
            "연결 오류·계산 결과 문의는 발생 시각, 도구 이름, 재현 가능한 가상 예시를 보내주세요.\n"
            "주민등록번호, 계정 비밀번호, 실제 고객의 계약서 등은 보내지 마세요.\n"
            "이 서비스는 한국 부동산 세금의 계산과 요건 판정을 지원합니다.\n"
            "세금 신고·납부를 대행하지 않으며, 결과는 입력 조건과 지원 연도에 따라 달라집니다.\n"
            "소스 코드: https://github.com/taylee9809/budongsan-tax\n"
        )

    @server.custom_route("/privacy", methods=["GET"])
    async def privacy(request):
        return HTMLResponse(PRIVACY_HTML)

    @server.custom_route("/demo.mp4", methods=["GET"])
    async def demo(request):
        # 심사 제출용 데모 영상(scripts/build_demo_video.py로 생성)
        return FileResponse(Path(__file__).parent / "plugin/assets/demo.mp4", media_type="video/mp4")

    @server.custom_route("/terms", methods=["GET"])
    async def terms(request):
        return HTMLResponse(TERMS_HTML)

    @server.custom_route("/.well-known/openai-apps-challenge", methods=["GET"])
    async def challenge(request):
        token = os.environ.get("OPENAI_APPS_CHALLENGE", "")
        return PlainTextResponse(token if token else "Not configured", status_code=200 if token else 404)

    @server.custom_route("/.well-known/glama.json", methods=["GET"])
    async def glama_claim(request):
        # Glama 커넥터 소유권 확인(HTTP 파일 방식)
        claim = os.environ.get("GLAMA_CLAIM", "")
        if not claim:
            return JSONResponse({"error": "Not configured"}, status_code=404)
        return JSONResponse({"$schema": "https://glama.ai/mcp/schemas/connector.json", "claim": claim})

    return server


def main():
    server = make_server()
    uvicorn.run(server.streamable_http_app(), host=server.settings.host,
                port=server.settings.port, access_log=False)


if __name__ == "__main__":
    main()
