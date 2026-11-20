"""질문 단위 리허설 — docs/QUESTION_CASES.md 의 질문을 로컬 서버에 붙은 모델(또는 사람)에게 풀게 하고 답을 대조한다.

이 스크립트는 답을 만들지 않는다. 하는 일은 넷이다.

  dump   서버(tax_http.py, LAW_OC 없음)를 띄워 `initialize` 의 instructions 와 `tools/list` 를 파일로 떨군다.
         이것이 "처음 붙은 모델이 보는 전부"다. 채점표의 질문 목록도 함께 떨군다.
  serve  서버를 띄운 채로 둔다(답하는 쪽이 도구를 부를 수 있게).
  call   도구 하나를 MCP(HTTP)로 부르고, 인자와 결과를 호출 기록(calls.jsonl)에 덧붙인다.
  check  답변 파일과 호출 기록을 받아 기계적으로 대조한다 — 답에 적힌 조문·세율·금액이 도구 결과에 있는지,
         법인 질문에 개인용 도구를 썼는지, 채점표가 적은 도구를 불렀는지.

리허설 한 벌의 디렉터리 구조(`check --run DIR`):

  DIR/Q1/calls.jsonl   call 이 쌓은 기록(한 줄에 {"tool","arguments","isError","text","turn"})
  DIR/facts.json       (선택) 질문별로 사용자가 준 사실 — {"Q1": "2026년, 공시가격 6억 …"}
  DIR/Q1/turn1.md      사실을 받기 전의 첫 답(되물음이면 되물음 그대로) — 있으면 함께 대조한다
  DIR/Q1/answer.md     채점용 사실을 받은 뒤의 최종 답

check 의 대조는 채점의 보조다. '조문' 칸(도구 결과에 없는 조문 번호)은 기계적으로 가를 수 있지만, 세율·금액은
모델이 합계를 직접 더한 값이나 사용자가 준 값일 수 있어 '확인 필요'로만 낸다. 세목 누락·범위 밖 답변은 사람이 읽는다.

    python scripts/question_rehearsal.py dump --out dist/rehearsal
    python scripts/question_rehearsal.py serve --port 8765
    python scripts/question_rehearsal.py call --url http://127.0.0.1:8765/mcp --log dist/rehearsal/Q1/calls.jsonl \\
        get_tax_scope '{"owner": "법인"}'
    python scripts/question_rehearsal.py check --run dist/rehearsal --surface dist/rehearsal/surface.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_MD = ROOT / "docs/QUESTION_CASES.md"

# ───────────────────────── 채점표 읽기 ─────────────────────────

_Q_HEAD = re.compile(r'^### Q(\d+)\. "(.+?)"(?:\s*—\s*(.*))?$')
_BULLET = re.compile(r"^- \*\*(.+?)\*\*: ?(.*)$")
_SECTION = re.compile(r"^## (.+)$")

#: 법인 명의인데 쓰면 감점인 개인용 도구(채점표 '공통 감점').
PERSONAL_ONLY = ("calc_transfer_tax", "calc_jongbu_tax", "calc_acquisition_tax")


def parse_questions(md_text: str) -> list[dict]:
    """채점표에서 질문과 항목(먼저 물을 것·채점용 사실·불러야 할 도구 …)을 뽑는다."""
    out: list[dict] = []
    section = ""
    cur: dict | None = None
    for line in md_text.splitlines():
        m = _SECTION.match(line)
        if m:
            section, cur = m.group(1).strip(), None
            continue
        m = _Q_HEAD.match(line)
        if m:
            cur = {"id": "Q" + m.group(1), "질문": m.group(2), "메모": m.group(3) or "", "구역": section, "항목": {}}
            out.append(cur)
            continue
        m = _BULLET.match(line)
        if m and cur is not None:
            cur["항목"][m.group(1)] = m.group(2).strip()
    for q in out:
        tools_line = " ".join(v for k, v in q["항목"].items() if k in ("불러야 할 도구", "정답 행동"))
        q["기대_도구"] = sorted(set(re.findall(r"`([a-z_0-9]+)(?:\(|`)", tools_line)))
        q["금지_도구"] = sorted(set(re.findall(r"`([a-z_0-9]+)(?:\(|`)", q["항목"].get("부르면 안 되는 도구", ""))))
        q["법인_질문"] = q["구역"].startswith("법인")
    return out


# ───────────────────────── 조문 인용 뽑기 ─────────────────────────

#: 줄임말 → 정식 이름.
LAW_ALIASES = {
    "종부세법": "종합부동산세법", "농특세법": "농어촌특별세법", "조특법": "조세특례제한법",
    "상증법": "상속세 및 증여세법", "상증세법": "상속세 및 증여세법", "지특법": "지방세특례제한법",
    "상속세및증여세법": "상속세 및 증여세법",
}
_KNOWN_LAWS = (
    "상속세 및 증여세법", "상속세및증여세법", "지방세특례제한법", "조세특례제한법", "종합부동산세법", "농어촌특별세법",
    "부가가치세법", "지방세기본법", "국세기본법", "지방세법", "법인세법", "소득세법", "인지세법", "주택법",
    "수도권정비계획법", "국민건강보험법", "민간임대주택에 관한 특별법", "도시 및 주거환경정비법",
    "재건축초과이익 환수에 관한 법률", "부동산 거래신고 등에 관한 법률",
    "종부세법", "농특세법", "조특법", "상증세법", "상증법", "지특법",
)
_LAW_ALT = "|".join(re.escape(n) for n in sorted(_KNOWN_LAWS, key=len, reverse=True))
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

_TOKEN = re.compile(
    r"(?P<node>(?P<nlaw>(?:%(law)s)(?:시행령|시행규칙)?)-(?P<njo>\d+(?:의\d+)?)(?:-(?P<nhang>\d+))?)"   # 노드 id: 지방세법-13의2-1
    r"|(?P<law>(?:%(law)s)(?:\s?(?:시행령|시행규칙))?)"
    r"|(?P<same>같은\s?법(?:\s?(?:시행령|시행규칙))?|동법(?:\s?(?:시행령|시행규칙))?)"
    r"|(?P<decree>(?<![가-힣])(?:시행령|시행규칙))"
    r"|(?P<bare>(?<![가-힣])법(?=\s?(?:§|제\s?\d+\s?조)))"
    r"|(?P<art>(?:§\s?(?P<jo1>\d+)|제\s?(?P<jo2>\d+)\s?조)(?:\s?의\s?(?P<ui>\d+))?"
    r"(?:\s?(?P<circ>[%(circ)s])|\s?제\s?(?P<hang>\d+)\s?항)?)"
    % {"law": _LAW_ALT, "circ": _CIRCLED}
)


def _canon_law(name: str) -> str:
    name = re.sub(r"\s+", " ", name.strip())
    suffix = ""
    m = re.search(r"\s?(시행령|시행규칙)$", name)
    if m:
        suffix, name = " " + m.group(1), name[:m.start()]
    name = LAW_ALIASES.get(name.replace(" ", ""), LAW_ALIASES.get(name, name))
    return name + suffix


def _base(law: str | None) -> str | None:
    return re.sub(r" (시행령|시행규칙)$", "", law) if law else law


def extract_citations(text: str) -> list[dict]:
    """글에서 조문 인용을 뽑는다. 각 항목: {"법령", "조", "항", "원문"}.

    법령 이름은 줄 단위로 이어받는다("지방세법 §111①3호·§112①2호" 의 §112 도 지방세법). 이름 없이 "시행령 §27③"이면
    바로 앞 법령의 시행령으로 읽고, 앞 법령도 없으면 법령을 "?시행령"으로 둔다. 법령을 알 수 없으면 None.
    "제2항"·"제3호"처럼 조가 없는 것은 인용으로 세지 않는다.
    """
    found: list[dict] = []
    for line in text.splitlines():
        law: str | None = None
        for m in _TOKEN.finditer(line):
            if m.group("node"):
                nlaw = m.group("nlaw")
                nlaw = re.sub(r"(시행령|시행규칙)$", r" \1", nlaw)
                found.append({"법령": _canon_law(nlaw), "조": m.group("njo"),
                              "항": int(m.group("nhang")) if m.group("nhang") else None, "원문": m.group("node")})
            elif m.group("law"):
                law = _canon_law(m.group("law"))
            elif m.group("same"):
                suffix = re.search(r"(시행령|시행규칙)$", m.group("same"))
                if law:
                    law = _base(law) + (" " + suffix.group(1) if suffix else "")
            elif m.group("decree"):
                law = (_base(law) + " " + m.group("decree")) if law else "?" + m.group("decree")
            elif m.group("bare"):
                law = _base(law)
            elif m.group("art"):
                jo = m.group("jo1") or m.group("jo2")
                if m.group("ui"):
                    jo += "의" + m.group("ui")
                hang = None
                if m.group("circ"):
                    hang = _CIRCLED.index(m.group("circ")) + 1
                elif m.group("hang"):
                    hang = int(m.group("hang"))
                found.append({"법령": law, "조": jo, "항": hang, "원문": ((law + " ") if law else "") + m.group("art").strip()})
    return found


def _strings(value) -> list[str]:
    """JSON 값 안의 문자열(키 포함)을 모두 꺼낸다 — 문자열마다 법령 이름을 따로 이어받게 하려는 것."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (_strings(k) + _strings(v))]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _strings(v)]
    return []


