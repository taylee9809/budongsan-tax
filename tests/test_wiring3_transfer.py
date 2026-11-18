"""분업 3차 '연결' 묶음 (2026-11-18) — 단독으로만 돌던 조문 노드를 계산 흐름·판정기에 이은 것의 회귀.

1. 지방세법 §111의2④ — 1세대1주택 특례세율과 지방세특례제한법 재산세 경감 중 경감 효과가 큰 것 하나만
2. 소득세법 시행령 §8의2④(겸용주택 범위) → 법 §12 2호나목 고가 판정, §8의2③2호 단서 가·나목(findings 111)
3. 소득세법 시행령 §154①2호 후단(수용 잔존주택·부수토지 5년) → §154①·법 §89①3호
4. 소득세법 §98·영 §162①(취득·양도시기) → 영 §155① 일시적 2주택 기산일
5. 부동산실명법 §4②(명의신탁 귀속)·법 §88 10호(분양권 범위)·영 §155② 매입 지분 → 주택 수(노드·판정기)·중과 조립·§156의3
6. judge_transfer_reliefs(holdings=…) — 중과 주택 수·제외를 조문 노드로
7. 이름으로 읽는 연결 노드의 모듈 로드(findings 112)
케이스 원본은 data/verification/node_cases/wiring3_transfer.jsonl (W3-*). 여기서는 그 파일 전체와, 연결 전 호출이 그대로인지를 본다.
"""
import importlib
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tax_judgment  # noqa: E402
import tax_nodes.yangdo_gita_b  # noqa: E402,F401
from tax_nodes.engine import 실행  # noqa: E402
from tax_nodes.jaesan import 재산세_주택  # noqa: E402
from tax_nodes.setdae_jutaeksu import 비과세판정_주택수, 중과판정_주택수  # noqa: E402
from tax_nodes.yangdo import 양도세_부동산  # noqa: E402
from tax_nodes.yangdo_jungkwa_ho import 중과세율_판정  # noqa: E402

