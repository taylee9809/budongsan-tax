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
