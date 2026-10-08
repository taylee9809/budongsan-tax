# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_adjusted_area_at_date.

결함: 코어 비교가 문자열 포함 검사뿐이라 '용인 처인구'(市 생략)가 이력 키 '용인시 처인구'와
연결되지 않아 "비조정(연표상 지정 이력 없음)"이라는 그럴듯한 오답을 반환했다.
"""
import json as _json
import os

from tax_judgment import _adj_split_region  # noqa: F401 — 변경 없는 헬퍼

_ADJ_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "..", "data", "adj_regions_history.json")


def judge_adjusted_area_at_date(region: str, target_date: str) -> dict:
    """특정 날짜에 해당 지역이 조정대상지역이었는지 판정 (data/adj_regions_history.json replay).

    region: "서울 마포구"·"성남시 분당구" 등. target_date: YYYY-MM-DD (취득일 — 분양권·입주권
    승계는 사용승인일 기준임을 주의). 이력 events를 시행일 오름차순으로 재생해 해당 날짜의
    지정 상태를 복원한다(2026-08-22 과거분 백필). 부분지정·시군구 미만 모호 입력은 단정하지
    않고 확인을 요구한다 — 그럴듯한 오답 금지 원칙. 결과의 acquired_in_adjusted_area를
    judge_exemption_requirements에 연결.
    """
    global _ADJ_HISTORY_PATH
    if _ADJ_HISTORY_PATH is None:
        import os
        _ADJ_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "data", "adj_regions_history.json")
    try:
        hist = _json.load(open(_ADJ_HISTORY_PATH, encoding="utf-8"))
    except FileNotFoundError:
        return {"판정": "판단불가", "사유": "adj_regions_history.json 없음"}

    d = target_date
    flags = ["분양권·입주권 승계취득은 취득시기=사용승인일 — 그 날짜로 다시 조회할 것 (대조 143346)"]

    # 세법상 조정대상지역 개념은 2017-08-03(소득세법 시행령 §154② 간주표)부터
    if d < "2017-08-03":
        return {"판정": "비조정(세법상 조정대상지역 개념 이전)", "acquired_in_adjusted_area": False,
                "확신도": "B(소득세법 시행령 §154② 간주표 기산일)",
                "근거": [{"규칙": "세법효력시기", "근거": hist["meta"]["세법효력시기"], "등급": "B"}],
                "플래그": flags + ["2016-11-03~2017-08-02의 청약·전매 규제는 별개 축 — 세법 판정에 사용 금지"]}

    rn = region.replace(" ", "")
    in_sido, in_core = _adj_split_region(rn)

    # 이벤트 재생 — 키별 최종 상태 복원
    state: dict[str, dict] = {}
    for ev in sorted(hist["events"], key=lambda e: e["시행일"]):
        if ev["시행일"] > d:
            break
        for ent in ev["지역"]:
            kn = ent["키"].replace(" ", "")
            state[kn] = {
                "상태": ev["유형"], "범위": ent.get("범위", "전체"), "상세": ent.get("상세", ""),
                "등급": ev["등급"], "근거": ev["근거"], "시행일": ev["시행일"],
            }

    # 입력과 키 매칭 — strong: 키가 입력에 포함(입력이 키 이상으로 구체적) / weak: 그 반대
    strong, weak = [], []
    for kn, st_ in state.items():
        k_sido, k_core = _adj_split_region(kn)
        if in_sido and k_sido != in_sido:
            continue
        if k_core and k_core in rn:
            strong.append((k_core, st_))
        elif in_core and in_core in k_core:
            weak.append((k_core, st_))
        elif not in_core and in_sido == k_sido:
            weak.append((k_core, st_))

    def _verdict(st_: dict, note: str = "") -> dict:
        cit = [{"규칙": "이력 replay", "근거": f"{st_['근거']} (시행 {st_['시행일']})", "등급": st_["등급"]}]
        fl = list(flags)
        if st_["등급"] not in ("A", "B"):
            fl.append(f"판정 근거 사건이 {st_['등급']}급(공고 원문 미열람) — 세액 확정 전 원문 대조 권장")
        if note:
            fl.append(note)
        if st_["상태"] == "지정" and st_["범위"] == "부분":
            return {"판정": "부분지정 구간 — 소재 읍면동·지구 확인 필요", "acquired_in_adjusted_area": None,
                    "부분상세": st_["상세"], "확신도": st_["등급"], "근거": cit, "플래그": fl}
        if st_["상태"] == "지정":
            return {"판정": "조정대상지역", "acquired_in_adjusted_area": True,
                    "확신도": st_["등급"], "근거": cit, "플래그": fl}
        return {"판정": "비조정(해제 구간)", "acquired_in_adjusted_area": False,
                "확신도": st_["등급"], "근거": cit, "플래그": fl}

    if strong:
        best_len = max(len(c) for c, _ in strong)
        best_core = next(c for c, _ in strong if len(c) == best_len)
        best_st = next(s for c, s in strong if len(c) == best_len)
        # 하위 키 충돌 가드: 입력이 상위 단위(예: '화성시')인데 그 하위 키(예: '화성시
        # 동탄구')의 상태가 다르면 단정 금지 — 그럴듯한 오답 방지
        subs = [
            (c2, s2) for kn2, s2 in state.items()
            for c2 in [_adj_split_region(kn2)[1]]
            if c2 != best_core and best_core in c2 and c2 not in rn
            and (s2["상태"], s2["범위"]) != (best_st["상태"], best_st["범위"])
        ]
        if subs:
            return {"판정": "판단불가", "acquired_in_adjusted_area": None,
                    "사유": "하위 행정구역별로 지정 상태가 갈림 — 더 구체적으로 입력 필요: "
                            + ", ".join(sorted({c for c, _ in subs})) + f" (기준 {best_core})",
                    "근거": [{"규칙": "이력 replay", "근거": "data/adj_regions_history.json", "등급": "혼합"}],
                    "플래그": flags}
        return _verdict(best_st)
    if weak:
        distinct = {(s["상태"], s["범위"]) for _, s in weak}
        if len(distinct) == 1:
            note = ("하위 행정구역 단위 키 다수와 일치(상태 동일) — 구 단위까지 입력하면 더 정밀"
                    if len(weak) > 1 else "")
            return _verdict(weak[0][1], note)
        return {"판정": "판단불가", "acquired_in_adjusted_area": None,
                "사유": "하위 행정구역(구·군)별로 지정 상태가 갈림 — 구 단위까지 명시 필요: "
                        + ", ".join(sorted(c for c, _ in weak)),
                "근거": [{"규칙": "이력 replay", "근거": "data/adj_regions_history.json", "등급": "혼합"}],
                "플래그": flags}

    # 어떤 사건에도 등장한 적 없는 지역 — 연표상 지정 이력 없음
    return {"판정": "비조정(연표상 지정 이력 없음)", "acquired_in_adjusted_area": False,
            "확신도": "C(연표 완전성에 의존 — 2016~2022 사건은 공고 원문 미열람)",
            "근거": [{"규칙": "이력 replay", "근거": "data/adj_regions_history.json 전 사건 무관 지역", "등급": "C"}],
            "플래그": flags}
