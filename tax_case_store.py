# -*- coding: utf-8 -*-
"""세금 판정툴 검증 DB 접근층 (data/tax_cases.db).

MCP 런타임은 이 모듈을 읽지 않는다 — 검증 전용. server.py에 툴로 노출하지 말 것.
스키마는 schema_tax_cases.sql. 원문 보관 근거는 저작권법 §7 3호(그 파일 헤더 참조).

  py -c "import tax_case_store as s; s.init(); s.load_rulings(); print(s.stats())"
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "tax_cases.db"
SCHEMA = BASE / "schema_tax_cases.sql"
RULINGS_DIR = BASE / "data" / "rulings"

_SERVICE_KEY = {
    "ttSpecialDecc": "SpecialDeccService",
    "ntsCgmExpc": "CgmExpcService",
    "moisCgmExpc": "CgmExpcService",
    "expc": "ExpcService",
    "prec": "PrecService",             # S5 법원 판례 — 2026-08-24 개통
    "ntsCnsl": "CgmExpcService",       # S4 국세상담센터 상담사례 — 2026-08-24 개통 (신뢰등급 최하·보조 전용)
}
_OC = os.environ.get("LAW_OC", "1356")
_AGENCY = {
    "ttSpecialDecc": "조세심판원", "ntsCgmExpc": "국세청",
    "moisCgmExpc": "행정안전부", "expc": "법제처·기재부",
    "prec": "법원(국가법령정보 판례)",
    "ntsCnsl": "국세상담센터",
}

# 정답지 소스 간 법적 권위 서열 (2026-08-24 확정, 노션 🧭 운영 원칙 반영).
# 숫자가 작을수록 상위 — 같은 법적 쟁점에서 두 소스가 다른 결론을 내면 낮은 숫자가 이긴다.
# tier 3 내부는 세목 도메인이 갈려(국세 vs 지방세) 서로 직접 충돌하지 않는다 — 동률 취급.
SOURCE_TIER = {
    "prec": 1,          # 법원 판례(특히 대법원 확정) — 최상위. 하위 전부를 무력화할 수 있음
    "ttSpecialDecc": 2,  # 조세심판원 심판결정례 — 행정심판. 법원과 다르면 법원이 이김
    "ntsCgmExpc": 3,      # 국세청 예규·해석 — 행정해석(국세 전용)
    "moisCgmExpc": 3,     # 행정안전부 지방세 해석 — 행정해석(지방세 전용, ntsCgmExpc와 도메인 분리)
    "expc": 3,            # 법제처·기재부 법령해석례 — 행정해석
    "ntsCnsl": 4,          # 국세상담센터 상담사례 — 최하위. 확정 결론 아님, 보조 전용
}
_TIER_DOMAIN = {"ntsCgmExpc": "국세", "moisCgmExpc": "지방세"}  # tier 3 동률 판단 시 도메인 분리 근거


def source_tier(target: str) -> int:
    """target(rulings.target 값)의 권위 서열. 모르는 소스는 최하위(4)로 취급 — 안전측 기본값."""
    return SOURCE_TIER.get(target, 4)


def check_source_hierarchy(con=None) -> list[dict]:
    """정답지 우선순위 위반 스캔 — 신규 케이스 추가 시 회귀적으로 실행할 것.

    검사 항목: ①ntsCnsl(상담사례) 소스 케이스인데 사유에 등급 강등 표시가 없는 것
    ②tax_judgment.py의 _cite() 중 상담을 근거로 A·B급을 매긴 것. 소스 간 결론 직접
    충돌(같은 쟁점·같은 사실축에 다른 답)은 자동판정이 어려워 사람이 케이스 목록을 눈으로
    대조해야 한다(2026-08-24 1차 감사 — cases.jsonl 분류·사유 필드 비교로 수행, 위반 0건).
    """
    import re as _re
    own_con = con is None
    con = con or connect()
    violations = []

    rows = con.execute(
        "SELECT c.case_id, c.tool, c.expected_사유 FROM cases c "
        "JOIN rulings r ON c.rid = r.rid WHERE r.target = 'ntsCnsl'"
    ).fetchall()
    for r in rows:
        reason = r["expected_사유"] or ""
        if not _re.search(r"D급|E급|신뢰등급|확인 권장|보조|상담", reason):
            violations.append({
                "유형": "S4 등급강등 미표시", "case_id": r["case_id"], "tool": r["tool"],
                "설명": "상담사례 소스인데 사유에 등급 강등·확인 필요 표시가 없음",
            })

    src_path = BASE / "tax_judgment.py"
    if src_path.exists():
        src = src_path.read_text(encoding="utf-8")
        for m in _re.finditer(
            r'_cite\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*,\s*"([A-E])"\s*\)', src
        ):
            rule, basis, grade = m.groups()
            if ("상담" in basis or "세법상담" in rule) and grade in ("A", "B"):
                violations.append({
                    "유형": "상담 근거 등급 과대", "case_id": None, "tool": None,
                    "설명": f"등급 {grade}인데 근거가 상담사례: {rule[:40]} | {basis[:60]}",
                })

    if own_con:
        con.close()
    return violations


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _git_rev() -> str:
    try:
        return subprocess.run(["git", "-C", str(BASE), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or "?"
    except Exception:
        return "?"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init(reset: bool = False) -> None:
    """스키마 적용 + FTS 인덱스 생성. reset=True면 DB 파일을 지우고 새로 만든다."""
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    con = connect()
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    _init_fts(con)
    con.commit()
    con.close()


def _fts_tokenizer(con: sqlite3.Connection) -> str:
    """한글 부분일치를 위해 trigram 우선, 미지원 빌드면 unicode61."""
    for tok in ("trigram", "unicode61"):
        try:
            con.execute(f"CREATE VIRTUAL TABLE _t USING fts5(x, tokenize='{tok}')")
            con.execute("DROP TABLE _t")
            return tok
        except sqlite3.OperationalError:
            continue
    raise RuntimeError("FTS5를 쓸 수 없는 sqlite3 빌드입니다")


def _init_fts(con: sqlite3.Connection) -> None:
    """사건명·재결요지·처분개요만 색인한다.

    '이유' 전문까지 trigram으로 색인하면 인덱스가 원문의 3배로 불어나 DB가 코퍼스 확장에
    비례해 감당 못 하게 커진다(94건 기준 실측 3MB→10MB). 사실관계·날짜는 처분개요에 모여
    있으므로 검색은 이걸로 충분하고, 전문 검색이 필요하면 rulings.이유 LIKE로 떨어뜨린다.
    """
    tok = _fts_tokenizer(con)
    con.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS rulings_fts USING fts5("
        f"  rid UNINDEXED, 사건명, 재결요지, 처분개요, tokenize='{tok}')")


# ── 정답지 적재 ──────────────────────────────────────────────────────────────
def _reason_of(d: dict) -> str:
    """소스별 본문 필드를 하나로 정규화한다.

    심판례=이유 / 국세청 예규=collect_nts가 '이유'로 정규화해 저장 / 행안부 해석=질의요지+회답 /
    판례(prec)=판례내용(판시사항·판결요지는 별도 컬럼).
    load_rulings와 import_jsonl이 **반드시 같은 규칙**을 써야 왕복 검사가 통과한다 —
    한쪽에만 행안부 매핑을 넣었다가 rebuild에서 본문이 날아간 사고가 있었다(2026-08-24).
    """
    reason = d.get("이유") or d.get("회신") or d.get("판례내용") or ""
    if not reason and d.get("회답"):
        q = (d.get("질의요지") or "").strip()
        reason = (f"[질의요지]\n{q}\n\n" if q else "") + f"[회답]\n{d['회답'].strip()}"
    return reason


def _split_gaeyo(reason: str) -> str:
    """'이유' 전문에서 1.처분개요 구간만 잘라낸다 (사실관계·날짜가 모여 있는 구간)."""
    if not reason:
        return ""
    m = re.split(r"2\s*\.\s*청구인", reason, maxsplit=1)
    return m[0][:2000]


def _iso(d: str | None) -> str | None:
    """20260408 / 2026.04.08 → 2026-04-08"""
    if not d:
        return None
    s = re.sub(r"[^0-9]", "", d)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else d


def load_rulings(directory: Path | None = None) -> dict:
    """data/rulings/*.json → rulings 테이블 + FTS. 이미 있으면 갱신(upsert)."""
    directory = directory or RULINGS_DIR
    index = {}
    idx_file = directory / "_index.json"
    if idx_file.exists():
        index = json.loads(idx_file.read_text(encoding="utf-8"))

    con = connect()
    _init_fts(con)
    n = 0
    for p in sorted(directory.glob("*.json")):
        if p.name.startswith("_"):
            continue
        target, rid = p.stem.split("_", 1)
        doc = json.loads(p.read_text(encoding="utf-8"))
        d = doc.get(_SERVICE_KEY.get(target, ""), doc)
        if not isinstance(d, dict):
            continue
        meta = index.get(rid, {})
        reason = _reason_of(d)
        row = dict(
            rid=rid, target=target,
            기관=d.get("재결청") or d.get("해석기관명") or d.get("법원명") or _AGENCY.get(target, ""),
            청구번호=(meta.get("청구번호") or d.get("청구번호") or d.get("안건번호")
                  or d.get("사건번호") or "").strip(),
            사건번호=(d.get("사건번호") or "").strip(),
            의결일자=_iso(d.get("의결일자") or d.get("해석일자") or d.get("선고일자")
                     or meta.get("의결일자")),
            세목=d.get("세목") or d.get("관련법령") or d.get("참조조문"),
            사건명=d.get("사건명") or d.get("안건명") or meta.get("사건명"),
            재결요지=d.get("재결요지") or d.get("질의요지") or d.get("판결요지") or d.get("판시사항"),
            주문=(d.get("주문") or "").strip(),
            처분개요=_split_gaeyo(reason), 이유=reason,
            관련법령=d.get("관련법령"),
            링크=meta.get("링크") or
                 f"https://www.law.go.kr/DRF/lawService.do?OC={_OC}&target={target}&ID={rid}&type=HTML",
            데이터기준일시=_iso(d.get("데이터기준일시")), source_file=p.name, 수집일=_now(),
        )
        cols = ",".join(row)
        con.execute(f"INSERT INTO rulings ({cols}) VALUES ({','.join('?' * len(row))}) "
                    f"ON CONFLICT(rid) DO UPDATE SET "
                    + ",".join(f"{c}=excluded.{c}" for c in row if c != "rid"),
                    tuple(row.values()))
        con.execute("DELETE FROM rulings_fts WHERE rid = ?", (rid,))
        con.execute("INSERT INTO rulings_fts (rid, 사건명, 재결요지, 처분개요) VALUES (?,?,?,?)",
                    (rid, row["사건명"] or "", row["재결요지"] or "", row["처분개요"]))
        n += 1
    con.commit()
    con.close()
    return {"적재": n}


def search(q: str, limit: int = 10, target: str | None = None) -> list[dict]:
    """FTS 검색 — 사건명·재결요지·처분개요. 전문 검색은 search_reason()."""
    con = connect()
    sql = ("SELECT r.rid, r.청구번호, r.의결일자, r.주문, r.사건명, "
           "       snippet(rulings_fts, 2, '«', '»', '…', 12) AS 발췌 "
           "FROM rulings_fts f JOIN rulings r ON r.rid = f.rid "
           "WHERE rulings_fts MATCH ?")
    args: list = [q]
    if target:
        sql += " AND r.target = ?"
        args.append(target)
    sql += " ORDER BY r.의결일자 DESC LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in con.execute(sql, args)]
    con.close()
    return rows


def search_reason(q: str, limit: int = 10) -> list[dict]:
    """'이유' 전문 부분일치 (FTS 미색인 구간 — 건수가 적어 LIKE 스캔으로 충분)."""
    con = connect()
    rows = [dict(r) for r in con.execute(
        "SELECT rid, 청구번호, 의결일자, 주문, 사건명 FROM rulings "
        "WHERE 이유 LIKE ? ORDER BY 의결일자 DESC LIMIT ?", (f"%{q}%", limit))]
    con.close()
    return rows


def rebuild_fts() -> dict:
    """FTS 스키마를 바꿨을 때 재구축."""
    con = connect()
    con.execute("DROP TABLE IF EXISTS rulings_fts")
    _init_fts(con)
    con.execute("INSERT INTO rulings_fts (rid, 사건명, 재결요지, 처분개요) "
                "SELECT rid, COALESCE(사건명,''), COALESCE(재결요지,''), COALESCE(처분개요,'') "
                "FROM rulings")
    con.commit()
    con.execute("VACUUM")
    con.close()
    return stats()


# ── 케이스 ───────────────────────────────────────────────────────────────────
def upsert_case(case: dict) -> None:
    row = dict(
        case_id=case["case_id"], tool=case["tool"], 노드=case.get("노드"),
        분류=case.get("분류"), rid=case.get("rid") or None,
        청구번호=case.get("청구번호"), 의결일=case.get("의결일"), 주문=case.get("주문"),
        사실요약=case["사실요약"], input_json=json.dumps(case["input"], ensure_ascii=False),
        expected_key=case["expected_key"],
        expected_json=json.dumps(case["expected"], ensure_ascii=False),
        expected_사유=case.get("사유"), 회색지대=int(bool(case.get("회색지대"))),
        재구성메모=case.get("재구성메모"), 활성=int(case.get("활성", 1)), 생성일=_now(),
    )
    con = connect()
    cols = ",".join(row)
    con.execute(f"INSERT INTO cases ({cols}) VALUES ({','.join('?' * len(row))}) "
                f"ON CONFLICT(case_id) DO UPDATE SET "
                + ",".join(f"{c}=excluded.{c}" for c in row if c != "case_id"),
                tuple(row.values()))
    con.commit()
    con.close()


def cases(tool: str | None = None, active_only: bool = True) -> list[dict]:
    con = connect()
    sql, args = "SELECT * FROM cases WHERE 1=1", []
    if tool:
        sql += " AND tool = ?"
        args.append(tool)
    if active_only:
        sql += " AND 활성 = 1"
    rows = [dict(r) for r in con.execute(sql + " ORDER BY case_id", args)]
    con.close()
    for r in rows:
        r["input"] = json.loads(r["input_json"])
        r["expected"] = json.loads(r["expected_json"])
    return rows


# ── 실행·결과 ────────────────────────────────────────────────────────────────
def start_run(구현: str, 코드설명: str = "", tool: str = "", 비고: str = "") -> int:
    con = connect()
    cur = con.execute(
        "INSERT INTO runs (실행시각, 구현, 코드설명, git_rev, tool, 비고) VALUES (?,?,?,?,?,?)",
        (_now(), 구현, 코드설명, _git_rev(), tool, 비고))
    con.commit()
    rid = cur.lastrowid
    con.close()
    return rid


def record_result(run_id: int, case_id: str, 판정: str, 기대, 실제,
                  미반영입력: list[str] | None = None, output: dict | None = None) -> None:
    con = connect()
    con.execute("INSERT OR REPLACE INTO results "
                "(run_id, case_id, 판정, 기대, 실제, 미반영입력, output_json) VALUES (?,?,?,?,?,?,?)",
                (run_id, case_id, 판정, json.dumps(기대, ensure_ascii=False),
                 json.dumps(실제, ensure_ascii=False), ",".join(미반영입력 or []),
                 json.dumps(output, ensure_ascii=False, default=str) if output else None))
    con.commit()
    con.close()


def finish_run(run_id: int) -> dict:
    con = connect()
    s = con.execute(
        "SELECT COUNT(*) n, SUM(판정 IN ('OK','GRAY-OK')) ok, SUM(판정='MISMATCH') ng, "
        "       SUM(판정='GRAY-OK') gray FROM results WHERE run_id = ?", (run_id,)).fetchone()
    con.execute("UPDATE runs SET 총건수=?, 일치=?, 불일치=?, 회색지대OK=? WHERE run_id=?",
                (s["n"], s["ok"] or 0, s["ng"] or 0, s["gray"] or 0, run_id))
    con.commit()
    out = dict(con.execute("SELECT * FROM v_run_summary WHERE run_id=?", (run_id,)).fetchone())
    con.close()
    return out


def add_finding(**kw) -> int:
    kw.setdefault("상태", "수정완료")
    kw["생성일"] = _now()
    con = connect()
    cols = ",".join(kw)
    cur = con.execute(f"INSERT INTO findings ({cols}) VALUES ({','.join('?' * len(kw))})",
                      tuple(kw.values()))
    con.commit()
    fid = cur.lastrowid
    con.close()
    return fid


def upsert_source(src: dict) -> None:
    """일부 필드만 넘겨도 된다 — 기존 행이 있으면 병합한다(부분 갱신)."""
    con = connect()
    old = con.execute("SELECT * FROM sources WHERE source_id = ?", (src["source_id"],)).fetchone()
    con.close()
    if old:
        src = {**dict(old), **src}
    src = {**src, "점검일": src.get("점검일") or _now()[:10]}
    con = connect()
    cols = ",".join(src)
    con.execute(f"INSERT INTO sources ({cols}) VALUES ({','.join('?' * len(src))}) "
                f"ON CONFLICT(source_id) DO UPDATE SET "
                + ",".join(f"{c}=excluded.{c}" for c in src if c != "source_id"),
                tuple(src.values()))
    con.commit()
    con.close()


# ── JSONL 정본 ↔ DB ──────────────────────────────────────────────────────────
# 정본은 data/verification/*.jsonl (git 추적, 줄 단위 diff). DB는 여기서 만들어지는
# 조회용 파생물이라 git에 넣지 않는다. 재결례 '이유' 전문은 부피의 90%이고 공개 API에서
# 다시 받을 수 있으므로 정본에는 sha256 해시만 남긴다 — 우리가 검증한 텍스트가 그거였다는
# 사실은 해시로 증명되고, 부피는 늘지 않는다.
VERIF_DIR = BASE / "data" / "verification"
_EXPORT = {
    "sources": "SELECT * FROM sources ORDER BY source_id",
    "cases": "SELECT * FROM cases ORDER BY case_id",
    "runs": "SELECT * FROM runs ORDER BY run_id",
    "results": "SELECT * FROM results ORDER BY run_id, case_id",
    "findings": "SELECT * FROM findings ORDER BY finding_id",
}
# rulings는 메타데이터만 — 본문(이유·처분개요)은 제외하고 해시로 대체
_RULINGS_EXPORT = (
    "SELECT rid, target, 기관, 청구번호, 사건번호, 의결일자, 세목, 사건명, 재결요지, 주문, "
    "       관련법령, 링크, 데이터기준일시, source_file, LENGTH(이유) AS 본문길이 "
    "FROM rulings ORDER BY rid")


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def export_jsonl() -> dict:
    """DB → data/verification/*.jsonl (git 정본)."""
    VERIF_DIR.mkdir(parents=True, exist_ok=True)
    con = connect()
    out = {}
    for name, sql in _EXPORT.items():
        rows = [dict(r) for r in con.execute(sql)]
        (VERIF_DIR / f"{name}.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
            encoding="utf-8")
        out[name] = len(rows)
    rows = []
    for r in con.execute(_RULINGS_EXPORT):
        d = dict(r)
        body = con.execute("SELECT 이유 FROM rulings WHERE rid = ?", (d["rid"],)).fetchone()[0]
        d["본문sha256"] = _sha(body)
        rows.append(d)
    (VERIF_DIR / "rulings.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8")
    out["rulings"] = len(rows)
    con.close()
    return out


def import_jsonl(reset: bool = True) -> dict:
    """data/verification/*.jsonl → DB 재생성.

    rulings 본문은 data/rulings/ 캐시에서 채우고, 캐시가 있으면 해시를 대조한다.
    캐시가 없으면 메타데이터만 들어가고 '본문없음'으로 집계된다(재수집: fetch_rulings.py).
    """
    init(reset=reset)
    out = {}

    # rulings 먼저 — cases.rid가 rulings를 참조하므로 순서가 뒤집히면 FK로 막힌다.
    f = VERIF_DIR / "rulings.jsonl"
    if f.exists():
        con = connect()
        _init_fts(con)
        n = miss = mismatch = 0
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            expect = row.pop("본문sha256", "")
            row.pop("본문길이", None)
            cache = RULINGS_DIR / (row.get("source_file") or f"{row['target']}_{row['rid']}.json")
            reason = ""
            if cache.exists():
                doc = json.loads(cache.read_text(encoding="utf-8"))
                d = doc.get(_SERVICE_KEY.get(row["target"], ""), doc)
                reason = _reason_of(d)
                if expect and _sha(reason) != expect:
                    mismatch += 1
            else:
                miss += 1
            row["이유"], row["처분개요"] = reason, _split_gaeyo(reason)
            row["수집일"] = _now()
            cols = ",".join(f'"{c}"' for c in row)
            con.execute(f"INSERT OR REPLACE INTO rulings ({cols}) "
                        f"VALUES ({','.join('?' * len(row))})", tuple(row.values()))
            con.execute("INSERT INTO rulings_fts (rid, 사건명, 재결요지, 처분개요) VALUES (?,?,?,?)",
                        (row["rid"], row.get("사건명") or "", row.get("재결요지") or "",
                         row["처분개요"]))
            n += 1
        con.commit()
        con.close()
        out.update({"rulings": n, "본문없음": miss, "해시불일치": mismatch})

    con = connect()
    for name in ("sources", "cases", "runs", "results", "findings"):
        f = VERIF_DIR / f"{name}.jsonl"
        if not f.exists():
            continue
        n = 0
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cols = ",".join(f'"{c}"' for c in row)
            con.execute(f"INSERT OR REPLACE INTO {name} ({cols}) "
                        f"VALUES ({','.join('?' * len(row))})", tuple(row.values()))
            n += 1
        out[name] = n
    con.commit()
    con.close()

    return out


def stats() -> dict:
    con = connect()
    q = lambda s: con.execute(s).fetchone()[0]  # noqa: E731
    out = {
        "sources": q("SELECT COUNT(*) FROM sources"),
        "rulings": q("SELECT COUNT(*) FROM rulings"),
        "cases": q("SELECT COUNT(*) FROM cases"),
        "runs": q("SELECT COUNT(*) FROM runs"),
        "results": q("SELECT COUNT(*) FROM results"),
        "findings": q("SELECT COUNT(*) FROM findings"),
        "db_kb": round(DB_PATH.stat().st_size / 1024) if DB_PATH.exists() else 0,
    }
    con.close()
    return out


if __name__ == "__main__":
    init()
    print(load_rulings())
    print(stats())
