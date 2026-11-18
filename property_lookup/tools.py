# -*- coding: utf-8 -*-
"""MCP 도구 본체 — tax_server가 얇게 감싸 등록한다. client를 받아 테스트에서 가짜로 바꾼다."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Optional

import httpx

from property_lookup import official_price as op
from property_lookup import pnu as pnu_mod
from property_lookup import redev_zone as rz
from property_lookup.common import (INPUT_NOTICE, JUSO_KEY_ENV, VWORLD_KEY_ENV, MissingKey,
                                    failure_text, has_keys, missing_key_response, parse_date, source)

# 도구 이름 → 필요한 키. 원격 서버는 키가 없으면 이 도구를 목록에서 뺀다.
TOOL_KEYS = {
    "lookup_pnu": (JUSO_KEY_ENV,),
    "lookup_official_price": (VWORLD_KEY_ENV,),
    "lookup_redev_zone": (VWORLD_KEY_ENV,),
}


def tool_enabled(name: str) -> bool:
    return has_keys(*TOOL_KEYS.get(name, ()))


@contextmanager
def _client(client: Optional[httpx.Client]):
    if client is not None:
        yield client
        return
    with httpx.Client(timeout=15) as c:
        yield c


def _failed(what: str, e: Exception) -> dict:
    return {"상태": "조회실패", "오류": f"{what} 실패: {failure_text(e)}",
            "안내": "API 응답을 받지 못했다. 값을 사용자에게 직접 물어 입력하거나 잠시 뒤 다시 조회한다."}


def lookup_pnu(jibun_address: str, client: Optional[httpx.Client] = None, today: Optional[date] = None) -> dict:
    """지번주소 → PNU. 토지특성이 1행 이상 나오면 '확정', VWorld 키가 없거나 0행이면 '미검증'."""
    try:
        with _client(client) as c:
            r = pnu_mod.resolve_pnu(c, jibun_address)
            out = {"상태": r["status"], "PNU": r["pnu"], "근거": r["basis"]}
            if not r["pnu"]:
                out["안내"] = {"주소불충분": "본번·부번이 들어간 지번주소가 필요하다 (예: 서울특별시 동대문구 용두동 232-76)",
                             "다건보류": "후보가 여럿이라 채우지 않았다. 동·리 이름과 지번을 더 정확히 넣는다",
                             }.get(r["status"], "주소를 확인해 다시 조회하거나 PNU를 직접 입력한다")
                return out
            if not has_keys(VWORLD_KEY_ENV):
                out.update(상태="미검증", 검증="VWORLD_API_KEY 미설정 — 토지특성 대조를 못 했다")
            else:
                try:
                    char = op.fetch_land_characteristics(c, r["pnu"])
                except httpx.HTTPError as e:
                    char, out["검증"] = None, f"토지특성 조회 실패: {failure_text(e)}"
                if char:
                    out.update(상태="확정", 검증=f"토지특성 {char['기준연도']}년 행 존재(지목 {char['지목'] or '-'})")
                else:
                    out["상태"] = "미검증"
                    out.setdefault("검증", "토지특성 0행 — 원장에 없는 필지일 수 있다(분할·합병 등)")
            out["출처"] = source("도로명주소 검색 API" + (" + VWorld 토지특성" if out["상태"] == "확정" else ""),
                               trust="확정" if out["상태"] == "확정" else "추정", today=today)
            return out
    except MissingKey as e:
        return missing_key_response(e.env_name)
    except httpx.HTTPError as e:
        return _failed("주소 검색", e)


def lookup_official_price(pnu: str, base_date: str, property_type: str, dong: str = "", ho: str = "",
                          exclusive_area: Optional[float] = None, client: Optional[httpx.Client] = None,
                          today: Optional[date] = None) -> dict:
    """기준일에 적용되는 공시가격 + 같은 연도 토지특성(용도지역·지목·필지면적)."""
    if not pnu_mod.is_pnu(pnu or ""):
        return {"상태": "입력오류", "오류": f"PNU는 19자리 숫자여야 한다: {pnu!r}"}
    try:
        bd = parse_date(base_date)
    except ValueError as e:
        return {"상태": "입력오류", "오류": str(e)}
    kind = op.property_kind(property_type)
    if kind == "오피스텔":
        return {"상태": "지원안함", "유형": "오피스텔",
                "안내": "오피스텔은 주택 공시가격이 없다. 취득세·재산세 시가표준액은 지자체 건물 시가표준액과 "
                       "개별공시지가로, 양도세 기준시가는 국세청 오피스텔 기준시가 고시로 확인한다."}
    if not kind:
        return {"상태": "입력오류", "오류": f"property_type을 알 수 없다: {property_type!r}",
                "안내": "아파트·연립·다세대·단독·다가구·토지 중 하나로 넣는다"}

    price_kind = {"공동주택": "공동주택가격", "개별주택": "개별주택가격", "토지": "개별공시지가"}[kind]
    yrs = op.applicable_years(bd, price_kind)
    flags = []
    if yrs["경계"]:
        flags.append(yrs["근거"])
    if kind in ("토지", "개별주택"):
        flags.append("분할·합병·신축 등으로 연중 추가 공시된 가격은 반영하지 않았다 — 해당되면 시·군·구에서 확인")

    try:
        with _client(client) as c:
            char = op.fetch_land_characteristics(c, pnu, yrs["연도"])
            if not char:
                return {"상태": "미검증", "PNU": pnu,
                        "오류": "토지특성 0행 — 원장에 없는 필지일 수 있어 가격을 붙이지 않는다(오귀속 방지)"}
            out = {"상태": "", "PNU": pnu, "기준일": bd.isoformat(), "유형": price_kind,
                   "적용연도": yrs["연도"][0], "연도판단": yrs["근거"]}
            price: dict = {}
            trusts: list[str] = []
            if kind == "공동주택":
                for y in yrs["연도"]:
                    ap = op.fetch_apart_price(c, pnu, y, dong, ho, exclusive_area)
                    if ap is None:
                        price[y] = {"원": None, "basis": f"{y}년 공동주택가격 행 없음"}
                        continue
                    price[y] = {"원": ap["원"], "basis": ap["basis"]}
                    if ap["원"]:
                        trusts.append(ap["신뢰"])
            elif kind == "개별주택":
                hp = op.fetch_house_price(c, pnu, yrs["연도"])
                for y in yrs["연도"]:
                    price[y] = {"원": hp["값"].get(y),
                                "산정대지면적_m2": hp["산정대지면적_m2"].get(y),
                                "basis": "개별주택가격(토지+건물 통합. 다가구는 건물 한 동 전체)"
                                if y in hp["값"] else f"{y}년 행 없음 (보유 연도 {hp['보유연도'][-3:]})"}
                    if y in hp["값"]:
                        trusts.append("확정")
            else:
                lp = op.fetch_land_price(c, pnu, yrs["연도"])
                area = char["필지면적_m2"]
                for y in yrs["연도"]:
                    unit = lp["값"].get(y)
                    price[y] = {"원_m2": unit, "필지면적_m2": area,
                                "원": int(unit * area) if unit and area else None,
                                "basis": "개별공시지가 × 토지특성 필지면적(공부면적). 지분 취득이면 지분율을 곱한다"
                                if unit else f"{y}년 행 없음 (보유 연도 {lp['보유연도'][-3:]})"}
                    if unit and area:
                        trusts.append("확정")
    except MissingKey as e:
        return missing_key_response(e.env_name)
    except httpx.HTTPError as e:
        return _failed("공시가격 조회", e)

    primary = price.get(yrs["연도"][0], {})
    found = any(v.get("원") for v in price.values())
    out["상태"] = "확인" if primary.get("원") else ("경계연도만 확인" if found else "확인 불가")
    out["공시가격"] = price
    trust = "확인 불가" if not trusts else ("추정" if "추정" in trusts else "확정")
    out["토지특성"] = {k: char[k] for k in ("용도지역", "용도지역2", "지목", "이용상황", "필지면적_m2", "기준연도")}
    if char.get("기준연도일치") is False:
        flags.append(f"토지특성은 {yrs['연도'][0]}년 행이 없어 {char['기준연도']}년 값을 보였다 — 용도지역은 기준일 현재와 다를 수 있다")
    out["플래그"] = flags
    out["출처"] = source(f"VWorld NED {price_kind}·토지특성", base_year=yrs["연도"][0], trust=trust, today=today,
                       근거="지방세법 제4조①(시가표준액)·소득세법 제99조①(기준시가)에서 쓰는 공시가격")
    out["주의"] = INPUT_NOTICE
    return out


def lookup_redev_zone(pnu: str, x: Optional[float] = None, y: Optional[float] = None,
                      client: Optional[httpx.Client] = None, today: Optional[date] = None) -> dict:
    """정비구역 편입 여부(조회일 현재)."""
    if not pnu_mod.is_pnu(pnu or ""):
        return {"상태": "입력오류", "오류": f"PNU는 19자리 숫자여야 한다: {pnu!r}"}
    if (x is None) != (y is None):
        return {"상태": "입력오류", "오류": "좌표는 x(경도)·y(위도)를 함께 넣는다"}
    try:
        with _client(client) as c:
            r = rz.check_redev_zone(c, pnu, x, y)
    except MissingKey as e:
        return missing_key_response(e.env_name)
    r["상태"] = {True: "편입", False: "조회상 미편입", None: "확인 불가"}[r["편입"]]
    r["PNU"] = pnu
    r["출처"] = source("VWorld 토지이용계획속성" + (" + UPIS" if x is not None else ""),
                     trust="참고", today=today)
    r["주의"] = INPUT_NOTICE
    return r
