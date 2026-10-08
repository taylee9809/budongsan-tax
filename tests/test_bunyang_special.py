# -*- coding: utf-8 -*-
"""주택+분양권 1세대1주택 특례(영 §156의3) 회귀 테스트 — 24차 순회.

이 조문에서 실제로 틀리는 자리는 요건 자체가 아니라 **경계일**이다. 부칙이 셋
(2021.2.17 §10 / 2022.2.15 §12 / 2023.2.28 §8)이고 각각 기준이 다르다 —
하나는 분양권 취득일, 하나는 양도일. 그래서 경계 케이스를 먼저 세운다.
"""
from datetime import date

import tax_judgment as tj

J = tj.judge_156_3_special


# ── 적용 개시 게이트 (부칙 2021.2.17 §10) ───────────────────────────────


def test_pre2021_bunyang_is_not_counted():
    """2020년 취득 분양권은 주택수에 안 들어간다 — '탈락'이 아니라 '특례 불필요'."""
    r = J("2015-01-01", "2020-12-31", "2023-05-01")
    assert r["특례적용"] is True
    assert r["판정근거항"] == "해당없음"
    assert "주택수에 산입되지 않는다" in r["사유"]


def test_2021_01_01_bunyang_enters_the_rule():
    r = J("2015-01-01", "2021-01-01", "2023-05-01")
    assert r["판정근거항"] == "②"


# ── ②항: 1년 경과 + 3년 내 양도 ────────────────────────────────────────


def test_clause2_basic():
    r = J("2018-03-01", "2021-06-01", "2023-05-01")
    assert r["특례적용"] is True and r["판정근거항"] == "②"


def test_clause2_exact_one_year_and_exact_three_years_pass():
    """만 1년 되는 날 취득, 만 3년 되는 날 양도 — 둘 다 충족이어야 한다.

    일수/365.25로 재면 0.9993년·3.0007년이 나와 둘 다 뒤집힌다.
    """
    r = J("2021-03-01", "2022-03-01", "2025-03-01")
    assert r["특례적용"] is True and r["판정근거항"] == "②"


def test_clause2_one_day_short_of_one_year_fails():
    r = J("2021-03-02", "2022-03-01", "2025-03-01")
    assert r["특례적용"] is False
    assert "2022-03-02 이후" in " ".join(r["플래그"])


def test_clause2_one_day_past_three_years_moves_to_clause3():
    r = J("2021-03-01", "2022-03-01", "2025-03-02")
    assert r["판정근거항"] == "③"


# ── ②항 후단: §154① 제1호·제2호가목·제3호만 1년 요건 면제 ──────────────


def test_expropriation_waives_one_year_rule():
    r = J("2021-06-01", "2021-09-01", "2024-06-01", holding_waiver_reason="수용")
    assert r["특례적용"] is True and r["판정근거항"] == "②"


def test_rental_five_year_and_unavoidable_one_year_residence_waive():
    for reason in ("건설임대5년거주", "부득이1년거주"):
        r = J("2021-06-01", "2021-09-01", "2024-06-01", holding_waiver_reason=reason)
        assert r["특례적용"] is True, reason


def test_overseas_emigration_does_not_waive_one_year_rule():
    """§154①제2호 '나목'이라 ②항 후단 인용 대상이 아니다 — 과다 면제 방지."""
    r = J("2021-06-01", "2021-09-01", "2024-06-01", holding_waiver_reason="해외이주2년")
    assert r["특례적용"] is False
    assert "나목·다목" in " ".join(r["플래그"])


def test_overseas_work_study_does_not_waive_either():
    r = J("2021-06-01", "2021-09-01", "2024-06-01", holding_waiver_reason="취학근무국외")
    assert r["특례적용"] is False


# ── 규칙 §75①: 부득이한 사유는 열거 3가지뿐 ────────────────────────────


def test_kamco_sale_request_keeps_clause2_past_three_years():
    r = J("2018-01-01", "2021-01-01", "2025-06-01",
          sale_delay_reason="캠코매각의뢰", delay_state_at_3y=True,
          sold_by_that_method=True)
    assert r["특례적용"] is True and r["판정근거항"] == "②(부득이)"


def test_delay_reason_needs_both_side_conditions():
    r = J("2018-01-01", "2021-01-01", "2025-06-01",
          sale_delay_reason="법원경매신청", delay_state_at_3y=True,
          sold_by_that_method=False)
    assert r["판정근거항"] != "②(부득이)"
    assert "실제로 그 방법에 따라 양도될 것" in " ".join(r["플래그"])


