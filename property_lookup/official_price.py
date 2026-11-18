# -*- coding: utf-8 -*-
"""공시가격·토지특성(용도지역) 조회 — 기준일에 적용되는 공시연도로 고른다.

원본: korea-realestate-mcp official_price.py (9ecd75a). NED 응답 처리(연도 중복행 제거,
공동주택 호 중복 제거, 공동주택은 연도 지정 조회)는 원본의 실측 대응을 그대로 따른다.

원본과 다른 점 — 기준연도 선택
  원본은 매물 시세 비교용이라 항상 최신 연도를 썼다. 세금은 기준일 현재 "공시된" 가격을 쓴다
  (지방세법 제4조① 시가표준액, 소득세법 제99조① 기준시가). 공시가격은 매년 1월 1일 기준으로
  다음 기한까지 공시된다(부동산 가격공시에 관한 법률 시행령).
      공동주택가격 4월 30일(§43①) · 개별주택가격 4월 30일(§38①) · 개별공시지가 5월 31일(§21①)
  그래서 기준일 D에 대해
      D가 그해 4월 1일 전           → 전년도 공시가격
      D가 4월 1일 ~ 공시 기한 사이   → 경계: 실제 공시일 전이면 전년도, 후면 당해. 두 연도 값을 모두 돌려준다
      D가 공시 기한 후              → 당해 공시가격
  재산세·종부세 과세기준일(6월 1일)은 항상 당해 연도다.
  분할·합병 필지 등의 추가 공시(개별공시지가 7월 1일 기준 등)는 다루지 않는다 — 플래그로 알린다.
"""
from __future__ import annotations

import statistics
from datetime import date
from typing import Optional

import httpx

from property_lookup.common import vworld_auth

# 원본은 http였다. 키가 평문으로 나가므로 같은 호스트의 /req/data(원본이 https로 실사용)와 맞춰 https로 쓴다.
# 실제 동작은 scripts/check_property_lookup.py로 국내 PC에서 확인한다(해외 IP는 서버가 연결을 끊는다).
NED_LAND_PRICE_URL = "https://api.vworld.kr/ned/data/getIndvdLandPriceAttr"
NED_HOUSE_PRICE_URL = "https://api.vworld.kr/ned/data/getIndvdHousingPriceAttr"
NED_APART_PRICE_URL = "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"
NED_LAND_CHAR_URL = "https://api.vworld.kr/ned/data/getLandCharacteristics"

# 공동주택가격 공시 대상은 아파트·연립·다세대다. 오피스텔은 주택 공시가격이 없다 —
# 시가표준액은 지자체 건물 시가표준액+개별공시지가, 양도 기준시가는 국세청 오피스텔 기준시가 고시를 따른다.
APART_TYPES = ("아파트", "연립", "다세대", "공동주택")
OFFICETEL_TYPES = ("오피스텔",)
HOUSE_TYPES = ("단독", "다가구", "다중주택", "한옥", "주택")
LAND_TYPES = ("토지", "나대지", "농지", "임야", "대지")
AREA_TOL = 3.0  # 전유면적 매칭 허용오차(㎡) — 원본 관례

# 공시 기한(월, 일)과 근거 — 부동산 가격공시에 관한 법률 시행령
PUBLISH_DEADLINE = {
    "공동주택가격": ((4, 30), "부동산 가격공시에 관한 법률 시행령 제43조①"),
    "개별주택가격": ((4, 30), "부동산 가격공시에 관한 법률 시행령 제38조①"),
    "개별공시지가": ((5, 31), "부동산 가격공시에 관한 법률 시행령 제21조①"),
}
BOUNDARY_START = (4, 1)  # 이 날 전에는 당해 공시가 나온 적이 없다고 본다


