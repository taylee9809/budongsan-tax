# -*- coding: utf-8 -*-
"""지번주소 → PNU(필지고유번호 19자리).

원본: korea-realestate-mcp pnu.py (9ecd75a). 조립 규칙과 함정 처리는 원본 그대로다.
PNU = 법정동코드(10) + 산여부(1: 일반=1, 산=2) + 본번(4) + 부번(4)

재료는 도로명주소(JUSO) 검색 API 응답의 admCd/mtYn/lnbrMnnm/lnbrSlno.
원본 앵커 실측: "서울 동대문구 용두동 232-76" → 1123010200102320076.

함정 (원본 설계)
  ① JUSO는 건물 있는 주소 위주 — 나대지·임야는 필지 정확일치가 안 나올 수 있다.
     → 같은 읍면동 결과에서 법정동코드만 빌려 지번을 직접 조립한다(동코드 폴백, basis에 명시).
  ② 주소가 동까지만이면 조립 불가 → status='주소불충분'.
  ③ 다건이면 지번 정확일치 우선, 그래도 다건이면 채우지 않는다(status='다건보류').
     틀린 PNU가 빈 PNU보다 나쁘다 — 다른 필지의 공시가격이 붙는다.

조립된 PNU는 토지특성 조회가 1행 이상 나와야 확정이다(검증은 도구 쪽에서 한다).
"""
from __future__ import annotations

import re
from typing import Optional

import httpx

from property_lookup.common import JUSO_KEY_ENV, MissingKey, failure_text, require_key

JUSO_API_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"

_JIBUN_RE = re.compile(r"(\S+[동리가])\s+(?:산\s*)?(\d+)(?:-(\d+))?\s*(?:번지)?")
_SAN_RE = re.compile(r"(\S+[동리가])\s+산\s*\d")


def parse_jibun(jibun_address: str) -> Optional[dict]:
    """지번주소 문자열 → {'umd', 'bun', 'ji', 'is_san'}. 지번이 없으면 None (함정②)."""
    m = _JIBUN_RE.search(jibun_address or "")
    if not m:
        return None
    return {
        "umd": m.group(1),
        "bun": m.group(2).zfill(4),
        "ji": (m.group(3) or "0").zfill(4),
        "is_san": bool(_SAN_RE.search(jibun_address or "")),
    }


def assemble(adm_cd: str, bun: str, ji: str, is_san: bool = False) -> str:
    """부품 → PNU 19자리. adm_cd는 법정동코드 10자리."""
    if len(adm_cd) != 10 or not adm_cd.isdigit():
        raise ValueError(f"법정동코드 10자리가 아님: {adm_cd!r}")
    return adm_cd + ("2" if is_san else "1") + bun.zfill(4)[-4:] + ji.zfill(4)[-4:]


def is_pnu(value: str) -> bool:
    return bool(value) and len(value) == 19 and value.isdigit() and value[10] in "12"


def _juso_search(client: httpx.Client, keyword: str, count: int = 10) -> list[dict]:
    key = require_key(JUSO_KEY_ENV)
    resp = client.get(JUSO_API_URL, params={
        "confmKey": key, "currentPage": 1, "countPerPage": count,
        "keyword": keyword, "resultType": "json",
    })
    resp.raise_for_status()
    results = resp.json().get("results") or {}
    common = results.get("common") or {}
    if str(common.get("errorCode", "0")) not in ("0", ""):
        raise RuntimeError(f"JUSO 오류 {common.get('errorCode')}: {common.get('errorMessage', '')}")
    juso = results.get("juso") or []
    return juso if isinstance(juso, list) else [juso]


def resolve_pnu(client: httpx.Client, jibun_address: str) -> dict:
    """지번주소 → {'pnu', 'status', 'basis'}. pnu는 실패 시 None.

    status: 'ok후보'(조립 성공 — 토지특성 검증 전) | '주소불충분' | '다건보류' | '검색실패'
    키 미설정은 MissingKey 예외로 올린다(도구가 안내로 바꾼다).
    """
    parsed = parse_jibun(jibun_address)
    if not parsed:
        return {"pnu": None, "status": "주소불충분",
                "basis": "지번(본번)이 주소 문자열에 없음 — 동까지만인 주소는 조립 불가"}

    try:
        juso = _juso_search(client, jibun_address)
    except MissingKey:
        raise
    except (httpx.HTTPError, RuntimeError, ValueError) as e:
        return {"pnu": None, "status": "검색실패", "basis": f"JUSO 호출 실패: {failure_text(e)}"}

    exact = []
    for j in juso:
        bun = (j.get("lnbrMnnm") or "0").zfill(4)
        ji = (j.get("lnbrSlno") or "0").zfill(4)
        if bun == parsed["bun"] and ji == parsed["ji"] and (j.get("mtYn") == "1") == parsed["is_san"]:
            exact.append(j)
    # 같은 필지의 건물 여러 동은 admCd·지번이 같아 PNU도 같다 — 하나로 접는다
    pnus = {assemble(j["admCd"], (j.get("lnbrMnnm") or "0"), (j.get("lnbrSlno") or "0"),
                     j.get("mtYn") == "1") for j in exact if j.get("admCd")}
    if len(pnus) == 1:
        return {"pnu": pnus.pop(), "status": "ok후보",
                "basis": f"JUSO 지번 정확일치 {len(exact)}건 → 단일 PNU"}
    if len(pnus) > 1:
        return {"pnu": None, "status": "다건보류",
                "basis": f"지번 일치가 서로 다른 PNU {len(pnus)}개 — 오귀속 방지 보류: {sorted(pnus)}"}

    # 함정① 폴백: 같은 읍면동 결과에서 법정동코드만 빌려 지번을 직접 조립한다
    dong_codes = {j["admCd"] for j in juso
                  if j.get("admCd") and parsed["umd"] and parsed["umd"] in (j.get("jibunAddr") or "")}
    if len(dong_codes) == 1:
        pnu = assemble(dong_codes.pop(), parsed["bun"], parsed["ji"], parsed["is_san"])
        return {"pnu": pnu, "status": "ok후보",
                "basis": "동코드 폴백 — JUSO에 필지 없음(나대지 추정), 동코드+지번 직접 조립. 토지특성 검증 필수"}
    if len(dong_codes) > 1:
        return {"pnu": None, "status": "다건보류",
                "basis": f"같은 동명이 다른 법정동코드 {len(dong_codes)}개 — 보류"}
    return {"pnu": None, "status": "검색실패",
            "basis": "JUSO 결과에서 대상 읍면동을 찾지 못함"}
