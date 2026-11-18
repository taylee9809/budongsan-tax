"""증여 예시·추정 도구 — 저가 양수·고가 양도(상증법 §35)와 증여 추정(§44 배우자 등 양도, §45 취득자금·채무 상환자금).
호스팅 서버에 붙인다(tax_http.py). 생성 파일 tax_server.py 는 건드리지 않는다.

판정·계산은 전부 조문 노드(tax_nodes/sangjeung_chujeong.py)가 하고, 증여재산가액이 나오면 기존 증여세 노드(tax_nodes/sangjeung.py 의
증여세_부동산)로 세액·신고기한·분납까지 잇는다. 이 파일은 도구 입출력만 맡는다. 기준금액·비율은 data/tax_params.json 에서 연도로 읽고,
검증되지 않은 연도는 계산을 거부한다. 입력이 모자라면 추정하지 않고 판정불가(None)와 필요한 사실을 돌려준다.
"""
from __future__ import annotations

TOOLS = ("judge_low_price_transfer_gift", "judge_gift_presumption")

_관계 = ("배우자", "직계존속", "직계비속", "기타친족", "기타")

#: judge_low_price_transfer_gift 결과에 붙이는 범위 고지.
LOW_PRICE_NOT_COVERED = [
    "시가 — 상증법 §60~§66 평가액(매매·감정·유사매매사례가액, 없으면 기준시가)을 호출자가 market_value 로 넘긴다. 이 도구는 시가를 정하지 않는다.",
    "특수관계인 해당 여부(시행령 §2의2) — related_party 로 받는다. facts 의 상대방관계를 주면 조문 노드가 판정한다.",
    "'거래의 관행상 정당한 사유'(§35②) — 사실판단이라 판정하지 않는다. no_legitimate_reason 으로 받는다.",
    "양도자의 양도소득세 — 특수관계인에게 시가보다 낮게 양도하면 소득세법 §101 부당행위계산으로 양도가액이 시가로 다시 계산될 수 있다(요건은 소득세법 시행령 §167). 증여세와 별개다.",
    "양수자의 취득세 — 시가인정액보다 낮은 가액으로 취득하면 지방세법 §10의3② 부당행위계산이 따로 적용될 수 있다.",
    "전환사채·상장주식 등 부동산이 아닌 재산, 법인세법 §52② 시가 해당 여부(§35③), 1년 이내 같은 거래의 합산(§43②), 10년 내 다른 증여의 합산은 facts·tax_facts 로 받은 값만 반영한다.",
]

#: judge_gift_presumption 결과에 붙이는 범위 고지.
PRESUMPTION_NOT_COVERED = [
    "추정은 반증으로 깨진다 — 이 도구는 준 사실로 법문 요건을 맞춰 볼 뿐, 과세관청·심판원이 증빙을 받아들일지는 판단하지 않는다.",
    "대가 지급이 일부만 입증된 경우(§44) — 입증되지 않은 부분을 어떻게 볼지 조문에 없어 판정하지 않는다.",
    "증권시장에서 처분된 유가증권(§44③4호), 실명 계좌 명의자 추정의 세부(§45④), 주식·예금 등 부동산이 아닌 재산의 취득자금.",
    "추정이 배제돼 양도로 인정된 뒤의 저가 양수·고가 양도 이익(§35) — judge_low_price_transfer_gift 로 따로 본다. 양도자의 양도소득세는 calc_transfer_tax.",
    "차용증을 쓴 가족 간 금전 대여의 이자 이익(§41의4) — judge_family_loan. 자금조달계획서 제출 대상 — judge_fund_plan_requirement.",
    "국세청 훈령(상속세 및 증여세 사무처리규정 §42)의 증여추정 배제기준은 과세관청 내부 기준이다. 배제기준에 미달해도 증여받은 사실이 확인되면 과세된다(같은 조 ②).",
]


def _자르기(r: dict) -> dict:
    r.pop("근거표", None)
    세 = r.get("증여세")
    if isinstance(세, dict):
        세.pop("근거표", None)
    return r