def result_strings(call_texts: list[str]) -> list[str]:
    """도구 결과 텍스트(JSON 이면 풀어서)를 문자열 조각으로."""
    out: list[str] = []
    for text in call_texts:
        try:
            out += _strings(json.loads(text))
        except (ValueError, TypeError):
            out.append(text)
    return out


def check_citations(answer: str, call_texts: list[str], surface_text: str = "") -> dict:
    """답에 적힌 조문을 도구 결과와 대조한다. surface_text 는 서버 안내문·도구 설명(있으면 '없음'을 한 번 더 가른다).

    판정(항목마다 하나):
      있음            같은 법령·같은 조가 도구 결과에 있다(항까지 적었으면 그 항도 있다). 도구 결과가 법령 이름을 줄여
                      적은 조("영 §154①", "시행령 §26①")는 조 번호가 같으면 있는 것으로 본다
      항_불일치       법령·조는 있으나 답이 적은 항이 도구 결과에 없다
      법령_불명       답이 법령 이름을 적지 않았다 — 조 번호는 도구 결과의 어느 법령에 있다
      법령_불일치     조 번호는 도구 결과에 있으나 다른 법령의 조다
      설명에만_있음   도구 결과에는 없고 서버 안내문·도구 설명에 같은 법령·조가 있다 → '조문' 칸 실패(출처는 기억이 아니라 설명)
      없음            조 번호가 도구 결과 어디에도 없다 → 채점표 '조문' 칸 실패(기억으로 적은 것)
    """
    surface = {(c["법령"], c["조"]) for c in extract_citations(surface_text)} if surface_text else set()
    surface_jo = {jo for _law, jo in surface}
    tool_cites = [c for s in result_strings(call_texts) for c in extract_citations(s)]
    by_law: dict[str, dict[str, set]] = {}
    any_jo: dict[str, set] = {}
    loose: dict[str, set] = {}                    # 도구 결과가 법령 이름 없이 적은 조("영 §154①" → None, "시행령 §26①" → "?시행령")
    for c in tool_cites:
        if c["법령"]:
            by_law.setdefault(c["법령"], {}).setdefault(c["조"], set()).add(c["항"])
        any_jo.setdefault(c["조"], set()).add(c["법령"])
        if c["법령"] is None or c["법령"].startswith("?"):
            loose.setdefault(c["조"], set()).add(c["법령"])

    def candidates(law: str | None) -> list[str]:
        if law is None:
            return []
        if law.startswith("?"):                       # 앞 법령 없는 "시행령 §…"
            return [k for k in by_law if k.endswith(law[1:])]
        return [law] if law in by_law else []

    rows, seen = [], set()
    for c in extract_citations(answer):
        key = (c["법령"], c["조"], c["항"])
        if key in seen:
            continue
        seen.add(key)
        laws = [l for l in candidates(c["법령"]) if c["조"] in by_law[l]]
        if laws:
            hangs = set().union(*(by_law[l][c["조"]] for l in laws))
            verdict = "있음" if c["항"] is None or c["항"] in hangs else "항_불일치"
        elif c["법령"] and c["조"] in loose and (None in loose[c["조"]] or any(
                k and k.startswith("?") and c["법령"].endswith(k[1:]) for k in loose[c["조"]])):
            verdict = "있음"                      # 도구 결과가 법령 이름을 줄여 적었다("영 §154①", "시행령 §26①")
        elif c["조"] in any_jo:
            verdict = "법령_불명" if c["법령"] is None else "법령_불일치"
        elif (c["법령"], c["조"]) in surface or (c["법령"] is None or c["법령"].startswith("?")) and c["조"] in surface_jo:
            verdict = "설명에만_있음"
        else:
            verdict = "없음"
        rows.append({**c, "판정": verdict,
                     "도구_결과의_법령": sorted(str(x) for x in any_jo.get(c["조"], ()) if x) if verdict != "있음" else None})
    return {"인용": rows, "없음": [r["원문"] for r in rows if r["판정"] == "없음"],
            "설명에만_있음": [r["원문"] for r in rows if r["판정"] == "설명에만_있음"],
            "확인_필요": [r["원문"] + " (" + r["판정"] + ")" for r in rows
                      if r["판정"] not in ("있음", "없음", "설명에만_있음")],
            "도구_결과_조문수": len({(c["법령"], c["조"]) for c in tool_cites})}


