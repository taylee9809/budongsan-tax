# -*- coding: utf-8 -*-
"""부동산 기초정보 조회 — 네트워크 없이 가짜 클라이언트로 검증한다.

원본(korea-realestate-mcp test_official_price.py·test_regulation_redev.py)의 PNU·중복행·정비구역
테스트를 옮기고, 이식하면서 바꾼 기준연도 선택과 도구 응답 형식을 더했다.
앵커: 용두동 232-76 → PNU 1123010200102320076 (원본 2026-08-29 실측).
"""
from datetime import date

import pytest

from property_lookup import official_price as op
from property_lookup import pnu
from property_lookup import redev_zone as rz
from property_lookup import tools

ANCHOR_PNU = "1123010200102320076"
TODAY = date(2026, 11, 18)


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class FakeClient:
    """URL별 고정 응답. handlers[url]은 dict(고정 응답) 또는 params를 받는 함수."""

    def __init__(self, **handlers):
        self.handlers = handlers
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        h = self.handlers.get(url)
        if h is None:
            raise AssertionError(f"예상하지 못한 호출: {url}")
        if isinstance(h, Exception):
            raise h
        return _Resp(h(params or {}) if callable(h) else h)


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("JUSO_API_KEY", "juso-test")
    monkeypatch.setenv("VWORLD_API_KEY", "vworld-test")


@pytest.fixture
def no_keys(monkeypatch):
    monkeypatch.delenv("JUSO_API_KEY", raising=False)
    monkeypatch.delenv("VWORLD_API_KEY", raising=False)


def _land_char(*years, zone="제2종일반주거지역"):
    return {"landCharacteristicss": {"field": [
        {"stdrYear": y, "lndpclAr": "107.7", "prposArea1Nm": zone, "lndcgrCodeNm": "대"} for y in years]}}


# ── PNU (원본 테스트) ──────────────────────────────────────────────

def test_pnu_parse_and_assemble():
    p = pnu.parse_jibun("서울특별시 동대문구 용두동 232-76")
    assert p == {"umd": "용두동", "bun": "0232", "ji": "0076", "is_san": False}
    assert pnu.assemble("1123010200", "232", "76") == ANCHOR_PNU
    ps = pnu.parse_jibun("경기도 광주시 목동 산 21-1")
    assert ps["is_san"] and ps["bun"] == "0021" and ps["ji"] == "0001"
    assert pnu.assemble("4161025321", "21", "1", True)[10] == "2"
    assert pnu.parse_jibun("서울특별시 동작구 노량진동") is None   # 동까지만


def test_resolve_pnu_exact_match_and_ambiguity(keys):
    juso = lambda rows: {pnu.JUSO_API_URL: {"results": {"common": {"errorCode": "0"}, "juso": rows}}}
    row = {"admCd": "1123010200", "mtYn": "0", "lnbrMnnm": "232", "lnbrSlno": "76",
           "jibunAddr": "서울특별시 동대문구 용두동 232-76"}
    r = pnu.resolve_pnu(FakeClient(**juso([row, dict(row)])), "서울특별시 동대문구 용두동 232-76")
    assert r["pnu"] == ANCHOR_PNU and r["status"] == "ok후보"      # 같은 필지 두 동은 하나로 접는다
    other = dict(row, admCd="1123010300")
    r = pnu.resolve_pnu(FakeClient(**juso([row, other])), "서울특별시 동대문구 용두동 232-76")
    assert r["pnu"] is None and r["status"] == "다건보류"           # 틀린 PNU보다 빈 PNU
    # 산번지를 찾는데 일반 지번만 있으면 정확일치로 치지 않는다
    r = pnu.resolve_pnu(FakeClient(**juso([row])), "서울특별시 동대문구 용두동 산 232-76")
    assert r["pnu"] == "1123010200202320076" and "동코드 폴백" in r["basis"]


# ── 원본 NED 실측 대응 ─────────────────────────────────────────────

def test_by_year_dedupes():
    rows = [{"stdrYear": "2022", "v": 1}, {"stdrYear": "2024", "stdrMt": "01", "v": 2},
            {"stdrYear": "2024", "stdrMt": "1", "v": 3}]
    assert sorted(op._by_year(rows)) == ["2022", "2024"]


