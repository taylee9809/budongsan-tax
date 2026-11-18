# -*- coding: utf-8 -*-
"""부동산 기초정보 조회 실호출 점검 — 키를 넣고 국내 PC에서 한 번 돌린다.

    python scripts/check_property_lookup.py

.env의 JUSO_API_KEY·VWORLD_API_KEY(·VWORLD_DOMAIN)를 읽어 실제 API를 부르고, korea-realestate-mcp가
2026-08-29에 실측한 앵커값과 대조한다. 해외 IP(클라우드 등)에서는 두 서버가 연결을 끊으므로 국내 회선에서 돌린다.

앵커: 서울특별시 동대문구 용두동 232-76
    PNU 1123010200102320076 / 필지 107.7㎡ / 제2종일반주거지역
    2026 개별공시지가 4,760,000원/㎡ / 2026 개별주택가격 401,000,000원 / 정비구역 편입 아님

https 점검을 겸한다. 원본은 NED를 http로 불렀는데, 이식본은 키가 평문으로 나가지 않도록 https로 부른다.
NED 항목이 연결 오류로 실패하면 https 미지원일 수 있으니 결과를 알려 달라.
종료 코드: 전부 통과 0, 실패 1, 키 없음 2.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

import http_redact  # noqa: E402
from property_lookup import tools  # noqa: E402

http_redact.install()

ADDRESS = "서울특별시 동대문구 용두동 232-76"
PNU = "1123010200102320076"
BASE_DATE = "2026-06-01"   # 재산세 과세기준일 — 2026년 공시가격이 적용돼야 한다


def main() -> int:
    missing = [k for k in ("JUSO_API_KEY", "VWORLD_API_KEY") if not os.environ.get(k)]
    if missing:
        print(f".env에 {', '.join(missing)}가 없습니다.")
        return 2

    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail) -> None:
        results.append((name, bool(ok), str(detail)[:300]))

    r = tools.lookup_pnu(ADDRESS)
    check("JUSO 주소 → PNU", r.get("PNU") == PNU, r)
    check("PNU 원장 대조(확정)", r.get("상태") == "확정", r.get("검증") or r)

    land = tools.lookup_official_price(PNU, BASE_DATE, "토지")
    lp = (land.get("공시가격") or {}).get("2026", {})
    check("NED https 응답(토지특성)", "토지특성" in land, land.get("오류") or "ok")
    check("적용연도 2026", land.get("적용연도") == "2026", land.get("연도판단") or land)
    check("개별공시지가 4,760,000원/㎡", lp.get("원_m2") == 4_760_000, lp or land)
    ch = land.get("토지특성") or {}
    check("필지면적 107.7㎡", ch.get("필지면적_m2") == 107.7, ch)
    check("용도지역 제2종일반주거지역", ch.get("용도지역") == "제2종일반주거지역", ch)

    house = tools.lookup_official_price(PNU, BASE_DATE, "단독")
    hp = (house.get("공시가격") or {}).get("2026", {})
    check("개별주택가격 401,000,000원", hp.get("원") == 401_000_000, hp or house)

    past = tools.lookup_official_price(PNU, "2025-08-01", "토지")
    check("과거 기준일은 과거 연도(2025)", past.get("적용연도") == "2025"
          and (past.get("공시가격") or {}).get("2025", {}).get("원_m2"), past.get("공시가격") or past)

    rz = tools.lookup_redev_zone(PNU)
    check("정비구역 조회 응답", rz.get("편입") is not None, rz.get("basis") or rz)
    check("정비구역 편입 아님(앵커)", rz.get("편입") is False, {k: rz.get(k) for k in ("상태", "지역지구", "접함")})

    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"{'통과' if ok else '실패'}  {name.ljust(width)}  {'' if ok else detail}")
    failed = sum(not ok for _, ok, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} 통과")
    conn = ("ConnectError", "Connection reset", "502 Bad Gateway", "disconnected", "ConnectTimeout", "SSL")
    if failed and any(any(c in d for c in conn) for _, ok, d in results if not ok):
        print("연결 오류가 있습니다. 해외 IP·클라우드에서는 두 서버가 연결을 끊습니다 — 국내 회선에서 다시 돌려 주세요.\n"
              "국내에서도 NED 항목만 연결 오류면 https 미지원일 수 있습니다.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
