"""호스팅 서버에만 붙는 도구가 등록돼 있고 읽기 전용인지."""
import tax_http

EXTRA = {"get_acquisition_tax_checklist", "calc_corporate_property_sale_tax",
         "judge_corporate_non_business_land", "calc_building_property_tax",
         "calc_corporate_jongbu_tax", "calc_corporate_acquisition_tax", "get_tax_scope"}


def test_extra_tools_registered_read_only():
    tools = {t.name: t for t in tax_http.make_server()._tool_manager.list_tools()}
    assert EXTRA <= set(tools)
    for name in EXTRA:
        assert tools[name].annotations.readOnlyHint and not tools[name].annotations.openWorldHint
        assert tools[name].description.strip()


def test_instructions_name_only_registered_tools():
    import re
    server = tax_http.make_server()
    names = {t.name for t in server._tool_manager.list_tools()}
    mentioned = set(re.findall(r"\b(?:calc|judge|get|count)_[a-z0-9_]+\b", server.instructions))
    assert mentioned <= names, mentioned - names
