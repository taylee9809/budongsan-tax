-- 세금 판정툴 검증 DB (data/tax_cases.db)
-- 목적: 공식 해석례를 정답지로 판정 알고리즘을 회귀 검증하고, 무엇을 무엇으로 검증했는지·
--       틀렸다면 어디가 왜 틀려서 어떻게 고쳤는지를 영구 기록한다.
-- 운영원칙① 사례 기반 검증(판정 모듈마다 10~20건 회귀 테스트셋)의 저장소.
--
-- 원문 보관 근거: 저작권법 §7 3호 — "법원의 판결·결정·명령 및 심판이나 행정심판절차 그 밖에
--   이와 유사한 절차에 의한 의결·결정 등"은 보호받지 못하는 저작물. 조세심판원 심판결정은
--   국세기본법상 심판청구(행정심판 특별절차)의 의결·결정이므로 3호에 해당한다.
--   국세청 예규(서면질의 회신)는 §7 2호(고시·공고·훈령 그 밖에 이와 유사한 것)에 준한다.
--   ※ 이 DB는 MCP 런타임이 읽지 않는다. 검증 전용이며 베타 배포물에서 차단된다(가드레일 7).

PRAGMA foreign_keys = ON;

-- ── 1. 정답지 원문 ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rulings (
    rid            TEXT PRIMARY KEY,          -- 법제처 일련번호
    target         TEXT NOT NULL,             -- ttSpecialDecc(조세심판원)|ntsCgmExpc(국세청해석)
                                              -- |moisCgmExpc(행안부)|expc(법령해석례)
    기관           TEXT,
    청구번호       TEXT,                      -- 예: 조심 2025중4302 (검색결과에만 있어 별도 병합)
    사건번호       TEXT,
    의결일자       TEXT,                      -- YYYY-MM-DD
    세목           TEXT,
    사건명         TEXT,
    재결요지       TEXT,
    주문           TEXT,                      -- 기각|취소|경정 … 기대결론의 1차 근거
    처분개요       TEXT,                      -- '이유'의 1.처분개요 절단본 (사실관계 추출 구간)
    이유           TEXT,                      -- 전문
    관련법령       TEXT,
    링크           TEXT,
    데이터기준일시 TEXT,
    source_file    TEXT,
    수집일         TEXT
);
CREATE INDEX IF NOT EXISTS idx_rulings_date   ON rulings(의결일자 DESC);
CREATE INDEX IF NOT EXISTS idx_rulings_target ON rulings(target);
CREATE INDEX IF NOT EXISTS idx_rulings_주문   ON rulings(주문);

-- ── 2. 회귀 케이스 (정답지에서 뽑아낸 입력·기대출력 쌍) ──────────────────────
CREATE TABLE IF NOT EXISTS cases (
    case_id       TEXT PRIMARY KEY,           -- 예: T155-01
    tool          TEXT NOT NULL,              -- 검증 대상 함수명
    노드          TEXT,                       -- 법문 노드 ID
    분류          TEXT,                       -- 전입요건부인|인용|취득시기|설계통제군 …
    rid           TEXT REFERENCES rulings(rid),
    청구번호      TEXT,
    의결일        TEXT,
    주문          TEXT,
    사실요약      TEXT NOT NULL,
    input_json    TEXT NOT NULL,              -- 툴 시그니처 그대로의 인자 맵
    expected_key  TEXT NOT NULL,              -- 비교할 출력 키 (보통 특례충족)
    expected_json TEXT NOT NULL,              -- 기대값 (JSON 스칼라)
    expected_사유 TEXT,
    회색지대      INTEGER NOT NULL DEFAULT 0, -- 1이면 우리 출력이 회색지대 플래그를 세워도 정답 처리
    재구성메모    TEXT,                       -- 마스킹된 사실을 재구성했으면 그 사실을 명시
    활성          INTEGER NOT NULL DEFAULT 1,
    생성일        TEXT
);
CREATE INDEX IF NOT EXISTS idx_cases_tool ON cases(tool, 활성);

