"""검증 정본(data/verification/cases.jsonl)을 엔진에 돌리는 회귀 테스트.

케이스를 도구에 연결하는 규칙은 scripts/verify_tool_cases.py 한 곳에 둔다(대체 도구 → 판정기 → 생성 래퍼 →
호스팅 전용 모듈). 여기서 따로 디스패치하면 새 도구가 생길 때마다 두 벌이 어긋난다.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_tool_cases  # noqa: E402

# 공개 저장소에 없는 도구 — 돌릴 수 없다.
NOT_RUNNABLE = {
    "judge_ltv_limit": "대출 규제 도구 — 공개판 범위 밖(CONTRIBUTING '하지 않는 것')",
}


def test_cases_match_engine():
    total, bad, missing, gray = verify_tool_cases.run()
    assert total > 0
    assert not bad, "불일치 %d건: %s" % (len(bad), [b["case_id"] for b in bad])


def test_only_known_tools_missing():
    tools = verify_tool_cases._tools()
    import json
    missing = set()
    for line in verify_tool_cases.CASES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            c = json.loads(line)
            if c.get("활성", 1) and c["tool"] not in tools:
                missing.add(c["tool"])
    assert missing <= set(NOT_RUNNABLE), f"케이스에 연결할 도구가 없다: {missing - set(NOT_RUNNABLE)}"