def test_market_slowness_is_not_an_unavoidable_reason():
    """'안 팔려서 늦었다'는 규칙 §75① 열거에 없다 — 상담 최빈 오해."""
    r = J("2018-01-01", "2021-01-01", "2025-06-01", sale_delay_reason="매수인이없어서")
    assert r["판정근거항"] != "②(부득이)"
    assert "시장에서 안 팔린 사정은 부득이한 사유가 아니다" in " ".join(r["플래그"])


# ── ③항 경과규정: 완성 후 2년 → 3년 (부칙 2023.2.28 §8, 양도일 기준) ───


def _clause3(sale, completed, moved, resided=1.5, bunyang="2021-01-01"):
    return J("2018-01-01", bunyang, sale, new_home_completed=completed,
             moved_in_date=moved, continuous_residence_years=resided)


def test_clause3_always_uses_three_year_window_for_bunyang():
    """§156의3에서 2년 창은 **구조상 도달할 수 없다**.

    ③항은 분양권 취득일 + 3년을 지나 양도한 경우에만 열린다. 그런데 이 특례는
    2021-01-01 이후 취득한 분양권에만 적용되므로 양도일은 반드시 2024-01-01을
    넘는다 — 2년/3년을 가르는 2023-01-12보다 항상 뒤다.

    입주권(§156의2)은 그런 취득일 제한이 없어 2년 창이 살아 있다. 같은 부칙
    (2023.2.28 §8)이 두 조문을 함께 개정했지만 도달 가능성이 다르다.
    """
    r = _clause3("2024-01-02", "2022-06-01", "2024-09-01")
    joined = " ".join(c["규칙"] for c in r["근거"])
    assert "완성 후 3년 기준" in joined
    assert "2년" not in joined


def test_earliest_reachable_clause3_sale_is_after_2024():
    """가장 이른 ③항 사례(2021-01-01 취득)도 양도일이 2024-01-02 이후다."""
    earliest = J("2018-01-01", "2021-01-01", "2024-01-01",
                 new_home_completed="2023-06-01", moved_in_date="2023-07-01",
                 continuous_residence_years=1.5)
    assert earliest["판정근거항"] == "②"   # 아직 3년 이내라 ②항이다
    just_after = J("2018-01-01", "2021-01-01", "2024-01-02",
                   new_home_completed="2023-06-01", moved_in_date="2023-07-01",
                   continuous_residence_years=1.5)
    assert just_after["판정근거항"] == "③"
    assert "완성 후 3년 기준" in " ".join(c["규칙"] for c in just_after["근거"])


def test_clause3_move_window_decides_outcome():
    """완성 후 3년을 넘겨 이사하면 탈락, 안쪽이면 통과."""
    # 완성 2024-01-01 → 제2호 양도기한은 2027-01-01. 양도는 양쪽 다 그 안에 두고
    # 제1호 이사시점만 달리해 이사 요건 단독 효과를 본다.
    late = _clause3("2026-12-15", "2024-01-01", "2027-05-01")
    intime = _clause3("2026-12-15", "2024-01-01", "2026-12-01")
    assert late["특례적용"] is False
    assert "3년 초과" in " ".join(late["플래그"])
    assert intime["특례적용"] is True


# ── ③항 1년 요건 경과조치 (부칙 2022.2.15 §12, 분양권 취득일 기준) ─────


def test_clause3_one_year_rule_not_applied_to_pre_20220215_bunyang():
    """2022-02-14 취득 분양권은 종전 규정 — 1년 요건 미적용."""
    r = J("2021-06-01", "2022-02-14", "2025-08-01",
          new_home_completed="2024-01-01", moved_in_date="2024-06-01",
          continuous_residence_years=1.2)
    assert r["특례적용"] is True
    assert "종전 규정" in " ".join(c["규칙"] for c in r["근거"])


def test_clause3_one_year_rule_applies_from_20220215():
    r = J("2021-06-01", "2022-02-15", "2025-08-01",
          new_home_completed="2024-01-01", moved_in_date="2024-06-01",
          continuous_residence_years=1.2)
    assert r["특례적용"] is False
    assert "③항 1년 요건 미달" in " ".join(r["플래그"])


def test_transition_is_keyed_to_acquisition_not_sale():
    """같은 양도일, 분양권 취득일 하루 차이로 결론이 갈린다."""
    a = J("2021-06-01", "2022-02-14", "2025-08-01", new_home_completed="2024-01-01",
          moved_in_date="2024-06-01", continuous_residence_years=1.2)
    b = J("2021-06-01", "2022-02-15", "2025-08-01", new_home_completed="2024-01-01",
          moved_in_date="2024-06-01", continuous_residence_years=1.2)
    assert a["특례적용"] != b["특례적용"]


