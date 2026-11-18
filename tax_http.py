"""Hosted MCP adapter. Keep generated tax_server.py unchanged."""
import os
from urllib.parse import urlsplit

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pathlib import Path
from mcp.types import ToolAnnotations

from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

import tax_overrides
import tax_server
from acquisition_checklist import get_acquisition_tax_checklist
from building_property_tax import calc_building_property_tax
from corporate_tax import (calc_corporate_acquisition_tax, calc_corporate_jongbu_tax,
                           calc_corporate_property_sale_tax, judge_corporate_non_business_land)
from gift_presumption import judge_gift_presumption, judge_low_price_transfer_gift
from tax_scope import get_tax_scope
from hosted_descriptions import DESCRIPTIONS
from policy_pages import CONTACT, PRIVACY_HTML, SUPPORT_NAME, TERMS_HTML
from usage_log import UsageLogMiddleware

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
    # 결함이 있는 생성 도구(findings 88·95·97·98)는 같은 이름의 고친 판으로 대체한다 — 목록은 tax_overrides.OVERRIDES.
    enabled = tax_overrides.replace_tools(enabled, DESCRIPTIONS)
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
    instructions += (
        " Users usually do not know which facts Korean acquisition tax depends on. "
        "When a user asks about acquisition tax (취득세) without giving all material facts, "
        "call get_acquisition_tax_checklist with the acquisition type if known and the item keys already provided, "
        "then ask only for the missing items, in everyday language, a few at a time, saying briefly why each matters. "
        "Do not ask for items whose condition does not apply."
    )
    instructions += (
        " Before answering a question that spans several taxes, or any question about a company (법인) owner, call get_tax_scope "
        "(owner=\"법인\" for companies): it lists which tool computes each tax, what no tool covers, and for a company the "
        "acquire-hold-sell sequence with commonly missed taxes. "
        "For a company, do not use calc_jongbu_tax, calc_acquisition_tax or calc_transfer_tax: use calc_corporate_jongbu_tax "
        "(housing owned on June 1: flat 2.7%/5%, no deduction, no burden cap — 종합부동산세법 §9②), "
        "calc_corporate_acquisition_tax (12% on housing with the low-price exception, and the large-city surcharge 지방세법 §13②) "
        "and calc_corporate_property_sale_tax (corporate tax on the taxable base, the additional tax on gains from housing, "
        "non-business land and housing rights under 법인세법 §55의2, and local corporate income tax; it does not compute the taxable base itself). "
        "judge_corporate_non_business_land judges whether land sold by a company is non-business land (법인세법 §55의2②) "
        "and returns no verdict when facts are missing. "
        "calc_building_property_tax computes property tax on non-residential buildings (상가·공장 등, 지방세법 §111①2호). "
        "A company that holds property on June 1 owes that year's property tax and holding tax even if it sells soon after. "
        "For anything get_tax_scope lists as not covered (주민세, 부가가치세, 배당 과세 and so on), say this server does not cover it "
        "and give no rates, amounts or article numbers from memory. "
        "Cite only statute articles that a tool result returned."
    )
    # 질문 리허설(docs/QUESTION_REHEARSAL.md)에서 나온 처방 a1~a4.
    instructions += (
        " Rates and article numbers written in these instructions or in tool descriptions are there to help you pick a tool. "
        "Before a tool result has returned them, do not state them to the user as the applicable rate; say which tax applies "
        "and that you will compute it. A get_tax_scope result counts as a tool result. "
        "If the user gave an amount but not the other inputs a calc_* tool needs (date, year, age, holding period, home count, ownership), "
        "ask for them first. Never fill a date argument with today's date or the current year on your own. "
        "If you still compute to show an order of magnitude, call it provisional in the first sentence and list every input you assumed. "
        "When comparing an individual with a company (개인 vs 법인), show each side's computed taxes stage by stage, but do not open with "
        "or conclude which side is cheaper overall: tax on taking money out of the company (배당·급여), VAT and social insurance are not "
        "computed here and can reverse the result. Say that in the same sentence as any total. "
        "Do not derive a tool input from your own tax arithmetic (for example 근로소득금액 from an annual salary). "
        "Ask the user for the figure, or call the tool without it and say which part was left out. "
        "A judge_* result of None (보류·판정불가) means a fact is missing: ask for it instead of picking a side."
    )
    server = FastMCP(
        "budongsan-tax", instructions=instructions, tools=enabled,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        streamable_http_path="/mcp", stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins),
    )

    # 생성 파일(tax_server.py)을 고치지 않고 호스팅 서버에만 붙이는 도구. 외부 조회 없음.
    server.add_tool(
        get_acquisition_tax_checklist,
        title="Acquisition tax checklist",
        annotations=ToolAnnotations(title="Acquisition tax checklist", readOnlyHint=True, destructiveHint=False,
                                    idempotentHint=True, openWorldHint=False),
    )

    # 법인의 부동산 양도 — 조문 노드(tax_nodes/beobin.py)로 계산한다. 외부 조회 없음.
    server.add_tool(
        calc_corporate_property_sale_tax,
        title="Corporate tax on a property sale (법인세)",
        annotations=ToolAnnotations(title="Corporate tax on a property sale (법인세)", readOnlyHint=True,
                                    destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )

    server.add_tool(
        judge_corporate_non_business_land,
        title="Corporate non-business land test (법인 비사업용 토지)",
        annotations=ToolAnnotations(title="Corporate non-business land test (법인 비사업용 토지)", readOnlyHint=True,
                                    destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    # 법인 종부세·법인 취득세 — 개인용 calc_jongbu_tax·calc_acquisition_tax 는 법인을 계산하지 않는다(findings 95·97·98).
    for fn, title in ((calc_corporate_jongbu_tax, "Corporate holding tax on housing (법인 종부세)"),
                      (calc_corporate_acquisition_tax, "Corporate acquisition tax (법인 취득세)"),
                      (get_tax_scope, "Tax scope and tool map (범위 안내)")):
        server.add_tool(fn, title=title, annotations=ToolAnnotations(
            title=title, readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    # 건축물(상가·공장 등) 재산세 — 조문 노드(tax_nodes/jaesan_geonchuk.py)로 계산한다.
    server.add_tool(
        calc_building_property_tax,
        title="Property tax on a building (건축물 재산세)",
        annotations=ToolAnnotations(title="Property tax on a building (건축물 재산세)", readOnlyHint=True,
                                    destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )

    # 증여 예시·추정 — 저가 양수·고가 양도(상증법 §35), 증여 추정(§44·§45). 조문 노드(tax_nodes/sangjeung_chujeong.py)로 판정한다.
    for fn, title in ((judge_low_price_transfer_gift, "Below-market sale gift (저가 양수·고가 양도 증여이익)"),
                      (judge_gift_presumption, "Gift presumption test (증여 추정 판정)")):
        server.add_tool(fn, title=title, annotations=ToolAnnotations(
            title=title, readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))

    @server.custom_route("/healthz", methods=["GET"])
    async def health(request):
        return JSONResponse({"status": "ok", "tools": len(server._tool_manager.list_tools()), "law_lookup": bool(tax_server.LAW_OC)})

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
    app = server.streamable_http_app()
    if os.environ.get("USAGE_LOG", "1") != "0":
        app = UsageLogMiddleware(app)
    uvicorn.run(app, host=server.settings.host,
                port=server.settings.port, access_log=False)


if __name__ == "__main__":
    main()
