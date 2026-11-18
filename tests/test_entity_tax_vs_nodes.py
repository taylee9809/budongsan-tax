"""구 가계산 모듈(entity_tax.py)의 법인 취득세·매각세와 조문 노드(tax_nodes/chwideuk.py · beobin.py)의 격자 대조.

entity_tax.py 는 고치지 않는다. 두 쪽이 갈라지면 여기서 드러난다 — 어느 쪽이 원문과 맞는지 확인해 findings 에 적는다.
2026-11-17 현재 격자 전체에서 일치한다. 다만 entity_tax.corp_acq_tax 는 시행령 §28의2(저가주택 등 중과 예외)와
취득일·시가표준액 입력이 없어 그 구간은 비교할 수 없다(호스팅 도구 calc_corporate_acquisition_tax 가 다룬다).
"""
import itertools

import pytest

import entity_tax
from tax_nodes.beobin import 법인_부동산양도
from tax_nodes.chwideuk import 취득세_부동산

취득격자 = list(itertools.product(
    (50_000_000, 150_000_000, 333_333_333, 1_000_000_000, 2_500_000_000),
    ("house", "shop"), (59, 85, 85.01, 120), (False, True)))


@pytest.mark.parametrize("price,kind,area,metro", 취득격자)
def test_corp_acquisition_tax(price, kind, area, metro):
    old, _ = entity_tax.corp_acq_tax(price, kind, area, metro)
    new = 취득세_부동산(price, 2026, "주택유상" if kind == "house" else "유상.농지외", 취득일="2026-03-02", 법인=True,
                   전용면적=area if kind == "house" else None, 대도시_법인설립전입_부동산=metro or None)
    assert abs(old - new["총납부세액"]) <= 3        # 구 모듈은 합산 세율에 한 번, 노드는 세목별로 원 미만을 버린다


def _node_total(base, sales):
    r = 법인_부동산양도(2026, sales, 과세표준=base)
    return (r["법인세_각사업연도소득"] + r["토지등양도소득_법인세"]
            + r["법인지방소득세_각사업연도소득"] + r["법인지방소득세_토지등양도"])


매각격자 = list(itertools.product(
    (-1, 0, 1, 50_000_000, 200_000_000, 200_000_001, 700_000_000, 25_000_000_000, 400_000_000_000),
    ("house", "shop", "land"), (0, 150_000_000, 19_900_000_000, 299_900_000_000), (False, True)))


@pytest.mark.parametrize("gain,kind,other,nonbiz", 매각격자)
def test_corp_exit_tax(gain, kind, other, nonbiz):
    old, _ = entity_tax.corp_exit_tax(gain, kind, other_corp_base=other, nonbiz_land=nonbiz)
    if gain <= 0:
        assert old == 0
        return
    종류 = "주택" if kind == "house" else ("비사업용토지" if nonbiz else "그밖")
    sale = {"라벨": "A", "종류": 종류, "양도금액": 10 ** 12 + gain, "장부가액": 10 ** 12}
    new = _node_total(other + gain, [sale]) - _node_total(other, [])       # 구 모듈은 다른 소득 위에 얹힌 증분을 낸다
    assert abs(old - new) <= 5
