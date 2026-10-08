# -*- coding: utf-8 -*-
"""공개 저장소용 텍스트 비식별 후처리.

배경(2026-10-08 스캔): 재결례·해석례 원문은 발행 기관이 이미 성명·주소를 "OOO"·"○○"로
가려 두었다. 남는 것은 뒷자리만 가린 계좌·전화번호("235074-52-04****", "010-7561-****")와
드물게 주민번호 형태("89****-1******")다. 이 모듈은 그런 숫자 패턴을 전부 "[번호삭제]"로
바꾼다. 세법 인용에 쓰는 번호(예규 "01254-2262", 사건번호 "2004중1234", 날짜, 금액)는 건드리지
않는다.

사용
  from scripts.sanitize_public_text import mask_text, sanitize_record
  py scripts/sanitize_public_text.py <in.jsonl> <out.jsonl>   # 줄 단위 JSON 전체 문자열 필드 처리
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

# 공개 정본에서 아예 빼는 키 — 비공개 노션 링크 등 내부 참조
DROP_KEYS = {"notion_url", "notion_page_id"}

# 예규·해석례 문서번호: "재일 01254-2262", "법인 46012-1234", "서면-2015-법령해석재산-1234"
_KEEP = re.compile(r"(?:\b\d{5}-\d{3,4}\b)|(?:서면[-\s]?\d{4}[-\s][가-힣]+[-\s]?\d+)")

# `\b`는 '*' 뒤에서 경계가 안 잡히므로 숫자·별표 전용 lookaround를 쓴다.
_L = r"(?<![\d*])"
_R = r"(?![\d*])"
_PATTERNS = [
    # 주민등록번호 (완전·부분 마스킹 포함) 123456-1234567 / 89****-1******
    re.compile(_L + r"[\d*]{6}-[1-8*][\d*]{6}" + _R),
    # 전화번호 (부분 마스킹 포함) 02-815-****, 010-7561-****, 011-220-1234
    re.compile(_L + r"0\d{1,2}-[\d*]{3,4}-[\d*]{4}" + _R),
    # 계좌번호류: 숫자·* 블록이 하이픈으로 2번 이상 이어지고 총 길이 10 이상.
    # ISO 날짜(2026-01-01)와 날짜시각(…T…)은 제외 — 첫 스캔에서 853건이 전부 날짜였다.
    re.compile(_L + r"(?!\d{4}-\d{2}-\d{2}(?![\d*-]))(?=[\d*-]{10,})[\d*]{2,8}(?:-[\d*]{2,8}){2,}" + _R),
    # 별표로 가린 숫자 조각 (아파트 2**-19**호, 2016-OOO-임대주택-108**, 344-****)
    re.compile(_L + r"\d{1,4}\*{2,}(?:-\d{0,4}\*{0,6})?" + _R),
    re.compile(_L + r"\d{1,6}-\d{0,4}\*{2,}" + _R),
    # 이메일
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    # 사업자등록번호 123-45-67890
    re.compile(_L + r"\d{3}-\d{2}-\d{5}" + _R),
]

MASK = "[번호삭제]"


def mask_text(text: str) -> str:
    if not text or not isinstance(text, str):
        return text
    keep_spans = [(m.start(), m.end()) for m in _KEEP.finditer(text)]

    def _protected(s: int, e: int) -> bool:
        return any(ks <= s and e <= ke for ks, ke in keep_spans)

    out = text
    for pat in _PATTERNS:
        pieces = []
        last = 0
        for m in pat.finditer(out):
            if _protected(m.start(), m.end()):
                continue
            pieces.append(out[last:m.start()])
            pieces.append(MASK)
            last = m.end()
        pieces.append(out[last:])
        out = "".join(pieces)
        keep_spans = [(m.start(), m.end()) for m in _KEEP.finditer(out)]
    return out


def sanitize_record(rec: dict) -> tuple[dict, int]:
    """dict의 모든 문자열 값에 mask_text를 적용하고 DROP_KEYS를 뺀다. (결과, 치환 건수)"""
    n = 0
    out = {}
    for k, v in rec.items():
        if k in DROP_KEYS:
            continue
        if isinstance(v, str):
            m = mask_text(v)
            n += m.count(MASK) - v.count(MASK)
            out[k] = m
        elif isinstance(v, dict):
            sub, c = sanitize_record(v)
            out[k] = sub
            n += c
        elif isinstance(v, list):
            lst = []
            for item in v:
                if isinstance(item, str):
                    m = mask_text(item)
                    n += m.count(MASK) - item.count(MASK)
                    lst.append(m)
                elif isinstance(item, dict):
                    sub, c = sanitize_record(item)
                    lst.append(sub)
                    n += c
                else:
                    lst.append(item)
            out[k] = lst
        else:
            out[k] = v
    return out, n


def sanitize_jsonl(src: pathlib.Path, dst: pathlib.Path) -> tuple[int, int]:
    rows = 0
    masked = 0
    with src.open(encoding="utf-8") as f, dst.open("w", encoding="utf-8") as g:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rec, n = sanitize_record(rec)
            masked += n
            rows += 1
            g.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return rows, masked


def _selftest() -> None:
    cases = {
        "계좌(235074-52-04****) 송금": "계좌([번호삭제]) 송금",
        "전화 010-7561-**** 로": "전화 [번호삭제] 로",
        "주민 89****-1****** 기재": "주민 [번호삭제] 기재",
        "재일 01254-2262, 1987. 8. 24.": "재일 01254-2262, 1987. 8. 24.",
        "조심 2004중1234 결정": "조심 2004중1234 결정",
        "OOO아파트 2**-19**호": "OOO아파트 [번호삭제]호",
        "양도가액 1,250,000,000원": "양도가액 1,250,000,000원",
        "사업자 123-45-67890": "사업자 [번호삭제]",
        "지방세법 제110조의2 제1항": "지방세법 제110조의2 제1항",
        "취득일 2017-08-03~ 적용": "취득일 2017-08-03~ 적용",
        "실행시각 2026-08-24T21:18:45+09:00": "실행시각 2026-08-24T21:18:45+09:00",
        "계좌 1002-610-****** 입금": "계좌 [번호삭제] 입금",
    }
    bad = {k: mask_text(k) for k, v in cases.items() if mask_text(k) != v}
    if bad:
        for k, got in bad.items():
            print("FAIL:", repr(k), "->", repr(got), "expected", repr(cases[k]))
        raise SystemExit(1)
    print("selftest ok (%d cases)" % len(cases))


if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] == "--selftest":
        _selftest()
    else:
        r, m = sanitize_jsonl(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
        print("rows=%d masked=%d" % (r, m))
