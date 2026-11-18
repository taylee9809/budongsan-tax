# -*- coding: utf-8 -*-
"""조회 모듈 공통 — 키 확인, 출처 표기, 오류 문구."""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

import http_redact

JUSO_KEY_ENV = "JUSO_API_KEY"
VWORLD_KEY_ENV = "VWORLD_API_KEY"
VWORLD_DOMAIN_ENV = "VWORLD_DOMAIN"

# 조회값을 판정·계산 입력으로 쓸 때 항상 붙는 주의
INPUT_NOTICE = ("공공 API 조회값이다. 판정·계산 입력으로 쓰기 전에 사용자에게 확인받고, "
                "사용자가 직접 준 값이 있으면 그 값을 우선한다.")


class MissingKey(RuntimeError):
    """API 키 미설정 — 도구는 이 예외를 안내 응답으로 바꾼다."""

    def __init__(self, env_name: str):
        super().__init__(env_name)
        self.env_name = env_name


def require_key(env_name: str) -> str:
    key = os.environ.get(env_name, "")
    if not key:
        raise MissingKey(env_name)
    return key


def vworld_auth() -> dict:
    return {"key": require_key(VWORLD_KEY_ENV), "domain": os.environ.get(VWORLD_DOMAIN_ENV, "")}


def has_keys(*env_names: str) -> bool:
    return all(os.environ.get(n) for n in env_names)


def missing_key_response(env_name: str) -> dict:
    where = {
        JUSO_KEY_ENV: "도로명주소 개발자센터(business.juso.go.kr) 검색 API 승인키",
        VWORLD_KEY_ENV: "브이월드 오픈API(vworld.kr) 인증키",
    }.get(env_name, env_name)
    return {
        "상태": "키 미설정",
        "오류": f"{env_name}가 설정되지 않았다",
        "안내": f".env에 {env_name}({where})를 넣으면 조회된다. 세금 판정·계산 도구는 키 없이 동작하므로 "
                "해당 값을 사용자에게 직접 물어 입력하면 된다.",
    }


def failure_text(e: Exception) -> str:
    """예외 문구에서 키를 가린다 — 접속 오류 문구에도 URL이 실릴 수 있다."""
    return http_redact.redact(f"{type(e).__name__}: {e}")


def source(api: str, base_year: Optional[str] = None, trust: str = "확정",
           today: Optional[date] = None, **extra) -> dict:
    """출처 표기. trust: 확정(필지·호 단위 원값) | 추정(대표값·폴백) | 참고(현재 상태만 확인)."""
    out = {"구분": "공공API조회", "API": api, "조회일": (today or date.today()).isoformat(), "신뢰": trust}
    if base_year:
        out["기준연도"] = base_year
    out.update(extra)
    return out


def parse_date(value) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        raise ValueError(f"기준일은 YYYY-MM-DD 형식이어야 한다: {value!r}") from None
