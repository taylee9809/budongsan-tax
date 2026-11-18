# 인수인계 — 국세청 예규 본문·혼인 특례 판례 회귀 (2026-11-18)

브랜치 `claude/split4-nts-rulings`. **다른 컴퓨터·다른 세션에서 그대로 이어받을 수 있게 맞춰 두었다.**

## 1. 결론 — 막힌 게 아니라 망 문제였다

| | 클라우드 세션 | 사용자 PC(국내 망) |
|---|---|---|
| `https://taxlaw.nts.go.kr/qt/USEQTA002P.do?ntstDcmId=…` | 443 이 TLS 인사에 **무응답**(80 은 302만) | **열린다** — 32,996바이트·로그인·캡차 없음 |

확인은 `python scripts/fetch_rulings_web.py nts-probe` 한 줄. 화면은 JS 로 그리지만 그 JS 가 부르는 액션을
직접 부르면 되므로 **브라우저는 필요 없다**. 받는 코드도 새로 만들 것이 없다 —
`scripts/fetch_rulings.py` 의 `nts_detail()` 이 이미 그 액션을 부른다
(`POST /action.do`, `actionId=ASIQTB002PR01`, `paramData={"dcmDVO":{"ntstDcmId":…}}`).
**국세청 본문 파서를 두 벌로 만들지 말 것** — `본문sha256` 이 갈려 왕복 검사가 깨진다.

## 2. 이 브랜치에 들어온 것

- `data/verification/node_cases/rulings4_nts_honin.jsonl` — 소득령 §155⑤ 혼인 특례 **5건**
  (활성 3 · 불일치 0, 비활성 2). `[판례 회귀] 3건 — 불일치 0`
  - 1주택자+2주택자 혼인 → **미적용** (부동산거래관리과-588). 질의 사실관계가 혼인 5년 안이라
    미적용이 **주택수 요건에서만** 나오게 날짜를 잡았다 — 쟁점이 분리된다.
  - 동일세대 자녀와 공동상속한 1주택 + 1주택 → **적용**(5년) (법규재산2011-372)
  - 혼인 후 배우자 사망, 생존 배우자의 당초 주택 양도 → **적용** (서면인터넷방문상담4팀-3305)
  - 비활성: 혼인합가·일시적 2주택 **중첩**(쟁점-노드밖) · 1997년 양도 **구 영 §155①**(구법)
- `data/verification/rulings.jsonl` — 국세청 5건 색인 추가 (1,366 → **1,371**줄)
- `data/verification/nts_bodies.jsonl` — **본문 꾸러미 6건**(27KB). `data/rulings/` 는 `.gitignore` 라
  새 복제본에 본문이 없어서, 국내 망에서 받은 본문을 이 파일로 올려 둔다.
- `scripts/restore_nts_bodies.py` — 꾸러미 → 캐시 복원(`--pack` 은 그 반대). 복원하면서 색인의
  `본문sha256` 과 대조한다.
- 고친 것: `nts_detail()` 이 `data/rulings/` 를 만들지 않아 새 복제본에서 `FileNotFoundError` 가 났다.
  `fetch_rulings_web.py` 머리말의 「이 환경에서는 받지 못한다」와 `test_rulings4_cases.py` 의
  「국세청 케이스가 없다」를 양쪽 실측으로 고쳤다.

## 3. 다른 컴퓨터에서 시작하는 절차

```bash
gh repo clone taylee9809/budongsan-tax && cd budongsan-tax
git checkout claude/split4-nts-rulings
python scripts/restore_nts_bodies.py          # 본문 캐시 되살리기(sha256 대조까지)
python scripts/verify_node_cases.py data/verification/node_cases/rulings4_nts_honin.jsonl
python -m pytest -q                            # 3,126 passed · 1 xfailed(findings 150)
```

본문을 더 받을 때(**국내 망에서만**):

```bash
python scripts/fetch_rulings_web.py nts-probe            # 먼저 "가능" 인지 본다
python scripts/fetch_rulings.py ntsCgmExpc '"<검색어>"'   # DRF 검색 → ntstDcmId → 본문 수집
python scripts/restore_nts_bodies.py --pack              # 꾸러미 다시 묶기(이걸 커밋한다)
python scripts/summarize_ruling_docs.py                  # docs/RULING_*.md 재생성
```

**함정**
- 새 복제본은 git 작성자 정보가 없어 커밋이 막힌다. 이 저장소는 `Claude <noreply@anthropic.com>` 으로
  쓰고 있다 — `git config user.name Claude && git config user.email noreply@anthropic.com`.
- 색인 재생성(전체 rebuild·`export_jsonl`)을 **돌리지 말 것**. 캐시에는 국세청 6건뿐이고
  나머지 1,365건의 본문은 로컬에 없다 — 전체 재생성은 색인을 날린다. 색인은 줄 단위로만 더한다.
- 법제처 DRF 검색은 `LAW_OC` 가 없어도 기본값(1356)으로 돈다. 국세청 본문과 달리 클라우드에서도 열린다.

## 4. 남은 일

1. **쟁점을 넓힌다** — 혼인 특례만 했다. 노드가 입력을 갖고 있는 쟁점(일시적 2주택·상속주택·동거봉양·
   상생임대 등)으로 국세청 예규를 같은 방식으로 모으면 바로 케이스가 된다.
2. **비활성 2건을 살린다** — 노드가 ① 특례 중첩 ② 공유·상속 지분을 받게 되면 활성으로 돌린다.
3. **findings 150**(영 §155⑤ 노드가 혼인 후 세대 내 증여를 받지 않는다)은 그대로 열려 있다.
   국세청 예규 중 같은 쟁점(세대 내 증여로 보유상태 변동)을 찾으면 법제처 15-0673 과 묶어 보강할 것.