def judge_low_price_transfer_gift(
    year: int,
    market_value: int,
    price: int,
    related_party: bool | None = None,
    direction: str | None = None,
    no_legitimate_reason: bool | None = None,
    settlement_date: str | None = None,
    donor_relation: str | None = None,
    facts: dict | None = None,
    tax_facts: dict | None = None,
) -> dict:
    """Korea Inheritance and Gift Tax Act art. 35: gift deemed to arise when property is bought below or sold above market value. Between related parties the gift is (difference − the lesser of 30% of market value and KRW 300 million); between unrelated parties, without a legitimate reason, (difference − KRW 300 million) once the difference reaches 30% of market value. Returns the statute trail and, if the donor relation is given, the gift tax.

    부동산을 시가보다 싸게 사거나(저가 양수) 비싸게 판(고가 양도) 경우 증여세가 과세되는 이익을 계산한다(상증법 §35, 시행령 §26).

    특수관계인 간(§35①): 시가와 대가의 차액이 기준금액(시가의 30%와 3억원 중 적은 금액) 이상이면 증여재산가액 = 차액 − 기준금액.
    특수관계인이 아닌 자 간(§35②): 거래의 관행상 정당한 사유 없이 차액이 시가의 30% 이상이면 증여재산가액 = 차액 − 3억원.
    이익을 얻은 자는 저가 양수면 양수자, 고가 양도면 양도자다. 증여일은 대금을 청산한 날이다(시행령 §26⑤).
    입력이 모자라면 추정하지 않고 증여재산가액=None 과 판정불가_사유를 돌려준다. 0 은 '과세되는 이익이 없다'는 판정이다.

    Args:
        year: 양수일·양도일(대금청산일)이 속하는 연도. 기준금액 조회 키이며 필수다. 검증되지 않은 연도는 계산을 거부한다.
        market_value: 시가(원) — 상증법 §60~§66 에 따라 평가한 가액. 호출자가 정해 넘긴다.
        price: 실제 주고받은 대가(원).
        related_party: 양도자와 양수자가 특수관계인(시행령 §2의2 — 친족 등)이면 True, 아니면 False. 모르면 생략(판정불가).
        direction: "저가양수" | "고가양도". 생략하면 대가가 시가보다 낮으면 저가양수, 높으면 고가양도로 본다.
        no_legitimate_reason: 특수관계인이 아닌 자 간 거래에서 거래의 관행상 정당한 사유가 없으면 True, 있으면 False.
            특수관계인이 아니고 이 값이 없으면 판정하지 않는다.
        settlement_date: 대금청산일 "YYYY-MM-DD". 증여일과 신고기한(증여일이 속하는 달의 말일부터 3개월)에 쓴다.
        donor_relation: 이익을 얻은 자가 본 상대방의 관계 — "배우자" | "직계존속" | "직계비속" | "기타친족" | "기타".
            주면 증여재산공제를 적용해 증여세·신고기한·분납·연부연납까지 계산한다. 생략하면 증여재산가액까지만 낸다.
        facts: 그 밖의 사실(키는 한국어 그대로) — 상대방관계(시행령 §2의2 판정용), 매매계약일, 매매계약일_기준사유(bool),
            재산종류("부동산"|"전환사채등"|"상장주식_장내거래"), 법인세법52조_시가거래(bool, §35③), 부정한방법(bool).
        tax_facts: 증여세 계산에 넘길 사실 — 사전증여_10년, 기공제_10년, 수증자_미성년, 기한내신고 등(calc_gift_tax 와 같은 노드).

    Returns:
        증여재산가액(원·0·None), 계산(차액·기준금액·차감액·사유), 증여일, 판정불가_사유, 증여세(donor_relation 을 준 경우),
        적용 조문, 미적용 조문(사유 포함), 값 출처, 주의, 다루지 않는 것.
    """
    from tax_nodes import sangjeung_chujeong as M

    if market_value is None or price is None or market_value <= 0 or price < 0:
        raise ValueError("market_value(시가)는 0보다 커야 하고 price(대가)는 0 이상이어야 합니다")
    if direction not in (None, "저가양수", "고가양도"):
        raise ValueError("direction 은 저가양수 | 고가양도 중 하나여야 합니다: %r" % direction)
    if donor_relation is not None and donor_relation not in _관계:
        raise ValueError("donor_relation 은 %s 중 하나여야 합니다: %r" % (" | ".join(_관계), donor_relation))
    facts = dict(facts or {})
    for k in ("시가", "대가", "특수관계인", "거래유형", "거래관행상_정당한사유없음", "대금청산일"):
        if k in facts:
            raise ValueError("facts 에 %s 를 넣지 않는다 — 인자로 준다" % k)
    r = _자르기(M.저가고가_증여이익(year, market_value, price, 특수관계인=related_party, 거래유형=direction,
                             증여자관계=donor_relation, 세액사실=tax_facts,
                             거래관행상_정당한사유없음=no_legitimate_reason, 대금청산일=settlement_date, **facts))
    notes = []
    if r["증여재산가액"] is None:
        notes.append("입력이 모자라 판정하지 않았다 — 판정불가_사유에 적힌 사실을 채워 다시 부른다. 증여세가 없다는 뜻이 아니다")
    elif r["증여재산가액"] == 0:
        notes.append("§35 의 증여재산가액은 없다 — 그래도 양도자에게 소득세법 §101 부당행위계산이 따로 적용될 수 있다")
    else:
        notes.append("증여재산가액은 차액 전부가 아니라 기준금액(차감액)을 뺀 금액이다")
        if not donor_relation:
            notes.append("donor_relation 이 없어 증여세는 계산하지 않았다 — 증여재산공제가 관계에 따라 달라진다")
    if (r.get("계산") or {}).get("거래유형") == "고가양도":
        notes.append("고가 양도에서 이익을 얻은 자는 양도자다 — 증여재산가액만큼은 양도가액에서 빼고 양도소득세를 계산한다(소득세법 §96③2호, 이 도구는 계산하지 않는다)")
    r["주의"] = notes
    r["다루지 않는 것"] = LOW_PRICE_NOT_COVERED
    return r


