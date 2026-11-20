# -*- coding: utf-8 -*-
"""법제처 Open API 는 HTTPS 로만 부른다 — OC 키와 검색어가 URL 쿼리에 실리므로 평문 HTTP 로 나가면 안 된다.

tax_server.py 는 생성 파일이다. 비공개 원본(server.py)에도 같은 주소가 들어가 있어야 한다 —
원본을 고치지 않고 다시 생성하면 이 테스트가 깨진다.
"""
import asyncio
import pathlib

import httpx
import pytest

import tax_server

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_law_api_urls_are_https():
    assert tax_server.LAW_SEARCH_URL.startswith("https://www.law.go.kr/")
    assert tax_server.LAW_SERVICE_URL.startswith("https://www.law.go.kr/")
    for path in ("tax_server.py", "scripts/coverage_audit.py"):
        assert "http://www.law.go.kr" not in (ROOT / path).read_text(encoding="utf-8"), path


def test_law_search_does_not_follow_redirect_to_http(monkeypatch):
    """HTTPS 요청이 HTTP 로 되돌려지면(redirect) 따라가지 않고 실패한다 — 키가 평문으로 다시 나가지 않는다."""
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://www.law.go.kr/DRF/lawSearch.do"})

    real = httpx.AsyncClient

    def client(*a, **kw):
        assert not kw.get("follow_redirects"), "법령 API 클라이언트는 redirect 를 따라가지 않는다"
        return real(*a, transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(tax_server, "LAW_OC", "test-key")
    monkeypatch.setattr(tax_server.httpx, "AsyncClient", client)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(tax_server.search_law("지방세법"))
    assert len(seen) == 1 and seen[0].startswith("https://")
