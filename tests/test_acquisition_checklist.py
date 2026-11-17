"""취득세 체크리스트: 원인별 항목 선택, 받은 항목 제외, 호스팅 서버 등록."""
import re

import pytest

import tax_http
from acquisition_checklist import ITEMS, TYPES, get_acquisition_tax_checklist


def _keys(result):
    return [i["항목"] for i in result["물어볼_항목"]]


def test_unknown_type_returns_common_items_and_choices():
    r = get_acquisition_tax_checklist()
    assert r["취득원인"] == "미정"
    assert set(r["취득원인_선택지"]) == set(TYPES)
    keys = _keys(r)
    assert keys[0] == "acquisition_type"
    # 원인별 항목은 원인을 정하기 전에는 묻지 않는다
    assert "price" not in keys and "donor_relation" not in keys and "heir_homes" not in keys


@pytest.mark.parametrize("kind,must,must_not", [
    ("매매", {"price", "household_homes", "prev_disposal_plan", "first_home"},
     {"market_value", "official_price", "donor_relation", "heir_homes", "bunyang_right_date"}),
    ("분양", {"price", "household_homes", "bunyang_right_date", "first_home"},
     {"market_value", "donor_relation", "heir_homes"}),
    ("증여", {"market_value", "household_homes", "donor_relation", "assumed_debt"},
     {"price", "first_home", "prev_disposal_plan", "heir_homes"}),
    ("상속", {"official_price", "heir_homes", "heir_share"},
     {"price", "market_value", "household_homes", "first_home", "donor_relation"}),
])
def test_items_by_type(kind, must, must_not):
    r = get_acquisition_tax_checklist(kind)
    keys = set(_keys(r))
    assert must <= keys
    assert not (must_not & keys)
    assert "acquisition_type" not in keys  # 원인을 줬으면 다시 묻지 않는다
    assert "취득원인_선택지" not in r


def test_known_items_move_out_of_questions():
    r = get_acquisition_tax_checklist("매매", known=["price", "location", " acquire_date ", "nonsense"])
    keys = _keys(r)
    assert "price" not in keys and "location" not in keys and "acquire_date" not in keys
    assert {"price", "location", "acquire_date", "acquisition_type"} <= set(r["받은_항목"])
    assert r["알수없는_항목"] == ["nonsense"]


def test_invalid_type_rejected():
    with pytest.raises(ValueError):
        get_acquisition_tax_checklist("교환")


def test_every_item_is_explained_and_cited():
    keys = [i["key"] for i in ITEMS]
    assert len(keys) == len(set(keys))
    for item in ITEMS:
        assert re.fullmatch(r"[a-z_]+", item["key"])
        assert item["질문"] and item["이유"]
        assert re.search(r"법 ?(제\d+조|시행령)", item["근거"]), item["key"]
        assert item["types"] is None or item["types"] <= set(TYPES)


def test_registered_on_hosted_server_without_network():
    tools = {t.name: t for t in tax_http.make_server()._tool_manager.list_tools()}
    tool = tools["get_acquisition_tax_checklist"]
    assert tool.annotations.readOnlyHint and tool.annotations.openWorldHint is False
    assert "get_acquisition_tax_checklist" in tax_http.make_server().instructions