# ───────────────────────── 세율·금액 대조(확인 필요만 낸다) ─────────────────────────

_PCT = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|퍼센트|％)(p|포인트)?")
_FRAC = re.compile(r"(1천|1,000|1000|100|1만|10,000|10000)\s?분의\s?(\d+(?:\.\d+)?)")
_FRAC_BASE = {"1천": 1000, "1,000": 1000, "1000": 1000, "100": 100, "1만": 10000, "10,000": 10000, "10000": 10000}


def _round(x: float) -> float:
    return round(x, 4)


def extract_rates(text: str) -> set[float]:
    """글에 적힌 세율(퍼센트 값)."""
    out = {_round(float(m.group(1))) for m in _PCT.finditer(text)}
    out |= {_round(float(m.group(2)) * 100 / _FRAC_BASE[m.group(1)]) for m in _FRAC.finditer(text)}
    return out


def _numbers(value) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers(v)]
    if isinstance(value, (list, tuple)):
        return [n for v in value for n in _numbers(v)]
    return []


def tool_rates(call_texts: list[str]) -> set[float]:
    """도구 결과에 있는 세율 — 글의 퍼센트·분수 표기와, JSON 숫자 가운데 0 과 1 사이의 값(0.027 → 2.7)."""
    out: set[float] = set()
    for text in call_texts:
        out |= extract_rates(text)
        try:
            nums = _numbers(json.loads(text))
        except (ValueError, TypeError):
            nums = []
        out |= {_round(n * 100) for n in nums if 0 < n < 1}
    return out


