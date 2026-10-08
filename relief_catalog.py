# -*- coding: utf-8 -*-
"""감면·특례 검토 후보 색인 (조특법·조특령·지특법).

**판정 엔진이 아니다.** 판정툴(judge_*)은 A등급 법문 노드를 근거로 결론을 내지만,
이 모듈은 "이 상담에서 검토했어야 할 감면 조문"을 빠짐없이 던져 주는 것까지만 한다.
감면 누락은 고객이 세금을 더 내는 방향이라 오답보다 조용히 위험하다 — 그 침묵을 깬다.

데이터: data/legal_nodes/relief_catalog.json (scripts/build_relief_catalog.py 생성)
근거등급: C (기계추출). 적용 전 원문 확인이 필수이며 출력에 그 문구를 항상 붙인다.
"""
from __future__ import annotations

import io
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(_HERE, "data", "legal_nodes", "relief_catalog.json")

_CACHE = {}

DISCLAIMER = ("근거등급 C — 제목·원문 기계추출 색인이다. 요건·감면율·한도는 "
              "원문과 판정툴로 확인해야 하며, 이 목록만으로 감면을 적용하면 안 된다.")

# 자유 텍스트 상담 문장에서 감면 계열을 끌어내는 키워드.
# 조문 제목에 없는 생활어(첫집·다둥이 등)를 법령 용어로 잇는 다리다.
SITUATION_KEYWORDS = {
    "생애최초": ["생애최초", "첫집", "첫 주택", "처음으로", "처음 사는", "무주택"],
    "출산·양육": ["출산", "육아", "다자녀", "아이", "둘째", "셋째", "양육"],
    "농지·자경": ["농지", "자경", "영농", "농업", "밭", "논", "과수원"],
    "산지·축사": ["임야", "산지", "축사", "축산"],
    "수용·공익사업": ["수용", "보상", "공익사업", "협의매수", "대토", "이주"],
    "임대주택": ["임대사업자", "장기일반", "민간임대", "임대주택", "등록임대"],
    "미분양": ["미분양", "준공후미분양"],
    "정비사업": ["재개발", "재건축", "정비사업", "조합원입주권", "가로주택", "소규모"],
    "농어촌주택": ["농어촌주택", "고향주택", "귀농", "귀촌", "세컨하우스"],
    "상가임대": ["상가", "임대료 인하", "착한임대"],
    "노후연금": ["주택연금", "역모기지", "노후연금"],
    "신축주택": ["신축", "분양받", "미등기 신축"],
}


def _load():
    if "doc" not in _CACHE:
        _CACHE["doc"] = json.load(io.open(_PATH, encoding="utf-8"))
    return _CACHE["doc"]


def catalog_meta():
    return dict(_load()["meta"])


def _norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def expand_situation(text):
    """상담 문장 → 카탈로그 계열 라벨. 매칭된 계열과 근거 단어를 함께 돌려준다."""
    t = _norm(text)
    hits = []
    for label, words in SITUATION_KEYWORDS.items():
        matched = [w for w in words if _norm(w) in t]
        if matched:
            hits.append({"계열": label, "걸린단어": matched})
    return hits


def _score(e, semok, situations, assets):
    """정렬용 점수. 순위를 매기되 무엇 때문에 올라왔는지 사유를 함께 남긴다."""
    score, why = 0, []
    if semok and any(s in e["세목"] for s in semok):
        score += 30
        why.append("세목 일치")
    blob = e["제목"] + " " + e["요지"]
    for label in situations:
        for w in SITUATION_KEYWORDS.get(label, []):
            if _norm(w) in _norm(blob):
                score += 35
                why.append("상황 '%s'" % label)
                break
    if assets and any(a in e["대상자산"] for a in assets):
        score += 15
        why.append("자산 일치")
    if e["부동산관련도"] == "높음":
        score += 10
    elif e["부동산관련도"] == "중간":
        score += 3
    if e["현행성"] == "현행":
        score += 8
    elif e["현행성"] == "상시":
        score += 5
    if e["종류"] == "법":
        score += 5
    if not e["구현"]:
        score += 4  # 판정툴이 없는 조문일수록 사람이 직접 봐야 한다
    if e["분류"] == "세액영향":
        score += 3
    return score, sorted(set(why))


def screen(semok=None, situation="", assets=None, include_corporate=False,
           include_expired=False, include_decree=False, include_implemented=True,
           limit=15):
    """상담 조건에 걸리는 감면·특례 후보를 점수순으로 돌려준다.

    semok: ["양도소득세", "취득세", ...] — 빈 값이면 세목으로 거르지 않는다
    situation: 상담 문장 그대로 넣어도 된다 (키워드 확장)
    assets: ["주택", "농지", ...]
    include_decree: 시행령 조문까지 볼지 (기본은 법 조문만 — 령은 요건 상세라 중복)
    include_expired: 본문 기한이 전부 과거인 조문까지 볼지 (경정청구·과거분 검토 시 True)
    """
    doc = _load()
    semok = [s for s in (semok or []) if s]
    assets = [a for a in (assets or []) if a]
    sits = [h["계열"] for h in expand_situation(situation)]

    rows = []
    for e in doc["entries"]:
        if not include_decree and e["종류"] != "법":
            continue
        if not include_corporate and e["적용대상"] == "법인·기관":
            continue
        if not include_expired and e["현행성"] == "과거분전용의심":
            continue
        if not include_implemented and e["구현"]:
            continue
        if e["부동산관련도"] == "낮음" and not (
                semok and any(s in e["세목"] for s in semok) and sits):
            continue
        if semok and not any(s in e["세목"] for s in semok):
            continue
        if assets and not any(a in e["대상자산"] for a in assets):
            continue
        sc, why = _score(e, semok, sits, assets)
        if (semok or sits or assets) and not why:
            continue
        rows.append((sc, e, why))

    rows.sort(key=lambda r: (-r[0], r[1]["법령"], r[1]["조문"]))
    out = []
    for sc, e, why in rows[:limit]:
        out.append({
            "id": e["id"],
            "근거": "%s %s(%s)" % (e["법령"], e["조문"], e["제목"]),
            "세목": e["세목"],
            "특례유형": e["특례유형"],
            "대상자산": e["대상자산"],
            "감면율후보": e["감면율후보"],
            "금액후보": e["금액후보"],
            "현행성": e["현행성"],
            "본문최종기한": e["본문최종기한"],
            "요지": e["요지"],
            "판정툴": "있음" if e["구현"] else "없음 — 원문 직접 확인",
            "연계노드": e["연계노드"],
            "걸린이유": why,
            "점수": sc,
        })
    return {
        "후보수": len(rows),
        "표시": len(out),
        "확장된계열": expand_situation(situation),
        "후보": out,
        "주의": DISCLAIMER,
    }


def lookup(article_id):
    """카탈로그 id 또는 '지특법 §36의5' 형태로 한 건 조회."""
    doc = _load()
    key = _norm(article_id)
    for e in doc["entries"]:
        if _norm(e["id"]) == key:
            return e
    m = re.search(r"§?\s*(\d+)(?:의(\d+))?", article_id)
    if m:
        want = "§%s%s" % (m.group(1), ("의" + m.group(2)) if m.group(2) else "")
        law_hint = ("지방세특례" if "지특" in article_id or "지방세특례" in article_id
                    else "조세특례")
        decree = "시행령" in article_id or "조특령" in article_id
        for e in doc["entries"]:
            if (e["조문"] == want and law_hint in e["법령"]
                    and (("시행령" in e["법령"]) == decree)):
                return e
    return None
