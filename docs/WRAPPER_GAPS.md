# 도구 래퍼가 넘기지 못하는 입력 (WRAPPER_GAPS)

`python scripts/wrapper_gaps.py` 가 만든다 — 손으로 고치지 않는다. 판정기(`tax_judgment.py`)나 대체 도구(`tax_overrides.py`)의
인자가 바뀌면 다시 만든다(`tests/test_tax_overrides.py` 가 낡은 문서를 잡는다).

`tax_server.py` 는 비공개 원본(`server.py`)에서 생성기가 만드는 파일이라 이 저장소에서 고치지 않는다. 그 안의 도구 래퍼가
판정기·조문 노드보다 뒤처진 곳은 `tax_overrides.OVERRIDES` 의 같은 이름 도구가 메운다(호스팅 서버와 `budongsan-tax-full`).
이 문서의 2절이 **원본 래퍼에 되돌려 넣을 인자 목록**이다 — 원본을 고쳐 다시 생성하면 그 도구의 대체를 걷어낸다.

요약: 도구 43개 가운데 빠진 입력이 있는 도구 0개(인자 0개), 대체 도구 0개가 더한 인자 0개, 남은 인자 0개.

## 1. 전수 조사

- **빠진 인자**: 판정기(또는 노드) 쪽에 있는데 생성 래퍼 시그니처에 없는 것.
- **남은 인자**: 대체 도구도 받지 못하는 것(0이어야 한다).
- **설명에 없는 키**: 판정기가 목록 원소에서 읽는 키(도구로는 닿는다) 가운데 도구 설명에 나오지 않는 것.