-- ── 3. 실행 이력 ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS runs (
    run_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    실행시각   TEXT NOT NULL,
    구현       TEXT NOT NULL,                 -- legacy_v0 | current — 수정 전/후 비교의 축
    코드설명   TEXT,
    git_rev    TEXT,
    tool       TEXT,
    총건수     INTEGER, 일치 INTEGER, 불일치 INTEGER, 회색지대OK INTEGER,
    비고       TEXT
);

CREATE TABLE IF NOT EXISTS results (
    run_id      INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    case_id     TEXT    NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    판정        TEXT NOT NULL,                -- OK | MISMATCH | GRAY-OK | ERROR
    기대        TEXT,
    실제        TEXT,
    미반영입력  TEXT,                         -- 툴 시그니처에 없어 버려진 입력키 = 누락 파라미터 신호
    output_json TEXT,
    PRIMARY KEY (run_id, case_id)
);

-- ── 4. 발견·조치 대장 ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS findings (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    제목       TEXT NOT NULL,
    tool       TEXT,
    노드       TEXT,
    증상       TEXT NOT NULL,                 -- 무엇이 어떻게 틀렸나
    원인       TEXT,                          -- 왜 틀렸나
    조치       TEXT,                          -- 어떻게 고쳤나
    조문근거   TEXT,
    차액영향   TEXT,                          -- 대(관문)|대(중과↔일반)|중(공제·특례)|소(절차)
    심각도     TEXT,
    상태       TEXT NOT NULL DEFAULT '수정완료',
    run_before INTEGER REFERENCES runs(run_id),
    run_after  INTEGER REFERENCES runs(run_id),
    영향케이스 TEXT,                          -- 쉼표 구분 case_id
    notion_url TEXT,
    생성일     TEXT
);

-- ── 5. 정답지 소스 검토 대장 ─────────────────────────────────────────────────
-- 어떤 공식 정답지를 쓸 수 있는지, 본문까지 확보되는지를 실측해서 남긴다.
-- "검색은 되는데 본문이 안 나온다"가 소스마다 갈려서 착수 순서를 여기서 정한다.
CREATE TABLE IF NOT EXISTS sources (
    source_id  TEXT PRIMARY KEY,              -- S1~S5
    이름       TEXT NOT NULL,
    기관       TEXT,
    접근경로   TEXT,                          -- API target / 포털 URL 패턴
    검색가능   TEXT,                          -- 가능|불가|미확인
    검색건수   INTEGER DEFAULT 0,             -- 실측 히트 수 (수집한 게 아니라 "검색하면 이만큼 나온다")
    본문확보   TEXT,                          -- 가능|불가|경로필요|미확인
    실측기준   TEXT,                          -- 검색건수를 잰 질의어 (소스마다 달라 그대로 비교 금지)
    실측결과   TEXT NOT NULL,                 -- 무엇을 어떻게 확인했나
    제약       TEXT,                          -- 마스킹·robots·저작권 등
    상태       TEXT NOT NULL,                 -- 완료|착수예정|미착수|보류
    우선순위   INTEGER,
    수집건수   INTEGER DEFAULT 0,             -- 실제로 DB에 적재한 원문 수
    점검일     TEXT
);

-- ── 6. 조회 뷰 ───────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_latest_results AS
SELECT r.case_id, c.분류, c.청구번호, c.사실요약, r.판정, r.기대, r.실제, r.run_id
FROM results r
JOIN cases c ON c.case_id = r.case_id
WHERE r.run_id = (SELECT MAX(run_id) FROM runs);

CREATE VIEW IF NOT EXISTS v_run_summary AS
SELECT run_id, 실행시각, 구현, tool, 총건수, 일치, 불일치, 회색지대OK,
       ROUND(100.0 * 일치 / NULLIF(총건수, 0), 1) AS 적중률
FROM runs ORDER BY run_id;

-- 수정 전/후 판정이 뒤집힌 케이스
CREATE VIEW IF NOT EXISTS v_flipped AS
SELECT b.case_id, c.청구번호, c.분류, b.run_id AS before_run, b.판정 AS before_판정,
       a.run_id AS after_run, a.판정 AS after_판정, c.expected_사유
FROM results b
JOIN results a ON a.case_id = b.case_id AND a.run_id > b.run_id
JOIN cases c   ON c.case_id = b.case_id
WHERE b.판정 <> a.판정;
