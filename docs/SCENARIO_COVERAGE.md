# 시나리오 커버리지 맵

`scenario_coverage.py` · 호스팅 도구 `get_tax_scenario_checklist` · 회귀셋 `data/coverage/scenario_regression.jsonl`

## 왜 만들었나

2026-11-18, ChatGPT에 이 커넥터를 붙여 "법인으로 경매 물건 연 6건 이상 단기매매" 질문을 했다.
조문 인용은 정확해졌지만 아래가 빠지거나 틀렸다.

| 빠진 것 | 원인 |
|---|---|
| 법인 주택 종부세 (공제 0, 2.7% / 5%) | 질문이 '보유세'를 직접 묻지 않아 `calc_jongbu_tax`를 부르지 않음 |
| 저가주택 중과 제외 (영 §28의2 1호), 법인에도 적용 | 모델이 몰랐고, **엔진도 법인이면 무조건 12%를 돌려줬다** (이번 PR에서 수정) |
| 토지등 양도소득 추가과세가 결손금으로 줄지 않음 | 엔진에 법인세 도구가 없어 모델이 기억으로 답함 |
| 건물분 부가가치세 | 엔진 범위 밖, 언급 없음 |
| "법인균등분 주민세" | 2021년에 사업소분으로 통합된 옛 명칭. 저장소 문구는 현행 용어였고 모델이 기억으로 채운 것 |

빠진 항목은 대부분 **다른 세목**이라 도구 하나를 고쳐서는 막히지 않는다.
그래서 상황(납세자 × 물건 × 단계 × 맥락)을 받으면 검토할 항목 전체를 고정 표에서 돌려주고,
엔진이 계산하지 않는 항목은 `범위밖`으로 표시해 모델이 기억으로 채우지 않게 한다.

## 구성

- **항목** 41개 — 각 항목에 세목·쟁점·요지·근거 조문·범위(`엔진`/`부분`/`범위밖`)·함정 여부·계산 도구
- **입력** — `taxpayer`(개인/법인/매매사업자), `assets`, `stages`(취득/보유/임대/양도/증여/상속), `context`(경매·공매/단기매매/반복매매/대도시/조정대상지역)
- **instructions** — 여러 세목·단계에 걸친 질문이면 먼저 이 도구를 부르고, 돌려준 항목을 전부 다루고, `범위밖` 항목은 조문만 제시하고 계산하지 않는다고 밝히라고 지시

호스팅 서버(`tax_http.py`)에만 붙인다. `tax_server.py`는 생성 파일이라 손대지 않는다.

## 회귀 테스트

| 파일 | 내용 |
|---|---|
| `tests/test_scenario_coverage.py` | 회귀 시나리오 24개의 필수·제외 항목, 모든 항목이 최소 한 시나리오에서 필수로 검증되는지, 도구 실재, 근거 조문 형식, 법인세율·추가과세율·저가주택 기준이 엔진 상수와 같은지 |
| `tests/test_verification_cases.py` | `data/verification/cases.jsonl` 활성 케이스 전체를 공개 저장소만으로 실행 (지금까지는 비공개 하네스에서만 돌았다) |
| `tests/test_stale_terms.py` | 도구 설명·instructions·체크리스트·README·docs에 폐지 용어(균등분·재산분·종업원할·소득할 주민세, 법인세분 지방소득세)가 없는지 |

시나리오를 더할 때는 `scenario_regression.jsonl`에 한 줄을 넣는다. `필수`는 답변에 반드시 나와야 할 항목 id, `제외`는 그 상황에 나오면 틀린 항목 id다.

## 함께 발견한 것

### 래퍼 드리프트 — 엔진은 받는데 MCP 도구가 못 받는 입력

정본 케이스 39건은 `tax_server.py` 래퍼로는 돌지 않고 `tax_judgment` 엔진으로만 돈다.
래퍼 시그니처가 엔진보다 뒤처져 있어서, MCP 사용자는 아래 입력을 넘길 수 없고 기본값으로 판정받는다.

| 도구 | 래퍼에 없는 입력 |
|---|---|
| judge_first_home_acquisition_relief | household_income, in_capital_area |
| judge_family_loan | loan_date, is_related, justifiable_reason |
| judge_temporary_two_homes | other_homes_at_acquisition, prev_adjusted_after_new_contract |
| judge_co_inherited_owner | is_first_priority, sale_date, same_household_at_inheritance, shares_changed_after_inheritance |
| judge_farmland_reduction | distance_km, heir_continuous_1yr, inherited_decedent_years, inherited_sold_within_3yr |
| judge_farmland_daeto | has_income_exclusion_period, new_acquired_by_inheritance_or_gift |
| judge_inherited_house_priority | agreed_label, demolished_label |
| judge_second_home_exclusion | land_area_m2, transfer_date |
| judge_reconstruction_membership_transfer | permit_application_date |
| judge_business_dealer_status | self_built_kind |
| judge_155_special | homes_at_sale (엔진에도 없음) |

생성기(`scripts/extract_tax_server.py`, 비공개)로 `tax_server.py`를 다시 만들면 해소된다.
`test_wrapper_drift_is_known`이 이 목록을 고정해 두어, 새로 늘면 실패하고 해소되면 목록을 지우라고 알린다.

### 엔진 밖 항목 (범위밖)

법인세(각 사업연도 소득·토지등 양도소득 추가과세)·법인지방소득세·성실신고 소규모법인 세율·주민세 사업소분·
부가가치세·토지분 종부세·배당소득세. `entity_tax.py`에 법인세·추가과세 계산이 있지만 MCP 도구로 열려 있지 않다.
도구로 열면 해당 항목의 범위를 `엔진`으로 바꾸고 회귀 시나리오가 그대로 통과하는지 본다.