_종류 = ("배우자등양도", "우회양도", "취득자금", "채무상환")


def judge_gift_presumption(
    year: int,
    kind: str,
    amount: int | None = None,
    transferee_relation: str | None = None,
    proven_amount: int | None = None,
    age: int | None = None,
    donor_relation: str | None = None,
    facts: dict | None = None,
    tax_facts: dict | None = None,
) -> dict:
    """Korea Inheritance and Gift Tax Act arts. 44-45: judges whether a transfer of property to a spouse or lineal relative is presumed a gift (and the exceptions: auction, bankruptcy, public sale, proven payment), and whether funds used to buy property or repay debt are presumed a gift (unproven amount vs the lesser of 20% and KRW 200 million, plus the NTS exclusion thresholds by age). Returns the statute trail.

    증여로 '추정'하는 두 규정을 판정한다. 추정이므로 반증(대가 지급·자금 출처 입증)으로 깨진다.

    배우자등양도(§44①③): 배우자·직계존비속에게 양도한 재산은 양도한 때 그 재산의 가액을 증여받은 것으로 추정한다.
        경매·파산·공매로 처분됐거나, 대가를 받고 양도한 사실이 명백하면(시행령 §33③ — 등기재산 교환, 신고한 소득·상속·수증재산
        이나 소유재산 처분대금으로 대가를 지급한 사실 입증) 추정하지 않는다.
    우회양도(§44②): 특수관계인에게 양도한 재산을 그 특수관계인이 3년 이내에 당초 양도자의 배우자·직계존비속에게 다시 양도하면
        추정한다. 당초 양도자와 중간 양수자의 소득세 결정세액 합계가 추정할 경우의 증여세액보다 크면 추정하지 않는다.
    취득자금(§45①)·채무상환(§45②): 출처가 입증된 금액이 취득가액(상환금액)에 모자라고, 모자란 금액이 취득가액의 20%와 2억원 중
        적은 금액 이상이면 모자란 금액을 증여받은 것으로 추정한다. 10년 이내 취득·상환 합계가 국세청장이 정한 금액(연령별
        주택·기타재산·채무상환·총액한도)에 미달하면 추정하지 않는다(시행령 §34②, 상속세 및 증여세 사무처리규정 §42).
    입력이 모자라면 추정하지 않고 증여추정=None 과 판정불가_사유를 돌려준다.

    Args:
        year: 양도일·취득일·상환일이 속하는 연도. 기준 조회 키이며 필수다. 검증되지 않은 연도는 계산을 거부한다.
        kind: "배우자등양도" | "우회양도" | "취득자금" | "채무상환".
        amount: 배우자등양도 — 양도한 때의 재산가액(상증법 평가액). 우회양도 — 다시 양도한 당시의 재산가액.
            취득자금 — 취득재산의 가액. 채무상환 — 상환금액.
        transferee_relation: (배우자등양도·우회양도) 당초 양도자가 본 양수자의 관계 — "배우자" | "직계존속" | "직계비속" | 그 밖.
        proven_amount: (취득자금·채무상환) 출처가 입증된 금액 합계 — 신고·과세된 소득, 신고·과세된 상속·수증재산,
            재산 처분대금·부채로 그 취득·상환에 직접 쓴 금액(시행령 §34① 각 호). 항목별로 주려면 facts 의 입증금액.
        age: (취득자금·채무상환) 취득일·상환일 현재 나이. 배제기준 판정에 쓴다.
        donor_relation: (취득자금·채무상환) 증여자로 볼 사람의 관계. 주면 증여세까지 계산한다 — 추정 규정은 증여자를 정하지 않는다.
            배우자등양도·우회양도는 transferee_relation 에서 정해지므로 주지 않는다.
        facts: 그 밖의 사실(키는 한국어 그대로).
            배우자등양도 — 양도일, 양도대가, 처분사유("경매"|"파산"|"공매"),
                대가지급_입증 [{"방법": "교환"|"신고소득"|"상속수증재산"|"재산처분대금", "금액": 원}].
            우회양도 — 특수관계인(bool, 당초 양도자와 중간 양수자), 중간양수일, 재양도일, 당초양도자_소득세결정세액,
                중간양수자_소득세결정세액, 추정시_증여세액(없으면 증여세 노드로 계산), 처분사유, 대가지급_입증, 양도대가.
            취득자금·채무상환 — 입증금액 {"소득": 원, "상속수증": 원, "처분대금_부채": 원}, 10년내_주택취득가액,
                10년내_기타재산취득가액, 10년내_채무상환금액(이번 건 포함), 증여사실_확인(bool), 취득일, 상환일.
        tax_facts: 증여세 계산에 넘길 사실 — 사전증여_10년, 기공제_10년, 수증자_미성년 등.

    Returns:
        증여추정(True·False·None), 증여재산가액, 계산, 판정불가_사유, 추정배제(사유), 증여세(계산한 경우),
        적용 조문, 미적용 조문(사유 포함), 값 출처, 주의, 다루지 않는 것.
    """
    from tax_nodes import sangjeung_chujeong as M

    if kind not in _종류:
        raise ValueError("kind 는 %s 중 하나여야 합니다: %r" % (" | ".join(_종류), kind))
    if amount is not None and amount < 0:
        raise ValueError("amount 는 0 이상이어야 합니다")
    if donor_relation is not None and donor_relation not in _관계:
        raise ValueError("donor_relation 은 %s 중 하나여야 합니다: %r" % (" | ".join(_관계), donor_relation))
    facts = dict(facts or {})
    notes = []
    if kind in ("배우자등양도", "우회양도"):
        if donor_relation is not None:
            raise ValueError("배우자등양도·우회양도는 donor_relation 을 주지 않는다 — transferee_relation 에서 정해진다")
        if transferee_relation is None:
            raise ValueError("배우자등양도·우회양도는 transferee_relation(양도자가 본 양수자의 관계)이 필요합니다")
        for k in ("양수자관계", "재산가액", "우회양도", "재양도_양수자관계", "재양도_재산가액"):
            if k in facts:
                raise ValueError("facts 에 %s 를 넣지 않는다 — kind·amount·transferee_relation 인자로 준다" % k)
        if kind == "배우자등양도":
            r = M.배우자등양도_증여추정(year, 양수자관계=transferee_relation, 재산가액=amount, 세액사실=tax_facts, **facts)
        else:
            r = M.배우자등양도_증여추정(year, 세액사실=tax_facts, 우회양도=True, 재양도_양수자관계=transferee_relation,
                                 재양도_재산가액=amount, **facts)
        if r["증여추정"] is False and r.get("추정배제"):
            notes.append("추정이 배제되면 증여가 아니라 양도다 — 대가가 시가와 다르면 judge_low_price_transfer_gift 로 §35 를, 양도자는 양도소득세를 따로 본다")
        if r["증여추정"]:
            notes.append("증여로 추정되면 그 재산의 가액 전부가 증여재산가액이다. 실제로 대가를 치렀다면 그 사실을 시행령 §33③ 각 호의 방법으로 입증해야 추정이 깨진다")
    else:
        if amount is None:
            raise ValueError("취득자금·채무상환은 amount(취득재산의 가액 또는 상환금액)가 필요합니다")
        for k in ("취득재산가액", "채무상환금액", "입증금액_합계", "연령", "자금유형"):
            if k in facts:
                raise ValueError("facts 에 %s 를 넣지 않는다 — amount·proven_amount·age 인자로 준다" % k)
        if proven_amount is not None and facts.get("입증금액") is not None:
            raise ValueError("proven_amount 와 facts 의 입증금액 중 하나만 줍니다")
        kw = {"취득재산가액": amount} if kind == "취득자금" else {"채무상환금액": amount}
        r = M.취득자금_증여추정(year, 증여자관계=donor_relation, 세액사실=tax_facts, 입증금액_합계=proven_amount, 연령=age, **kw, **facts)
        if r["증여추정"]:
            notes.append("추정되는 금액은 출처가 입증되지 않은 금액이다. 증여자가 누구인지는 이 규정이 정하지 않는다"
                         + ("" if donor_relation else " — donor_relation 이 없어 증여세는 계산하지 않았다"))
        if r["증여추정"] is False and "사무처리규정" in str(r.get("추정배제") or ""):
            notes.append("국세청 훈령의 배제기준에 미달해 추정하지 않는다 — 증여받은 사실이 따로 확인되면 과세된다(사무처리규정 §42②)")
    r = _자르기(r)
    if r["증여추정"] is None:
        notes.append("입력이 모자라 판정하지 않았다 — 판정불가_사유에 적힌 사실을 채워 다시 부른다. 추정되지 않는다는 뜻이 아니다")
    r["종류"] = kind
    r["주의"] = notes
    r["다루지 않는 것"] = PRESUMPTION_NOT_COVERED
    return r