def test_dedupe_units_drops_exact_duplicate_rows():
    u = lambda ho: {"pnu": "1", "dongNm": "", "hoNm": ho, "floorNm": "2", "prvuseAr": "49.35",
                    "stdrYear": "2026", "pblntfPc": "150000000"}
    assert [r["hoNm"] for r in op._dedupe_units([u("201"), u("302")] * 2)] == ["201", "302"]


# ── 기준연도 선택 (이식하며 새로 만든 부분) ─────────────────────────

@pytest.mark.parametrize("d, kind, years, boundary", [
    (date(2026, 3, 31), "공동주택가격", ["2025"], False),
    (date(2026, 4, 15), "공동주택가격", ["2025", "2026"], True),
    (date(2026, 4, 30), "공동주택가격", ["2025", "2026"], True),
    (date(2026, 5, 1), "공동주택가격", ["2026"], False),
    (date(2026, 5, 15), "개별공시지가", ["2025", "2026"], True),   # 토지는 5월 31일까지
    (date(2026, 6, 1), "개별공시지가", ["2026"], False),           # 재산세 과세기준일
    (date(2026, 6, 1), "개별주택가격", ["2026"], False),
    (date(2026, 1, 1), "개별주택가격", ["2025"], False),
])
def test_applicable_years(d, kind, years, boundary):
    r = op.applicable_years(d, kind)
    assert r["연도"] == years and r["경계"] is boundary


def test_property_kind_routes_officetel_separately():
    assert op.property_kind("아파트") == "공동주택"
    assert op.property_kind("다세대") == "공동주택"
    assert op.property_kind("다가구") == "개별주택"
    assert op.property_kind("토지") == "토지"
    assert op.property_kind("오피스텔") == "오피스텔"
    assert op.property_kind("상가") == ""


# ── 공시가격 도구 ─────────────────────────────────────────────────

def test_official_price_land_uses_year_of_base_date_not_latest(keys):
    c = FakeClient(**{
        op.NED_LAND_CHAR_URL: _land_char("2024", "2025", "2026"),
        op.NED_LAND_PRICE_URL: {"indvdLandPrices": {"field": [
            {"stdrYear": "2024", "pblntfPclnd": "4500000"},
            {"stdrYear": "2025", "pblntfPclnd": "4600000"},
            {"stdrYear": "2026", "pblntfPclnd": "4760000"}]}},
    })
    r = tools.lookup_official_price(ANCHOR_PNU, "2025-08-01", "토지", client=c, today=TODAY)
    assert r["상태"] == "확인" and r["적용연도"] == "2025"
    assert r["공시가격"]["2025"]["원_m2"] == 4600000                   # 최신(2026)이 아니라 2025
    assert r["공시가격"]["2025"]["원"] == int(4600000 * 107.7)
    assert r["토지특성"]["용도지역"] == "제2종일반주거지역" and r["토지특성"]["기준연도"] == "2025"
    assert r["출처"]["신뢰"] == "확정" and r["출처"]["조회일"] == "2026-11-18"


def test_official_price_boundary_returns_both_years(keys):
    c = FakeClient(**{
        op.NED_LAND_CHAR_URL: _land_char("2025", "2026"),
        op.NED_HOUSE_PRICE_URL: {"indvdHousingPrices": {"field": [
            {"stdrYear": "2025", "housePc": "390000000"}, {"stdrYear": "2026", "housePc": "401000000"}]}},
    })
    r = tools.lookup_official_price(ANCHOR_PNU, "2026-04-20", "단독", client=c, today=TODAY)
    assert set(r["공시가격"]) == {"2025", "2026"}
    assert r["공시가격"]["2025"]["원"] == 390000000 and r["공시가격"]["2026"]["원"] == 401000000
    assert any("공시일 확인" in f for f in r["플래그"])