| 도구 | 대조 대상 | 빠진 인자 | 대체 | 남은 인자 | 목록 인자 | 설명에 없는 키 | 설명 |
|---|---|---|---|---|---|---|---|
| `search_law` | 판정기 없음(조회·카탈로그·서식) | — | — | — | — | — | 호스팅 |
| `get_law_detail` | 판정기 없음(조회·카탈로그·서식) | — | — | — | — | — | 호스팅 |
| `get_local_tax_ordinances` | 판정기 없음(조회·카탈로그·서식) | — | — | — | — | — | 호스팅 |
| `calc_transfer_tax` | 스스로 계산 — 노드 쪽 상대 tax_nodes.yangdo.양도세_부동산 | — | — | — | `tax_brackets` | — | 호스팅 |
| `calc_acquisition_tax` | 스스로 계산 — 노드 쪽 상대 tax_nodes.chwideuk.취득세_부동산 | — | — | — | — | — | 호스팅 |
| `calc_property_tax` | 스스로 계산 — 노드 쪽 상대 tax_nodes.jaesan.재산세_주택 | — | — | — | `tax_brackets` · `jiteuk_relief_facts` | — | 호스팅 |
| `calc_jongbu_tax` | 스스로 계산 — 노드 쪽 상대 tax_nodes.jongbu.종부세_주택 | — | — | — | `tax_brackets` | — | 호스팅 |
| `judge_acquisition_homes_and_rate` | tax_judgment.judge_acquisition_homes_and_rate | — | — | — | `homes` | — | 호스팅 |
| `judge_transfer_reliefs` | tax_judgment.judge_transfer_reliefs | — | — | — | `holdings` · `sale_home` · `heavy_facts` | — | 호스팅 |
| `judge_same_household` | tax_judgment.judge_same_household | — | — | — | — | — | 생성 docstring |
| `count_transfer_homes` | tax_judgment.count_transfer_homes | — | — | — | `items` | — | 호스팅 |
| `judge_temporary_two_homes` | tax_judgment.judge_temporary_two_homes | — | — | — | — | — | 호스팅 |
| `judge_155_special` | tax_judgment.judge_155_special | — | — | — | — | — | 호스팅 |
| `count_heavy_homes` | tax_judgment.count_heavy_homes | — | — | — | `items` · `household_facts` | — | 호스팅 |
| `judge_jongbu_one_home_status` | tax_judgment.judge_jongbu_one_home_status | — | — | — | `other_homes` | — | 호스팅 |
| `judge_inherited_house_priority` | tax_judgment.judge_inherited_house_priority | — | — | — | `houses` | — | 호스팅 |
| `judge_co_inherited_owner` | tax_judgment.judge_co_inherited_owner | — | — | — | `shares` | — | 생성 docstring |
| `calc_attached_land_limit` | tax_judgment.calc_attached_land_limit | — | — | — | — | — | 호스팅 |
| `judge_reconstruction_membership_transfer` | tax_judgment.judge_reconstruction_membership_transfer | — | — | — | — | — | 호스팅 |
| `judge_exemption_requirements` | tax_judgment.judge_exemption_requirements | — | — | — | — | — | 호스팅 |
| `judge_rental_income_tax` | tax_judgment.judge_rental_income_tax | — | — | — | `own_homes` · `spouse_homes` · `deposits` | — | 생성 docstring |
| `calc_rental_income_tax` | tax_judgment.calc_rental_income_tax | — | — | — | — | — | 생성 docstring |
| `judge_business_dealer_status` | tax_judgment.judge_business_dealer_status | — | — | — | — | — | 생성 docstring |
| `calc_dealer_comparative_tax` | tax_judgment.calc_dealer_comparative_tax | — | — | — | `housing_trade_profits` · `tax_brackets` | — | 생성 docstring |
| `estimate_reconstruction_levy` | tax_judgment.estimate_reconstruction_levy | — | — | — | `development_cost_items` | — | 호스팅 |
| `judge_transfer_reduction_limit` | tax_judgment.judge_transfer_reduction_limit | — | — | — | `reductions` | — | 생성 docstring |
| `judge_small_house_rental_reduction` | tax_judgment.judge_small_house_rental_reduction | — | — | — | — | — | 호스팅 |
| `judge_farmland_reduction` | tax_judgment.judge_farmland_reduction | — | — | — | `yearly_incomes` | — | 호스팅 |
| `judge_farmland_daeto` | tax_judgment.judge_farmland_daeto | — | — | — | — | — | 호스팅 |
| `judge_second_home_exclusion` | tax_judgment.judge_second_home_exclusion | — | — | — | — | — | 생성 docstring |
| `judge_first_home_acquisition_relief` | tax_judgment.judge_first_home_acquisition_relief | — | — | — | — | — | 생성 docstring |
| `judge_family_loan` | tax_judgment.judge_family_loan | — | — | — | — | — | 생성 docstring |
| `judge_fund_plan_requirement` | tax_judgment.judge_fund_plan_requirement | — | — | — | — | — | 생성 docstring |
| `format_consultation_report` | tax_judgment.format_consultation_report | — | — | — | `evidences` · `owner_qa` · `scenarios` | — | 호스팅 |
| `judge_adjusted_area_at_date` | tax_judgment.judge_adjusted_area_at_date | — | — | — | — | — | 호스팅 |
| `format_consultation_output` | tax_judgment.format_consultation_output | — | — | — | `scenarios` · `extra_flags` | — | 호스팅 |
| `calc_gift_tax` | 스스로 계산 — 노드 쪽 상대 tax_nodes.sangjeung (증여세 노드) | — | — | — | `penalty` | — | 생성 docstring |
| `calc_inheritance_tax` | 스스로 계산 — 노드 쪽 상대 tax_nodes.sangjeung (상속세 노드) | — | — | — | `penalty` | — | 생성 docstring |
| `search_tax_rulings` | 판정기 없음(조회·카탈로그·서식) | — | — | — | — | — | 호스팅 |
| `judge_156_3_special` | tax_judgment.judge_156_3_special | — | — | — | — | — | 호스팅 |
| `screen_relief_candidates` | 판정기 없음(조회·카탈로그·서식) | — | — | — | — | — | 호스팅 |
| `judge_156_3_from_portfolio` | tax_judgment.judge_156_3_from_portfolio → judge_156_3_special | — | — | — | `items` | — | 호스팅 |
| `get_relief_catalog_entry` | 판정기 없음(조회·카탈로그·서식) | — | — | — | — | — | 호스팅 |

메모

