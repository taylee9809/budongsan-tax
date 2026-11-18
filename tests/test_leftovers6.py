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
