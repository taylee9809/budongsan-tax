"""Cloud Logging의 tool_call 로그로 사용자 수·사용 빈도를 집계한다.

  gcloud logging read 'resource.type="cloud_run_revision" AND jsonPayload.event="tool_call"' \
      --freshness=30d --format=json --project=PROJECT > usage.json
  py scripts/usage_report.py usage.json

로컬 stdout 로그(한 줄 JSON)도 그대로 넣을 수 있다. 날짜는 Asia/Seoul 기준.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def load(path: str):
    text = open(path, encoding="utf-8").read().strip()
    if text.startswith("["):  # gcloud --format=json
        for e in json.loads(text):
            p = e.get("jsonPayload") or {}
            if p.get("event") == "tool_call":
                yield p, e.get("timestamp")
    else:  # stdout 한 줄 JSON
        for line in text.splitlines():
            try:
                p = json.loads(line)
            except ValueError:
                continue
            if isinstance(p, dict) and p.get("event") == "tool_call":
                yield p, p.get("ts")


def day(ts) -> str:
    if not ts:
        return "?"
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(KST).strftime("%Y-%m-%d")


def main(path: str) -> None:
    rows = [(p, day(ts)) for p, ts in load(path)]
    if not rows:
        print("tool_call 로그 없음")
        return
    users = {p["user"] for p, _ in rows if p.get("user") not in (None, "-")}
    anon = sum(1 for p, _ in rows if p.get("user") in (None, "-"))
    per_user = Counter(p["user"] for p, _ in rows if p.get("user") not in (None, "-"))
    days_per_user = defaultdict(set)
    sessions_per_user = defaultdict(set)
    for p, d in rows:
        if p.get("user") not in (None, "-"):
            days_per_user[p["user"]].add(d)
            sessions_per_user[p["user"]].add(p.get("session"))

    print(f"총 호출 {len(rows)}건 · 고유 사용자 {len(users)}명 · 사용자 ID 없는 호출 {anon}건")
    if per_user:
        counts = list(per_user.values())
        active = [len(v) for v in days_per_user.values()]
        sess = [len(v) for v in sessions_per_user.values()]
        print(f"사용자당 호출: 중앙값 {statistics.median(counts)} · 평균 {statistics.mean(counts):.1f} · 최대 {max(counts)}")
        print(f"사용자당 대화(세션) 수: 중앙값 {statistics.median(sess)} · 평균 {statistics.mean(sess):.1f}")
        print(f"사용자당 사용 일수: 중앙값 {statistics.median(active)} · 2일 이상 재방문 {sum(a >= 2 for a in active)}명 "
              f"({sum(a >= 2 for a in active) / len(active):.0%})")

    print("\n일별: 날짜  호출  활성사용자  신규")
    seen = set()
    by_day = defaultdict(list)
    for p, d in rows:
        by_day[d].append(p)
    for d in sorted(by_day):
        us = {p["user"] for p in by_day[d] if p.get("user") not in (None, "-")}
        new = us - seen
        seen |= us
        print(f"  {d}  {len(by_day[d]):>4}  {len(us):>4}  {len(new):>4}")

    print("\n도구별: 호출  실패율  중앙 ms")
    by_tool = defaultdict(list)
    for p, _ in rows:
        by_tool[p.get("tool", "?")].append(p)
    for tool, ps in sorted(by_tool.items(), key=lambda kv: -len(kv[1])):
        fail = sum(not p.get("ok") for p in ps) / len(ps)
        ms = statistics.median(p.get("ms", 0) for p in ps)
        print(f"  {tool:<40} {len(ps):>4}  {fail:>5.0%}  {ms:>6.0f}")

    # 어떤 항목을 채워서 묻는지(인수 이름만. 값은 로그에 없다).
    with_args = [p for p, _ in rows if p.get("args")]
    if not with_args:
        print("\n입력 항목: 기록 없음 (args 필드가 추가되기 전 로그이거나 인수 없는 호출)")
        return
    print(f"\n입력 항목(값 아님, 이름만) · 인수가 있는 호출 {len(with_args)}건")
    print("  인수 개수: 중앙값 "
          f"{statistics.median(len(p['args']) for p in with_args):.0f} · "
          f"최대 {max(len(p['args']) for p in with_args)}")
    for tool, ps in sorted(by_tool.items(), key=lambda kv: -len(kv[1])):
        named = [p for p in ps if p.get("args")]
        if not named:
            continue
        freq = Counter(name for p in named for name in p["args"])
        top = " · ".join(f"{name} {c}/{len(named)}" for name, c in freq.most_common(6))
        print(f"  {tool}\n      {top}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