- `calc_transfer_tax`: 노드 합성은 자유 형식 사실(**사실·**덮어쓰기)을 받아 시그니처로 대조할 수 없다. 도구는 상수표로 스스로 계산하고 노드를 부르지 않는다 — 노드 입력을 넘기려면 인자 추가가 아니라 계산 경로를 바꿔야 해서 대체하지 않았다(조사 범위 밖으로 남김)
- `calc_acquisition_tax`: 노드 합성은 자유 형식 사실(**사실·**덮어쓰기)을 받아 시그니처로 대조할 수 없다. 도구는 상수표로 스스로 계산하고 노드를 부르지 않는다 — 노드 입력을 넘기려면 인자 추가가 아니라 계산 경로를 바꿔야 해서 대체하지 않았다(조사 범위 밖으로 남김)
- `calc_property_tax`: 금액 키는 생성 도구와 같다(격자 대조). 감면유형을 줄 때만 노드 합성의 결과를 돌려준다
- `calc_jongbu_tax`: 노드 합성은 자유 형식 사실(**사실·**덮어쓰기)을 받아 시그니처로 대조할 수 없다. 도구는 상수표로 스스로 계산하고 노드를 부르지 않는다 — 노드 입력을 넘기려면 인자 추가가 아니라 계산 경로를 바꿔야 해서 대체하지 않았다(조사 범위 밖으로 남김)
- `count_heavy_homes`: 더한 인자는 판정기가 아니라 tax_nodes.yangdo_jungkwa_ho.중과세율_판정 에 넘긴다(판정기 시그니처에는 없다)
- `calc_gift_tax`: 노드 합성은 자유 형식 사실(**사실·**덮어쓰기)을 받아 시그니처로 대조할 수 없다. 도구는 상수표로 스스로 계산하고 노드를 부르지 않는다 — 노드 입력을 넘기려면 인자 추가가 아니라 계산 경로를 바꿔야 해서 대체하지 않았다(조사 범위 밖으로 남김)
- `calc_inheritance_tax`: 노드 합성은 자유 형식 사실(**사실·**덮어쓰기)을 받아 시그니처로 대조할 수 없다. 도구는 상수표로 스스로 계산하고 노드를 부르지 않는다 — 노드 입력을 넘기려면 인자 추가가 아니라 계산 경로를 바꿔야 해서 대체하지 않았다(조사 범위 밖으로 남김)

## 2. 원본 server.py 래퍼에 추가해야 할 인자

기존 인자(이름·순서·기본값)는 그대로 두고 아래 인자를 뒤에 선택 인자로 더한 뒤 판정기에 키워드로 넘긴다.
원본의 판정기가 이 저장소의 `tax_judgment.py` 보다 옛 판이면 판정기부터 동기화해야 한다.

| 도구 | 인자 | 기본값 | 판정기·노드 쪽 뜻 | 근거 |
|---|---|---|---|---|

인자만 더해서는 안 되는 것

- `count_heavy_homes`: 더한 인자는 판정기 인자가 아니다. 래퍼가 `sale_label` 이 있을 때 `tax_nodes.yangdo_jungkwa_ho.중과세율_판정` 을
  부르는 본문(`tax_overrides.count_heavy_homes`)까지 원본에 옮겨야 한다.
- `calc_property_tax`: `jiteuk_relief_type` 을 주면 `tax_nodes.jaesan.재산세_주택` 의 결과를 돌려주고, 직접 지정 인자와 함께 주면 계산하지 않는다
  (`tax_overrides.calc_property_tax` 본문).
- `judge_156_3_from_portfolio`: `other_homes`·`excluded_homes` 는 None 이 아닐 때만 넘긴다(판정기가 목록에서 센 수를 덮어쓰므로).
- 설명: 새 인자의 뜻은 `hosted_descriptions.py` 에 있다. 원본 docstring 에도 옮긴다. `judge_jongbu_one_home_status`·`count_transfer_homes` 는
  인자는 그대로지만 목록 원소의 키(조정대상지역 2년 판정용 키, 명의신탁·분양권 범위·상속 지분 내역)가 생성 docstring 에 없다.
