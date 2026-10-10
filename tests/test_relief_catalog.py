# -*- coding: utf-8 -*-
"""감면 카탈로그 색인 회귀 테스트.

카탈로그는 판정을 하지 않으므로 "세액이 맞나"가 아니라 **놓치지 않나**를 본다.
상담 문장을 넣었을 때 그 상황의 대표 조문이 후보에 반드시 들어와야 한다.
"""
import relief_catalog as rc


def ids(res):
    return [c["id"] for c in res["후보"]]


def test_meta_counts():
    m = rc.catalog_meta()
    assert m["총건수"] == m["구현"] + m["미구현"]
    # coverage_gaps.md가 세는 미반영 세액영향 건수와 일치해야 한다
    assert m["미구현_세액영향"] == 170


def test_disclaimer_always_present():
    r = rc.screen(semok=["취득세"], situation="집 삽니다")
    assert "C" in r["주의"] and "원문" in r["주의"]
    e = rc.lookup("지특36의5")
    assert e["근거등급"] == "C"


def test_situation_expansion():
    hits = {h["계열"] for h in rc.expand_situation("아이 낳고 첫집을 삽니다")}
    assert "출산·양육" in hits
    assert "생애최초" in hits


def test_birth_relief_surfaces():
    r = rc.screen(semok=["취득세"], situation="둘째 낳고 집을 사려고 합니다", limit=10)
    assert "지특36의5" in ids(r)


def test_first_home_relief_surfaces():
    r = rc.screen(semok=["취득세"], situation="무주택자인데 생애최초로 집을 삽니다", limit=10)
    assert "지특36의3" in ids(r)


def test_farmland_transfer_surfaces():
    r = rc.screen(semok=["양도소득세"], situation="20년 자경한 농지를 팝니다", limit=10)
    got = ids(r)
    assert "조특69" in got or "조특70" in got


def test_expropriation_surfaces_local_relief():
    r = rc.screen(semok=["취득세"], situation="토지가 수용돼 보상금으로 대체취득합니다",
                  limit=10)
    assert "지특73" in ids(r)


def test_rental_house_surfaces():
    r = rc.screen(semok=["양도소득세"], situation="장기일반민간임대주택 8년 임대 후 양도",
                  limit=10)
    assert "조특97의3" in ids(r)


def test_decree_excluded_by_default():
    r = rc.screen(semok=["양도소득세"], situation="자경 농지", limit=30)
    assert all(not c["근거"].startswith("조세특례제한법 시행령") for c in r["후보"])
    r2 = rc.screen(semok=["양도소득세"], situation="자경 농지", include_decree=True,
                   limit=60)
    assert any("시행령" in c["근거"] for c in r2["후보"])


def test_expired_excluded_by_default():
    """§40의2 주택거래 취득세 감면은 2013년 취득분 전용 — 신규 상담에 뜨면 안 된다."""
    r = rc.screen(semok=["취득세"], situation="주택을 삽니다", limit=40)
    assert "지특40의2" not in ids(r)
    r2 = rc.screen(semok=["취득세"], situation="주택을 삽니다", include_expired=True,
                   limit=60)
    assert "지특40의2" in ids(r2)


def test_corporate_only_excluded_by_default():
    r = rc.screen(semok=["양도소득세"], situation="부동산투자회사에 현물출자합니다",
                  limit=30)
    assert all(c["점수"] >= 0 for c in r["후보"])
    r2 = rc.screen(semok=["양도소득세"], situation="현물출자", include_corporate=True,
                   limit=30)
    assert r2["후보수"] >= r["후보수"]


def test_reason_always_explains_hit():
    r = rc.screen(semok=["취득세"], situation="농지를 취득합니다", limit=10)
    for c in r["후보"]:
        assert c["걸린이유"], c["근거"]


def test_lookup_forms():
    a = rc.lookup("지특36의5")
    b = rc.lookup("지특법 §36의5")
    assert a and b and a["id"] == b["id"]
    assert rc.lookup("조특법 §9999") is None


def test_implemented_flag_marks_existing_tools():
    """판정툴이 이미 있는 조문은 '없음 — 원문 직접 확인'으로 나오면 안 된다."""
    e = rc.lookup("조특133")
    assert e is not None and e["구현"] is True