verify_node_cases = importlib.import_module("verify_node_cases")
_CASES = [json.loads(l) for l in (ROOT / "data" / "verification" / "node_cases" / "wiring3_transfer.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
K = "지특법 중복 판정(§111의2④)"


@pytest.mark.parametrize("case", _CASES, ids=[c["case_id"] for c in _CASES])
def test_w3_case(case):
    ok, detail = verify_node_cases.run_case(case)
    assert ok, detail


# ------------------------------------------------------------------ 1. 재산세 §111의2④
@pytest.mark.parametrize("가액", [50_000_000, 150_000_000, 300_000_000, 600_000_000, 900_000_000, 1_200_000_000])
@pytest.mark.parametrize("일주택", [True, False])
def test_property_tax_without_relief_type_is_unchanged(가액, 일주택):
    """감면유형을 주지 않은 호출(아무것도 없음 / '지방세특례_경감대상'만)은 결과가 같고 ④항은 미적용으로 남는다."""
    a = 재산세_주택(가액, 2026, 일세대일주택=일주택)
    b = 재산세_주택(가액, 2026, 일세대일주택=일주택, 지방세특례_경감대상=True)
    for k in ("재산세 본세", "적용세율", "도시지역분", "지방교육세", "총납부세액"):
        assert a[k] == b[k]
    assert K not in a and K not in b
    assert any(m["표기"] == "지방세법 §111의2④" for m in b["미적용 조문"])
    assert any("판정불가" in m["사유"] for m in b["미적용 조문"] if m["표기"] == "지방세법 §111의2④")


def test_property_tax_picks_larger_relief():
    전세 = {"전세사기피해자": True, "전세사기피해주택": True}
    r = 재산세_주택(300_000_000, 2026, 일세대일주택=True, 지방세특례_감면유형="전세사기피해자", 지방세특례_사실=dict(전세, 전용면적=59))
    assert r["재산세 본세"] == 163_500 and r[K]["특례세율_배제"] is True and r[K]["지특법경감후_세액"] == 81_750
    assert any(m["표기"] == "지방세법 §111의2①" and "제4항" in m["사유"] for m in r["미적용 조문"])
    r = 재산세_주택(300_000_000, 2026, 일세대일주택=True, 지방세특례_감면유형="전세사기피해자", 지방세특례_사실=dict(전세, 전용면적=84))
    assert r["재산세 본세"] == 99_000 and r[K]["특례세율_배제"] is False
    # 어느 쪽을 고르든 고른 세액은 두 후보 중 작은 쪽이다
    for 가액 in (60_000_000, 150_000_000, 300_000_000, 600_000_000, 900_000_000):
        for 면적 in (59, 84):
            j = 재산세_주택(가액, 2026, 일세대일주택=True, 지방세특례_감면유형="전세사기피해자", 지방세특례_사실=dict(전세, 전용면적=면적))[K]
            assert min(j["특례세율_세액"], j["지특법경감후_세액"]) == (j["지특법경감후_세액"] if j["특례세율_배제"] else j["특례세율_세액"])


# ------------------------------------------------------------------ 2. 주택임대소득
def _임대(연도=2026, **f):
    return 실행(f, 연도, 세목="종합소득세").값("주택임대소득_비과세_b", None)


@pytest.mark.parametrize("연도", [2015, 2022, 2023, 2026])
@pytest.mark.parametrize("시가, 고가", [(500_000_000, None), (1_000_000_000, None), (1_500_000_000, None), (None, True), (None, False)])
def test_rental_direct_value_wins_over_mixed_use_scope(연도, 시가, 고가):
    f = {"주택수": 1}
    if 시가 is not None:
        f["임대주택_기준시가"] = 시가
    if 고가 is not None:
        f["고가주택"] = 고가
    assert _임대(연도, **f) == _임대(연도, 주택부분면적=120, 사업용건물면적=80, 건물전체_기준시가=2_000_000_000, 주택부분_기준시가=100_000_000, **f)


def test_rental_mixed_use_scope():
    g = dict(주택수=1, 건물전체_기준시가=1_500_000_000, 주택부분_기준시가=900_000_000)
    assert _임대(주택부분면적=120, 사업용건물면적=80, **g)["비과세"] is False
    assert _임대(주택부분면적=80, 사업용건물면적=120, **g)["비과세"] is True
    assert _임대(주택부분면적=80, 사업용건물면적=120, 주택수=1, 건물전체_기준시가=1_500_000_000) is None       # 판정불가
    assert _임대(2008, 주택부분면적=120, 사업용건물면적=80, **g) is None                                    # ④항 신설(2010.2.18.) 전은 잇지 않는다


# ------------------------------------------------------------------ 3·4. 양도세 경로
_양도 = dict(양도가액=800_000_000, 취득가액=500_000_000, 필요경비=0, 연도=2026, 보유연수=1, 양도일="2026-06-01")


@pytest.mark.parametrize("사유", [None, "수용", "해외이주2년", "부득이1년거주"])
@pytest.mark.parametrize("종류", ["주택", "토지", "조합원입주권"])
def test_transfer_without_remainder_facts_is_unchanged(사유, 종류):
    f = {"1세대1주택": True, "자산종류": 종류}
    if 사유:
        f["요건배제사유"] = 사유
    r = 양도세_부동산(**_양도, **f)
    기대 = 종류 != "토지" and 사유 in ("수용", "부득이1년거주") or (종류 == "주택" and 사유 == "해외이주2년")
    assert bool(r["비과세"]) is bool(기대)


def test_expropriation_remainder_deadline():
    f = {"1세대1주택": True, "요건배제사유": "수용"}
    assert 양도세_부동산(**_양도, 주택수용일="2022-01-10", **f)["비과세"]
    r = 양도세_부동산(**_양도, 주택수용일="2020-01-10", **f)
    assert not r["비과세"] and "§154①2호 후단" in r["값 출처"]
    assert 양도세_부동산(**_양도, 자산종류="토지", 수용잔존_부수토지=True, 고가주택=False, 주택수용일="2022-01-10", **f)["비과세"]
    assert not 양도세_부동산(**_양도, 자산종류="토지", 수용잔존_부수토지=True, 고가주택=False, 주택수용일="2020-01-10", **f)["비과세"]
    assert not 양도세_부동산(**_양도, 자산종류="토지", 수용잔존_부수토지=True, 주택수용일="2022-01-10", **f)["비과세"]    # 고가 여부 없음 — 판정불가


def test_temporary_two_homes_timing_from_article_98():
    t = dict(prev_acquired="2018-01-01", prev_sale_date="2026-06-01")
    kw = dict(_양도, 보유연수=5)
    직접 = 양도세_부동산(**kw, 일시적2주택=dict(t, new_acquired="2023-08-01"))
    사실 = 양도세_부동산(**kw, 일시적2주택=t, 신규주택_시기사실={"대금청산일": "2023-08-01"})
    assert 직접["비과세"] and 사실["비과세"] and "§98 신규주택 취득시기" in 사실["값 출처"]
    assert 양도세_부동산(**kw, 일시적2주택=dict(t, new_acquired="2023-08-01"), 신규주택_시기사실={"대금청산일": "2020-01-01"})["비과세"]   # 값을 주면 그 값
    assert not 양도세_부동산(**kw, 일시적2주택=t, 신규주택_시기사실={"대금청산일": "2023-07-20", "등기접수일": "2023-05-20"})["비과세"]
    r = 양도세_부동산(**kw, 일시적2주택=t, 신규주택_시기사실={"시기원인": "매매"})
    assert not r["비과세"] and any("판정 불가" in m["사유"] for m in r["미적용 조문"])


# ------------------------------------------------------------------ 5. 주택 수
A = {"라벨": "A", "기준시가": 900_000_000, "양도대상": True}
B = {"라벨": "B", "기준시가": 800_000_000}
C = {"라벨": "C", "기준시가": 700_000_000}
P = {"라벨": "P", "종류": "분양권", "기준시가": 500_000_000, "취득일": "2023-03-01"}


@pytest.mark.parametrize("유형, 지위, 내것", [
    ("3자간등기명의신탁", "수탁자", False), ("3자간등기명의신탁", "신탁자", True), ("2자간등기명의신탁", "수탁자", False),
    ("계약명의신탁", "수탁자", True), ("계약명의신탁", "신탁자", False)])
def test_trust_attribution_reaches_every_counter(유형, 지위, 내것):
    목록 = [A, B, dict(C, 명의신탁유형=유형, 명의신탁_지위=지위)]
    n = 3 if 내것 else 2
    assert 비과세판정_주택수(목록)["비과세판정_주택수"] == n
    assert 중과판정_주택수(목록)["중과판정_주택수"] == n
    assert tax_judgment.count_transfer_homes(목록)["비과세판정_주택수"] == n
    assert tax_judgment.count_heavy_homes(목록)["중과판정_주택수"] == n
    assert 중과세율_판정(A, 목록, "2026-08-01", True)["가산_주택수"] == n


@pytest.mark.parametrize("법률, 대상, 분양권", [("주택법", "주택", True), ("건축물의 분양에 관한 법률", "주택", True), ("건축물의 분양에 관한 법률", "오피스텔", False), ("관광진흥법", "주택", False)])
def test_presale_right_scope_reaches_every_counter(법률, 대상, 분양권):
    목록 = [A, dict(P, 지위_근거법률=법률, 공급대상=대상)]
    n = 2 if 분양권 else 1
    assert 비과세판정_주택수(목록)["비과세판정_주택수"] == n
    assert 중과판정_주택수(목록)["중과판정_주택수"] == n
    assert tax_judgment.count_transfer_homes(목록)["비과세판정_주택수"] == n
    assert tax_judgment.count_heavy_homes(목록)["중과판정_주택수"] == n
    assert (중과세율_판정(A, 목록, "2026-08-01", True)["적용호"] == "법 §104⑦2호") is 분양권


@pytest.mark.parametrize("목록", [[A], [A, B], [A, B, C], [A, P], [A, B, P], [A, {"라벨": "H", "공동상속_소수지분": True}], [A, {"라벨": "I", "상속특례주택": True}]],
                         ids=["A", "AB", "ABC", "AP", "ABP", "A+소수지분", "A+상속특례"])
def test_lists_without_new_keys_count_as_before(목록):
    """새 키가 없는 목록 — 노드 목록 함수와 판정기가 같은 수를 낸다(연결 전과 같은 식)."""
    기대 = sum(1 for it in 목록 if not (it.get("공동상속_소수지분") or it.get("상속특례주택")))
    assert 비과세판정_주택수(목록)["비과세판정_주택수"] == 기대 == tax_judgment.count_transfer_homes(목록)["비과세판정_주택수"]
    assert 중과판정_주택수(목록)["중과판정_주택수"] == len(목록) == tax_judgment.count_heavy_homes(목록)["중과판정_주택수"]


# ------------------------------------------------------------------ 6. judge_transfer_reliefs
@pytest.mark.parametrize("n", [1, 2, 3])
@pytest.mark.parametrize("일자", ["", "2021-01-01", "2026-04-01", "2026-08-01"])
@pytest.mark.parametrize("조정", [True, False])
def test_reliefs_without_holdings_is_unchanged(n, 일자, 조정):
    r = tax_judgment.judge_transfer_reliefs(False, 5, 0, 1_000_000_000, adjusted_at_sale=조정, heavy_home_count=n, sale_date=일자)
    assert "중과판정" not in r
    한시 = 일자 == "2026-04-01"          # 가목 창(2022-05-10~2026-05-09) 안
    assert r["중과여부"] is (조정 and n >= 2 and not 한시)
    if r["중과여부"]:
        assert r["surcharge_rate"] == {(2, False): 0.2, (3, False): 0.3, (2, True): 0.1, (3, True): 0.2}[(n, 일자 == "2021-01-01")]


@pytest.mark.parametrize("목록, n", [([A, B, C], 3), ([A, B], 2), ([A], 1), ([A, B, dict(C, 지방소재=True, 기준시가=200_000_000)], 2)])
@pytest.mark.parametrize("일자", ["2026-04-01", "2026-08-01"])
def test_reliefs_with_holdings_matches_count_path(목록, n, 일자):
    """제외 사유가 없는 목록이면 holdings 경로와 (count_heavy_homes → heavy_home_count) 경로의 결론이 같다."""
    계열 = 2 if n == 2 else 3
    cnt = tax_judgment.count_heavy_homes(목록, 계열)["중과판정_주택수"]
    kw = dict(is_one_household_one_home=False, holding_years=5, residing_years=0, sale_price=1_000_000_000, adjusted_at_sale=True, sale_date=일자)
    a = tax_judgment.judge_transfer_reliefs(heavy_home_count=cnt, **kw)
    b = tax_judgment.judge_transfer_reliefs(holdings=목록, **kw)
    assert (a["중과여부"], a["surcharge_rate"], a["long_term_deduction_rate"]) == (b["중과여부"], b["surcharge_rate"], b["long_term_deduction_rate"])


def test_attached_land_limit_default_is_unchanged():
    r = tax_judgment.calc_attached_land_limit(100, 600)
    assert r["비과세_한도면적_m2"] == 300.0 and "한도기준" not in r
    assert tax_judgment.calc_attached_land_limit(100, 600, demolished_inherited_footprint_m2=60)["비과세_한도면적_m2"] == 180.0


# ------------------------------------------------------------------ 7. 모듈 로드 (findings 112)
def test_wiring_does_not_depend_on_import_state():
    """tax_nodes.yangdo 만 올린 새 프로세스에서도 이름으로 읽는 연결 노드(비과세판정_주택수_b 등)가 닿는다."""
    code = ("import sys, json\n"
            "from tax_nodes.yangdo import 양도세_부동산\n"
            "r = 양도세_부동산(800000000, 500000000, 0, 2026, 5, 양도일='2026-06-01', 보유주택목록_b=[{'이름': 'A', '구분': '일반'}])\n"
            "print(json.dumps([bool(r['비과세']), 'tax_nodes.yangdo_gita_b' in sys.modules]))\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout
    assert json.loads(out.strip().splitlines()[-1]) == [True, True]