def test_official_price_apartment_needs_unit(keys):
    def apart(params):
        assert params["stdrYear"] == "2026"                               # 연도를 지정해 조회
        rows = [{"pnu": ANCHOR_PNU, "dongNm": "101동", "hoNm": h, "floorNm": "", "prvuseAr": a,
                 "stdrYear": "2026", "pblntfPc": p}
                for h, a, p in (("1203", "84.9", "900000000"), ("1204", "59.8", "700000000"))] * 2
        return {"apartHousingPrices": {"field": rows}}
    c = FakeClient(**{op.NED_LAND_CHAR_URL: _land_char("2026"), op.NED_APART_PRICE_URL: apart})
    r = tools.lookup_official_price(ANCHOR_PNU, "2026-06-01", "아파트", dong="101동", ho="1203", client=c)
    assert r["공시가격"]["2026"]["원"] == 900000000 and r["출처"]["신뢰"] == "확정"
    r = tools.lookup_official_price(ANCHOR_PNU, "2026-06-01", "아파트", exclusive_area=60.0, client=c)
    assert r["공시가격"]["2026"]["원"] == 700000000 and r["출처"]["신뢰"] == "추정"
    r = tools.lookup_official_price(ANCHOR_PNU, "2026-06-01", "아파트", client=c)
    assert r["공시가격"]["2026"]["원"] is None and r["상태"] == "확인 불가"   # 필지 중위값은 내지 않는다


def test_official_price_unverified_parcel_gets_no_price(keys):
    c = FakeClient(**{op.NED_LAND_CHAR_URL: {"landCharacteristicss": {"field": []}}})
    r = tools.lookup_official_price(ANCHOR_PNU, "2026-06-01", "토지", client=c)
    assert r["상태"] == "미검증" and "공시가격" not in r


def test_official_price_input_errors_and_officetel(keys):
    assert tools.lookup_official_price("123", "2026-06-01", "토지")["상태"] == "입력오류"
    assert tools.lookup_official_price(ANCHOR_PNU, "2026/06/01x", "토지")["상태"] == "입력오류"
    assert tools.lookup_official_price(ANCHOR_PNU, "2026-06-01", "오피스텔")["상태"] == "지원안함"


# ── 키 미설정 ─────────────────────────────────────────────────────

def test_missing_keys_return_guidance_not_exception(no_keys):
    r = tools.lookup_pnu("서울특별시 동대문구 용두동 232-76", client=FakeClient())
    assert r["상태"] == "키 미설정" and "JUSO_API_KEY" in r["오류"]
    r = tools.lookup_official_price(ANCHOR_PNU, "2026-06-01", "토지", client=FakeClient())
    assert r["상태"] == "키 미설정" and "VWORLD_API_KEY" in r["오류"]
    r = tools.lookup_redev_zone(ANCHOR_PNU, client=FakeClient())
    assert r["상태"] == "키 미설정"
    assert not tools.tool_enabled("lookup_pnu")


def test_lookup_pnu_verifies_with_land_characteristics(keys):
    row = {"admCd": "1123010200", "mtYn": "0", "lnbrMnnm": "232", "lnbrSlno": "76",
           "jibunAddr": "서울특별시 동대문구 용두동 232-76"}
    c = FakeClient(**{pnu.JUSO_API_URL: {"results": {"juso": [row]}},
                      op.NED_LAND_CHAR_URL: _land_char("2026")})
    r = tools.lookup_pnu("서울특별시 동대문구 용두동 232-76", client=c)
    assert r["상태"] == "확정" and r["PNU"] == ANCHOR_PNU


def test_lookup_pnu_unverified_without_vworld_key(monkeypatch):
    monkeypatch.setenv("JUSO_API_KEY", "juso-test")
    monkeypatch.delenv("VWORLD_API_KEY", raising=False)
    row = {"admCd": "1123010200", "mtYn": "0", "lnbrMnnm": "232", "lnbrSlno": "76", "jibunAddr": "용두동 232-76"}
    r = tools.lookup_pnu("서울특별시 동대문구 용두동 232-76",
                         client=FakeClient(**{pnu.JUSO_API_URL: {"results": {"juso": [row]}}}))
    assert r["상태"] == "미검증" and r["PNU"] == ANCHOR_PNU and r["출처"]["신뢰"] == "추정"


# ── 정비구역 (원본 테스트 + 좌표 선택화) ────────────────────────────