_WON_DIGITS = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d{5,})\s?원")
_WON_UNIT = re.compile(
    r"(?<![\d.,억만천])(?:(\d+(?:[.,]\d+)?)\s?억)?\s?(?:(\d+(?:,\d{3})*(?:\.\d+)?)\s?(천만|백만|만))?\s?(?:(\d+(?:,\d{3})*)\s?천)?\s?원")
_UNIT = {"만": 10_000, "백만": 1_000_000, "천만": 10_000_000}


def extract_amounts(text: str) -> set[int]:
    """글에 적힌 원 단위 금액 — "9,360,000원", "9억 3,600만원", "5억원", "3천만원". 1만원 미만은 버린다."""
    out: set[int] = set()
    for m in _WON_DIGITS.finditer(text):
        out.add(int(m.group(1).replace(",", "")))
    for m in _WON_UNIT.finditer(text):
        eok, man, unit, chun = m.groups()
        if not (eok or man or chun):
            continue
        total = 0.0
        if eok:
            total += float(eok.replace(",", "")) * 100_000_000
        if man:
            total += float(man.replace(",", "")) * _UNIT[unit]
        if chun:
            total += float(chun.replace(",", "")) * 1_000
        out.add(int(round(total)))
    return {n for n in out if n >= 10_000}


