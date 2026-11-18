# 도구 래퍼가 넘기지 못하는 입력 (WRAPPER_GAPS)

`python scripts/wrapper_gaps.py` 가 만든다 — 손으로 고치지 않는다. 판정기(`tax_judgment.py`)나 대체 도구(`tax_overrides.py`)의
인자가 바뀌면 다시 만든다(`tests/test_tax_overrides.py` 가 낡은 문서를 잡는다).

`tax_server.py` 는 비공개 원본(`server.py`)에서 생성기가 만드는 파일이라 이 저장소에서 고치지 않는다. 그 안의 도구 래퍼가
판정기·조문 노드보다 뒤처진 곳은 `tax_overrides.OVERRIDES` 의 같은 이름 도구가 메운다(호스팅 서버와 `budongsan-tax-full`).
이 문서의 2절이 **원본 래퍼에 되돌려 넣을 인자 목록**이다 — 원본을 고쳐 다시 생성하면 그 도구의 대체를 걷어낸다.

요약: 도구 43개 가운데 빠진 입력이 있는 도구 8개(인자 21개), 대체 도구 9개가 더한 인자 33개, 남은 인자 0개.

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
| `calc_property_tax` | 스스로 계산 — 노드 쪽 상대 tax_nodes.jaesan.재산세_주택 | `jiteuk_relief_type` · `jiteuk_relief_facts` | 대체 | — | `tax_brackets` | — | 호스팅 |
| `calc_jongbu_tax` | 스스로 계산 — 노드 쪽 상대 tax_nodes.jongbu.종부세_주택 | — | — | — | `tax_brackets` | — | 호스팅 |
| `judge_acquisition_homes_and_rate` | tax_judgment.judge_acquisition_homes_and_rate | `prev_home_in_adjusted_area` · `new_contract_date` · `new_deposit_paid_date` | 대체 | — | `homes` | — | 호스팅 |
| `judge_transfer_reliefs` | tax_judgment.judge_transfer_reliefs | `land_permit_target` · `land_permit_applied_date` · `land_permit_granted` · `six_month_region` · `location` · `holdings` · `sale_home` · `heavy_facts` | 대체 | — | — | — | 호스팅 |
| `judge_same_household` | tax_judgment.judge_same_household | — | — | — | — | — | 생성 docstring |
| `count_transfer_homes` | tax_judgment.count_transfer_homes | — | — | — | `items` | — | 호스팅 |
| `judge_temporary_two_homes` | tax_judgment.judge_temporary_two_homes | `adjusted_area_notice_date` | 대체 | — | — | — | 호스팅 |
| `judge_155_special` | tax_judgment.judge_155_special | `homes_at_sale` | 대체 | — | — | — | 호스팅 |
| `count_heavy_homes` | tax_judgment.count_heavy_homes | — | 대체 | — | `items` | — | 호스팅 |
| `judge_jongbu_one_home_status` | tax_judgment.judge_jongbu_one_home_status | — | — | — | `other_homes` | — | 호스팅 |
| `judge_inherited_house_priority` | tax_judgment.judge_inherited_house_priority | — | — | — | `houses` | — | 호스팅 |
| `judge_co_inherited_owner` | tax_judgment.judge_co_inherited_owner | — | — | — | `shares` | — | 생성 docstring |
| `calc_attached_land_limit` | tax_judgment.calc_attached_land_limit | `demolished_inherited_footprint_m2` · `sale_date` | 대체 | — | — | — | 호스팅 |
| `judge_reconstruction_membership_transfer` | tax_judgment.judge_reconstruction_membership_transfer | — | — | — | — | — | 호스팅 |
| `judge_exemption_requirements` | tax_judgment.judge_exemption_requirements | — | — | — | — | — | 호스팅 |
| `judge_rental_income_tax` | tax_judgment.judge_rental_income_tax | — | — | — | `own_homes` · `spouse_homes` · `deposits` | — | 생성 docstring |
| `calc_rental_income_tax` | tax_judgment.calc_rental_income_tax | — | — | — | — | — | 생성 docstring |
| `judge_business_dealer_status` | tax_judgment.judge_business_dealer_status | — | — | — | — | — | 생성 docstring |
| `calc_dealer_comparative_tax` | tax_judgment.calc_dealer_comparative_tax | — | — | — | `housing_trade_profits` · `tax_brackets` | — | 생성 docstring |
| `estimate_reconstruction_levy` | tax_judgment.estimate_reconstruction_levy | `development_cost_items` | 대체 | — | — | — | 호스팅 |
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
| `judge_156_3_from_portfolio` | tax_judgment.judge_156_3_from_portfolio → judge_156_3_special | `other_homes` · `excluded_homes` · `bunyang_already_completed` | 대체 | — | `items` | — | 호스팅 |
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
| `calc_property_tax` | `jiteuk_relief_type` | `''` | 지방세특례제한법 재산세 경감 유형(노드 사실 '지방세특례_감면유형'). 특례세율과 견주어 경감 효과가 큰 쪽 하나를 고른다 | 지방세법 §111의2④ — findings 113 |
| `calc_property_tax` | `jiteuk_relief_facts` | `None` | 그 경감 규정의 요건 사실(노드 사실 '지방세특례_사실') | 지방세법 §111의2④ · 지방세특례제한법 §35②·§36의4② 등 — findings 113 |
| `judge_acquisition_homes_and_rate` | `prev_home_in_adjusted_area` | `None` | 종전 주택등의 조정대상지역 여부. 신규(in_adjusted_area)와 모두 조정대상지역이면 처분기한 2년, 모르면(None) 2~3년 사이 처분은 보류 | 지방세법 시행령 §28의5①(대통령령 제36736호, 2026-09-30)·부칙 §2① — findings 170 |
| `judge_acquisition_homes_and_rate` | `new_contract_date` | `None` | 신규 주택 매매계약일. 계약금 지급일과 함께 2026-08-26 이전이면 종전 규정(3년) | 대통령령 제36736호 부칙 §2② — findings 170 |
| `judge_acquisition_homes_and_rate` | `new_deposit_paid_date` | `None` | 신규 주택 계약금 지급일(위와 한 쌍) | 대통령령 제36736호 부칙 §2② — findings 170 |
| `judge_transfer_reliefs` | `land_permit_target` | `None` | 토지거래허가 대상 주택인지(None=모름 → 종전 판정) | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) — findings 88 |
| `judge_transfer_reliefs` | `land_permit_applied_date` | `''` | 토지거래허가 신청일(2026-05-09까지 신청이 요건) | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `judge_transfer_reliefs` | `land_permit_granted` | `False` | 허가를 받았는지 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `judge_transfer_reliefs` | `six_month_region` | `None` | 나목 4)의 표 지역(계약 후 6개월·2026-11-09) 여부 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `judge_transfer_reliefs` | `location` | `''` | 소재지 — six_month_region 을 주지 않았을 때 표 지역을 판정한다 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `judge_transfer_reliefs` | `holdings` | `None` | 양도일 현재 세대 보유 목록 — 주면 heavy_home_count 대신 목록으로 중과를 판정한다 | 소득세법 §104⑦ · 시행령 §167의3①·§167의10① — findings 113 |
| `judge_transfer_reliefs` | `sale_home` | `None` | 양도 주택(보유 목록의 항목 또는 그 사실) | 소득세법 §104⑦ · 시행령 §167의3①·§167의10① |
| `judge_transfer_reliefs` | `heavy_facts` | `None` | 세대 단위 사실(혼인일 등) | 소득세법 시행령 §167의3⑨·§167의4⑤ |
| `judge_temporary_two_homes` | `adjusted_area_notice_date` | `None` | 조정대상지역 공고일. 그날 이전에 신규 주택(권리 포함)을 취득했거나 계약·계약금 지급이면 1호(2년)에서 빠져 3년 | 소득세법 시행령 §155①1호 대괄호(대통령령 제36737호, 2026-09-30) — findings 173 |
| `judge_155_special` | `homes_at_sale` | `None` | 양도일 현재 세대 주택 수. 1+1 요건(합가 당시 기준)을 바꾸지 않고 안내 플래그·'주택수_판정기준'만 낸다 | 소득세법 시행령 §155④·⑤ · 법규과-1599(2024.6.25.) |
| `count_heavy_homes` | `sale_label` | `''` | 양도 주택의 라벨 — 주면 같은 목록으로 그 주택의 중과 대상 여부를 판정해 '양도주택_중과판정'에 싣는다 | 소득세법 §104⑦ · 시행령 §167의3①·§167의10① — findings 88 |
| `count_heavy_homes` | `sale_date` | `''` | 양도일 | 소득세법 §104⑦ · 시행령 §167의3①·§167의10① |
| `count_heavy_homes` | `adjusted_at_sale` | `None` | 양도 당시 조정대상지역 여부(None=대상 주택 여부까지만) | 소득세법 §104⑦ |
| `count_heavy_homes` | `holding_years` | `None` | 양도 주택 보유 연수(한시 배제는 2년 이상 전제) | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `count_heavy_homes` | `contract_date` | `''` | 매매계약일 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `count_heavy_homes` | `deposit_received` | `False` | 계약금 수령 여부 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `count_heavy_homes` | `land_permit_target` | `None` | 토지거래허가 대상 여부 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `count_heavy_homes` | `land_permit_applied_date` | `''` | 토지거래허가 신청일 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `count_heavy_homes` | `land_permit_granted` | `False` | 허가 여부 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `count_heavy_homes` | `six_month_region` | `None` | 나목 4)의 표 지역 여부 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `count_heavy_homes` | `location` | `''` | 소재지 | 소득세법 시행령 §167의3①12호의2 나목·다목(§167의4③·§167의10①·§167의11① 준용) |
| `count_heavy_homes` | `household_facts` | `None` | 세대 단위 사실(혼인일·혼인후_신규취득일 등) | 소득세법 시행령 §167의3⑨·§167의4⑤ |
| `calc_attached_land_limit` | `demolished_inherited_footprint_m2` | `None` | 멸실된 상속주택의 정착면적. 주면 한도 = 멸실 전 정착면적 × 배율(노드 소득세법시행령-155-2-멸실신축-b) | 소득세법 시행령 §155②·§154⑦ · 서면4팀-2283(2005.11.23.) — findings 113 |
| `calc_attached_land_limit` | `sale_date` | `''` | 양도일. 멸실 신축 경로에서 2022-01-01 전 양도분은 수도권 도시지역도 5배 | 소득세법 시행령 §154⑦(2020.2.11. 개정 부칙 §39) — findings 113 |
| `estimate_reconstruction_levy` | `development_cost_items` | `None` | 개발비용을 항목(공사비·설계감리비·부대비용·그밖의경비·세금공과금·기부채납가액 등)으로 주면 노드가 산정해 development_cost 로 쓴다(development_cost 가 0일 때만) | 재건축초과이익 환수에 관한 법률 §11①·시행령 §9 (노드 tax_nodes/jaegeonchuk_gaebalbiyong.py) |
| `judge_156_3_from_portfolio` | `bunyang_already_completed` | `False` | 양도 당시 분양권이 이미 완공돼 주택이 된 경우 — ③항 2호 기한 확인 플래그 | 소득세법 시행령 §156의3③2호 |
| `judge_156_3_from_portfolio` | `other_homes` | `None` | 종전주택·분양권 외 주택 수를 직접 지정(목록에서 센 수를 덮어쓴다). 판정기 기본은 목록 산정이라 도구 기본값은 None | 소득세법 시행령 §156의3②(1주택과 1분양권 전제) |
| `judge_156_3_from_portfolio` | `excluded_homes` | `None` | 그중 주택 수 제외 특례로 빠지는 수를 직접 지정(위와 한 쌍) | 소득세법 시행령 §156의3② · 조세특례제한법 §99의4 등 |

인자만 더해서는 안 되는 것

- `count_heavy_homes`: 더한 인자는 판정기 인자가 아니다. 래퍼가 `sale_label` 이 있을 때 `tax_nodes.yangdo_jungkwa_ho.중과세율_판정` 을
  부르는 본문(`tax_overrides.count_heavy_homes`)까지 원본에 옮겨야 한다.
- `calc_property_tax`: `jiteuk_relief_type` 을 주면 `tax_nodes.jaesan.재산세_주택` 의 결과를 돌려주고, 직접 지정 인자와 함께 주면 계산하지 않는다
  (`tax_overrides.calc_property_tax` 본문).
- `judge_156_3_from_portfolio`: `other_homes`·`excluded_homes` 는 None 이 아닐 때만 넘긴다(판정기가 목록에서 센 수를 덮어쓰므로).
- 설명: 새 인자의 뜻은 `hosted_descriptions.py` 에 있다. 원본 docstring 에도 옮긴다. `judge_jongbu_one_home_status`·`count_transfer_homes` 는
  인자는 그대로지만 목록 원소의 키(조정대상지역 2년 판정용 키, 명의신탁·분양권 범위·상속 지분 내역)가 생성 docstring 에 없다.
