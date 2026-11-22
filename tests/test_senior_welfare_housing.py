# -*- coding: utf-8 -*-
"""노인복지주택(준주택) — 취득세 주택 수 밖, 취득 대상이면 일반 건축물 세율 (조심 2026지0865, 2026-10-01)."""
from tax_judgment import judge_acquisition_homes_and_rate, count_acquisition_homes


def _home(std=500_000_000, **kw):
    return dict({"종류": "주택", "시가표준액": std, "수도권": True}, **kw)


def test_held_senior_housing_not_counted():
    # 보유 노인복지주택 1 + 이번에 취득하는 주택 1 — 조정대상지역이어도 산입 1주택이라 중과 없음
    homes = [{"종류": "노인복지주택", "라벨": "실버타운"}, _home(라벨="신규", 취득대상=True)]
    r = judge_acquisition_homes_and_rate(homes, in_adjusted_area=True, acquire_date="2026-12-01")
    assert r["산입_주택수"] == 1
    assert r["중과여부"] is False
    row = [x for x in r["주택수_산정"]["항목별"] if x["항목"] == "실버타운"][0]
    assert row["산입"] is False and "2026지0865" in row["사유"]


def test_acquire_senior_housing_general_building_rate():
    # 2주택 세대가 조정대상지역 노인복지주택 취득 — 주택 중과(8%) 아님, 일반 건축물 4%
    homes = [_home(라벨="A"), _home(라벨="B"), {"종류": "노인복지주택", "취득대상": True}]
    r = judge_acquisition_homes_and_rate(homes, in_adjusted_area=True, acquire_date="2026-12-01")
    assert r["취득세율"] == 0.04
    assert r["중과여부"] is False
    assert r["산입_주택수"] == 2
    assert r["세율_판정"]["지방교육세율(과표대비)"] == 0.004
    assert any("부동산세제과-923" in f for f in r["플래그"])


def test_gift_senior_housing_rate():
    r = judge_acquisition_homes_and_rate([{"종류": "노인복지주택"}], in_adjusted_area=True,
                                         is_gift=True, gift_std_value=500_000_000)
    assert r["취득세율"] == 0.035 and r["중과여부"] is False


def test_count_only():
    c = count_acquisition_homes([{"종류": "노인복지주택"}, _home(), _home()])
    assert c["산입_주택수"] == 2
