# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_transfer_reduction_limit (run#31 재현용).

결함: tax_year를 받고도 한도 연혁에 쓰지 않았다 — §133② 분리(2025 과세연도부터)를 전 연도에
적용, 다목 3억(2016~2017)·구법 과세기간 2억(~2015)도 없음.
"""


def _cite(rule, basis, grade="B"):
    return {"규칙": rule, "근거": basis, "등급": grade}


RELIEF_LIMIT_YEAR = 100_000_000
RELIEF_LIMIT_5YEAR = 200_000_000
RELIEF_LIMIT_5YEAR_DAETO = 100_000_000
RELIEF_LIMIT_YEAR_TAKING = 200_000_000
RELIEF_LIMIT_5YEAR_TAKING = 300_000_000


def judge_transfer_reduction_limit(
    reductions: list[dict],
    tax_year: int,
    prior_4year_reductions: int = 0,
    prior_4year_taking_reductions: int = 0,
    contract_price_mismatch: bool = False,
    unregistered_transfer: bool = False,
) -> dict:
    """양도소득세 감면 공통 게이트 — §129 배제 → §133 종합한도 → §127⑦ 택일.

    reductions 각 원소: {"조문": "69"|"70"|"77"|..., "감면세액": int, "라벨": str}
    같은 자산에 둘 이상 감면이 걸리면 §127⑦로 하나만 선택해야 하므로, 호출자는
    시나리오별로 나눠 호출하거나 후보 목록을 넘겨 비교한다(택일 안내를 반환).
    prior_4year_*: 직전 4개 과세기간에 이미 감면받은 세액(5개 과세기간 한도 계산용).
    """
    if contract_price_mismatch or unregistered_transfer:
        why = "매매계약서 거래가액 상이(다운·업 계약)" if contract_price_mismatch else "미등기양도자산"
        return {
            "감면가능": False,
            "최종감면세액": 0,
            "판정": f"{why} — 비과세·감면 전면 배제",
            "근거": [_cite("감면 전면 배제", "조세특례제한법 §129①② (N조특129-1)", "A")],
            "플래그": ["감면 요건을 갖췄더라도 이 게이트에서 탈락하면 전부 무효"],
        }

    LIMIT1 = {"33", "43", "66", "67", "68", "69", "69의2", "69의3", "69의4", "70", "85의10"}
    LIMIT2 = {"77", "77의2", "77의3"}
    basket1 = [r for r in (reductions or []) if str(r.get("조문", "")).replace("제", "").replace("조", "") in LIMIT1]
    basket2 = [r for r in (reductions or []) if str(r.get("조문", "")).replace("제", "").replace("조", "") in LIMIT2]
    others = [r for r in (reductions or []) if r not in basket1 and r not in basket2]

    def _cut(items, year_limit, five_limit, prior, label):
        raw = sum(int(i.get("감면세액", 0)) for i in items)
        if raw == 0:
            return 0, 0, []
        notes = []
        allowed = min(raw, year_limit)
        if allowed < raw:
            notes.append(f"{label} 과세기간 한도 {year_limit:,}원 초과분 {raw - allowed:,}원 감면 배제")
        five_room = max(0, five_limit - int(prior))
        if allowed > five_room:
            notes.append(f"{label} 5개 과세기간 한도 {five_limit:,}원 — 직전 4개 과세기간 감면 {int(prior):,}원 반영, "
                         f"잔여 {five_room:,}원까지만 감면")
            allowed = five_room
        return allowed, raw - allowed, notes

    daeto_only = basket1 and all(str(r.get("조문")) == "70" for r in basket1)
    five_limit1 = RELIEF_LIMIT_5YEAR_DAETO if daeto_only else RELIEF_LIMIT_5YEAR
    a1, cut1, note1 = _cut(basket1, RELIEF_LIMIT_YEAR, five_limit1, prior_4year_reductions, "§133① 바스켓")
    a2, cut2, note2 = _cut(basket2, RELIEF_LIMIT_YEAR_TAKING, RELIEF_LIMIT_5YEAR_TAKING,
                           prior_4year_taking_reductions, "§133② 공익수용 바스켓")
    other_sum = sum(int(r.get("감면세액", 0)) for r in others)

    flags = list(note1) + list(note2)
    if basket1 and basket2:
        flags.append("§133①과 §133②는 별도 바스켓 — 각각 한도를 계산하며 서로 잠식하지 않는다")
    if len(reductions or []) > 1:
        flags.append("같은 자산에 둘 이상 감면이 걸리면 §127⑦로 하나만 선택 — 감면율뿐 아니라 한도까지 "
                     "넣어 시나리오별로 비교할 것(토지 일부는 분리 적용 가능)")
    if others:
        flags.append(f"§133 한도 열거에 없는 감면 {[r.get('조문') for r in others]} — 한도 컷 없이 전액 반영. "
                     "다만 개별 조문의 자체 제한은 별도 확인")
    flags.append("§133③: 양도일 소급 1년 내 분할 후 일부 양도, 지분 양도 후 2년 내 나머지를 동일인·배우자에게 "
                 "양도하면 1개 과세기간으로 간주 — 해 넘겨 나눠 팔기로 한도를 두 번 쓰는 구조는 차단됨")

    return {
        "감면가능": True,
        "최종감면세액": int(a1 + a2 + other_sum),
        "바스켓별": {
            "§133①(자경·대토 등)": {"신청": sum(int(i.get("감면세액", 0)) for i in basket1), "인정": a1, "배제": cut1,
                              "적용한도": f"과세기간 {RELIEF_LIMIT_YEAR:,} / 5개 과세기간 {five_limit1:,}"},
            "§133②(공익수용)": {"신청": sum(int(i.get("감면세액", 0)) for i in basket2), "인정": a2, "배제": cut2,
                            "적용한도": f"과세기간 {RELIEF_LIMIT_YEAR_TAKING:,} / 5개 과세기간 {RELIEF_LIMIT_5YEAR_TAKING:,}"},
            "한도외": {"신청": other_sum, "인정": other_sum},
        },
        "과세연도": tax_year,
        "근거": [
            _cite("§133① 과세기간 1억·5개 과세기간 2억(§70 단독 5년 1억)", "조세특례제한법 §133① (N조특133-1)", "A"),
            _cite("§133② 공익수용 과세기간 2억·5개 과세기간 3억", "조세특례제한법 §133② (2025-03-14 신설, N조특133-2)", "A"),
            _cite("둘 이상 감면 동시 해당 시 택일", "조세특례제한법 §127⑦⑧ (N조특127-7)", "A"),
        ],
        "플래그": flags,
    }
