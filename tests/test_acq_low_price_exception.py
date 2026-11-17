"""취득세 저가주택 중과 예외(영 §28의2 1호) — 판정기와 실행 노드 격자 대조.

판정기(tax_judgment.judge_acquisition_homes_and_rate)는 기준액을 모르고 실행 노드
지방세법시행령-28의2(조립 함수 주택중과_예외)에 묻는다. 여기서는 (1) 둘이 격자 전체에서 같은 답을
내는지, (2) 노드가 법령 원문(수도권 1억·그 외 2억 이하, 정비구역 제외, 2025-01-02 이후 취득분)과
맞는지, (3) 취득 주택 지정 규칙을 본다.
"""
import itertools

import pytest

import tax_judgment as tj
from tax_nodes.chwideuk_gwase import 주택중과_예외

금액 = (1, 50_000_000, 99_999_999, 100_000_000, 100_000_001, 150_000_000,
      199_999_999, 200_000_000, 200_000_001, 300_000_000)
취득일 = (None, "2024-12-31", "2025-01-01", "2025-01-02", "2026-03-02")
격자 = list(itertools.product(금액, (True, False), (True, False), 취득일))
큰집 = {"종류": "주택", "시가표준액": 500_000_000, "수도권": True}


def _노드(std, 수도권, 정비, 일):
    return 주택중과_예외(취득일=일 or "", 시가표준액=std, 수도권=수도권, 정비구역=정비)["중과예외"]


def _원문(std, 수도권, 정비, 일):
    """영 §28의2 1호 + 영 35477호 부칙 §2 를 그대로 옮긴 독립 기준 — 노드가 틀리면 여기서 잡힌다."""
    if 정비:
        return False
    if 수도권 or (일 is not None and 일 < "2025-01-02"):
        return std <= 100_000_000
    return std <= 200_000_000


def _집(std, 수도권, 정비, **k):
    return dict({"종류": "주택", "시가표준액": std, "수도권": 수도권, "정비구역": 정비}, **k)


@pytest.mark.parametrize("std,수도권,정비,일", 격자)
def test_노드는_원문_기준과_같다(std, 수도권, 정비, 일):
    assert _노드(std, 수도권, 정비, 일) is _원문(std, 수도권, 정비, 일)


@pytest.mark.parametrize("std,수도권,정비,일", 격자)
def test_법인_취득_판정기와_노드(std, 수도권, 정비, 일):
    예외 = _노드(std, 수도권, 정비, 일)
    r = tj.judge_acquisition_homes_and_rate([_집(std, 수도권, 정비)], False, is_corporation=True, acquire_date=일)
    assert r["저가주택_중과예외"] is 예외
    assert r["중과여부"] is (not 예외)
    assert (r["취득세율"] == 0.12) is (not 예외)
    assert r["농특세율(과표대비)"] == (0.002 if 예외 else 0.010)
    assert r["산입_주택수"] == (0 if 예외 else 1)   # 주택 수 제외(영 §28의4⑥1호)도 같은 판정


@pytest.mark.parametrize("std,수도권,정비,일", 격자)
@pytest.mark.parametrize("조정", (True, False))
def test_다주택_취득_판정기와_노드(std, 수도권, 정비, 일, 조정):
    예외 = _노드(std, 수도권, 정비, 일)
    homes = [큰집, 큰집, 큰집, _집(std, 수도권, 정비, 라벨="신규")]
    r = tj.judge_acquisition_homes_and_rate(homes, 조정, acquire_date=일)
    assert r["저가주택_중과예외"] is 예외
    assert r["중과여부"] is (not 예외)          # 예외가 아니면 4주택 — 조정·비조정 모두 12%
    assert r["산입_주택수"] == (3 if 예외 else 4)


@pytest.mark.parametrize("std,수도권,정비,일", 격자)
def test_증여는_저가주택_예외와_무관(std, 수도권, 정비, 일):
    r = tj.judge_acquisition_homes_and_rate([_집(std, 수도권, 정비)], True, acquire_date=일,
                                            is_gift=True, gift_std_value=std)
    assert r["저가주택_중과예외"] is None
    assert r["취득세율"] == (0.12 if std >= 300_000_000 else 0.035)


def test_사업시행구역도_정비구역처럼_제외():
    home = {"종류": "주택", "시가표준액": 90_000_000, "수도권": True, "사업시행구역": True}
    r = tj.judge_acquisition_homes_and_rate([home], False, is_corporation=True, acquire_date="2026-03-02")
    assert r["취득세율"] == 0.12 and r["저가주택_중과예외"] is False


def test_취득_주택_지정_규칙():
    저가 = _집(90_000_000, True, False)
    # 취득대상 키가 라벨보다 앞선다
    r = tj.judge_acquisition_homes_and_rate([dict(큰집, 라벨="신규"), dict(저가, 취득대상=True)], False, is_corporation=True)
    assert r["저가주택_중과예외"] is True and r["취득주택_저가판정"]["취득주택"] == "주택"
    # 여러 채 + 지정 없음 → 종전 동작 + 플래그
    r = tj.judge_acquisition_homes_and_rate([큰집, 저가], False, is_corporation=True)
    assert r["취득세율"] == 0.12 and r["저가주택_중과예외"] is None
    assert any("취득 주택 미지정 — 저가주택 예외를 판정하지 못했다" in f for f in r["플래그"])
    # 지정이 둘 이상 → 고르지 않는다
    r = tj.judge_acquisition_homes_and_rate([dict(큰집, 라벨="신규"), dict(저가, 라벨="신규")], False, is_corporation=True)
    assert r["취득세율"] == 0.12 and any("취득 주택 미지정" in f for f in r["플래그"])
    # 시가표준액이 없으면 저가주택으로 추정하지 않는다
    r = tj.judge_acquisition_homes_and_rate([{"종류": "주택", "수도권": True}], False, is_corporation=True)
    assert r["취득세율"] == 0.12 and r["저가주택_중과예외"] is None
    assert any("시가표준액 미입력" in f for f in r["플래그"])


def test_일시적_2주택과_겹치면_저가주택이_먼저():
    homes = [dict(큰집, 라벨="종전"), _집(90_000_000, True, False, 라벨="신규")]
    r = tj.judge_acquisition_homes_and_rate(homes, True, acquire_date="2026-03-02", prev_disposal_date="2027-03-02")
    assert r["일시적2주택"] is True and r["저가주택_중과예외"] is True
    assert r["판정"].startswith("저가주택")
    assert not any("추징" in f for f in r["플래그"])    # 저가주택 예외에는 3년 내 처분 사후관리가 없다


def test_법인은_일시적_2주택으로_빠지지_않는다():
    homes = [dict(큰집, 라벨="종전"), dict(큰집, 라벨="신규")]
    r = tj.judge_acquisition_homes_and_rate(homes, True, is_corporation=True,
                                            acquire_date="2026-03-02", prev_disposal_date="2027-03-02")
    assert r["취득세율"] == 0.12 and r["중과여부"] is True
