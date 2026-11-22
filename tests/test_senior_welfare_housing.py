# -*- coding: utf-8 -*-
"""노인복지주택(준주택) — 주택법-2-1 노드가 '주택 아님'으로 내고, 취득세 노드·판정기가 그 결과를 읽는다 (조심 2026지0865)."""
from tax_judgment import judge_acquisition_homes_and_rate, count_acquisition_homes
from tax_nodes.chwideuk import 취득세_부동산
from tax_nodes.jutaek_jeongui import 주택여부


def _home(std=500_000_000, **kw):
    return dict({"종류": "주택", "시가표준액": std, "수도권": True}, **kw)


# ── 정의 노드 ────────────────────────────────────────────────────────────
def test_definition_nodes():
    r = 주택여부({"종류": "노인복지주택"})
    assert r["주택"] is False and r["준주택"] is True
    assert "주택법 시행령 §4 3호" in r["근거"] and "부동산세제과-923" in r["해석메모"]
    assert 주택여부({"종류": "주택", "건축물용도": "노유자시설(노인복지주택)"})["주택"] is False
    assert 주택여부({"종류": "주택"}) is None          # 일반 주택은 이 노드가 판정하지 않는다
    assert 주택여부({"종류": "오피스텔"}) is None      # 영 §4 4호는 옮기지 않았다 — §13의3 4호가 따로 센다


# ── 취득세 노드 ──────────────────────────────────────────────────────────
def test_acquisition_nodes_route_to_7_na():
    r = 취득세_부동산(500_000_000, 2026, "주택유상", "2026-12-01", 조정대상지역=True, 세대주택수_취득포함=2,
                 전용면적=60, 종류="노인복지주택")
    assert r["표준세율_호"] == "§11①7호나목" and r["적용세율(표준+중과+조례)"] == 0.04
    assert r["세율 내역"]["중과유형"] is None
    assert (r["취득세"], r["지방교육세"], r["농어촌특별세"]) == (20_000_000, 2_000_000, 1_000_000)   # 서민주택 비과세 아님


def test_acquisition_nodes_plain_house_unchanged():
    r = 취득세_부동산(500_000_000, 2026, "주택유상", "2026-12-01", 조정대상지역=True, 세대주택수_취득포함=2, 전용면적=60)
    assert r["적용세율(표준+중과+조례)"] == 0.08


def test_gift_no_13_2_2():
    r = 취득세_부동산(500_000_000, 2026, "무상", "2026-12-01", 조정대상지역=True, 무상취득_시가표준액=400_000_000,
                 종류="노인복지주택")
    assert r["적용세율(표준+중과+조례)"] == 0.035


# ── 판정기 ────────────────────────────────────────────────────────────────
def test_held_senior_housing_not_counted():
    homes = [{"종류": "노인복지주택", "라벨": "실버타운"}, _home(라벨="신규", 취득대상=True)]
    r = judge_acquisition_homes_and_rate(homes, in_adjusted_area=True, acquire_date="2026-12-01")
    assert r["산입_주택수"] == 1 and r["중과여부"] is False
    row = [x for x in r["주택수_산정"]["항목별"] if x["항목"] == "실버타운"][0]
    assert row["산입"] is False and any("2026지0865" in g for g in row["근거"])


def test_acquire_senior_housing_rate_from_nodes():
    homes = [_home(라벨="A"), _home(라벨="B"), {"종류": "노인복지주택", "취득대상": True}]
    r = judge_acquisition_homes_and_rate(homes, in_adjusted_area=True, acquire_date="2026-12-01")
    assert r["취득세율"] == 0.04 and r["중과여부"] is False and r["산입_주택수"] == 2
    assert r["세율_판정"]["지방교육세율(과표대비)"] == 0.004 and r["농특세율(과표대비)"] == 0.002
    assert r["세율_판정"]["노드결과"]["표준세율_호"] == "§11①7호나목"
    assert any("부동산세제과-923" in f for f in r["플래그"])


def test_gift_senior_housing_rate():
    r = judge_acquisition_homes_and_rate([{"종류": "노인복지주택"}], in_adjusted_area=True,
                                         is_gift=True, gift_std_value=500_000_000, acquire_date="2026-12-01")
    assert r["취득세율"] == 0.035 and r["중과여부"] is False


def test_count_only():
    assert count_acquisition_homes([{"종류": "노인복지주택"}, _home(), _home()])["산입_주택수"] == 2
