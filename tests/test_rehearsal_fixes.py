"""리허설·전수조사에서 나온 결함의 회귀 — findings 290(일시적 2주택 조정대상지역 미입력), 341(항 없는 조의 호 표기), 342(법인 취득세 근거 사유)."""
import tax_judgment
import tax_overrides
from corporate_tax import calc_corporate_acquisition_tax


def test_290_unknown_adjusted_area_is_pending_between_two_and_three_years():
    f = tax_judgment.judge_temporary_two_homes
    assert f("2020-01-01", "2026-09-01", "2028-06-01")["특례충족"] is True          # 2년 안 — 어느 쪽이든 충족
    r = f("2020-01-01", "2026-09-01", "2029-01-15")                                # 2년~3년 사이 — 보류
    assert r["특례충족"] is None and r["양도기한내"] is None
    assert any("조정대상지역 여부 미입력" in x and "판정 보류" in x for x in r["플래그"])
    assert f("2020-01-01", "2026-09-01", "2029-12-01")["특례충족"] is False         # 3년 넘김 — 어느 쪽이든 미충족
    assert f("2020-01-01", "2026-09-01", "2029-01-15", prev_in_adjusted_area=False)["특례충족"] is True
    assert f("2020-01-01", "2026-09-01", "2029-01-15", prev_in_adjusted_area=True, new_in_adjusted_area=True)["특례충족"] is False
    assert f("2020-01-01", "2026-09-01", "2029-01-15", new_in_adjusted_area=True)["특례충족"] is None


def test_290_before_2026_amendment_unchanged():
    assert tax_judgment.judge_temporary_two_homes("2018-01-01", "2021-03-01", "2023-06-01")["특례충족"] is True


def test_290_override_defaults_to_unknown():
    r = tax_overrides.judge_temporary_two_homes("2020-01-01", "2026-09-01", "2029-01-15")
    assert r["특례충족"] is None


_LOW = dict(acquisition_price=90000000, acquire_date="2026-03-02", property_kind="주택", property_in_metro=False,
            exclusive_area=59, standard_value=80000000, in_capital_area=True, in_redevelopment_zone=False)


def test_341_item_label_has_space_when_no_paragraph():
    r = calc_corporate_acquisition_tax(**_LOW)
    labels = r["적용 조문"] + [m["표기"] for m in r["미적용 조문"]]
    assert "농어촌특별세법 §4 11호" in labels and "농어촌특별세법 §4 9호" in labels
    assert not any("§411호" in x or "§49호" in x for x in labels)


def test_342_reasons_follow_corporate_judgment():
    r = calc_corporate_acquisition_tax(**_LOW)
    사유 = {m["표기"]: m["사유"] for m in r["미적용 조문"]}
    assert "지방세법 시행령 §28의2" in r["적용 조문"] and "지방세법 시행령 §28의2" not in 사유
    assert "저가주택 예외" in 사유["지방세법 §13의2①"] and "개인" not in 사유["지방세법 §13의2①"]
    assert 사유["지방세법 §13의3"].startswith("법인 취득")
    r = calc_corporate_acquisition_tax(acquisition_price=500000000, acquire_date="2026-03-02", property_kind="주택",
                                       exclusive_area=59, standard_value=350000000, in_capital_area=True)
    사유 = {m["표기"]: m["사유"] for m in r["미적용 조문"]}
    assert r["대도시중과"] is None and 사유["지방세법 §13②"].startswith("판정 불가")
    assert 사유["지방세법 §13의2④"].startswith("법인 취득")
