"""분업 6차 '남은 것' 묶음 (2026-11-18) — 앞선 분업들이 '옮기지 못했다·잇지 못했다'로 남긴 항목의 회귀.

케이스 원본은 data/verification/node_cases/leftovers6.jsonl (L6-<항목>-NN). 여기서는 그 파일 전체와, 연결 전 호출이 그대로인지를 본다.
"""
import importlib
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tax_nodes.engine import 실행  # noqa: E402
from tax_nodes.jongbu import 종부세_주택  # noqa: E402

verify_node_cases = importlib.import_module("verify_node_cases")
_CASES = [json.loads(l) for l in (ROOT / "data" / "verification" / "node_cases" / "leftovers6.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.mark.parametrize("case", _CASES, ids=[c["case_id"] for c in _CASES])
def test_l6_case(case):
    ok, detail = verify_node_cases.run_case(case)
    assert ok, detail


# ------------------------------------------------------------------ 1. 종부세 시행령 §4의3③ 세율 적용 주택 수
@pytest.mark.parametrize("주택수", [None, 1, 2, 3])
def test_jongbu_home_count_given_value_unchanged(주택수):
    """주택수를 직접 주던(또는 안 주던) 호출은 그대로 — 영 §4의3③ 노드는 돌지 않는다."""
    kw = {} if 주택수 is None else {"주택수": 주택수}
    r = 종부세_주택(3_000_000_000, 2026, 직전연도_합산공시가격=2_800_000_000, **kw)
    assert r["적용세율"] == (0.02 if (주택수 or 1) >= 3 else 0.013)
    assert "세율 적용 주택 수(영 §4의3③)" not in r
    assert not [x for x in r["근거표"] if x["노드"] == "종부세법시행령-4의3-3"]


def test_jongbu_home_count_does_not_touch_property_tax_credit():
    """영 §4의3① 재산세액 공제 산식에는 주택 수가 들어가지 않는다 — 같은 과세표준이면 공제액이 같다."""
    목록 = [{"이름": "A"}, {"이름": "B"}, {"이름": "C"}]
    a = 종부세_주택(3_000_000_000, 2026, 직전연도_합산공시가격=2_800_000_000, 세율적용_주택목록=목록)
    b = 종부세_주택(3_000_000_000, 2026, 직전연도_합산공시가격=2_800_000_000, 세율적용_주택목록=목록[:2])
    assert (a["세율 적용 주택 수(영 §4의3③)"]["주택수"], b["세율 적용 주택 수(영 §4의3③)"]["주택수"]) == (3, 2)
    assert a["과세표준"] == b["과세표준"] and a["재산세액 공제"] == b["재산세액 공제"] > 0
    assert a["산출세액"] > b["산출세액"]


def test_jongbu_home_count_corporate_rate():
    """법 §9②3호 법인 비례세율(2.7%·5%)도 같은 주택 수를 읽는다."""
    목록 = [{"이름": "A"}, {"이름": "B"}, {"이름": "C"}]
    assert 종부세_주택(3_000_000_000, 2026, 법인=True, 세율적용_주택목록=목록)["적용세율"] == 0.05
    assert 종부세_주택(3_000_000_000, 2026, 법인=True, 세율적용_주택목록=목록[:2])["적용세율"] == 0.027


# ------------------------------------------------------------------ 2. 지방세법 §111의2④ 비교 범위·감면 후 금액
from tax_nodes.jaesan import 재산세_주택  # noqa: E402

_K4 = "지특법 중복 판정(§111의2④)"


@pytest.mark.parametrize("가액", [50_000_000, 150_000_000, 300_000_000, 600_000_000, 900_000_000])
@pytest.mark.parametrize("유형, 사실", [
    ("빈집정비", {}), ("장기미집행도시계획시설", {"미집행기간_년": 12}),
    ("전세사기피해자", {"전세사기피해자": True, "전세사기피해주택": True, "전용면적": 59}),
    ("전세사기피해자", {"전세사기피해자": True, "전세사기피해주택": True, "전용면적": 84}),
    ("주택연금담보주택", {"1가구1주택": True}),
])
@pytest.mark.parametrize("도시", [None, 0])
def test_property_tax_overlap_picks_smaller_total(가액, 유형, 사실, 도시):
    """고른 쪽의 재산세액(1호 + 도시지역분)이 다른 쪽보다 크지 않고, 결과 금액은 고른 쪽의 금액이다."""
    kw = {} if 도시 is None else {"도시지역분세율": 도시}
    기준 = 재산세_주택(가액, 2026, 일세대일주택=True, **kw)          # 특례세율만 적용한 결과
    r = 재산세_주택(가액, 2026, 일세대일주택=True, 지방세특례_감면유형=유형, 지방세특례_사실=사실, **kw)
    j = r.get(_K4)
    if j is None:           # 지특법 감면 요건 미충족 — 종전 결과 그대로
        assert (r["재산세 본세"], r["총납부세액"]) == (기준["재산세 본세"], 기준["총납부세액"])
        return
    특례쪽 = 기준["재산세 본세"] + 기준["도시지역분"]
    지특쪽 = j["지특법경감후_세액"] + 기준["도시지역분"] - j.get("도시지역분_감면세액", 0)
    if j["특례세율_배제"]:
        assert 지특쪽 < 특례쪽
        assert r["재산세 본세"] == j["지특법경감후_세액"] == j["감면전_재산세_본세"] - j["지특법_감면세액"]
        assert r["도시지역분"] == 기준["도시지역분"] - j.get("도시지역분_감면세액", 0)
        assert r["지방교육세"] == int(r["재산세 본세"] * 0.2)
        assert r["총납부세액"] == r["재산세 본세"] + r["도시지역분"] + r["지방교육세"] < 기준["총납부세액"]
    else:
        assert 특례쪽 <= 지특쪽
        for k in ("재산세 본세", "도시지역분", "지방교육세", "총납부세액", "적용세율"):
            assert r[k] == 기준[k]


def test_property_tax_without_relief_type_unchanged():
    """감면유형을 주지 않는 호출은 그대로 — 판정 키가 없고 금액이 같다."""
    r = 재산세_주택(300_000_000, 2026, 일세대일주택=True)
    assert _K4 not in r and (r["재산세 본세"], r["도시지역분"], r["지방교육세"], r["총납부세액"]) == (99_000, 180_600, 19_800, 299_400)


# ------------------------------------------------------------------ 3. 재산세 감면의 '직접 사용하는 부동산' → 지특법 §2①8호
def test_property_relief_direct_use_not_asked_without_facts():
    """사용주체·직접사용을 주지 않은 재산세 감면 호출은 그대로다(연결 전과 같은 값)."""
    from tax_nodes.jiteuk_chwideuk import 지특법_재산세감면
    for 유형, 감면 in (("노동조합", 850_000), ("지역아동센터", 850_000), ("노인복지시설", 250_000), ("빈집정비", 500_000)):
        r = 지특법_재산세감면(1_000_000, 2026, 유형)
        assert r["감면세액"] == 감면 and not r.get("직접사용_제외")


def test_property_relief_direct_use_reason_recorded():
    from tax_nodes.jiteuk_chwideuk import 지특법_재산세감면
    r = 지특법_재산세감면(1_000_000, 2026, "노동조합", 사용주체="임차인")
    assert r["감면세액"] == 0
    assert any("직접 사용하는 부동산이 아님" in m["사유"] and "소유자의 사용이 아님" in m["사유"] for m in r["미적용 조문"])
    # '직접 사용'을 요건으로 적지 않은 조문(빈집 정비 §75의6③)은 사용주체를 줘도 그대로
    assert 지특법_재산세감면(1_000_000, 2026, "빈집정비", 사용주체="임차인")["감면세액"] == 500_000


# ------------------------------------------------------------------ 4. 주택임대소득 영 §8의2 — ③2호 단서·④ 후단
import itertools  # noqa: E402
from fractions import Fraction  # noqa: E402

import tax_judgment  # noqa: E402


@pytest.mark.parametrize("연도", [2018, 2019, 2020, 2022, 2023, 2026])
def test_rental_home_count_judge_matches_node(연도):
    """판정기 count_rental_homes 와 노드(소득세법시행령-8의2-3-b)가 공동소유 소수지분 단서(가·나목)에서 같은 답을 낸다."""
    for 지분, 수입, 시가 in itertools.product(["1/5", "31/100", "2/5"], [0, 5_999_999, 6_000_000], [800_000_000, 1_000_000_000, 1_300_000_000]):
        판정기 = tax_judgment.count_rental_homes(
            [{"라벨": "공동", "공동소유": True, "지분율": float(Fraction(지분)), "최대지분자": False, "기준시가": 시가, "연임대수입": 수입}], [], 연도)["주택수"]
        노드 = 실행({"임대소득_보유주택목록": [{"이름": "공동", "본인지분": 지분, "타인최대지분": "3/5", "기준시가": 시가, "본인_임대수입_연": 수입}]},
                  연도, 세목="종합소득세").값("임대소득_주택수_b")
        assert 판정기 == 노드, (연도, 지분, 수입, 시가)


def test_rental_home_count_existing_calls_unchanged():
    """2020년 이후·주택ID 없는 호출은 그대로다."""
    소수 = {"라벨": "공동", "공동소유": True, "지분율": 0.2, "최대지분자": False, "기준시가": 500_000_000, "연임대수입": 7_000_000}
    for y in (None, 2020, 2023, 2026):
        assert tax_judgment.count_rental_homes([소수], [], y)["주택수"] == 1
    부부 = {"라벨": "부부공동", "공동소유": True, "지분율": 0.5, "최대지분자": True}
    r = tax_judgment.count_rental_homes([부부], [dict(부부)], 2026)        # 주택ID 없음 — 서로 다른 주택으로 본다(종전)
    assert r["주택수"] == 2 and all("_share" not in x for x in r["항목별"])
    r = tax_judgment.count_rental_homes([dict(부부, 주택ID="H", 지분율=0.3)], [dict(부부, 주택ID="H", 지분율=0.7)], 2026)
    assert (r["주택수"], r["본인"], r["배우자"]) == (1, 0, 1)


def test_rental_mixed_use_single_tenant_same_as_whole_building():
    """임차인이 1명이면 ④ 후단이 아니라 본문 — 건물 전체 면적으로 본 결과와 같다."""
    a = 실행({"주택부분면적": 90, "사업용건물면적": 70}, 2026, 세목="종합소득세").값("임대소득_겸용주택범위_b")
    b = 실행({"임차인별_면적": [{"임차인": "갑", "주택부분면적": 90, "사업용건물면적": 70}]}, 2026, 세목="종합소득세").값("임대소득_겸용주택범위_b")
    assert a == b == {"전부주택": True, "기준시가판정대상": "건물 전체와 그 부수토지(전부 주택)", "주택부수토지비율": 1.0}


# ------------------------------------------------------------------ 5. 영 §156① 일부 양도 환산 · §160① 후단
from tax_nodes.yangdo import 양도세_부동산  # noqa: E402

_양도5 = dict(양도가액=300_000_000, 취득가액=100_000_000, 필요경비=0, 연도=2026, 보유연수=10, 거주연수=10, 양도일="2026-06-01")
_잔존5 = {"1세대1주택": True, "요건배제사유": "수용", "주택수용일": "2022-01-10", "자산종류": "토지", "수용잔존_부수토지": True}


@pytest.mark.parametrize("전체, 고가", [(300, False), (400, False), (401, True), (500, True), (1000, True)])
def test_partial_transfer_high_value_conversion(전체, 고가):
    """환산가액 = 3억 × 전체/100 — 12억 초과면 고가주택(과세비율은 (환산−12억)/환산), 아니면 비과세."""
    r = 양도세_부동산(**_양도5, **_잔존5, 일부양도_양도면적=100, 일부양도_전체면적=전체)
    assert bool(r["비과세"]) is (not 고가)
    if 고가:
        환산 = 300_000_000 * 전체 // 100
        assert r["고가주택 과세비율"] == round((환산 - 1_200_000_000) / 환산, 4) and 0 < r["고가주택 과세비율"] < 1


def test_high_value_flag_without_area_never_negative():
    r = 양도세_부동산(**_양도5, **_잔존5, 고가주택=True)
    assert r["고가주택 과세비율"] is None and r["총납부세액"] > 0
    assert any("§160①" in m["표기"] and "안분을 할 수 없다" in m["사유"] for m in r["미적용 조문"])


@pytest.mark.parametrize("가액, 비율", [(900_000_000, None), (1_500_000_000, 0.2), (2_400_000_000, 0.5)])
def test_whole_home_transfer_unchanged(가액, 비율):
    """전체 양도(면적 사실 없음)는 종전 그대로."""
    r = 양도세_부동산(가액, 가액 // 2, 0, 2026, 10, 10, 양도일="2026-06-01", **{"1세대1주택": True})
    assert r["고가주택 과세비율"] == 비율 and bool(r["비과세"]) is (비율 is None)


# ------------------------------------------------------------------ 6. 주택부수토지 한도 — 법 §89①3호 본문 · 영 §154⑦
_K6 = "부수토지 한도(법 §89①3호·영 §154⑦)"


@pytest.mark.parametrize("도시, 수도권, 구역, 키", [
    (True, True, "주거상업공업", "수도권_주거상업공업"), (True, True, "녹지", "수도권_녹지"),
    (True, False, "주거상업공업", "수도권밖_도시"), (False, False, "주거상업공업", "도시지역밖")])
def test_attached_land_node_matches_judgment_function(도시, 수도권, 구역, 키):
    """조문 노드(영 §154⑦ + 법 §89①3호 본문)와 판정기 calc_attached_land_limit(도구)의 격자 대조."""
    from tax_nodes.yangdo_busutoji import 부수토지_한도
    for 정착, 토지 in itertools.product([40, 100, 133.3], [100, 300, 500, 1500]):
        a = tax_judgment.calc_attached_land_limit(정착, 토지, 도시, 수도권, 구역)
        b = 부수토지_한도(토지, "2026-06-01", 주택_정착면적=정착, 부수토지_용도지역=키)
        assert (a["적용배율"], a["비과세_한도면적_m2"], a["초과면적_m2"], a["전부비과세"]) == (b["배율"], b["한도면적_㎡"], b["초과면적_㎡"], b["전부_주택부수토지"])
    # 상속주택 멸실·신축 — 판정기의 demolished_inherited_footprint_m2 경로와 같은 한도
    a = tax_judgment.calc_attached_land_limit(200, 500, 도시, 수도권, 구역, demolished_inherited_footprint_m2=80, sale_date="2026-06-01")
    b = 부수토지_한도(500, "2026-06-01", 주택_정착면적=200, 상속주택_멸실후신축=True, 멸실주택_정착면적=80, 부수토지_용도지역=키)
    assert (a["비과세_한도면적_m2"], a["초과면적_m2"]) == (b["한도면적_㎡"], b["초과면적_㎡"])


def test_transfer_tax_without_land_area_unchanged():
    """부수토지_면적을 주지 않는 호출은 그대로 — 판정 키가 없다. 한도 이내면 세액도 같다."""
    기본 = dict(양도가액=1_500_000_000, 취득가액=600_000_000, 필요경비=0, 연도=2026, 보유연수=10, 거주연수=10, 양도일="2026-06-01")
    a = 양도세_부동산(**기본, **{"1세대1주택": True})
    assert _K6 not in a
    b = 양도세_부동산(**기본, **{"1세대1주택": True}, 부수토지_면적=250, 주택_정착면적=100, 부수토지_용도지역="수도권_주거상업공업")
    assert b[_K6]["전부_주택부수토지"] and {k: v for k, v in b.items() if k not in (_K6, "적용 조문")} == {k: v for k, v in a.items() if k != "적용 조문"}


def test_attached_land_missing_zone_is_undetermined():
    r = 양도세_부동산(1_000_000_000, 400_000_000, 0, 2026, 10, 10, 양도일="2026-06-01", **{"1세대1주택": True}, 부수토지_면적=500, 주택_정착면적=100)
    assert "판정불가" in r[_K6] and r["총납부세액"] == 0
