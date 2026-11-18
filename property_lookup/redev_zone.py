# -*- coding: utf-8 -*-
"""정비구역 편입 여부 — 토지이용계획속성(필지) + UPIS 정비구역 폴리곤(좌표, 선택).

원본: korea-realestate-mcp regulation.py (9ecd75a) check_redev_zone·parse_land_use_redev.
판정 규칙은 원본 그대로다.
  · 토지이용계획속성(getLandUseAttr)의 지역지구명이 정비사업 계열이고 저촉여부가 '포함'·'저촉'이면 편입.
    '접함'은 옆 필지가 구역이라는 뜻이라 편입으로 세지 않는다.
    원본 실측(2026-09-19, 서울 3구+광명·성남 진행 구역 95곳): 이 속성 87% 검출, UPIS 폴리곤 31%.
  · 좌표를 주면 UPIS(LT_C_UPISUQ161) POINT 질의를 더해 구역 이름을 얻는다. 둘 중 하나라도 잡히면 편입.
  · 볼 수 있는 출처가 전부 실패하면 None(확인 불가).

세법용 한계 — 결과에 항상 붙인다
  · 조회일 현재 상태다. 세법 판정은 관리처분계획인가일·사업시행인가일 등 특정 날짜를 기준으로 하므로
    이 값을 그 날짜의 사실로 쓰면 안 된다.
  · 구역지정 전(추진위 단계)은 두 출처 모두 안 잡힌다. '편입 아님'은 확정이 아니다.
"""
from __future__ import annotations

from typing import Optional

import httpx

from property_lookup.common import MissingKey, failure_text, vworld_auth

VWORLD_DATA_URL = "https://api.vworld.kr/req/data"
NED_LAND_USE_URL = "https://api.vworld.kr/ned/data/getLandUseAttr"
REDEV_LAYER = "LT_C_UPISUQ161"

# UPIS dgm_nm에서 정비구역 계열만 — UQ161엔 지구단위계획 등도 섞여 있다
REDEV_KEYWORDS = ("정비구역", "재정비촉진", "재개발", "재건축", "주거환경",
                  "도시환경정비", "가로주택", "소규모재건축", "모아타운")
# 토지이용계획속성 지역지구명 중 정비사업 계열. '아파트지구'는 구 주택건설촉진법 재건축 단지가
# '정비구역' 없이 이것만 달고 있어서 넣는다(원본 실측: 명일동 15 삼익그린2차).
LAND_USE_REDEV_RE = ("정비구역", "재정비촉진", "정비예정구역", "아파트지구", "주거환경개선")
LAND_USE_INSIDE = ("포함", "저촉")

LIMITS = (
    "조회일 현재 상태다 — 관리처분계획인가일 등 판정 기준일의 사실로 쓰려면 고시문으로 확인해야 한다",
    "구역지정 전(추진위 단계)은 잡히지 않는다 — '편입 아님'은 확정이 아니며 최신 고시는 토지이음에서 대조",
)


def fetch_land_use_rows(client: httpx.Client, pnu: str) -> list[dict]:
    resp = client.get(NED_LAND_USE_URL, params=dict(vworld_auth(), pnu=pnu, format="json",
                                                    numOfRows=100, pageNo=1))
    resp.raise_for_status()
    rows = (resp.json().get("landUses") or {}).get("field") or []
    return rows if isinstance(rows, list) else [rows]


def parse_land_use_redev(rows: list[dict]) -> dict:
    """토지이용계획속성 행 → 정비사업 계열 편입·접함·관리번호."""
    inside, adjacent, manage = [], [], []
    for r in rows:
        name = r.get("prposAreaDstrcCodeNm") or ""
        if not any(k in name for k in LAND_USE_REDEV_RE):
            continue
        if (r.get("cnflcAtNm") or "") in LAND_USE_INSIDE:
            inside.append(name)
            if r.get("manageNo"):
                manage.append(str(r["manageNo"]))
        else:
            adjacent.append(name)
    # 관리번호 = 기관7+시군구5+고시연도4+고시번호4+지역지구코드6+일련7 — 같은 구역 필지가 공유한다
    return {"행수": len(rows), "편입": sorted(set(inside)), "접함": sorted(set(adjacent)),
            "관리번호": sorted(set(manage))}


def notice_from_manage_no(manage_no: str) -> Optional[dict]:
    """관리번호에서 고시연도·고시번호. 형식이 아니면 None."""
    s = (manage_no or "").strip()
    if len(s) < 20 or not s[:20].isdigit():
        return None
    return {"고시연도": s[12:16], "고시번호": str(int(s[16:20]))}


def _upis_features(client: httpx.Client, x: float, y: float, size: int = 20) -> list[dict]:
    resp = client.get(VWORLD_DATA_URL, params=dict(
        vworld_auth(), service="data", request="GetFeature", data=REDEV_LAYER,
        format="json", size=size, geometry="false", geomFilter=f"POINT({x} {y})"))
    resp.raise_for_status()
    res = resp.json().get("response", {})
    if res.get("status") == "NOT_FOUND":
        return []
    if res.get("status") != "OK":
        raise RuntimeError(f"{REDEV_LAYER} 조회 실패: {res.get('error', res.get('status'))}")
    feats = res.get("result", {}).get("featureCollection", {}).get("features", [])
    return [f.get("properties", {}) for f in feats]


def check_redev_zone(client: httpx.Client, pnu: Optional[str], x: Optional[float] = None,
                     y: Optional[float] = None) -> dict:
    """정비구역 편입 — {'편입': True|False|None, '구역명', '지역지구', '접함', '고시', 'basis'}."""
    lu, lu_err = None, None
    if pnu:
        try:
            lu = parse_land_use_redev(fetch_land_use_rows(client, pnu))
        except MissingKey:
            raise
        except (httpx.HTTPError, RuntimeError, ValueError) as e:
            lu_err = failure_text(e)

    hits, upis_err, use_upis = [], None, x is not None and y is not None
    if use_upis:
        try:
            hits = [p for p in _upis_features(client, x, y)
                    if any(k in (p.get("dgm_nm") or "") for k in REDEV_KEYWORDS)]
        except MissingKey:
            raise
        except (httpx.HTTPError, RuntimeError, ValueError) as e:
            upis_err = failure_text(e)

    lu_inside = (lu or {}).get("편입") or []
    lu_ok = pnu is not None and lu_err is None
    upis_ok = use_upis and upis_err is None
    if hits or lu_inside:
        inside: Optional[bool] = True
    elif lu_ok or upis_ok:
        inside = False
    else:
        inside = None

    basis = []
    if pnu:
        basis.append("토지이용계획속성(필지)" + (f" 조회 실패({lu_err})" if lu_err else ""))
    if use_upis:
        basis.append("UPIS 정비구역 폴리곤(좌표)" + (f" 조회 실패({upis_err})" if upis_err else ""))
    elif pnu:
        basis.append("좌표 없음 — UPIS 미조회(구역 이름은 확인 못 함)")
    if inside is False and not lu_ok:
        basis.append("필지 속성을 못 보고 UPIS만으로 '아님' — 원본 실측 검출률 31%라 신뢰 낮음")

    manage = (lu or {}).get("관리번호") or []
    return {
        "편입": inside,
        "구역명": [p.get("dgm_nm") for p in hits],
        "지역지구": lu_inside,
        "접함": (lu or {}).get("접함") or [],
        "고시": [n for n in (notice_from_manage_no(m) for m in manage) if n],
        "관리번호": manage,
        "basis": " / ".join(basis),
        "한계": list(LIMITS),
    }
