"""대체 도구(tax_overrides) — 생성 도구와의 호환, 고친 동작, 호스팅 서버·stdio 진입점 등록."""
import asyncio
import inspect
import itertools
import json

import pytest

import tax_http
import tax_judgment
import tax_overrides
import tax_server

SOURCE = {t.name: t for t in tax_server.mcp._tool_manager.list_tools()}
_EMPTY = inspect.Parameter.empty


def test_overrides_name_generated_tools():
    # 2026-11-18 calc_jongbu_tax·calc_acquisition_tax, 2026-11-19 나머지 9개를 원본(server.py)에서 고쳐 다시 생성했다 — 대체 도구는 없다
    assert tax_overrides.OVERRIDES == {}
    assert set(tax_overrides.UPSTREAMED) == {
        "judge_transfer_reliefs", "count_heavy_homes", "judge_temporary_two_homes", "judge_155_special",
        "judge_156_3_from_portfolio", "calc_attached_land_limit", "judge_acquisition_homes_and_rate", "calc_property_tax",
        "estimate_reconstruction_levy"}
    assert set(tax_overrides.UPSTREAMED) <= set(SOURCE)
    assert all(getattr(tax_overrides, name) is SOURCE[name].fn for name in tax_overrides.UPSTREAMED)


#: 원본에 되돌려 반영한 도구 — 아래 테스트는 생성 도구가 그 인자를 계속 받는지 지킨다(생성기가 인자를 떨어뜨리면 깨진다).
_TOOLS = {name: getattr(tax_overrides, name) for name in tax_overrides.UPSTREAMED}


@pytest.mark.parametrize("name", sorted(tax_overrides.OVERRIDES))
def test_override_parameters_are_a_superset(name):
    """생성기가 인자를 바꾸면 여기서 깨진다 — 기존 인자는 이름·순서·기본값이 같고, 더한 인자는 모두 선택이다."""
    old = inspect.signature(SOURCE[name].fn).parameters
    new = inspect.signature(tax_overrides.OVERRIDES[name]).parameters
    assert list(new)[:len(old)] == list(old), "기존 인자의 이름·순서(위치 인자 호환)"
    changed = tax_overrides.CHANGED_DEFAULTS.get(name, {})
    for p, spec in old.items():
        if p in changed:
            assert new[p].default == changed[p] and spec.default is not _EMPTY
        else:
            assert new[p].default == spec.default, p
    for p in list(new)[len(old):]:
        assert new[p].default is not _EMPTY, "더한 인자 %s 는 기본값이 있어야 한다" % p


#: 판정기를 같은 이름으로 부르지 않는 대체 도구 — 무엇과 대조하는지 따로 적는다.
#:   count_heavy_homes           판정기는 (items, heavy_tier)뿐이고 나머지는 조문 노드 중과세율_판정에 넘긴다
#:   judge_156_3_from_portfolio  판정기가 **kw 로 judge_156_3_special 인자를 받는다(앞의 취득일 둘은 목록에서 읽는다)
#:   calc_property_tax           판정기가 없다 — 생성 도구와 조문 노드 합성(재산세_주택)을 부른다
_NOT_SAME_NAME = {"count_heavy_homes", "judge_156_3_from_portfolio", "calc_property_tax"}


@pytest.mark.parametrize("name", sorted(set(tax_overrides.UPSTREAMED) - _NOT_SAME_NAME))
def test_passthrough_overrides_cover_the_judgment_signature(name):
    """판정기를 그대로 부르는 대체 도구는 판정기 인자를 빠짐없이 받는다 — 판정기에 인자가 늘면 깨진다(의도한 것)."""
    judged = inspect.signature(getattr(tax_judgment, name)).parameters
    assert all(p.kind is p.POSITIONAL_OR_KEYWORD for p in judged.values()), "**kw 판정기는 _NOT_SAME_NAME 에서 따로 대조한다"
    new = inspect.signature(_TOOLS[name]).parameters
    assert set(judged) <= set(new), sorted(set(judged) - set(new))
    for p in set(new) - set(inspect.signature(SOURCE[name].fn).parameters):      # 더한 인자의 기본값 = 판정기 기본값
        assert new[p].default == judged[p].default, p


