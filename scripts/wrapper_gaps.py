# -*- coding: utf-8 -*-
"""도구 래퍼 전수 조사 — 생성 서버(tax_server.py)의 도구가 판정기·조문 노드에 넘기지 못하는 입력을 표로 낸다.

무엇을 대조하나
  1. 시그니처: 도구가 본문에서 부르는 판정기 함수(tax_judgment.<이름>)의 인자 가운데 생성 래퍼에 없는 것(빠진 인자).
     tax_overrides.OVERRIDES 의 대체 도구가 그 인자를 받으면 '대체로 메움', 아니면 '남은 인자'다.
     판정기가 **kw 로 다른 판정기에 넘기는 경우(_FORWARDS)는 그 판정기의 인자로 대조한다.
  2. 조문 노드 입력: 판정기를 부르지 않고 스스로 계산하는 calc_* 도구는 시그니처로 대조할 상대가 없다.
     대응하는 노드 합성 함수와, 대체 도구가 넘기게 한 노드 입력을 _NODE_INPUTS 에 손으로 적는다.
  3. 목록 원소의 키: 판정기(와 판정기가 부르는 tax_nodes 함수)가 목록 원소에서 .get("키")로 읽는 입력은 도구로 닿는다.
     그 키가 호스팅 설명(hosted_descriptions.py, 없으면 생성 docstring)에 적혀 있는지만 본다 — 설명에 없으면 모델이 모른다.

산출물: docs/WRAPPER_GAPS.md (전수 조사 표 + 원본 server.py 래퍼에 되돌릴 인자 목록).
대체한 인자마다 뜻과 근거 조문을 _NOTES 에 적어야 한다 — 없으면 이 스크립트가 멈춘다.

실행: python scripts/wrapper_gaps.py          문서를 다시 쓴다
      python scripts/wrapper_gaps.py --check  문서가 낡았으면 종료코드 1 (쓰지 않는다)
tests/test_tax_overrides.py 가 audit()·render() 를 불러 '남은 인자 0'과 문서 최신 여부를 지킨다.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DOC = ROOT / "docs" / "WRAPPER_GAPS.md"

#: 판정기가 **kw 로 넘기는 곳 — 도구 → (실제로 인자를 받는 판정기, 목록에서 읽어 넘기지 않아도 되는 앞쪽 인자 수)
_FORWARDS = {"judge_156_3_from_portfolio": ("judge_156_3_special", 3)}

_NOT_ROUTED = ("노드 합성은 자유 형식 사실(**사실·**덮어쓰기)을 받아 시그니처로 대조할 수 없다. 도구는 상수표로 스스로 계산하고 노드를 부르지 않는다 — "
               "노드 입력을 넘기려면 인자 추가가 아니라 계산 경로를 바꿔야 해서 대체하지 않았다(조사 범위 밖으로 남김)")

#: 스스로 계산하는 도구의 노드 쪽 상대 — 도구 → (노드 합성 함수, 대체 도구가 넘기는 노드 입력 {도구 인자: 노드 사실}, 메모)
_NODE_INPUTS = {
    "calc_property_tax": ("tax_nodes.jaesan.재산세_주택",
                          {"jiteuk_relief_type": "지방세특례_감면유형", "jiteuk_relief_facts": "지방세특례_사실"},
                          "금액 키는 생성 도구와 같다(격자 대조). 감면유형을 줄 때만 노드 합성의 결과를 돌려준다"),
    "calc_acquisition_tax": ("tax_nodes.chwideuk.취득세_부동산", {}, _NOT_ROUTED),
    "calc_jongbu_tax": ("tax_nodes.jongbu.종부세_주택", {}, _NOT_ROUTED),
    "calc_transfer_tax": ("tax_nodes.yangdo.양도세_부동산", {}, _NOT_ROUTED),
    "calc_gift_tax": ("tax_nodes.sangjeung (증여세 노드)", {}, _NOT_ROUTED),
    "calc_inheritance_tax": ("tax_nodes.sangjeung (상속세 노드)", {}, _NOT_ROUTED),
}

#: 판정기가 아니라 조문 노드에 넘기는 대체 도구 인자(count_heavy_homes — 주택 목록으로 중과세율_판정을 부른다)
_NODE_ONLY = {"count_heavy_homes": "tax_nodes.yangdo_jungkwa_ho.중과세율_판정"}

#: 목록 원소를 가리키는 변수 이름 — 이 이름에 .get("키")를 부른 것만 입력 키로 센다(결과 dict 의 키를 걸러낸다)
_ELEMENT_NAMES = {"it", "h", "row"}

_한시 = "소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용)"
_중과 = "소득세법 §104⑦ · 시행령 §167의3①·§167의10①"
#: (도구, 인자) → (판정기·노드 쪽 뜻, 근거 조문). 대체로 메운 인자는 빠짐없이 적는다.
_NOTES = {
    ("judge_temporary_two_homes", "adjusted_area_notice_date"): (
        "조정대상지역 공고일. 그날 이전에 신규 주택(권리 포함)을 취득했거나 계약·계약금 지급이면 1호(2년)에서 빠져 3년",
        "소득세법 시행령 §155①1호 대괄호(대통령령 제36737호, 2026-09-30) — findings 173"),
    ("judge_acquisition_homes_and_rate", "prev_home_in_adjusted_area"): (
        "종전 주택등의 조정대상지역 여부. 신규(in_adjusted_area)와 모두 조정대상지역이면 처분기한 2년, 모르면(None) 2~3년 사이 처분은 보류",
        "지방세법 시행령 §28의5①(대통령령 제36736호, 2026-09-30)·부칙 §2① — findings 170"),
    ("judge_acquisition_homes_and_rate", "new_contract_date"): (
        "신규 주택 매매계약일. 계약금 지급일과 함께 2026-08-26 이전이면 종전 규정(3년)", "대통령령 제36736호 부칙 §2② — findings 170"),
    ("judge_acquisition_homes_and_rate", "new_deposit_paid_date"): (
        "신규 주택 계약금 지급일(위와 한 쌍)", "대통령령 제36736호 부칙 §2② — findings 170"),
    ("judge_155_special", "homes_at_sale"): (
        "양도일 현재 세대 주택 수. 1+1 요건(합가 당시 기준)을 바꾸지 않고 안내 플래그·'주택수_판정기준'만 낸다",
        "소득세법 시행령 §155④·⑤ · 법규과-1599(2024.6.25.)"),
    ("judge_156_3_from_portfolio", "bunyang_already_completed"): (
        "양도 당시 분양권이 이미 완공돼 주택이 된 경우 — ③항 2호 기한 확인 플래그", "소득세법 시행령 §156의3③2호"),
    ("judge_156_3_from_portfolio", "other_homes"): (
        "종전주택·분양권 외 주택 수를 직접 지정(목록에서 센 수를 덮어쓴다). 판정기 기본은 목록 산정이라 도구 기본값은 None",
        "소득세법 시행령 §156의3②(1주택과 1분양권 전제)"),
    ("judge_156_3_from_portfolio", "excluded_homes"): (
        "그중 주택 수 제외 특례로 빠지는 수를 직접 지정(위와 한 쌍)", "소득세법 시행령 §156의3② · 조세특례제한법 §99의4 등"),
    ("calc_attached_land_limit", "demolished_inherited_footprint_m2"): (
        "멸실된 상속주택의 정착면적. 주면 한도 = 멸실 전 정착면적 × 배율(노드 소득세법시행령-155-2-멸실신축-b)",
        "소득세법 시행령 §155②·§154⑦ · 서면4팀-2283(2005.11.23.) — findings 113"),
    ("calc_attached_land_limit", "sale_date"): (
        "양도일. 멸실 신축 경로에서 2022-01-01 전 양도분은 수도권 도시지역도 5배", "소득세법 시행령 §154⑦(2020.2.11. 개정 부칙 §39) — findings 113"),
    ("estimate_reconstruction_levy", "development_cost_items"): (
        "개발비용을 항목(공사비·설계감리비·부대비용·그밖의경비·세금공과금·기부채납가액 등)으로 주면 노드가 산정해 development_cost 로 쓴다(development_cost 가 0일 때만)",
        "재건축초과이익 환수에 관한 법률 §11①·시행령 §9 (노드 tax_nodes/jaegeonchuk_gaebalbiyong.py)"),
    ("calc_property_tax", "jiteuk_relief_type"): (
        "지방세특례제한법 재산세 경감 유형(노드 사실 '지방세특례_감면유형'). 특례세율과 견주어 경감 효과가 큰 쪽 하나를 고른다",
        "지방세법 §111의2④ — findings 113"),
    ("calc_property_tax", "jiteuk_relief_facts"): (
        "그 경감 규정의 요건 사실(노드 사실 '지방세특례_사실')", "지방세법 §111의2④ · 지방세특례제한법 §35②·§36의4② 등 — findings 113"),
    ("judge_transfer_reliefs", "land_permit_target"): ("토지거래허가 대상 주택인지(None=모름 → 종전 판정)", _한시 + " — findings 88"),
    ("judge_transfer_reliefs", "land_permit_applied_date"): ("토지거래허가 신청일(2026-05-09까지 신청이 요건)", _한시),
    ("judge_transfer_reliefs", "land_permit_granted"): ("허가를 받았는지", _한시),
    ("judge_transfer_reliefs", "six_month_region"): ("나목 4)의 표 지역(계약 후 6개월·2026-11-09) 여부", _한시),
    ("judge_transfer_reliefs", "location"): ("소재지 — six_month_region 을 주지 않았을 때 표 지역을 판정한다", _한시),
    ("judge_transfer_reliefs", "holdings"): ("양도일 현재 세대 보유 목록 — 주면 heavy_home_count 대신 목록으로 중과를 판정한다", _중과 + " — findings 113"),
    ("judge_transfer_reliefs", "sale_home"): ("양도 주택(보유 목록의 항목 또는 그 사실)", _중과),
    ("judge_transfer_reliefs", "heavy_facts"): ("세대 단위 사실(혼인일 등)", "소득세법 시행령 §167의3⑨·§167의4⑤"),
    ("count_heavy_homes", "sale_label"): ("양도 주택의 라벨 — 주면 같은 목록으로 그 주택의 중과 대상 여부를 판정해 '양도주택_중과판정'에 싣는다", _중과 + " — findings 88"),
    ("count_heavy_homes", "sale_date"): ("양도일", _중과),
    ("count_heavy_homes", "adjusted_at_sale"): ("양도 당시 조정대상지역 여부(None=대상 주택 여부까지만)", "소득세법 §104⑦"),
    ("count_heavy_homes", "holding_years"): ("양도 주택 보유 연수(한시 배제는 2년 이상 전제)", _한시),
    ("count_heavy_homes", "contract_date"): ("매매계약일", _한시),
    ("count_heavy_homes", "deposit_received"): ("계약금 수령 여부", _한시),
    ("count_heavy_homes", "land_permit_target"): ("토지거래허가 대상 여부", _한시),
    ("count_heavy_homes", "land_permit_applied_date"): ("토지거래허가 신청일", _한시),
    ("count_heavy_homes", "land_permit_granted"): ("허가 여부", _한시),
    ("count_heavy_homes", "six_month_region"): ("나목 4)의 표 지역 여부", _한시),
    ("count_heavy_homes", "location"): ("소재지", _한시),
    ("count_heavy_homes", "household_facts"): ("세대 단위 사실(혼인일·혼인후_신규취득일 등)", "소득세법 시행령 §167의3⑨·§167의4⑤"),
}


# ───────────────────────────────────────────────────────────── 소스 읽기
_FUNCS: dict = {}


def _functions(module: str) -> dict:
    if module not in _FUNCS:
        tree = ast.parse(inspect.getsource(importlib.import_module(module)))
        _FUNCS[module] = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    return _FUNCS[module]


def _closure(module: str, name: str, seen: set) -> None:
    """name 이 부르는 함수들(같은 모듈 안 + 함수 안에서 tax_nodes 에서 들여온 것)을 seen 에 모은다."""
    funcs = _functions(module)
    if (module, name) in seen or name not in funcs:
        return
    seen.add((module, name))
    imported = {}
    for node in ast.walk(funcs[name]):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("tax_nodes"):
            for alias in node.names:
                imported[alias.asname or alias.name] = (node.module, alias.name)
    for node in ast.walk(funcs[name]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in imported:
                _closure(*imported[node.func.id], seen)
            else:
                _closure(module, node.func.id, seen)


def element_keys(judgment_name: str) -> set:
    """판정기와 그것이 부르는 함수가 목록 원소에서 .get("키")로 읽는 키."""
    seen: set = set()
    _closure("tax_judgment", judgment_name, seen)
    keys = set()
    for module, name in seen:
        for node in ast.walk(_functions(module)[name]):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id in _ELEMENT_NAMES
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                keys.add(node.args[0].value)
    return keys


def _called_judgments(fn) -> list:
    """래퍼 본문(독스트링 제외)에서 부르는 _tj.<이름>."""
    body = ast.parse(inspect.getsource(fn)).body[0]
    return sorted({node.func.attr for node in ast.walk(body)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and isinstance(node.func.value, ast.Name) and node.func.value.id == "_tj"})


def _default(param) -> str:
    return "(필수)" if param.default is inspect.Parameter.empty else repr(param.default)


# ───────────────────────────────────────────────────────────── 조사
def audit() -> list:
    """도구마다 한 줄 — 생성 서버 도구 순서."""
    import hosted_descriptions
    import tax_judgment
    import tax_overrides
    import tax_server

    rows = []
    for tool in tax_server.mcp._tool_manager.list_tools():
        name = tool.name
        wrapper = inspect.signature(tool.fn).parameters
        override = tax_overrides.OVERRIDES.get(name)
        over = inspect.signature(override).parameters if override else {}
        desc = hosted_descriptions.DESCRIPTIONS.get(name) or tool.description
        called = _called_judgments(tool.fn)
        row = {"도구": name, "대조대상": "", "빠진_인자": [], "대체": bool(override), "남은_인자": [], "더한_인자": [],
               "목록_인자": [p for p, v in wrapper.items() if "dict" in str(v.annotation)], "설명에_없는_키": [],
               "설명": "호스팅" if name in hosted_descriptions.DESCRIPTIONS else "생성 docstring", "메모": ""}
        if called:
            judged_name = called[0]
            target, skip = _FORWARDS.get(name, (judged_name, 0))
            judged = inspect.signature(getattr(tax_judgment, target)).parameters
            names = [p for p, v in list(judged.items())[skip:] if v.kind is v.POSITIONAL_OR_KEYWORD]
            if any(v.kind is v.VAR_KEYWORD for v in judged.values()):
                raise SystemExit("%s: 판정기 %s 가 **kw 를 받는다 — _FORWARDS 에 넘기는 곳을 적는다" % (name, target))
            row["대조대상"] = "tax_judgment." + judged_name + (" → " + target if target != judged_name else "")
            row["빠진_인자"] = [p for p in names if p not in wrapper]
            row["남은_인자"] = [p for p in row["빠진_인자"] if p not in over]
            row["설명에_없는_키"] = sorted(k for k in element_keys(judged_name) if k not in desc) if row["목록_인자"] else []
        elif name in _NODE_INPUTS:
            composite, mapped, memo = _NODE_INPUTS[name]
            row["대조대상"] = "스스로 계산 — 노드 쪽 상대 " + composite
            row["빠진_인자"] = [p for p in mapped]
            row["남은_인자"] = [p for p in mapped if p not in over]
            row["메모"] = memo
        else:
            row["대조대상"] = "판정기 없음(조회·카탈로그·서식)"
        row["더한_인자"] = [p for p in over if p not in wrapper]
        if name in _NODE_ONLY:
            row["메모"] = "더한 인자는 판정기가 아니라 %s 에 넘긴다(판정기 시그니처에는 없다)" % _NODE_ONLY[name]
        for p in row["더한_인자"]:
            if (name, p) not in _NOTES:
                raise SystemExit("%s.%s: 대체로 더한 인자의 뜻·근거가 _NOTES 에 없다" % (name, p))
            if p not in desc:
                raise SystemExit("%s.%s: 대체로 더한 인자가 호스팅 설명에 없다" % (name, p))
        rows.append(row)
    return rows


def _cell(items) -> str:
    return " · ".join("`%s`" % x for x in items) if items else "—"


def render(rows: list) -> str:
    import tax_overrides
    gap = [r for r in rows if r["빠진_인자"]]
    added = [r for r in rows if r["더한_인자"]]
    out = [
        "# 도구 래퍼가 넘기지 못하는 입력 (WRAPPER_GAPS)",
        "",
        "`python scripts/wrapper_gaps.py` 가 만든다 — 손으로 고치지 않는다. 판정기(`tax_judgment.py`)나 대체 도구(`tax_overrides.py`)의",
        "인자가 바뀌면 다시 만든다(`tests/test_tax_overrides.py` 가 낡은 문서를 잡는다).",
        "",
        "`tax_server.py` 는 비공개 원본(`server.py`)에서 생성기가 만드는 파일이라 이 저장소에서 고치지 않는다. 그 안의 도구 래퍼가",
        "판정기·조문 노드보다 뒤처진 곳은 `tax_overrides.OVERRIDES` 의 같은 이름 도구가 메운다(호스팅 서버와 `budongsan-tax-full`).",
        "이 문서의 2절이 **원본 래퍼에 되돌려 넣을 인자 목록**이다 — 원본을 고쳐 다시 생성하면 그 도구의 대체를 걷어낸다.",
        "",
        "요약: 도구 %d개 가운데 빠진 입력이 있는 도구 %d개(인자 %d개), 대체 도구 %d개가 더한 인자 %d개, 남은 인자 %d개." % (
            len(rows), len(gap), sum(len(r["빠진_인자"]) for r in gap), len(tax_overrides.OVERRIDES),
            sum(len(r["더한_인자"]) for r in added), sum(len(r["남은_인자"]) for r in rows)),
        "",
        "## 1. 전수 조사",
        "",
        "- **빠진 인자**: 판정기(또는 노드) 쪽에 있는데 생성 래퍼 시그니처에 없는 것.",
        "- **남은 인자**: 대체 도구도 받지 못하는 것(0이어야 한다).",
        "- **설명에 없는 키**: 판정기가 목록 원소에서 읽는 키(도구로는 닿는다) 가운데 도구 설명에 나오지 않는 것.",
        "",
        "| 도구 | 대조 대상 | 빠진 인자 | 대체 | 남은 인자 | 목록 인자 | 설명에 없는 키 | 설명 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append("| `%s` | %s | %s | %s | %s | %s | %s | %s |" % (
            r["도구"], r["대조대상"], _cell(r["빠진_인자"]), "대체" if r["대체"] else "—", _cell(r["남은_인자"]),
            _cell(r["목록_인자"]), _cell(r["설명에_없는_키"]), r["설명"]))
    memo = [r for r in rows if r["메모"]]
    if memo:
        out += ["", "메모", ""] + ["- `%s`: %s" % (r["도구"], r["메모"]) for r in memo]
    out += [
        "",
        "## 2. 원본 server.py 래퍼에 추가해야 할 인자",
        "",
        "기존 인자(이름·순서·기본값)는 그대로 두고 아래 인자를 뒤에 선택 인자로 더한 뒤 판정기에 키워드로 넘긴다.",
        "원본의 판정기가 이 저장소의 `tax_judgment.py` 보다 옛 판이면 판정기부터 동기화해야 한다.",
        "",
        "| 도구 | 인자 | 기본값 | 판정기·노드 쪽 뜻 | 근거 |",
        "|---|---|---|---|---|",
    ]
    for r in added:
        params = inspect.signature(tax_overrides.OVERRIDES[r["도구"]]).parameters
        for p in r["더한_인자"]:
            meaning, basis = _NOTES[(r["도구"], p)]
            out.append("| `%s` | `%s` | `%s` | %s | %s |" % (r["도구"], p, _default(params[p]), meaning, basis))
    out += [
        "",
        "인자만 더해서는 안 되는 것",
        "",
        "- `count_heavy_homes`: 더한 인자는 판정기 인자가 아니다. 래퍼가 `sale_label` 이 있을 때 `tax_nodes.yangdo_jungkwa_ho.중과세율_판정` 을",
        "  부르는 본문(`tax_overrides.count_heavy_homes`)까지 원본에 옮겨야 한다.",
        "- `calc_property_tax`: `jiteuk_relief_type` 을 주면 `tax_nodes.jaesan.재산세_주택` 의 결과를 돌려주고, 직접 지정 인자와 함께 주면 계산하지 않는다",
        "  (`tax_overrides.calc_property_tax` 본문).",
        "- `judge_156_3_from_portfolio`: `other_homes`·`excluded_homes` 는 None 이 아닐 때만 넘긴다(판정기가 목록에서 센 수를 덮어쓰므로).",
        "- 설명: 새 인자의 뜻은 `hosted_descriptions.py` 에 있다. 원본 docstring 에도 옮긴다. `judge_jongbu_one_home_status`·`count_transfer_homes` 는",
        "  인자는 그대로지만 목록 원소의 키(조정대상지역 2년 판정용 키, 명의신탁·분양권 범위·상속 지분 내역)가 생성 docstring 에 없다.",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    rows = audit()
    text = render(rows)
    if "--check" in sys.argv:
        stale = not DOC.exists() or DOC.read_text(encoding="utf-8") != text
        print("docs/WRAPPER_GAPS.md %s" % ("낡았다 — python scripts/wrapper_gaps.py" if stale else "최신"))
        return 1 if stale else 0
    DOC.write_text(text, encoding="utf-8")
    print("[래퍼 틈] 도구 %d개 — 빠진 인자 %d · 대체로 더한 인자 %d · 남은 인자 %d · 설명에 없는 키 %d → %s" % (
        len(rows), sum(len(r["빠진_인자"]) for r in rows), sum(len(r["더한_인자"]) for r in rows),
        sum(len(r["남은_인자"]) for r in rows), sum(len(r["설명에_없는_키"]) for r in rows), DOC.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