# ── ③항 개별 요건 ──────────────────────────────────────────────────────


def test_clause3_needs_completion_date():
    r = J("2018-01-01", "2021-01-01", "2025-06-01")
    assert r["특례적용"] is False
    assert "신축주택 완성일" in r["사유"]


def test_clause3_residence_under_one_year_fails():
    r = _clause3("2025-06-01", "2024-01-01", "2024-03-01", resided=0.5)
    assert r["특례적용"] is False
    assert "1년 미달" in " ".join(r["플래그"])


def test_clause3_sale_before_completion_is_ok():
    """제2호는 '완성되기 전' 양도도 인정한다."""
    r = J("2018-01-01", "2021-01-01", "2024-06-01",
          new_home_completed="2024-12-01", moved_in_date="2025-01-01",
          continuous_residence_years=1.5)
    assert "완성 후" not in r["사유"]


def test_clause3_success_carries_aftercare_warning():
    r = _clause3("2025-06-01", "2024-01-01", "2024-03-01", resided=1.5)
    assert r["특례적용"] is True
    assert "2개월 이내" in r["사후관리"]


def test_clause3_failure_has_no_aftercare_text():
    r = _clause3("2025-06-01", "2024-01-01", "2024-03-01", resided=0.5)
    assert r["사후관리"] == ""


# ── 규칙 §75의2·§71③: 세대원 일부 미이사 사유 ──────────────────────────


def test_partial_move_reason_listed():
    r = _clause3("2025-06-01", "2024-01-01", "2024-03-01")
    r2 = J("2018-01-01", "2021-01-01", "2025-06-01",
           new_home_completed="2024-01-01", moved_in_date="2024-03-01",
           continuous_residence_years=1.5, partial_move_reason="질병")
    assert r["특례적용"] and r2["특례적용"]
    assert "재학·재직·요양증명서" in " ".join(c["규칙"] for c in r2["근거"])


def test_partial_move_reason_unlisted_flagged():
    r = J("2018-01-01", "2021-01-01", "2025-06-01",
          new_home_completed="2024-01-01", moved_in_date="2024-03-01",
          continuous_residence_years=1.5, partial_move_reason="초등학교취학")
    assert "초·중학교를 제외한다" in " ".join(r["플래그"])


# ── 입력 방어 ──────────────────────────────────────────────────────────


def test_bad_date_returns_error():
    assert "오류" in J("2018/01/01", "2021-01-01", "2025-06-01")


def test_add_years_handles_leap_day():
    assert tj._b3_add_years(date(2020, 2, 29), 1) == date(2021, 2, 28)
    assert tj._b3_add_years(date(2020, 2, 29), 4) == date(2024, 2, 29)


# ── 구현범위 고지 (검증 지적 반영 — 반쪽 구현 침묵 금지) ────────────────


def test_scope_field_on_every_verdict():
    """④~⑧항 미구현을 모든 반환이 고지해야 한다 — 상속분양권 상담 오용 방지."""
    cases = [
        J("2015-01-01", "2020-12-31", "2023-05-01"),                # 해당없음
        J("2018-03-01", "2021-06-01", "2023-05-01"),                # ② 충족
        J("2021-03-02", "2022-03-01", "2025-03-01"),                # ② 탈락
        J("2018-01-01", "2021-01-01", "2025-06-01"),                # ③ 완성일 없음
    ]
    for r in cases:
        assert r["판정범위"] == "②③항 한정(④~⑧ 미구현)"
    # 본판정(②③ 경로)에 들어간 경우에는 플래그로도 문구 고지
    assert "상속분양권" in " ".join(cases[1]["플래그"])


def test_scope_field_not_leaked_into_155():
    """전역 치환 사고 회귀 방지 — §155 특례 함수에는 이 필드가 없어야 한다."""
    r = tj.judge_155_special("혼인", event_date="2020-05-01", sale_date="2024-01-01")
    assert "판정범위" not in r


# ── 주택수 전제 (S1 예규 교차검증 반영, finding #39) ────────────────────


def test_other_home_breaks_the_premise():
    """§156의3②은 '1주택과 1분양권' 전제 — 서면-2021-부동산-5364."""
    r = J("2018-01-01", "2022-06-01", "2024-05-01", other_homes=1)
    assert r["특례적용"] is False
    assert r["판정근거항"] == "전제"
    assert "별도 특례" in " ".join(r["플래그"])