def test_other_overrides_cover_what_they_call():
    assert set(tax_overrides.UPSTREAMED) >= _NOT_SAME_NAME
    assert list(inspect.signature(tax_judgment.count_heavy_homes).parameters) == ["items", "heavy_tier"]
    kw = inspect.signature(tax_judgment.judge_156_3_from_portfolio).parameters["kw"]
    assert kw.kind is kw.VAR_KEYWORD
    special = list(inspect.signature(tax_judgment.judge_156_3_special).parameters)
    assert special[:3] == ["prior_home_acquired", "bunyang_acquired", "sale_date"]
    assert set(special[3:]) <= set(inspect.signature(tax_overrides.judge_156_3_from_portfolio).parameters)
    # 재산세: 노드가 읽는 사실 이름이 그대로인지(바뀌면 대체 도구가 넘기는 키도 바꿔야 한다)
    import tax_nodes.jaesan as jaesan
    src = inspect.getsource(jaesan.제111조의2제4항)
    assert '"지방세특례_감면유형"' in src and '"지방세특례_사실"' in src


def test_every_generated_wrapper_gap_is_overridden():
    """생성 래퍼가 넘기지 못하는 판정기 인자가 새로 생기면 여기서 깨진다 — tax_overrides 에 더하고 docs/WRAPPER_GAPS.md 를 다시 만든다."""
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location(
        "wrapper_gaps", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "wrapper_gaps.py")
    wg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wg)
    rows = wg.audit()
    assert len(rows) == len(SOURCE) == 43
    open_gaps = {r["도구"]: r["남은_인자"] for r in rows if r["남은_인자"]}
    assert open_gaps == {}, open_gaps
    assert {r["도구"] for r in rows if r["빠진_인자"]} <= set(tax_overrides.OVERRIDES)
    doc = (pathlib.Path(wg.DOC)).read_text(encoding="utf-8")
    assert doc == wg.render(rows), "docs/WRAPPER_GAPS.md 가 낡았다 — python scripts/wrapper_gaps.py 로 다시 만든다"


def test_hosted_server_serves_the_overrides():
    tools = {t.name: t for t in tax_http.make_server()._tool_manager.list_tools()}
    assert len(tools) == 49
    for name, fn in tax_overrides.OVERRIDES.items():
        assert tools[name].fn is fn
        assert tools[name].title == SOURCE[name].title and tools[name].annotations == SOURCE[name].annotations
        assert tools[name].description.strip() and "tax_overrides" not in tools[name].description
    assert [n for n in tools if n in SOURCE] == [n for n in SOURCE if n in tools]      # 순서도 그대로
    props = tools["calc_jongbu_tax"].parameters["properties"]
    assert props["basic_deduction"]["default"] is None and "is_corporation" in props
    assert tax_server.mcp._tool_manager.get_tool("calc_jongbu_tax").fn is tax_server.calc_jongbu_tax   # 생성 서버는 그대로


# ───────────────────────────────────────────────────────────── 종합부동산세
def test_jongbu_unspecified_and_positive_deduction_match_the_generated_tool():
    for price, prev, one, n, age, hold, ded in itertools.product(
            (500_000_000, 1_300_000_000, 3_000_000_000), (0, 1_000_000_000, 2_500_000_000), (False, True),
            (1, 3), (0, 66), (0, 12), (None, 600_000_000)):
        kw = dict(prev_year_official_price=prev, one_home=one, home_count=n, age=age, holding_years=hold)
        assert (tax_overrides.calc_jongbu_tax(price, 2026, basic_deduction=ded, **kw)
                == tax_server.calc_jongbu_tax(price, 2026, basic_deduction=ded, **kw))


def test_jongbu_zero_deduction_is_zero():
    flat = [{"upto": None, "rate": 0.027, "deduction": 0}]
    r = tax_overrides.calc_jongbu_tax(600_000_000, 2026, basic_deduction=0, tax_brackets=flat)
    assert (r["공제금액"], r["과세표준"], r["종합부동산세"]) == (0, 360_000_000, 9_720_000)
    assert len(r["경고"]) == 1 and "§8①2호" in r["경고"][0]
    # 생성 도구도 원본을 고쳐 다시 만든 뒤로 같은 답을 낸다(finding 95 해소, 2026-11-18)
    assert tax_server.calc_jongbu_tax(600_000_000, 2026, basic_deduction=0, tax_brackets=flat)["과세표준"] == 360_000_000
    # 공제 0원 + 직전 연도 가격 → 상한이 걸리면 그 사실을 경고한다(금액은 원래 함수의 계산)
    r = tax_overrides.calc_jongbu_tax(2_000_000_000, 2026, basic_deduction=0, prev_year_official_price=1_000_000_000)
    assert r["세부담상한 적용여부"] and any("§10 단서" in w for w in r["경고"]) and any("§9①" in w for w in r["경고"])
    assert tax_params_untouched()


