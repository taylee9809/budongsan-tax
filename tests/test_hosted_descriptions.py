"""Hosted connector: tool descriptions must not tell the model to call other tools."""
import re

import tax_http
import tax_server
from hosted_descriptions import DESCRIPTIONS


def _hosted_tools():
    return tax_http.make_server()._tool_manager.list_tools()


def test_every_override_names_a_real_tool():
    names = {t.name for t in tax_server.mcp._tool_manager.list_tools()}
    assert set(DESCRIPTIONS) <= names


def test_no_description_mentions_another_tool():
    tools = _hosted_tools()
    names = {t.name for t in tax_server.mcp._tool_manager.list_tools()}
    for t in tools:
        words = set(re.findall(r"\b[a-z][a-z0-9_]*\*?", t.description))
        others = {w for w in words if w in names and w != t.name}
        others |= {w for w in words if w.endswith("_*")}
        assert not others, f"{t.name} mentions {sorted(others)}"


def test_overrides_are_applied():
    tools = {t.name: t for t in _hosted_tools()}
    for name, text in DESCRIPTIONS.items():
        if name in tools:
            assert tools[name].description == text