def applicable_years(base_date: date, kind: str) -> dict:
    """기준일에 적용되는 공시연도. {'연도': [우선, (경계면) 대안], '경계': bool, '근거': str}"""
    (m, d), law = PUBLISH_DEADLINE[kind]
    y = base_date.year
    if base_date < date(y, *BOUNDARY_START):
        return {"연도": [str(y - 1)], "경계": False,
                "근거": f"기준일이 {y}년 공시 전 — {y - 1}년 1월 1일 기준 {kind} ({law})"}
    if base_date <= date(y, m, d):
        return {"연도": [str(y - 1), str(y)], "경계": True,
                "근거": (f"기준일이 {y}년 {kind} 공시 기한({m}월 {d}일) 이전 구간 — 실제 공시일 전이면 {y - 1}년, "
                         f"후면 {y}년 가격이 적용된다. 해당 시·군·구 공시일 확인 필요 ({law})")}
    return {"연도": [str(y)], "경계": False,
            "근거": f"기준일이 {y}년 공시 기한 후 — {y}년 1월 1일 기준 {kind} ({law})"}


def property_kind(property_type: str) -> str:
    """'아파트' 등 → '공동주택' | '개별주택' | '토지' | '오피스텔'. 모르면 ''."""
    pt = property_type or ""
    if any(t in pt for t in OFFICETEL_TYPES):
        return "오피스텔"
    if any(t in pt for t in APART_TYPES):
        return "공동주택"
    if any(t in pt for t in HOUSE_TYPES):
        return "개별주택"
    if any(t in pt for t in LAND_TYPES):
        return "토지"
    return ""


def _ned_params(pnu: str, **extra) -> dict:
    p = dict(vworld_auth(), pnu=pnu, format="json", numOfRows=100, pageNo="1")
    p.update({k: v for k, v in extra.items() if v})
    return p


def _fields(payload: dict, root: str) -> list[dict]:
    rows = (payload.get(root) or {}).get("field") or []
    return rows if isinstance(rows, list) else [rows]


def _by_year(rows: list[dict], year_key: str = "stdrYear") -> dict[str, dict]:
    """연도별 1행 — NED가 오래된 연도부터 + 같은 연도 중복행('01'/'1')을 주는 실측 대응."""
    out: dict[str, dict] = {}
    for r in rows:
        y = str(r.get(year_key) or "")
        if y:
            out[y] = r
    return out


def _pick(by_year: dict[str, dict], years: list[str]) -> tuple[Optional[str], Optional[dict]]:
    for y in years:
        if y in by_year:
            return y, by_year[y]
    return None, None


def fetch_land_characteristics(client: httpx.Client, pnu: str, years: Optional[list[str]] = None) -> Optional[dict]:
    """토지특성 — 필지면적·용도지역·지목. years를 주면 그 연도 행, 없으면 최신 행.

    PNU 검증 게이트를 겸한다: 0행이면 None(원장에 없는 필지).
    """
    resp = client.get(NED_LAND_CHAR_URL, params=_ned_params(pnu))
    resp.raise_for_status()
    by_year = _by_year(_fields(resp.json(), "landCharacteristicss"))
    if not by_year:
        return None
    year, row = _pick(by_year, years or [])
    exact = row is not None
    if not exact:
        year = max(by_year)
        row = by_year[year]
    return {
        "필지면적_m2": float(row.get("lndpclAr") or 0) or None,   # 공부(토지대장) 면적
        "용도지역": row.get("prposArea1Nm") or "",
        "용도지역2": row.get("prposArea2Nm") or "",
        "지목": row.get("lndcgrCodeNm") or "",
        "이용상황": row.get("ladUseSittnNm") or "",
        "기준연도": year,
        "기준연도일치": exact if years else None,
        "보유연도": sorted(by_year),
    }


def fetch_land_price(client: httpx.Client, pnu: str, years: list[str]) -> dict:
    """개별공시지가(원/㎡). {'값': {연도: 원_m2}, '보유연도': [...]}"""
    resp = client.get(NED_LAND_PRICE_URL, params=_ned_params(pnu))
    resp.raise_for_status()
    by_year = {y: r for y, r in _by_year(_fields(resp.json(), "indvdLandPrices")).items() if r.get("pblntfPclnd")}
    return {"값": {y: int(by_year[y]["pblntfPclnd"]) for y in years if y in by_year},
            "보유연도": sorted(by_year)}


