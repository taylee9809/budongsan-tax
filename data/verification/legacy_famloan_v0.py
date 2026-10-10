# -*- coding: utf-8 -*-
"""수정 전 스냅샷 — judge_family_loan.

결함: 적정이자율 4.6%를 전 기간에 적용(8.5%〔~2012-02-27〕·6.9%〔2012-02-28~2016-03-06〕
연혁 부재 — 법인규칙 §43② eflaw 실측), 비특수관계자 정당사유 예외(§41의4③) 입력 부재.
"""


def _cite(rule, basis, grade="B"):
    return {"규칙": rule, "근거": basis, "등급": grade}


FAIR_INTEREST_RATE = 0.046
LOAN_GIFT_THRESHOLD = 10_000_000


def judge_family_loan(loan_amount, agreed_interest_rate=0.0):
    benefit = int(loan_amount * FAIR_INTEREST_RATE - loan_amount * agreed_interest_rate)
    taxable = benefit >= LOAN_GIFT_THRESHOLD
    safe_line = int(LOAN_GIFT_THRESHOLD / FAIR_INTEREST_RATE)
    return {
        "연간_증여이익": max(benefit, 0),
        "과세대상": taxable,
        "판정": (f"이익 {benefit:,}원 ≥ 1천만 — 대출일 기준 증여재산가액 (매년 재계산: 1년 단위 재대출 간주)"
                  if taxable else f"이익 {max(benefit,0):,}원 < 1천만 — 과세 제외"),
        "무상대출_안전선": safe_line,
        "근거": [],
        "플래그": [],
    }
