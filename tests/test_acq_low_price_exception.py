"""취득세 저가주택 중과 예외(영 §28의2 1호) — 판정기와 실행 노드 격자 대조.

판정기(tax_judgment.judge_acquisition_homes_and_rate)는 기준액을 모르고 실행 노드
지방세법시행령-28의2(조립 함수 주택중과_예외)에 묻는다. 여기서는 (1) 둘이 격자 전체에서 같은 답을
내는지, (2) 노드가 법령 원문(수도권 1억·그 외 2억 이하, 정비구역 제외, 2025-01-02 이후 취득분)과
맞는지, (3) 취득 주택 지정 규칙을 본다.

2026-11-17: 취득하는 주택은 저가주택이어도 주택 수에 든다(영 §28의4① '취득하는 주택을 포함하여', ⑥ 괄호 '취득하는 주택을
포함하지 아니한 소유주택'). 중과에서 빠지는 것은 영 §28의2 이고, 주택 수에서 빠지는 것(⑥1호가목)은 보유 중인 저가주택이다.
(4) 판정기와 세액 계산 노드(취득세_부동산)가 같은 목록에서 같은 중과 결론을 내는지도 본다.
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
    assert r["산입_주택수"] == 1                     # 취득하는 주택은 ⑥으로 빠지지 않는다(영 §28의4①·⑥ 괄호)


@pytest.mark.parametrize("std,수도권,정비,일", 격자)
@pytest.mark.parametrize("조정", (True, False))
def test_다주택_취득_판정기와_노드(std, 수도권, 정비, 일, 조정):
    예외 = _노드(std, 수도권, 정비, 일)
    homes = [큰집, 큰집, 큰집, _집(std, 수도권, 정비, 라벨="신규")]
    r = tj.judge_acquisition_homes_and_rate(homes, 조정, acquire_date=일)
    assert r["저가주택_중과예외"] is 예외
    assert r["중과여부"] is (not 예외)          # 예외가 아니면 4주택 — 조정·비조정 모두 12%
    assert r["산입_주택수"] == 4                     # 저가주택이어도 취득분은 센다 — 중과만 영 §28의2로 빠진다


@pytest.mark.parametrize("std,수도권,정비,일", 격자)
def test_보유_저가주택은_주택수에서_빠진다(std, 수도권, 정비, 일):
    """소유 주택의 ⑥1호가목(지방세법시행령-28의4-6-1 노드)과 취득 주택의 영 §28의2 1호 노드가 같은 기준을 쓴다."""
    예외 = _노드(std, 수도권, 정비, 일)
    r = tj.judge_acquisition_homes_and_rate([_집(std, 수도권, 정비), dict(큰집, 취득대상=True)], True, acquire_date=일)
    assert r["산입_주택수"] == (1 if 예외 else 2)
    assert r["저가주택_중과예외"] is False           # 취득분(큰집)은 저가주택이 아니다
    assert r["중과여부"] is (not 예외)               # 조정 2주택 8% ↔ 1주택


@pytest.mark.parametrize("std,수도권,정비,일", 격자[::7])
@pytest.mark.parametrize("조정", (True, False))
@pytest.mark.parametrize("보유", (0, 1, 2, 3))
def test_판정기와_세액계산_노드가_같은_결론(std, 수도권, 정비, 일, 조정, 보유):
    """같은 homes 목록을 판정기와 취득세_부동산(법 §13의3·§13의2① 노드)에 넣으면 중과 여부·세율이 같다."""
    from tax_nodes.chwideuk import 취득세_부동산
    homes = [dict(큰집) for _ in range(보유)] + [_집(std, 수도권, 정비, 취득대상=True)]
    j = tj.judge_acquisition_homes_and_rate(homes, 조정, acquire_date=일)
    일2 = 일 or "2026-03-02"
    n = 취득세_부동산(300_000_000, int(일2[:4]), "주택유상", 일 or "", 조정대상지역=조정, 보유주택목록=homes)
    중과 = n["세율 내역"]["중과유형"] is not None
    assert 중과 is j["중과여부"]
    if 중과:
        assert n["적용세율(표준+중과+조례)"] == j["취득세율"]
    else:
        assert n["적용세율(표준+중과+조례)"] == 0.01      # 3억 — §11①8호 6억 이하 1%


@pytest.mark.parametrize("std,수도권,정비,일", 격자[::3])
def test_법인_세액계산_노드도_영28의2를_읽는다(std, 수도권, 정비, 일):
    from tax_nodes.chwideuk import 취득세_부동산
    예외 = _노드(std, 수도권, 정비, 일)
    일2 = 일 or "2026-03-02"
    n = 취득세_부동산(std, int(일2[:4]), "주택유상", 일 or "", 법인=True, 시가표준액=std, 수도권=수도권, 정비구역=정비)
    assert (n["적용세율(표준+중과+조례)"] == 0.12) is (not 예외)
    assert (n["세율 내역"]["중과유형"] == "법인") is (not 예외)
    if 예외:   # 중과가 빠지면 지방교육세·농특세도 일반 주택 유상거래 산식
        assert n["적용세율(표준+중과+조례)"] == 0.01 and n["세율 내역"]["지방교육세율"] == 0.001 and n["세율 내역"]["농특세율"] == 0.002


def test_대도시_법인_중과_경로는_영28의2를_적용하지_않고_기록만_남긴다():
    """법 §13②가 끌어오는 §13의2①1호 세율에 영 §28의2가 미치는지는 확인하지 못했다 — 종전 계산(12%)을 유지한다."""
    from tax_nodes.chwideuk import 취득세_부동산
    n = 취득세_부동산(90_000_000, 2026, "주택유상", "2026-03-02", 시가표준액=90_000_000, 수도권=True, 대도시_법인설립전입_부동산=True)
    assert n["적용세율(표준+중과+조례)"] == 0.12
    assert any("§13② 경로 미적용" in k for k in n["값 출처"])


def test_부속토지는_자체_가액과_전체_주택_가액을_나눠_받는다():
    신규 = dict(큰집, 취득대상=True)
    # 보유 부속토지: ⑥5호는 부속토지 자체 1억, ⑥1호가목은 전체 주택(수도권 1억·그 외 2억)
    땅 = {"종류": "부속토지", "시가표준액": 150_000_000, "수도권": False}
    assert tj.count_acquisition_homes([땅, 신규], "2026-03-02")["산입_주택수"] == 2            # 전체 가액을 모르면 1호로 빼지 않는다(종전과 같다)
    assert tj.count_acquisition_homes([dict(땅, 전체주택_시가표준액=190_000_000), 신규], "2026-03-02")["산입_주택수"] == 1
    assert tj.count_acquisition_homes([dict(땅, 전체주택_시가표준액=210_000_000), 신규], "2026-03-02")["산입_주택수"] == 2
    assert tj.count_acquisition_homes([dict(땅, 시가표준액=80_000_000, 전체주택_시가표준액=900_000_000), 신규], "2026-03-02")["산입_주택수"] == 1   # ⑥5호
    # 부속토지만 취득: 저가주택 여부는 전체 주택 가액 — 부속토지 8천만원이어도 전체가 3억이면 중과
    취득땅 = {"종류": "부속토지", "시가표준액": 80_000_000, "전체주택_시가표준액": 300_000_000, "수도권": True, "취득대상": True}
    r = tj.judge_acquisition_homes_and_rate([취득땅], False, is_corporation=True, acquire_date="2026-03-02")
    assert r["취득세율"] == 0.12 and r["저가주택_중과예외"] is False and r["취득주택_저가판정"]["판정가액_키"] == "전체주택_시가표준액"
    assert r["산입_주택수"] == 1                    # 1억 이하 부속토지여도 취득분은 ⑥5호로 빠지지 않는다
    # 종전 입력(시가표준액 하나)은 그대로 — 전체 주택 가액으로 읽고 그 사실을 플래그에 남긴다
    r = tj.judge_acquisition_homes_and_rate([{"종류": "부속토지", "시가표준액": 80_000_000, "수도권": True}], False,
                                            is_corporation=True, acquire_date="2026-03-02")
    assert r["저가주택_중과예외"] is True and r["중과여부"] is False
    assert any("전체주택_시가표준액" in f for f in r["플래그"])


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