def _redev_client(upis=None, land_use=None, upis_fail=False, lu_fail=False):
    lu = RuntimeError("ned down") if lu_fail else {"landUses": {"field": [
        {"prposAreaDstrcCodeNm": n, "cnflcAtNm": c, **({"manageNo": m} if m else {})}
        for n, c, m in (land_use or [])]}}
    if upis_fail:
        up = RuntimeError("upis down")
    elif upis:
        up = {"response": {"status": "OK", "result": {"featureCollection": {
            "features": [{"properties": {"dgm_nm": n}} for n in upis]}}}}
    else:
        up = {"response": {"status": "NOT_FOUND"}}
    return FakeClient(**{rz.NED_LAND_USE_URL: lu, rz.VWORLD_DATA_URL: up})


def test_land_use_catches_what_upis_misses(keys):
    c = _redev_client(upis=["천호지구지구단위계획구역"],
                      land_use=[("정비구역", "포함", "61100001174020240576UDT1000001001"), ("도시지역", "포함", None)])
    r = tools.lookup_redev_zone("1174010900104670061", 127.1, 37.5, client=c)
    assert r["상태"] == "편입" and r["구역명"] == [] and r["지역지구"] == ["정비구역"]
    assert r["고시"] == [{"고시연도": "2024", "고시번호": "576"}]
    assert r["출처"]["신뢰"] == "참고" and r["한계"]


def test_adjacent_is_not_inside(keys):
    r = tools.lookup_redev_zone("1" * 10 + "1" + "0" * 8, client=_redev_client(land_use=[("정비구역", "접함", None)]))
    assert r["편입"] is False and r["상태"] == "조회상 미편입" and r["접함"] == ["정비구역"]


def test_apartment_district_counts(keys):
    c = _redev_client(land_use=[("아파트지구", "포함", None)])
    assert tools.lookup_redev_zone(ANCHOR_PNU, client=c)["편입"] is True


def test_without_coordinates_upis_is_skipped(keys):
    c = _redev_client(land_use=[("도시지역", "포함", None)])
    r = tools.lookup_redev_zone(ANCHOR_PNU, client=c)
    assert r["편입"] is False and all(url != rz.VWORLD_DATA_URL for url, _ in c.calls)
    assert "좌표 없음" in r["basis"]


def test_all_sources_failed_is_unknown(keys):
    r = tools.lookup_redev_zone(ANCHOR_PNU, 127.0, 37.5, client=_redev_client(upis_fail=True, lu_fail=True))
    assert r["편입"] is None and r["상태"] == "확인 불가"


def test_one_source_failed_other_decides(keys):
    c = _redev_client(upis_fail=True, land_use=[("재정비촉진지구", "포함", None)])
    assert tools.lookup_redev_zone(ANCHOR_PNU, 127.0, 37.5, client=c)["편입"] is True
    c = _redev_client(lu_fail=True)
    r = tools.lookup_redev_zone(ANCHOR_PNU, 127.0, 37.5, client=c)
    assert r["편입"] is False and "신뢰 낮음" in r["basis"]


def test_redev_input_errors(keys):
    assert tools.lookup_redev_zone("abc")["상태"] == "입력오류"
    assert tools.lookup_redev_zone(ANCHOR_PNU, x=127.0)["상태"] == "입력오류"


# ── 서버 등록 ─────────────────────────────────────────────────────

def test_tools_registered_and_hidden_on_hosted_without_keys(no_keys):
    import tax_http
    import tax_server
    names = {t.name for t in tax_server.mcp._tool_manager.list_tools()}
    assert {"lookup_pnu", "lookup_official_price", "lookup_redev_zone"} <= names
    hosted = {t.name for t in tax_http.make_server()._tool_manager.list_tools()}
    assert not hosted & {"lookup_pnu", "lookup_official_price", "lookup_redev_zone"}


def test_tax_engine_does_not_import_lookup_layer():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for f in [root / "tax_judgment.py", root / "tax_params.py", *sorted((root / "tax_nodes").glob("*.py"))]:
        assert "property_lookup" not in f.read_text(encoding="utf-8"), f.name
