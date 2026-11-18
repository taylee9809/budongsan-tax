# -*- coding: utf-8 -*-
"""취득세 3차 분업 — 영 §28의2 2~18호, 영 §26① 37개 호, 과밀억제권역 소재지 판정, 취득세 감면분 농특세, 직접 사용 요건 (2026-11-18).

기대값은 법제처 현행 본문(지방세법 시행령 대통령령 제36736호, 수도권정비계획법 시행령 별표 1, 농어촌특별세법 §4·시행령 §4)에서 직접 읽은 것이다.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import tax_judgment as tj  # noqa: E402
import tax_nodes.jiteuk_entity  # noqa: E402,F401
import tax_nodes.nongteuk as nongteuk  # noqa: E402
from corporate_tax import calc_corporate_acquisition_tax as corp_acq  # noqa: E402
from tax_nodes.chwideuk import 취득세_부동산  # noqa: E402
from tax_nodes.chwideuk_gwase import (_대도시예외업종, _주택중과예외, _원문_26_1, _원문_28의2, 대도시_판정, 대도시중과_범위,  # noqa: E402
                                      주택중과_예외)
from tax_nodes.jiteuk_chwideuk import 지특법_취득세감면  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- 영 §28의2
def test_every_item_of_28_2_is_in_the_statute_text():
    for 키 in _주택중과예외:
        assert (" %s. " % 키) in _원문_28의2, 키
    assert " 19. " not in _원문_28의2


@pytest.mark.parametrize("호", ["9", 9, "9호", "제9호"])
def test_item_notation_is_normalised(호):
    assert 주택중과_예외(취득일="2026-03-02", 주택중과_예외호=호)["호"] == "9호"


def test_item_1_needs_standard_value():
    assert 주택중과_예외(취득일="2026-03-02", 주택중과_예외호=1)["중과예외"] is False


@pytest.mark.parametrize("호,사실,취득일,기대", [
    ("7", {"시가표준액": 500_000_000}, "2026-03-02", True), ("7", {"시가표준액": 500_000_001}, "2026-03-02", False), ("7", {}, "2026-03-02", False),
    ("12", {"전용면적": 60}, "2026-03-02", True), ("12", {"전용면적": 61}, "2026-03-02", False),
    ("12", {"전용면적": 85, "수도권": False}, "2026-03-02", True), ("12", {"전용면적": 86, "수도권": False}, "2026-03-02", False),
    ("12", {"전용면적": 85, "수도권": True}, "2026-03-02", False), ("12", {"전용면적": 85, "수도권": True, "인구감소지역": True}, "2026-03-02", True),
    ("12", {"전용면적": 59, "주택유형": "단독주택"}, "2026-03-02", False), ("12", {"전용면적": 59, "주택유형": "다가구주택", "다가구_호별구분": True}, "2026-03-02", True),
    ("12", {"전용면적": 59, "주택유형": "다가구주택", "다가구_호별구분": False}, "2026-03-02", False), ("12", {"전용면적": 59, "특수관계인_제공": True}, "2026-03-02", False),
    ("16", {"수도권": False}, "2024-03-27", False), ("16", {"수도권": False}, "2024-03-28", True), ("16", {"수도권": False}, "2026-12-31", True),
    ("16", {"수도권": False}, "2027-01-01", False), ("16", {"수도권": True}, "2026-03-02", False), ("16", {"수도권": False, "주택유형": "다세대주택"}, "2026-03-02", False),
    ("17", {"전용면적": 85, "취득당시가액": 600_000_000}, "2026-01-01", True), ("17", {"전용면적": 85, "취득당시가액": 600_000_000}, "2025-12-31", False),
    ("17", {"전용면적": 85, "취득당시가액": 600_000_000}, "2027-01-01", False), ("17", {"전용면적": 85.1, "취득당시가액": 600_000_000}, "2026-03-02", False),
    ("17", {"전용면적": 85, "취득당시가액": 600_000_001}, "2026-03-02", False), ("17", {}, "2026-03-02", False),
    ("18", {"인구감소지역": True, "임대등록_60일내": True}, "2026-03-02", True), ("18", {"인구감소지역": True, "임대등록_60일내": False}, "2026-03-02", False),
    ("18", {"인구감소지역": False}, "2026-03-02", False), ("18", {"인구감소지역": True}, "2027-01-01", False),
    ("9", {"미분양_취득상대": "건축허가자", "거주기간_개월": 12}, "2026-03-02", False), ("9", {"미분양_취득상대": "건축허가자", "거주기간_개월": 11}, "2026-03-02", True),
    ("9", {"미분양_취득상대": "사업계획승인자", "거주기간_개월": 30}, "2026-03-02", True),
    ("8", {"멸실취득_주체": "주택신축판매업자"}, "2026-03-02", True), ("8", {"멸실취득_주체": "개인"}, "2026-03-02", False), ("8", {"약정_해제": True}, "2026-03-02", False),
    ("2", {"공공주택사업자": False}, "2026-03-02", False), ("5", {"임대사업자": False}, "2026-03-02", False), ("3", {"요건충족": False}, "2026-03-02", False),
    ("13의2", {}, "2026-03-02", True), ("19", {}, "2026-03-02", False),
])
def test_item_requirements_of_28_2(호, 사실, 취득일, 기대):
    assert 주택중과_예외(취득일=취득일, 주택중과_예외호=호, **사실)["중과예외"] is 기대


def test_follow_up_conditions_are_reported_not_judged():
    r = 주택중과_예외(취득일="2026-03-02", 주택중과_예외호="8", 멸실취득_주체="주택신축판매업자")
    assert "1년" in r["사후관리"][0] and "3년" in r["사후관리"][0] and "5년" in r["사후관리"][0]      # 8호 본문 단서 — 나목6)
    r = 주택중과_예외(취득일="2026-03-02", 주택중과_예외호="8", 멸실취득_주체="공공지원민간임대개발사업시행자")
    assert "2년" in r["사후관리"][0] and "6년" in r["사후관리"][0]                                # 나목5)
    r = 주택중과_예외(취득일="2026-03-02", 주택중과_예외호="8", 멸실취득_주체="주택조합")
    assert "3년" in r["사후관리"][0] and "7년" in r["사후관리"][0]
    r = 주택중과_예외(취득일="2026-03-02", 주택중과_예외호="10")
    assert any("3년" in x for x in r["사후관리"]) and r["확인필요"]


def test_judge_keeps_low_price_key_for_item_1_only():
    신규 = {"종류": "주택", "취득대상": True, "중과예외호": "6"}
    r = tj.judge_acquisition_homes_and_rate([신규], True, is_corporation=True, acquire_date="2026-03-02")
    assert r["중과여부"] is False and r["중과예외_호"] == "6호" and r["저가주택_중과예외"] is False
    assert any(f.startswith("사후관리") for f in r["플래그"]) and any(f.startswith("확인 필요") for f in r["플래그"])
    r = tj.judge_acquisition_homes_and_rate([dict(신규, 시가표준액=90_000_000, 수도권=True)], True, is_corporation=True, acquire_date="2026-03-02")
    assert r["저가주택_중과예외"] is True and r["중과예외_호"] == "1호 저가주택"
    # 호를 주지 않은 종전 입력은 그대로다
    r = tj.judge_acquisition_homes_and_rate([{"종류": "주택", "취득대상": True, "시가표준액": 500_000_000, "수도권": True}], True, is_corporation=True)
    assert r["중과여부"] is True and r["저가주택_중과예외"] is False and r["중과예외_호"] is None


def test_judge_does_not_guess_when_item_fails_and_value_is_missing():
    r = tj.judge_acquisition_homes_and_rate([{"종류": "주택", "취득대상": True, "중과예외호": "17", "수도권": True}], False, is_corporation=True,
                                             acquire_date="2026-03-02")
    assert r["중과여부"] is True and r["저가주택_중과예외"] is None
    assert any("17호" in f and "시가표준액 미입력" in f for f in r["플래그"])


# ---------------------------------------------------------------- 영 §26
def test_all_37_excluded_businesses_are_in_the_statute_text():
    assert sorted(_대도시예외업종) == list(range(1, 38))
    for n in range(1, 38):
        assert (" %d. " % n) in _원문_26_1
    for n in range(1, 38):
        assert 대도시중과_범위(대도시_예외업종호=n)["대도시중과_예외업종"] is True
    assert 대도시중과_범위(대도시_예외업종호=38)["대도시중과_예외업종"] is None


@pytest.mark.parametrize("호,사실,기대", [
    (3, {"예외업종_세부": "해외건설업", "해외건설_당해실적": False}, None), (3, {"예외업종_세부": "해외건설업", "해외건설_당해실적": True, "해외건설_사무실용": True}, True),
    (3, {"예외업종_세부": "주택건설사업", "주택건설_3년내착공": False}, None), (8, {"정부출자비율": 0.2}, True), (8, {"정부출자비율": 0.19}, None),
    (10, {"법인전환_초과부분": True}, None), (17, {"설립후1개월내_등록": False}, None), (25, {"설립후1개월내_등록": True}, True),
    (34, {"대도시밖에서_전입": True}, None), (34, {"대도시밖에서_전입": False}, True),
    (36, {"매입임대_약정일": "2022-12-31", "주거용오피스텔": True}, True), (36, {"매입임대_약정일": "2023-01-01"}, None), (36, {"주거용오피스텔": False}, None),
])
def test_provisos_of_26_1(호, 사실, 기대):
    assert 대도시중과_범위(대도시_예외업종호=호, **사실)["대도시중과_예외업종"] is 기대


def test_26_3_and_26_4():
    assert 대도시중과_범위(주택건설사업=True)["대도시중과_주택건설_기한"]["기한_년"] == 3
    assert 대도시중과_범위()["대도시중과_주택건설_기한"]["기한_년"] == 1
    assert 대도시중과_범위(대도시_예외업종호=4, 전기통신설비_공동사용임대=True)["대도시중과_임대불가피업종"] is True
    assert 대도시중과_범위(대도시_예외업종호=6, 임대허용매장_임대=True)["대도시중과_임대불가피업종"] is True
    assert 대도시중과_범위(대도시_예외업종호=9, 임대허용매장_임대=True)["대도시중과_임대불가피업종"] is False


# ---------------------------------------------------------------- 과밀억제권역
def test_zone_table_matches_the_annex_text():
    d = json.loads((ROOT / "data" / "metro_overconcentration_zone.json").read_text(encoding="utf-8"))
    원문 = d["원문"]["과밀억제권역"]
    assert d["MST"] == "277967" and d["확인일"]
    전부 = [e["시군구"] for e in d["표"] if e["과밀억제권역"] == "전부" and e["시도"] == "경기도"]
    assert len(전부) == 12 and all(c in 원문 for c in 전부)
    for e in d["표"]:
        if e["과밀억제권역"] == "제외" and e["시도"] == "경기도":
            assert e["시군구"] not in 원문.replace("남양주시", ""), e          # 과밀억제권역 란에 없는 시·군
            assert e["시군구"] in d["원문"]["성장관리권역"] + d["원문"]["자연보전권역"]
    남양주 = next(e for e in d["표"] if e["시군구"] == "남양주시")
    assert all(x in 원문 for x in 남양주["해당_읍면동"]) and len(남양주["해당_읍면동"]) == 10
    서구 = next(e for e in d["표"] if e["시군구"] == "서구")
    assert all(x in 원문 for x in 서구["제외_읍면동"]) and len(서구["제외_읍면동"]) == 8


@pytest.mark.parametrize("소재지,기대", [
    ("서울 강남구 역삼동", True), ("서울특별시 금천구", True), ("경기도 성남시 분당구", True), ("수원시 영통구", True), ("경기 고양시 일산동구", True),
    ("경기도 의정부시", True), ("구리시", True), ("하남시", True), ("안양시 동안구", True), ("부천시", True), ("광명시", True), ("과천시", True), ("의왕시", True), ("군포시", True),
    ("경기 남양주시 호평동", True), ("경기 남양주시 화도읍", False), ("경기 남양주시 다산동", None), ("경기도 남양주시", None),
    ("경기 시흥시", None), ("인천 부평구", None), ("인천 서구 청라동", None), ("인천 서구 불로동", False), ("인천 강화군", False), ("인천광역시 옹진군", False),
    ("경기도 용인시", False), ("경기 양주시", False), ("화성시", False), ("김포시", False), ("경기 광주시", False), ("광주광역시 서구", False),
    ("부산 해운대구", False), ("제주 서귀포시", False), ("강남구 역삼동", None), ("경기도", None),
])
def test_zone_by_location(소재지, 기대):
    r = 대도시_판정(소재지)
    assert r["과밀억제권역"] is 기대 and r["대도시"] is 기대
    if 기대:
        assert any("산업단지" in x for x in r["확인필요"])          # 산업단지 제외는 호출자 확인


def test_industrial_complex_is_not_metro():
    assert 대도시_판정("서울 금천구", 산업단지=True)["대도시"] is False
    assert 대도시_판정("서울 금천구", 산업단지=False)["확인필요"] == []


def test_corporate_tool_location_and_business_item():
    기본 = dict(acquisition_price=1_000_000_000, acquire_date="2026-03-02", property_kind="주택외", metro_office_date="2023-05-01")
    assert corp_acq(**기본, property_location="서울 강남구")["적용세율"] == 0.08
    assert corp_acq(**기본, property_location="경기 용인시")["적용세율"] == 0.04
    r = corp_acq(**기본, property_location="인천 연수구")
    assert r["대도시중과"] is None and r["적용세율"] is None and set(r["경우별_세액"]) == {"대도시 중과 아님", "대도시 중과"}
    r = corp_acq(**기본, property_in_metro=False, property_location="서울 강남구")       # 호출자 값이 먼저, 어긋남은 주의에
    assert r["대도시중과"] is False and any("다르다" in n for n in r["주의"])
    r = corp_acq(**기본, property_in_metro=True, excluded_business_item="31")
    assert r["적용세율"] == 0.04 and r["대도시중과_제외업종"]["호"] == "31호"
    r = corp_acq(**기본, property_in_metro=True, excluded_business=True, excluded_business_item="34", excluded_business_facts={"대도시밖에서_전입": True})
    assert r["적용세율"] == 0.08 and r["대도시중과_제외업종"]["해당"] is False
    assert corp_acq(**기본, property_in_metro=True, excluded_business=True)["적용세율"] == 0.04      # 종전 입력 그대로
    with pytest.raises(ValueError):
        corp_acq(**기본, property_in_metro=True, in_industrial_complex=True)


def test_corporate_tool_string_item_of_28_2_now_works():
    r = corp_acq(500_000_000, "2026-03-02", "주택", property_in_metro=False, heavy_exception_item="3")
    assert r["적용세율"] == 0.01 and r["주택중과_예외"]["호"] == "3호" and r["주택중과_예외"]["사후관리"]


# ---------------------------------------------------------------- 취득세 감면분 농특세 (농특세법 §5①1호, §4, 영 §4)
@pytest.mark.parametrize("조,항,사실,세액,호", [
    ("36의3", "1", {"전용면적": 100}, 400_000, None),      # 생애최초 — 영 §4⑦5호 목록에 없다 → 20%
    ("36의3", "1", {"전용면적": 85}, 0, "9"),              # 서민주택(국민주택규모 이하) 취득세 감면 — §4 9호
    ("36의3", "1", {}, 400_000, None),                    # 전용면적 미입력 — 서민주택을 판정하지 못해 과세
    ("6", "1", {}, 0, "2"),                               # 자경농민 농지 — 영 §4①3호
    ("6", "4", {}, 0, "2"),                               # 귀농인 — 영 §4①3호
    ("73", "1", {}, 0, "12"),                             # 토지수용 대체취득 — 영 §4⑦5호
    ("31", "1", {}, 0, "12"), ("31", "2", {}, 0, "12"),   # 공공임대 — 영 §4⑦5호
    ("31의3", "1", {}, 0, "12"), ("36", "", {}, 0, "12"), ("22", "1", {}, 0, "12"), ("33", "2", {}, 0, "12"), ("74", "3", {}, 0, "12"),
    ("57의2", "2", {}, 0, "8"),                           # 영 §4④
    ("36의5", "1", {"전용면적": 100}, 400_000, None),      # 출산·양육 — 목록에 없다
    ("75의5", "4", {"전용면적": 120}, 400_000, None),      # 인구감소지역 주택 — 목록에 없다
    ("31", "6", {"전용면적": 100}, 400_000, None),         # §31은 ①②만 목록에 있다
    ("57의2", "1", {}, 400_000, None), ("57의2", "1", {"적격합병": True}, 0, "12"),      # 적격합병일 때만 — 영 §4⑦5호 괄호
])
def test_relief_share_follows_article_4_lists(조, 항, 사실, 세액, 호):
    r = nongteuk.취득세_감면분_농특세(2_000_000, "지방세특례제한법", 조, 항, **사실)
    assert r["세액"] == 세액
    assert r["내역"][0].get("호") == 호


def test_first_home_relief_share_in_acquisition_tax():
    """생애최초(지특 §36의3) 5억 주택 — 취득세 500만 − 200만, 취득세분 0.2% 100만, 감면분 200만×20% = 40만(85㎡ 초과만)."""
    r = 취득세_부동산(500_000_000, 2026, "주택유상", 취득일="2026-03-02", 생애최초_감면신청=True, 전용면적=100)
    assert r["취득세"] == 3_000_000 and r["농어촌특별세"] == 1_000_000 + 400_000
    assert r["농어촌특별세_감면분"]["세액"] == 400_000
    r = 취득세_부동산(500_000_000, 2026, "주택유상", 취득일="2026-03-02", 생애최초_감면신청=True, 전용면적=84)
    assert r["농어촌특별세"] == 0                                             # §4 9호(감면분)·11호(취득세분)
    r = 취득세_부동산(500_000_000, 2026, "주택유상", 취득일="2026-03-02", 전용면적=100)
    assert r["농어촌특별세"] == 1_000_000 and r["농어촌특별세_감면분"] is None      # 감면이 없으면 종전 그대로


def test_relief_assembly_reports_the_share():
    r = 지특법_취득세감면(10_000_000, "2026-03-02", "사회복지법인", 사회복지법인=True)
    assert r["감면세액"] == 8_500_000 and r["농어촌특별세_감면분"]["세액"] == 0 and r["농어촌특별세_감면분"]["내역"][0]["호"] == "12"
    r = 지특법_취득세감면(10_000_000, "2026-03-02", "사회복지법인")
    assert r["감면세액"] == 0 and "농어촌특별세_감면분" not in r


# ---------------------------------------------------------------- 직접 사용 요건 → 지특법 §2①8호
@pytest.mark.parametrize("사실,감면", [
    ({}, True), ({"사용주체": "소유자"}, True), ({"사용주체": "임차인"}, False), ({"사용주체": "소유자", "임대사용": True}, False),
    ({"사용주체": "수탁자"}, False), ({"사용주체": "수탁자", "신탁등기": True}, True), ({"직접사용": False}, False), ({"직접사용": True}, True),
])
def test_direct_use_requirement_uses_the_definition(사실, 감면):
    r = 지특법_취득세감면(10_000_000, "2026-03-02", "사회복지법인", 사회복지법인=True, **사실)
    assert (r["감면세액"] > 0) is 감면
    if not 감면:
        assert any("§2①8호" in m["사유"] for m in r["미적용 조문"])


def test_direct_use_is_not_asked_of_reliefs_without_that_wording():
    r = 지특법_취득세감면(10_000_000, "2026-03-02", "대체취득", 사용주체="임차인")       # §73① — '직접 사용' 문구가 없는 감면
    assert r["감면세액"] == 10_000_000