def fetch_house_price(client: httpx.Client, pnu: str, years: list[str]) -> dict:
    """개별주택가격(원, 토지+건물 통합). 다가구는 건물 한 동 전체 가격이다(원본 실측)."""
    resp = client.get(NED_HOUSE_PRICE_URL, params=_ned_params(pnu))
    resp.raise_for_status()
    by_year = {y: r for y, r in _by_year(_fields(resp.json(), "indvdHousingPrices")).items() if r.get("housePc")}
    return {"값": {y: int(by_year[y]["housePc"]) for y in years if y in by_year},
            "산정대지면적_m2": {y: float(by_year[y].get("calcPlotAr") or 0) or None for y in years if y in by_year},
            "보유연도": sorted(by_year)}


def _dedupe_units(rows) -> list[dict]:
    """공동주택가격 행을 호 단위로 1행씩 — NED가 같은 호를 2번씩 주는 실측 대응(순서 보존)."""
    seen, out = set(), []
    for r in rows:
        k = (r.get("pnu"), r.get("dongNm"), r.get("hoNm"), r.get("floorNm"), r.get("prvuseAr"), r.get("stdrYear"))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def fetch_apart_price(client: httpx.Client, pnu: str, year: str, dong: str = "", ho: str = "",
                      exclusive_area: Optional[float] = None) -> Optional[dict]:
    """공동주택가격 한 연도. 반드시 연도를 지정해 조회한다(원본 실측: 무지정 조회는 2006년부터 와서
    대단지는 100행이 최신 연도에 못 닿는다). 같은 호가 2번씩 오므로 호 키로 중복을 지운다.

    동·호를 주면 그 호의 값(신뢰: 확정). 동·호 없이 전유면적만 주면 ±3㎡ 세대 중위값(신뢰: 추정).
    둘 다 없으면 값을 내지 않는다 — 필지 전체 중위값은 세액 입력으로 쓸 수 없다.
    """
    resp = client.get(NED_APART_PRICE_URL, params=_ned_params(
        pnu, dongNm=dong, hoNm=ho, stdrYear=year, numOfRows=1000))
    resp.raise_for_status()
    rows = _dedupe_units(r for r in _fields(resp.json(), "apartHousingPrices") if r.get("pblntfPc"))
    if not rows:
        return None
    if ho:
        hits = [r for r in rows if str(r.get("hoNm") or "").strip() == str(ho).strip()
                and (not dong or str(r.get("dongNm") or "").strip() == str(dong).strip())]
        if len(hits) == 1:
            return {"원": int(hits[0]["pblntfPc"]), "신뢰": "확정",
                    "basis": f"동·호 지정({dong or '-'}/{ho}) 단일 세대",
                    "전유면적_m2": float(hits[0].get("prvuseAr") or 0) or None}
        return {"원": None, "신뢰": "확인 불가",
                "basis": f"동·호 지정({dong or '-'}/{ho})에 맞는 세대 {len(hits)}건 — 단일 세대로 특정되지 않음"}
    if exclusive_area:
        near = [r for r in rows if abs(float(r.get("prvuseAr") or 0) - exclusive_area) <= AREA_TOL]
        if near:
            return {"원": int(statistics.median(int(r["pblntfPc"]) for r in near)), "신뢰": "추정",
                    "basis": f"동·호 미상 — 전유면적 ±{AREA_TOL}㎡ {len(near)}세대 중위값. 세액 확정에는 동·호 지정 필요"}
    return {"원": None, "신뢰": "확인 불가",
            "basis": f"동·호와 전유면적이 없어 필지 {len(rows)}세대 중 대상 세대를 특정할 수 없음"}
