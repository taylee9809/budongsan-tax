# -*- coding: utf-8 -*-
"""생성 서버(tax_server.py) 도구의 고친 판 — 같은 이름으로 대체한다.

tax_server.py 는 비공개 생성기(server.py → scripts/extract_tax_server.py)가 만드는 파일이라 이 저장소에서 손으로 고치지
않는다. 2026-11-18 에 원본을 고쳐 다시 생성하면서 결함 95·97·98(종부세 공제 0원, 법인 취득세)과 래퍼가 떨어뜨리던 판정기
인자 31개(findings 120)는 생성 파일 쪽에서 해소됐다. 2026-11-19 에는 남아 있던 대체 9개(인자 33개)도 원본 래퍼에 넣고 다시 생성했다. 지금 대체 도구는 없다.
대체가 필요해지는 때: 공개 저장소의 판정기·조문 노드에 새 인자가 생겼는데 생성 래퍼가 아직 넘기지 못할 때. 그때는 같은
이름의 고친 판을 여기에 두고 OVERRIDES 에 등록한다. 계산은 새로 짜지 않는다 — 판정기·노드를 그대로 부른다.

대체 목록은 OVERRIDES 한 곳이다. 호스팅 서버(tax_http.make_server), stdio 진입점(tax_full), 케이스 실행기
(scripts/verify_tool_cases.py)가 이 표를 읽는다. 대체 도구의 인자가 원래 도구 인자의 상위집합인지는
tests/test_tax_overrides.py 가 지킨다 — 생성기가 인자를 바꾸면 깨진다.
"""
from __future__ import annotations

import types

import tax_judgment as _tj
import tax_params
import tax_server as _ts

#: 원래 도구와 기본값이 달라진 인자. 그 밖의 기존 인자는 이름·순서·기본값이 원래 도구와 같아야 한다(테스트가 대조).
CHANGED_DEFAULTS: dict = {}


def _거부(사유: str, 근거: str, **더) -> dict:
    """계산하지 않았다는 결과. 금액 키를 넣지 않는다 — 금액처럼 읽힐 값이 없어야 한다."""
    return dict({"계산불가": True, "사유": 사유, "근거": 근거}, **더)


# ──────────────────────────────────────────────── 종합부동산세·취득세 (원본에서 고침)
# calc_jongbu_tax(공제 0원·법인 거부, findings 95)와 calc_acquisition_tax(§13의2는 주택 유상취득만·가산세율 경고,
# findings 97·98)는 2026-11-18 생성기 원본(server.py)에서 고쳐 tax_server.py 를 다시 만들었다. 여기서 대체하지 않는다.
# 이름은 남겨 둔다 — 이 모듈을 통해 부르던 코드와 테스트가 같은 함수를 받는다.
calc_jongbu_tax = _ts.calc_jongbu_tax
calc_acquisition_tax = _ts.calc_acquisition_tax


# ───────────────────────────────────────────────── 원본에 되돌려 반영한 도구 (2026-11-19)
# 아래 9개 도구는 대체 도구로 인자 33개를 메우고 있었다. 2026-11-19 생성기 원본(server.py) 래퍼에 같은 인자를 넣고
# tax_server.py 를 다시 만들어, 생성 도구가 곧 고친 판이다. 여기서 대체하지 않는다. 이름은 남겨 둔다 — 이 모듈을 통해
# 부르던 코드와 테스트가 같은 함수를 받는다.
judge_transfer_reliefs = _ts.judge_transfer_reliefs
count_heavy_homes = _ts.count_heavy_homes
judge_temporary_two_homes = _ts.judge_temporary_two_homes
judge_155_special = _ts.judge_155_special
judge_156_3_from_portfolio = _ts.judge_156_3_from_portfolio
calc_attached_land_limit = _ts.calc_attached_land_limit
judge_acquisition_homes_and_rate = _ts.judge_acquisition_homes_and_rate
calc_property_tax = _ts.calc_property_tax
estimate_reconstruction_levy = _ts.estimate_reconstruction_levy


#: 원본에 되돌려 반영해 대체를 걷어낸 도구 이름.
UPSTREAMED = ("judge_transfer_reliefs", "count_heavy_homes", "judge_temporary_two_homes", "judge_155_special", "judge_156_3_from_portfolio", "calc_attached_land_limit", "judge_acquisition_homes_and_rate", "calc_property_tax", "estimate_reconstruction_levy")

#: 대체 도구 — 이름 → 고친 판 함수. 이름은 생성 서버 도구 이름과 같아야 한다. 지금은 비어 있다:
#: 공개판 판정기·노드가 생성 래퍼보다 앞서 나가 넘기지 못하는 인자가 다시 생기면 여기에 더한다(scripts/wrapper_gaps.py 가 잡는다).
OVERRIDES: dict = {}


def replace_tools(source_tools: list, descriptions: dict | None = None) -> list:
    """생성 서버 도구 목록에서 OVERRIDES 에 있는 이름을 고친 판으로 바꾼 목록(순서 유지).

    제목·annotations 는 원래 도구 것을 물려받고, 설명은 descriptions[name](없으면 원래 도구의 설명)을 쓴다.
    목록에 없는 이름은 더하지 않는다 — 도구 수는 그대로다.
    """
    from mcp.server.fastmcp.tools import Tool
    out = []
    for t in source_tools:
        fn = OVERRIDES.get(t.name)
        out.append(t if fn is None else Tool.from_function(
            fn, name=t.name, title=t.title, annotations=t.annotations,
            description=(descriptions or {}).get(t.name) or t.description))
    return out
