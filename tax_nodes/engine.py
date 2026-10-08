"""세금엔진 4층 — 조문 노드 실행기 (2026-09-22 파일럿).

왜 만드는가
-----------
지금까지 calc_* 함수 하나가 여러 조문을 한 몸에 담고 있었다. calc_property_tax는
지방세법 §110①·§110③·§111①·§111의2·§112·§151·§122를 한 함수 안에서 처리한다.
2026-08-30 사고(§110③ 과세표준상한제 누락)가 오래 안 잡힌 이유가 이 구조다 —
함수는 "재산세"라는 덩어리였고, 어느 항이 반영됐고 어느 항이 빠졌는지 셀 방법이
없었다. scripts/coverage_audit.py가 "노드가 참조하는 조문"만 셀 수 있었던 것도
계산기 쪽에 조문 단위 노드가 없었기 때문이다.

여기서는 조·항·호 하나를 함수 하나(노드)로 만들고, 계산을 노드의 합성으로 바꾼다.

  - 노드 = 조문 하나. id·법령·조·항·호·MST·원문·시행일·종료일을 들고 있다.
  - 계산은 "무엇이 필요한가"를 따라가는 수요 기반(pull) 해석이다. 호출 순서를
    사람이 적지 않는다. §112①1호가 산출세액을 필요로 하면 §111①이 불린다.
  - "~에도 불구하고"(§111의2① → §111①3호나목)는 우선순위 + 제외 관계로 적는다.
    같은 산출물을 내는 노드가 여럿일 때 우선순위가 앞선 노드부터 시도하고,
    요건 미충족으로 미적용을 돌려주면 다음 노드로 내려간다.
  - 적용되지 않은 조문도 기록에 남는다. "§122 세부담상한 — 단서로 주택 제외"가
    결과에 찍힌다. 2026-08-30에 없던 것이 바로 이 줄이다.

무엇을 하지 않는가
------------------
원문을 파싱해서 자동으로 실행하지 않는다. 노드 본문(산식·요건)은 사람이 옮긴다.
이 모듈이 주는 것은 "옮긴 결과가 어느 조문에 붙어 있는지"를 기계가 셀 수 있게
만드는 구조이고, 옮기지 않은 조문을 차집합으로 드러내는 것이다.

의존
----
값(세율표·비율·상한율)은 기존 1층 data/tax_params.json에서 읽는다. 이 층은
상수를 새로 만들지 않는다. 산식만 조문 단위로 쪼갠다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

_없음 = object()

_항기호 = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


class 조문없음(LookupError):
    """그 산출물을 내는 노드가 등록돼 있지 않다 — 아직 옮기지 않은 조문이다."""


class 순환참조(RuntimeError):
    """노드 의존이 서로를 물고 있다."""


class 실효(RuntimeError):
    """기준일이 조문의 시행일·종료일 밖이다(일몰·미시행)."""


class 미적용:
    """조문은 있으나 이 사안에는 적용되지 않는다. 노드 본문이 이것을 돌려준다.

    값이 아니라 사유를 나른다. 결과 기록에 '적용 안 됨'으로 찍히는 것이 핵심이다 —
    누락(조문이 아예 없음)과 미적용(조문을 보고 안 쓰기로 함)은 다른 사건이다.
    """

    __slots__ = ("사유",)

    def __init__(self, 사유: str):
        self.사유 = 사유

    def __repr__(self):
        return "미적용(%r)" % self.사유


@dataclass(frozen=True)
class 조문:
    id: str
    법령: str
    조: str
    #: 이 노드가 속한 세목("재산세"·"종부세"…). 같은 이름의 산출물이라도 세목이 다르면
    #: 서로 보이지 않는다. 재산세 공정시장가액비율(영 §109①2호)과 종부세 공정시장가액비율
    #: (영 §2의4①)이 둘 다 "공정시장가액비율"인데 값이 다르므로, 세목으로 갈라놓지 않으면
    #: 조용히 섞인다. 빈 값은 모든 세목에서 보이는 공용 노드.
    세목: str = ""
    항: str = ""
    호: str = ""
    목: str = ""
    제목: str = ""
    mst: str = ""
    원문: str = ""
    시행일: str = ""          # YYYYMMDD. 빈 값이면 검사하지 않는다.
    종료일: str = ""          # 일몰 조항. 빈 값이면 무기한.
    산출: tuple = ()
    필요: tuple = ()
    준용: tuple = ()          # 이 조문이 끌어다 쓰는 다른 조문 id
    제외: tuple = ()          # 이 조문이 배제하는 다른 조문 id ("~에도 불구하고")
    우선순위: int = 10        # 같은 산출물끼리 낮은 값 먼저 시도
    비고: str = ""
    fn: Optional[Callable] = None

    @property
    def 표기(self) -> str:
        s = "%s §%s" % (self.법령, self.조)
        if self.항:
            i = int(self.항)
            s += _항기호[i - 1] if 1 <= i <= len(_항기호) else "제%s항" % self.항
        if self.호:
            s += "%s호" % self.호
        if self.목:
            s += "%s목" % self.목
        return s


_등록부: dict[str, 조문] = {}
_산출표: dict[str, list[str]] = {}


def 등록(n: 조문) -> 조문:
    if n.id in _등록부:
        raise ValueError("노드 id 중복: %s" % n.id)
    _등록부[n.id] = n
    for 이름 in n.산출:
        _산출표.setdefault(이름, []).append(n.id)
        _산출표[이름].sort(key=lambda i: (_등록부[i].우선순위, i))
    return n


_현재세목 = ""


def 세목설정(이름: str) -> None:
    """이 모듈에서 앞으로 등록되는 노드의 기본 세목을 정한다. 파일 맨 위에서 한 번 부른다."""
    global _현재세목
    _현재세목 = 이름


def 노드(**kw):
    """조문 하나를 노드로 등록하는 데코레이터."""
    kw.setdefault("세목", _현재세목)

    def deco(fn):
        등록(조문(fn=fn, **kw))
        return fn
    return deco


def 전체() -> dict[str, 조문]:
    return dict(_등록부)


def 참조조문() -> set[tuple]:
    """등록된 노드가 덮고 있는 (법령, 조) 집합 — 커버리지 감사가 쓰는 입력."""
    return {(n.법령, n.조) for n in _등록부.values()}


class 실행:
    """사실 + 기준연도를 받아 노드를 수요 기반으로 풀어내는 실행기."""

    def __init__(self, 사실: dict, 연도: int, 기준일: str = "", 세목: str = ""):
        self.사실 = dict(사실)
        self.연도 = 연도
        self.기준일 = 기준일
        self.세목 = 세목
        self.계산값: dict[str, Any] = {}
        self.기록: list[dict] = []
        self.미적용목록: list[dict] = []
        self.상수근거: dict[str, str] = {}
        self._진행중: set[str] = set()
        self._끝난노드: set[str] = set()

    def 점검(self, *노드ids: str) -> None:
        """산출물이 필요 없어 수요 기반 해석이 건드리지 않는 조문을 일부러 돌린다.

        "이 조문을 봤고, 적용하지 않기로 했다"를 기록에 남기기 위한 것이다.
        누락과 미적용을 가르는 줄이 여기서 생긴다.
        """
        for nid in 노드ids:
            n = _등록부.get(nid)
            if n is None:
                raise 조문없음("점검 대상 노드가 없습니다: %s" % nid)
            self._실행(n)

    # -- 값 조회 ---------------------------------------------------------
    def 값(self, 이름: str, 기본: Any = _없음) -> Any:
        if 이름 in self.계산값:
            return self.계산값[이름]
        if 이름 in self.사실 and self.사실[이름] is not None:
            v = self.사실[이름]
            self.계산값[이름] = v
            self.기록.append({"순번": len(self.기록) + 1, "노드": "", "표기": "(호출자 지정)",
                              "제목": 이름, "근거": "호출자가 직접 넘긴 값", "산출": 이름,
                              "값": v, "상태": "입력"})
            return v

        후보 = [i for i in _산출표.get(이름, [])
              if not self.세목 or _등록부[i].세목 in ("", self.세목)]
        if not 후보:
            if 기본 is not _없음:
                return 기본
            raise 조문없음(
                "'%s'를 산출하는 조문 노드가 없습니다. 아직 옮기지 않은 조문이면 "
                "tax_nodes에 조문 단위로 추가하십시오." % 이름)

        마지막사유 = None
        for nid in 후보:
            r = self._실행(_등록부[nid])
            if isinstance(r, 미적용):
                마지막사유 = r.사유
                continue
            if 이름 in self.계산값:
                return self.계산값[이름]
        if 기본 is not _없음:
            return 기본
        raise 조문없음("'%s'를 낼 수 있는 조문이 모두 미적용입니다 (마지막 사유: %s)"
                    % (이름, 마지막사유))

    def 있나(self, 이름: str) -> bool:
        return (이름 in self.계산값
                or (이름 in self.사실 and self.사실[이름] is not None)
                or bool(_산출표.get(이름)))

    def 사실값(self, 이름: str, 기본: Any = None) -> Any:
        """노드를 돌리지 않고 호출자가 준 사실만 본다(요건 판정용)."""
        return self.사실.get(이름, 기본)

    # -- 노드 실행 -------------------------------------------------------
    def _실행(self, n: 조문):
        if n.id in self._끝난노드:
            return None
        if n.id in self._진행중:
            raise 순환참조("%s 가 자기 자신을 필요로 합니다" % n.표기)

        if n.종료일 and self.기준일 and self.기준일 > n.종료일:
            self._남김(n, None, "실효", "기준일 %s > 종료일 %s (일몰)" % (self.기준일, n.종료일))
            self._끝난노드.add(n.id)
            return 미적용("일몰")
        if n.시행일 and self.기준일 and self.기준일 < n.시행일:
            self._남김(n, None, "미시행", "기준일 %s < 시행일 %s" % (self.기준일, n.시행일))
            self._끝난노드.add(n.id)
            return 미적용("미시행")

        self._진행중.add(n.id)
        try:
            r = n.fn(self)
        finally:
            self._진행중.discard(n.id)
        self._끝난노드.add(n.id)

        if isinstance(r, 미적용):
            self._남김(n, None, "미적용", r.사유)
            self.미적용목록.append({"표기": n.표기, "제목": n.제목, "사유": r.사유})
            return r

        if isinstance(r, dict):
            값들 = r
        elif len(n.산출) == 1:
            값들 = {n.산출[0]: r}
        else:
            raise ValueError("%s 는 산출이 %d개인데 dict를 돌려주지 않았습니다"
                             % (n.표기, len(n.산출)))

        for k, v in 값들.items():
            self.계산값[k] = v
        self._남김(n, 값들, "적용", "")
        return None

    def _남김(self, n: 조문, 값들, 상태, 사유):
        self.기록.append({
            "순번": len(self.기록) + 1,
            "노드": n.id,
            "표기": n.표기,
            "제목": n.제목,
            "근거": "%s (MST %s)" % (n.표기, n.mst or "?"),
            "산출": "·".join(n.산출),
            "값": 값들,
            "상태": 상태,
            "사유": 사유,
        })

    # -- 결과 ------------------------------------------------------------
    def 근거표(self) -> list[dict]:
        return list(self.기록)

    def 적용조문(self) -> list[str]:
        return [r["표기"] for r in self.기록 if r["상태"] == "적용"]