def tax_params_untouched():
    import tax_params
    return tax_params.get_param("종부세.주택.기본공제", 2026)["일반"] == 900_000_000


def test_jongbu_refuses_corporations_and_contradictions():
    r = tax_overrides.calc_jongbu_tax(600_000_000, 2026, is_corporation=True)
    assert r["계산불가"] is True and "§9②" in r["근거"] and not {"과세표준", "종합부동산세", "총납부세액"} & set(r)
    r = tax_overrides.calc_jongbu_tax(1_500_000_000, 2026, one_home=True, basic_deduction=0)
    assert r["계산불가"] is True and "종합부동산세" not in r
    with pytest.raises(ValueError):
        tax_overrides.calc_jongbu_tax(600_000_000, 2026, basic_deduction=-1)
    with pytest.raises(ValueError):
        tax_overrides.calc_jongbu_tax(0, 2026)


# ───────────────────────────────────────────────────────────────── 취득세
def _acq(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ValueError:
        return "ValueError"


def test_acquisition_differs_only_by_refusing_heavy_type_on_non_housing():
    kinds = ("주택유상", "유상.농지외", "유상.농지", "무상", "원시취득", "공유물분할", "상속.농지외")
    refused = 0
    for price, kind, heavy, area, special in itertools.product(
            (300_000_000, 750_000_000, 2_000_000_000), kinds,
            ("", "법인", "2주택조정_또는_3주택비조정", "3주택이상조정_또는_4주택이상비조정"), (0, 60, 100),
            ("", "재산분할", "없음")):
        new = _acq(tax_overrides.calc_acquisition_tax, price, 2026, kind, heavy, area, rate_special=special)
        if isinstance(new, dict) and new.get("계산불가"):
            assert heavy and kind != "주택유상" and "취득세" not in new, (kind, heavy, special)
            refused += 1
        elif isinstance(new, dict):
            assert not (heavy and kind != "주택유상"), (kind, heavy, special)
    assert refused
    r = tax_overrides.calc_acquisition_tax(1_000_000_000, 2026, "유상.농지외", heavy_type="법인")
    assert r["계산불가"] is True and "§13의2①" in r["근거"]
    with pytest.raises(ValueError):                      # 모르는 유형은 원래 함수가 거부한다
        tax_overrides.calc_acquisition_tax(1_000_000_000, 2026, "유상.농지외", heavy_type="없는유형")


def test_acquisition_warns_on_hand_built_surcharge_without_changing_amounts():
    args = (1_000_000_000, 2026, "유상.농지외")
    new = tax_overrides.calc_acquisition_tax(*args, heavy_surcharge_rate=0.04)
    warn = new.pop("경고")
    assert new["지방교육세"] == 4_000_000 and new["취득세"] == 80_000_000      # 금액은 바꾸지 않는다
    assert len(warn) == 1 and "§13②" in warn[0] and "12,000,000원" in warn[0] and "§151①1호가목" in warn[0]
    # §13② 세율 모양이 아니면 일반 경고
    warn = tax_overrides.calc_acquisition_tax(1_000_000_000, 2026, "주택유상", heavy_surcharge_rate=0.08)["경고"]
    assert len(warn) == 1 and "§13의2" in warn[0] and "농어촌특별세" in warn[0]
    # 지방교육세율을 직접 주었거나 가산세율을 주지 않은 호출에는 경고가 없다
    assert "경고" not in tax_overrides.calc_acquisition_tax(*args, heavy_surcharge_rate=0.04, local_education_tax_rate=0.012)
    assert "경고" not in tax_overrides.calc_acquisition_tax(*args)
    assert "경고" not in tax_overrides.calc_acquisition_tax(1_000_000_000, 2026, "주택유상", heavy_type="법인")


# ───────────────────────────────────────────────────────────── 양도소득세
def test_transfer_reliefs_passes_land_permit_facts():
    base = dict(is_one_household_one_home=False, holding_years=5, residing_years=0, sale_price=1_000_000_000,
                adjusted_at_sale=True, heavy_home_count=3, sale_date="2026-08-20", contract_date="2026-05-01",
                deposit_received=True)
    assert tax_overrides.judge_transfer_reliefs(**base) == tax_server.judge_transfer_reliefs(**base)
    assert tax_overrides.judge_transfer_reliefs(**base)["중과여부"] is False            # 허가 대상 여부를 모르면 종전 판정
    assert tax_overrides.judge_transfer_reliefs(**base, land_permit_target=True)["중과여부"] is True
    r = tax_overrides.judge_transfer_reliefs(**base, land_permit_target=True, land_permit_applied_date="2026-04-20",
                                             land_permit_granted=True)
    assert r["중과여부"] is False and r == tax_judgment.judge_transfer_reliefs(
        **base, land_permit_target=True, land_permit_applied_date="2026-04-20", land_permit_granted=True)
    late = dict(base, sale_date="2026-10-20", contract_date="2026-05-08")               # 4개월(09-08) 지나고 6개월 안
    assert tax_overrides.judge_transfer_reliefs(**late, land_permit_target=False)["중과여부"] is True
    assert tax_overrides.judge_transfer_reliefs(**late, land_permit_target=False, six_month_region=True)["중과여부"] is False


A = {"라벨": "A", "종류": "주택", "기준시가": 900_000_000}
B = {"라벨": "B", "종류": "주택", "기준시가": 80_000_000}
C = {"라벨": "C", "종류": "주택", "기준시가": 500_000_000}


def test_count_heavy_homes_without_sale_label_is_the_judgment_result():
    for items, tier in (([A, B], 2), ([A, B], 3), ([A, B, C], 3), ([], 3)):
        assert tax_overrides.count_heavy_homes(items, tier) == tax_judgment.count_heavy_homes(items, tier)


def test_count_heavy_homes_judges_the_sale_home_from_the_list():
    r = tax_overrides.count_heavy_homes([A, B], 2, sale_label="B", sale_date="2026-10-01", adjusted_at_sale=True)
    p = r["양도주택_중과판정"]
    assert r["중과판정_주택수"] == 2 and p["중과대상"] is False and p["중과적용"] is False
    assert p["적용호"] == "법 §104⑦1호" and any("9호" in w for w in p["제외사유"])
    p = tax_overrides.count_heavy_homes([A, B], 2, sale_label="A", sale_date="2026-10-01",
                                        adjusted_at_sale=True)["양도주택_중과판정"]
    assert p["중과적용"] is True and p["중과가산세율"] == 0.2 and p["장기보유특별공제_배제"] is True
    # 조정대상지역 여부를 주지 않으면 대상 주택 여부까지만
    p = tax_overrides.count_heavy_homes([A, B], 2, sale_label="A", sale_date="2026-10-01")["양도주택_중과판정"]
    assert p["중과대상"] is True and p["중과적용"] is None and p["중과가산세율"] is None
    # 한시 배제 — 다목(허가 대상 아님) / 나목(허가 대상: 신청·허가가 있어야)
    kw = dict(sale_label="A", sale_date="2026-08-20", adjusted_at_sale=True, holding_years=5,
              contract_date="2026-05-01", deposit_received=True)
    f = lambda **more: tax_overrides.count_heavy_homes([A, B, C], 3, **kw, **more)["양도주택_중과판정"]
    assert f(land_permit_target=False)["중과적용"] is False
    assert f(land_permit_target=True)["중과적용"] is True and f(land_permit_target=True)["중과가산세율"] == 0.3
    assert f(land_permit_target=True, land_permit_applied_date="2026-04-20", land_permit_granted=True)["중과적용"] is False
    assert A == {"라벨": "A", "종류": "주택", "기준시가": 900_000_000}                    # 입력 목록을 고치지 않는다
    # 계열이 heavy_tier 와 다르면 플래그, 라벨이 없으면 판정하지 않는다
    r = tax_overrides.count_heavy_homes([A, B, C], 2, sale_label="A", sale_date="2026-10-01")
    assert any("계열이 다르다" in x for x in r["플래그"])
    assert tax_overrides.count_heavy_homes([A, B], 2, sale_label="Z")["양도주택_중과판정"]["판정불가"] is True


# ───────────────────────────────────────────── 2026-11-19 에 더한 대체 도구 — 기존 호출 호환 격자
def _same_as_generated(name, grid):
    n = 0
    for kw in grid:
        assert _TOOLS[name](**kw) == SOURCE[name].fn(**kw), (name, kw)
        n += 1
    return n


def _product(**axes):
    keys = list(axes)
    return [dict(zip(keys, vals)) for vals in itertools.product(*axes.values())]


def test_temporary_two_homes_grid_matches_the_generated_tool():
    grid = _product(prev_acquired=("2015-03-01", "2025-12-01"), new_acquired=("2019-12-20", "2026-08-03", "2026-08-04", "2026-10-15"),
                    prev_sale_date=(None, "2021-06-01", "2028-09-01", "2029-03-01", "2029-11-01"),
                    prev_in_adjusted_area=(False, True), new_in_adjusted_area=(False, True),
                    new_contract_date=(None, "2026-07-20"), other_homes_at_acquisition=(0, 1),
                    new_right_acquired=(None, "2026-06-01"))
    assert _same_as_generated("judge_temporary_two_homes", grid) == 1280


def test_temporary_two_homes_notice_date_reaches_the_judgment():
    base = dict(prev_acquired="2020-01-01", new_acquired="2026-09-01", prev_sale_date="2029-03-01",
                prev_in_adjusted_area=True, new_in_adjusted_area=True)
    r = tax_overrides.judge_temporary_two_homes(**base)
    assert r["특례충족"] is False and r["양도기한연수"] == 2 and r["양도데드라인"] == "2028-09-01"
    for notice, years in (("2026-09-15", 3), ("2026-09-01", 3), ("2026-08-31", 2)):       # 공고일 이전(당일 포함) 취득이면 3년
        r = tax_overrides.judge_temporary_two_homes(**base, adjusted_area_notice_date=notice)
        assert r == tax_judgment.judge_temporary_two_homes(**base, adjusted_area_notice_date=notice)
        assert (r["양도기한연수"], r["특례충족"]) == (years, years == 3), notice
    # 계약·계약금 지급이 공고일 이전인 경우도 3년
    r = tax_overrides.judge_temporary_two_homes(**base, new_contract_date="2026-08-20", adjusted_area_notice_date="2026-08-25")
    assert r["양도기한연수"] == 3 and "대괄호" in r["적용법령"]


_HOMES = [{"라벨": "종전", "종류": "주택", "시가표준액": 500_000_000, "수도권": True},
          {"라벨": "신규", "종류": "주택", "시가표준액": 700_000_000, "수도권": True, "취득대상": True}]


def test_acquisition_homes_grid_matches_the_generated_tool():
    grid = _product(homes=(_HOMES, _HOMES[1:], _HOMES + [{"라벨": "셋째", "종류": "주택", "시가표준액": 90_000_000, "수도권": True}]),
                    in_adjusted_area=(False, True), is_corporation=(False, True),
                    acquire_date=(None, "2025-06-01", "2026-09-30", "2026-10-01", "2026-10-15"),
                    prev_disposal_date=(None, "2028-09-30", "2029-03-01", "2029-12-01"),
                    disposal_to_same_household=(False, True), is_gift=(False, True))
    assert _same_as_generated("judge_acquisition_homes_and_rate", grid) == 960


def test_acquisition_temporary_two_homes_new_inputs():
    base = dict(homes=_HOMES, in_adjusted_area=True, acquire_date="2026-10-15", prev_disposal_date="2029-03-01")
    f = lambda **more: tax_overrides.judge_acquisition_homes_and_rate(**base, **more)
    assert f()["일시적2주택"] is None and f()["중과여부"] is True                        # 생성 도구와 같은 보류
    r = f(prev_home_in_adjusted_area=True)
    assert r["일시적2주택"] is False and r["취득세율"] == 0.08 and r["일시적2주택_판정"]["처분데드라인"] == "2028-10-15"
    r = f(prev_home_in_adjusted_area=False)
    assert r["일시적2주택"] is True and r["중과여부"] is False and r["일시적2주택_판정"]["처분데드라인"] == "2029-10-15"
    paid = dict(new_contract_date="2026-08-20", new_deposit_paid_date="2026-08-20")
    assert f(prev_home_in_adjusted_area=True, **paid)["일시적2주택"] is True              # 부칙 §2② — 종전 규정 3년
    assert f(prev_home_in_adjusted_area=True, new_contract_date="2026-08-20")["일시적2주택"] is False   # 계약금 지급일이 없으면 경과규정 아님
    assert f(prev_home_in_adjusted_area=True, **paid) == tax_judgment.judge_acquisition_homes_and_rate(
        **base, prev_home_in_adjusted_area=True, **paid)
    # 신규 주택이 조정대상지역 밖이면 종전 쪽을 몰라도 3년
    out = tax_overrides.judge_acquisition_homes_and_rate(**dict(base, in_adjusted_area=False))
    assert out["일시적2주택"] is True
    # 2026-10-01 전 취득분은 새 인자와 무관하게 3년
    old = dict(base, acquire_date="2026-09-30", prev_disposal_date="2029-03-01")
    assert tax_overrides.judge_acquisition_homes_and_rate(**old, prev_home_in_adjusted_area=True)["일시적2주택"] is True


def test_155_special_grid_and_homes_at_sale():
    grid = _product(kind=("혼인", "동거봉양", "상속주택", "거주주택"), event_date=("2015-03-01", "2021-05-01"),
                    sale_date=("", "2024-11-11", "2026-03-01", "2032-01-01"), homes_mine=(1, 2), homes_spouse_or_parent=(1, 2),
                    parent_max_age_at_merge=(None, 58, 65), excluded_homes_mine=(0, 1), rental_registered=(False, True),
                    residence_years_in_home=(0.0, 3.0))
    assert _same_as_generated("judge_155_special", grid) == 3072
    base = dict(kind="혼인", event_date="2020-05-01", sale_date="2026-03-01")
    plain = tax_overrides.judge_155_special(**base)
    for n, word in ((3, "늘어난"), (1, "§154①"), (2, "합가 당시")):
        r = tax_overrides.judge_155_special(**base, homes_at_sale=n)
        assert r["특례적용"] is plain["특례적용"] is True                                # 요건 판정은 바꾸지 않는다
        assert r["주택수_판정기준"] == {"합가당시": "1+1", "양도일현재": n} and word in r["플래그"][-1]
        assert r == tax_judgment.judge_155_special(**base, homes_at_sale=n)
    r = tax_overrides.judge_155_special(**dict(base, homes_mine=2), homes_at_sale=2)
    assert r["특례적용"] is False and any("법규과-1599" in x for x in r["플래그"])


_PORTFOLIO = [{"라벨": "종전", "종류": "주택", "취득일": "2018-01-01", "양도대상": True},
              {"라벨": "분양권", "종류": "분양권", "취득일": "2022-03-01"}]


def test_156_3_portfolio_grid_and_new_inputs():
    extra = {"라벨": "농가", "종류": "주택", "취득일": "2019-01-01", "농어촌주택특례": True}
    plain = {"라벨": "셋째", "종류": "주택", "취득일": "2019-01-01"}
    grid = _product(items=(_PORTFOLIO, _PORTFOLIO + [extra], _PORTFOLIO + [plain], _PORTFOLIO[:1], []),
                    sale_date=("2024-06-01", "2025-06-01", "2027-01-01"), new_home_completed=("", "2025-01-10"),
                    moved_in_date=("", "2025-06-01"), continuous_residence_years=(0.0, 1.5),
                    sale_delay_reason=("", "법원경매신청"), delay_state_at_3y=(False, True))
    assert _same_as_generated("judge_156_3_from_portfolio", grid) == 480
    base = dict(items=_PORTFOLIO, sale_date="2024-06-01")
    plain_r = tax_overrides.judge_156_3_from_portfolio(**base)
    assert plain_r["특례적용"] is True and plain_r["주택수산정"]["그 밖의 주택"] == 0
    r = tax_overrides.judge_156_3_from_portfolio(**base, bunyang_already_completed=True)
    assert r["특례적용"] is True and any("이미 완공" in x for x in r["플래그"]) and not any("이미 완공" in x for x in plain_r["플래그"])
    assert tax_overrides.judge_156_3_from_portfolio(**base, other_homes=1)["특례적용"] is False
    assert tax_overrides.judge_156_3_from_portfolio(**base, other_homes=1, excluded_homes=1)["특례적용"] is True
    # 0 을 직접 주면 목록에서 센 수(1)를 덮어쓴다 — None(생략)과 다르다
    listed = dict(items=_PORTFOLIO + [plain], sale_date="2024-06-01")
    assert tax_overrides.judge_156_3_from_portfolio(**listed)["특례적용"] is False
    assert tax_overrides.judge_156_3_from_portfolio(**listed, other_homes=0)["특례적용"] is True


def test_attached_land_limit_grid_and_rebuilt_inherited_home():
    grid = _product(building_footprint_m2=(60, 100.5, 150), land_area_m2=(100, 400, 2000), is_urban_area=(True, False),
                    is_capital_region=(True, False), urban_zone=("주거상업공업", "녹지"))
    assert _same_as_generated("calc_attached_land_limit", grid) == 72
    for kw in grid:                                                                  # 양도일만 주면 결과가 바뀌지 않는다
        assert tax_overrides.calc_attached_land_limit(**kw, sale_date="2021-05-01") == SOURCE["calc_attached_land_limit"].fn(**kw)
    r = tax_overrides.calc_attached_land_limit(150, 500, demolished_inherited_footprint_m2=80, sale_date="2026-05-01")
    assert (r["적용배율"], r["비과세_한도면적_m2"], r["초과면적_m2"], r["전부비과세"]) == (3, 240.0, 260.0, False)
    assert r["신축주택_정착면적_m2"] == 150.0 and "멸실된 상속주택" in r["한도기준"]
    r = tax_overrides.calc_attached_land_limit(150, 500, demolished_inherited_footprint_m2=80, sale_date="2021-05-01")
    assert (r["적용배율"], r["비과세_한도면적_m2"]) == (5, 400.0)                       # 2022-01-01 전 양도 — 수도권 도시지역 5배
    r = tax_overrides.calc_attached_land_limit(150, 500, False, demolished_inherited_footprint_m2=80)
    assert (r["적용배율"], r["전부비과세"]) == (10, True)


_JEONSE = {"전세사기피해자": True, "전세사기피해주택": True}
_AMOUNTS = ("시가표준액(공시가격)", "공정시장가액비율", "과세표준", "과표상한 적용여부", "적용세율", "누진공제", "재산세 본세",
            "도시지역분", "지방교육세", "총납부세액", "과세연도")
_K4 = "지특법 중복 판정(§111의2④)"


def test_property_tax_grid_matches_the_generated_tool():
    flat = [{"upto": None, "rate": 0.002, "deduction": 0}]
    grid = _product(official_price=(50_000_000, 300_000_000, 900_000_000, 1_500_000_000), year=(2025, 2026),
                    prev_year_official_price=(0, 280_000_000), one_home=(False, True), fair_market_ratio=(0.0, 0.5),
                    tax_brackets=(None, flat), urban_area_rate=(-1.0, 0.0), local_education_tax_rate=(-1.0, 0.1),
                    taxable_base_cap=(0, 100_000_000))
    assert _same_as_generated("calc_property_tax", grid) == 1024
    with pytest.raises(ValueError):
        tax_overrides.calc_property_tax(0, 2026)
    with pytest.raises(ValueError):
        tax_overrides.calc_property_tax(0, 2026, jiteuk_relief_type="전세사기피해자")


def test_property_tax_relief_comparison_is_the_node_result():
    from tax_nodes.jaesan import 재산세_주택
    r = tax_overrides.calc_property_tax(300_000_000, 2026, one_home=True, jiteuk_relief_type="전세사기피해자",
                                        jiteuk_relief_facts=dict(_JEONSE, 전용면적=59))
    assert r == 재산세_주택(300_000_000, 2026, 0, True, 지방세특례_감면유형="전세사기피해자", 지방세특례_사실=dict(_JEONSE, 전용면적=59))
    assert r["재산세 본세"] == 81_750 and r[_K4]["특례세율_배제"] is True and r[_K4]["지특법경감후_세액"] == 81_750
    assert "감면 후 금액" in r[_K4]["주의"]
    # 비교 결과가 특례세율이거나 비교 대상이 아니면 금액은 생성 도구와 같다
    seen = {"특례": 0, "지특": 0, "비교없음": 0}
    for price, prev, one, kind, facts in itertools.product(
            (60_000_000, 300_000_000, 900_000_000, 1_200_000_000), (0, 280_000_000), (False, True),
            ("전세사기피해자", "주택연금담보주택", "없는유형"),
            (dict(_JEONSE, 전용면적=59), dict(_JEONSE, 전용면적=84), {"1가구1주택": True}, None)):
        new = tax_overrides.calc_property_tax(price, 2026, prev, one, jiteuk_relief_type=kind, jiteuk_relief_facts=facts)
        old = tax_server.calc_property_tax(price, 2026, prev, one)
        if kind == "없는유형":      # 어느 감면 노드도 읽지 않는 이름 — 계산하지 않는다(findings 292)
            seen["비교없음"] += 1
            assert new.get("계산불가") is True and "없는유형" in new["사유"] and "재산세 본세" not in new
            continue
        if _K4 in new and new[_K4]["특례세율_배제"]:
            seen["지특"] += 1
            # findings 110·291 조치 뒤 — 지특법을 고르면 본세는 감면 후 금액이다(표준세율 세액은 old 이상).
            assert new["재산세 본세"] == new[_K4]["지특법경감후_세액"] and new[_K4]["표준세율_세액"] >= old["재산세 본세"]
            assert new["과세표준"] == old["과세표준"] and new["도시지역분"] <= old["도시지역분"]
        else:
            seen["특례" if _K4 in new else "비교없음"] += 1
            assert {k: new[k] for k in _AMOUNTS} == {k: old[k] for k in _AMOUNTS}, (price, prev, one, kind, facts)
            assert _K4 in new or any(m["표기"] == "지방세법 §111의2④" for m in new["미적용 조문"])
    assert all(seen.values()), seen


def test_property_tax_relief_refuses_what_it_cannot_compare():
    r = tax_overrides.calc_property_tax(300_000_000, 2026, one_home=True, jiteuk_relief_type="전세사기피해자", fair_market_ratio=0.5)
    assert r["계산불가"] is True and "fair_market_ratio" in r["사유"] and "재산세 본세" not in r
    r = tax_overrides.calc_property_tax(300_000_000, 2026, one_home=True, jiteuk_relief_facts=_JEONSE)
    assert r["계산불가"] is True and "jiteuk_relief_type" in r["사유"] and "총납부세액" not in r


def test_new_override_arguments_are_described():
    """더한 인자는 호스팅 설명에 이름이 나온다 — 설명에 없으면 모델이 그 인자를 모른다."""
    from hosted_descriptions import DESCRIPTIONS
    for name, fn in tax_overrides.OVERRIDES.items():
        old = inspect.signature(SOURCE[name].fn).parameters
        for p in inspect.signature(fn).parameters:
            if p not in old:
                assert p in DESCRIPTIONS[name], (name, p)
    for key in ("종전_조정대상지역", "신규_조정대상지역", "신규계약일", "신규계약금지급일", "신규권리취득일", "조정대상지역_공고일"):
        assert key in DESCRIPTIONS["judge_jongbu_one_home_status"], key


def test_new_overrides_through_the_server():
    server = tax_http.make_server()

    def call(name, args):
        out = asyncio.run(server.call_tool(name, args))
        return out[1] if isinstance(out, tuple) else json.loads(out[0].text)

    props = {t.name: t.parameters["properties"] for t in server._tool_manager.list_tools()}
    assert "adjusted_area_notice_date" in props["judge_temporary_two_homes"]
    assert {"prev_home_in_adjusted_area", "new_contract_date", "new_deposit_paid_date"} <= set(props["judge_acquisition_homes_and_rate"])
    assert "homes_at_sale" in props["judge_155_special"] and "jiteuk_relief_type" in props["calc_property_tax"]
    r = call("judge_acquisition_homes_and_rate", {"homes": _HOMES, "in_adjusted_area": True, "acquire_date": "2026-10-15",
                                                  "prev_disposal_date": "2029-03-01", "prev_home_in_adjusted_area": False})
    assert r["일시적2주택"] is True
    r = call("calc_property_tax", {"official_price": 300_000_000, "year": 2026, "one_home": True,
                                   "jiteuk_relief_type": "전세사기피해자", "jiteuk_relief_facts": dict(_JEONSE, 전용면적=59)})
    assert r["재산세 본세"] == 81_750


# ───────────────────────────────────────────────────────────── stdio 진입점
def test_full_stdio_entry_uses_the_hosted_assembly(monkeypatch):
    import tax_full
    seen = {}

    def fake_run(self, transport="stdio", **kw):
        seen["transport"] = transport
        seen["tools"] = {t.name: t.fn for t in self._tool_manager.list_tools()}

    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", fake_run)
    tax_full.main()
    assert seen["transport"] == "stdio" and len(seen["tools"]) == 49
    assert all(seen["tools"][n] is fn for n, fn in tax_overrides.OVERRIDES.items())
    assert "get_tax_scope" in seen["tools"]


def test_override_call_through_the_server_returns_the_refusal():
    server = tax_http.make_server()
    out = asyncio.run(server.call_tool("calc_acquisition_tax", {
        "acquisition_price": 1_000_000_000, "year": 2026, "acquisition_type": "유상.농지외", "heavy_type": "법인"}))
    structured = out[1] if isinstance(out, tuple) else out
    assert "계산불가" in str(structured)