def tool_amounts(call_texts: list[str], arguments: list[dict]) -> set[int]:
    """도구 결과의 숫자, 결과 글 속 금액, 그리고 호출 인자(사용자가 준 값)."""
    out: set[int] = set()
    for text in call_texts:
        out |= extract_amounts(text)
        out |= {int(x.replace(",", "")) for x in re.findall(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?![\d.])", text)}
        try:
            out |= {int(n) for n in _numbers(json.loads(text)) if n >= 10_000 and float(n).is_integer()}
        except (ValueError, TypeError):
            pass
    out |= {int(n) for a in arguments for n in _numbers(a) if n >= 10_000 and float(n).is_integer()}
    return out


# ───────────────────────── 한 질문 대조 ─────────────────────────

def load_calls(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_answer(question: dict, answer: str, calls: list[dict], known_text: str = "", surface_text: str = "") -> dict:
    """한 질문의 답을 호출 기록과 대조한다.

    known_text 는 사용자가 준 글(질문·채점용 사실) — 거기 있는 금액은 지어낸 것이 아니다.
    surface_text 는 서버 안내문·도구 설명 — 도구 결과에는 없지만 설명에 적힌 조문·세율을 따로 가른다.
    """
    ok_calls = [c for c in calls if not c.get("isError")]
    texts = [c.get("text", "") for c in ok_calls]
    called = [c["tool"] for c in calls]
    cites = check_citations(answer, texts, surface_text)
    rates_unknown = extract_rates(answer) - tool_rates(texts) - extract_rates(known_text)
    rates_surface = sorted(rates_unknown & extract_rates(surface_text))
    rates_missing = sorted(rates_unknown - set(rates_surface))
    amounts_ok = tool_amounts(texts, [c.get("arguments", {}) for c in calls]) | extract_amounts(known_text)
    amounts_missing = sorted(extract_amounts(answer) - amounts_ok)
    expected = question.get("기대_도구", [])
    return {
        "id": question["id"],
        "부른_도구": called,
        "오류난_호출": [c["tool"] for c in calls if c.get("isError")],
        "기대_도구_중_부른_것": [t for t in expected if t in called],
        "기대_도구_중_안_부른_것": [t for t in expected if t not in called],
        "법인에_개인용_도구": [t for t in called if t in PERSONAL_ONLY] if question.get("법인_질문") else [],
        "금지_도구_호출": [t for t in question.get("금지_도구", []) if t in called],
        "조문_없음": cites["없음"],                 # 도구 결과에도 설명에도 없는 조문 번호 → '조문' 칸 실패
        "조문_설명에만_있음": cites["설명에만_있음"],   # 도구 결과에는 없고 설명에 있다 → '조문' 칸 실패(출처는 설명)
        "조문_확인_필요": cites["확인_필요"],
        "조문_인용수": len(cites["인용"]),
        "세율_확인_필요": rates_missing,            # 도구 결과·설명에 그 값이 없다(모델이 더한 합계율일 수도 있다)
        "세율_설명에만_있음": rates_surface,        # 도구 결과에는 없고 안내문·도구 설명에 있는 값
        "금액_확인_필요": amounts_missing,          # 도구 결과·호출 인자·사용자 글에 없다(모델이 더한 합계일 수도 있다)
        "균등분": "균등분" in answer,
    }


def check_run(run_dir: Path, questions: list[dict], surface_text: str = "") -> list[dict]:
    """run_dir/Q*/ 의 turn1.md·answer.md 를 대조한다.

    호출 기록에 "turn" 이 있으면 turn1.md 는 turn 1 의 호출만으로 대조한다(뒤 차례의 도구 결과로 첫 답을 봐주지 않는다).
    run_dir/facts.json ({"Q1": "사용자가 준 사실", …}) 이 있으면 그 글의 금액·세율도 사용자가 준 값으로 본다.
    """
    facts_path = run_dir / "facts.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.exists() else {}
    rows = []
    for q in questions:
        qdir = run_dir / q["id"]
        all_calls = load_calls(qdir / "calls.jsonl")
        for name in ("turn1.md", "answer.md"):
            path = qdir / name
            if path.exists():
                first = name == "turn1.md"
                calls = [c for c in all_calls if c.get("turn", 1) == 1] if first else all_calls
                known = q["질문"] if first else "\n".join([q["질문"], q["항목"].get("채점용 사실", ""), facts.get(q["id"], "")])
                row = check_answer(q, path.read_text(encoding="utf-8"), calls, known, surface_text)
                row["파일"] = name
                rows.append(row)
    return rows


# ───────────────────────── 서버·MCP ─────────────────────────

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(port: int, log):
    """tax_http.py 를 로컬 포트로 띄운다 — scripts/check_chatgpt_http.py 와 같은 환경(LAW_OC 없음 → 도구 46개)."""
    env = dict(os.environ, HOST="127.0.0.1", PORT=str(port), LAW_OC="", PUBLIC_BASE_URL="",
               RENDER_EXTERNAL_HOSTNAME="", USAGE_LOG="0", PYTHONIOENCODING="utf-8")
    return subprocess.Popen([sys.executable, "tax_http.py"], cwd=ROOT, env=env, stdout=log, stderr=log)


async def _wait_ready(root: str) -> dict:
    import httpx
    async with httpx.AsyncClient(trust_env=False, timeout=10) as http:
        for _ in range(150):
            try:
                response = await http.get(root + "/health")
                if response.status_code == 200:
                    return response.json()
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.1)
    raise RuntimeError("서버가 뜨지 않았다: " + root)


async def _session(url: str, fn):
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with httpx.AsyncClient(trust_env=False, timeout=60) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as client:
                init = await client.initialize()
                return await fn(client, init)


async def fetch_surface(url: str) -> dict:
    """처음 붙은 모델이 보는 것 — instructions 와 도구 이름·설명·입력 스키마."""
    async def run(client, init):
        tools = (await client.list_tools()).tools
        return {"server": init.serverInfo.name, "instructions": init.instructions or "",
                "tools": [{"name": t.name, "title": t.title, "description": t.description or "",
                           "inputSchema": t.inputSchema} for t in tools]}
    return await _session(url, run)


async def call_tool(url: str, name: str, arguments: dict) -> dict:
    async def run(client, _init):
        result = await client.call_tool(name, arguments)
        text = "\n".join(getattr(c, "text", "") for c in result.content)
        return {"tool": name, "arguments": arguments, "isError": bool(result.isError), "text": text}
    return await _session(url, run)


def surface_markdown(surface: dict) -> str:
    """모델에게 그대로 보여 줄 글 — 서버 안내문과 도구 목록."""
    lines = ["# MCP server: %s" % surface["server"], "", "## Server instructions", "", surface["instructions"], "",
             "## Tools (%d)" % len(surface["tools"]), ""]
    for t in surface["tools"]:
        lines += ["### %s" % t["name"], "", t["description"], "", "Input schema:", "```json",
                  json.dumps(t["inputSchema"], ensure_ascii=False), "```", ""]
    return "\n".join(lines)


# ───────────────────────── 명령 ─────────────────────────

def cmd_dump(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    with tempfile.TemporaryFile(mode="w+b") as log:
        process = start_server(port, log)
        try:
            root = "http://127.0.0.1:%d" % port
            health = asyncio.run(_wait_ready(root))
            surface = asyncio.run(fetch_surface(root + "/mcp"))
        except BaseException:
            log.seek(0)
            print(log.read().decode("utf-8", errors="replace"), file=sys.stderr)
            raise
        finally:
            process.terminate()
            process.wait(timeout=10)
    questions = parse_questions(CASES_MD.read_text(encoding="utf-8"))
    (out / "instructions.txt").write_text(surface["instructions"], encoding="utf-8")
    (out / "tools.json").write_text(json.dumps(surface["tools"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "surface.md").write_text(surface_markdown(surface), encoding="utf-8")
    (out / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"health": health, "tools": len(surface["tools"]), "instructions_chars": len(surface["instructions"]),
                      "questions": len(questions), "out": str(out)}, ensure_ascii=False))
    for q in questions:
        print("%s\t%s" % (q["id"], q["질문"]))
    return 0


def cmd_serve(args) -> int:
    port = args.port or _free_port()
    process = start_server(port, None)
    try:
        asyncio.run(_wait_ready("http://127.0.0.1:%d" % port))
        print("MCP endpoint: http://127.0.0.1:%d/mcp  (Ctrl-C 로 끈다)" % port, flush=True)
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
    return 0


def cmd_call(args) -> int:
    raw = Path(args.args_file).read_text(encoding="utf-8") if args.args_file else (args.arguments or "{}")
    try:
        arguments = json.loads(raw)
    except ValueError as exc:
        print("인자는 JSON 객체여야 한다: %s" % exc, file=sys.stderr)
        return 2
    record = asyncio.run(call_tool(args.url, args.tool, arguments))
    if args.turn:
        record["turn"] = args.turn
    if args.log:
        log = Path(args.log)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(("ERROR: " if record["isError"] else "") + record["text"])
    return 1 if record["isError"] else 0


def cmd_check(args) -> int:
    questions = parse_questions(CASES_MD.read_text(encoding="utf-8"))
    surface = Path(args.surface).read_text(encoding="utf-8") if args.surface else ""
    rows = check_run(Path(args.run), questions, surface)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for r in rows:
        print("%s %s — 부른 도구 %d개%s" % (r["id"], r["파일"], len(r["부른_도구"]),
                                        " (오류 %d)" % len(r["오류난_호출"]) if r["오류난_호출"] else ""))
        for key in ("기대_도구_중_안_부른_것", "법인에_개인용_도구", "금지_도구_호출", "조문_없음", "조문_설명에만_있음",
                    "조문_확인_필요", "세율_확인_필요", "세율_설명에만_있음", "금액_확인_필요"):
            if r[key]:
                print("    %s: %s" % (key, ", ".join(str(x) for x in r[key])))
        if r["균등분"]:
            print("    '균등분'이라는 말이 답에 있다")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dump", help="서버를 띄워 instructions·tools/list·질문 목록을 떨군다")
    p.add_argument("--out", default=str(ROOT / "dist/rehearsal"))
    p.set_defaults(fn=cmd_dump)
    p = sub.add_parser("serve", help="서버를 띄운 채로 둔다")
    p.add_argument("--port", type=int, default=0)
    p.set_defaults(fn=cmd_serve)
    p = sub.add_parser("call", help="도구 하나를 부르고 호출 기록에 덧붙인다")
    p.add_argument("--url", required=True)
    p.add_argument("--log")
    p.add_argument("--args-file", help="인자 JSON 을 파일에서 읽는다")
    p.add_argument("--turn", type=int, help="몇 번째 차례의 호출인지(1 = 사실을 받기 전). 기록에 남긴다")
    p.add_argument("tool")
    p.add_argument("arguments", nargs="?")
    p.set_defaults(fn=cmd_call)
    p = sub.add_parser("check", help="답변과 호출 기록을 기계적으로 대조한다")
    p.add_argument("--run", required=True)
    p.add_argument("--surface", help="dump 가 떨군 surface.md — 도구 결과에는 없고 설명에만 있는 조문·세율을 따로 가른다")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_check)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
