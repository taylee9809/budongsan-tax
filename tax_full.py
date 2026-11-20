# -*- coding: utf-8 -*-
"""stdio 진입점 — 호스팅 서버와 같은 도구 구성으로 띄운다(`budongsan-tax-full`).

`budongsan-tax` 명령(tax_server.main)은 생성 파일 그대로라 대체 도구(tax_overrides.OVERRIDES)와 호스팅 전용 도구
(취득세 체크리스트, 법인 도구, 건축물 재산세, 범위 안내)가 없다. 이 진입점은 생성 파일을 고치지 않고
tax_http.make_server() 의 조립(도구 목록·설명·서버 안내문)을 그대로 stdio 로 띄운다. HTTP 는 열지 않는다.

호스팅 서버와 같으므로 법령·재결례 조회 도구 4개는 LAW_OC 가 있을 때만 등록된다(`budongsan-tax` 는 항상 등록하고
호출 때 오류를 낸다). `budongsan-tax` 의 동작은 바뀌지 않는다.
"""
import tax_http


def main() -> None:
    tax_http.make_server().run()        # FastMCP 기본 전송 = stdio


if __name__ == "__main__":
    main()