def test_excluded_home_restores_the_premise():
    """농어촌주택·인구감소지역주택은 주택수에서 빠진다 — 서면-2022-부동산-4530 등."""
    r = J("2018-01-01", "2022-06-01", "2024-05-01", other_homes=1, excluded_homes=1)
    assert r["특례적용"] is True and r["판정근거항"] == "②"
    assert "주택수 제외 특례" in " ".join(c["규칙"] for c in r["근거"])


def test_excluded_cannot_go_negative():
    r = J("2018-01-01", "2022-06-01", "2024-05-01", other_homes=0, excluded_homes=3)
    assert r["특례적용"] is True


def test_completed_bunyang_raises_deadline_flag():
    r = J("2018-01-01", "2022-06-01", "2024-05-01", bunyang_already_completed=True)
    assert "③항 제2호" in " ".join(r["플래그"])


# ── 주택수 배선 자동화 (judge_156_3_from_portfolio) ────────────────────


P = tj.judge_156_3_from_portfolio

TARGET = {"종류": "주택", "취득일": "2018-01-01", "라벨": "A종전주택", "양도대상": True}
BUNYANG = {"종류": "분양권", "취득일": "2022-06-01", "라벨": "C분양권"}


def test_portfolio_auto_excludes_rural_house():
    """농어촌주택은 트리②가 제외하므로 사람이 excluded_homes를 안 넣어도 된다."""
    r = P([TARGET, {"종류": "주택", "취득일": "2016-04-01",
                    "농어촌주택특례": True, "라벨": "B농어촌"}, BUNYANG],
          sale_date="2024-05-01")
    assert r["특례적용"] is True and r["판정근거항"] == "②"
    assert r["주택수산정"]["그 밖의 주택"] == 1
    assert r["주택수산정"]["그중 제외"] == 1


def test_portfolio_counts_plain_extra_home():
    r = P([TARGET, {"종류": "주택", "취득일": "2019-04-01", "라벨": "B일반"}, BUNYANG],
          sale_date="2024-05-01")
    assert r["특례적용"] is False and r["판정근거항"] == "전제"
    assert r["주택수산정"]["그중 제외"] == 0


def test_portfolio_matches_manual_call():
    """배선 경로와 수동 경로의 결론이 같아야 한다 — 두 입구가 갈리면 안 된다."""
    auto = P([TARGET, {"종류": "주택", "취득일": "2019-04-01", "라벨": "B"}, BUNYANG],
             sale_date="2024-05-01")
    manual = J("2018-01-01", "2022-06-01", "2024-05-01",
               other_homes=1, excluded_homes=0)
    assert auto["특례적용"] == manual["특례적용"]
    assert auto["판정근거항"] == manual["판정근거항"]


def test_portfolio_two_bunyang_is_clause6_territory():
    r = P([TARGET, BUNYANG, {"종류": "분양권", "취득일": "2023-01-01", "라벨": "C2"}],
          sale_date="2024-05-01")
    assert r["특례적용"] is False
    assert "⑥항" in r["사유"]


def test_portfolio_pre2021_bunyang_needs_no_special():
    r = P([{"종류": "주택", "취득일": "2015-01-01", "라벨": "A", "양도대상": True},
           {"종류": "분양권", "취득일": "2020-12-31", "라벨": "C"}],
          sale_date="2023-05-01")
    assert r["판정근거항"] == "해당없음"


def test_portfolio_requires_exactly_one_target():
    assert "오류" in P([{"종류": "주택", "취득일": "2018-01-01"}, BUNYANG],
                     sale_date="2024-05-01")
    assert "오류" in P([TARGET, dict(TARGET, 라벨="dup"), BUNYANG],
                     sale_date="2024-05-01")


def test_portfolio_without_bunyang_points_elsewhere():
    r = P([TARGET, {"종류": "주택", "취득일": "2019-04-01", "라벨": "B"}],
          sale_date="2024-05-01")
    assert "§155①" in r["오류"]


def test_portfolio_explicit_override_wins():
    """수동으로 넣은 값이 자동 산정을 덮어쓴다 — 예외 사실관계 대응."""
    r = P([TARGET, {"종류": "주택", "취득일": "2019-04-01", "라벨": "B"}, BUNYANG],
          sale_date="2024-05-01", other_homes=1, excluded_homes=1)
    assert r["특례적용"] is True
