"""Tool descriptions for the hosted connector.

The generated tax_server.py docstrings were written for in-house use and tell the
model which tool to call next. Directory review forbids that, so the hosted server
replaces those descriptions with ones that say only what each tool does and what
its inputs mean. Calculation code is unchanged.
"""

DESCRIPTIONS = {
    "search_law": """Search Korean statutes and administrative rules on the national law database (law.go.kr).

법제처 국가법령정보에서 법령 또는 행정규칙(고시)을 검색한다.

Args:
    query: 법령명·고시명 또는 키워드
    target: "law"(법률·시행령·시행규칙, 기본값) | "admrul"(행정규칙 — 투기과열지구·조정대상지역 지정 고시 등) | "ordin"(자치법규)
    display: 결과 개수 (최대 100)

결과마다 "법령일련번호"(law) 또는 "행정규칙일련번호"(admrul)가 들어 있다. 이 번호가 원문 조회의 doc_id다.""",

    "get_law_detail": """Fetch the full text of a Korean statute or administrative rule by its serial number.

법령 조문 또는 행정규칙(고시) 원문 전체를 조회한다.

Args:
    doc_id: 법령일련번호(target="law") 또는 행정규칙일련번호(target="admrul"). 법령명이 아니라 숫자 번호다.
    target: "law" | "admrul" | "ordin\"""",

    "get_local_tax_ordinances": """Look up a Korean province/metropolitan tax ordinance (rate adjustments, local reliefs).

관할 시·도 지방세 조례에서 취득세(또는 keyword) 관련 조문을 실시간 조회한다.

지방세법 §14는 조례로 취득세 세율을 표준세율의 50% 범위에서 가감할 수 있게 한다(탄력세율). 재산세는 §111③이 같은 구조다. 조례는 개정이 잦아 호출 시점에 조회하며 캐시하지 않는다.

Args:
    sido: 광역 지자체 전체 명칭 — "서울특별시", "경기도", "부산광역시" 등. 취득세는 광역단체세라 시군구가 아니라 광역 단위다.
    keyword: 조문에서 찾을 세목 키워드 (기본 "취득세")

Returns:
    ordinances: 관할 지방세 조례 목록(자치법규일련번호 포함)
    matched_articles: keyword·탄력세율 관련 조문 발췌
    flexible_rate_found: 탄력세율 가감 조문 발견 여부. 미발견이면 표준세율이 적용된다. 감면 조례는 별도다.""",

    "calc_transfer_tax": """Korea capital gains tax (양도소득세) on real estate: rate, long-term holding deduction, heavy rates, surtax. Returns the statute trail.

양도소득세를 계산한다. 세율표·기본공제·중과 가산세율은 year로 상수표에서 읽고, 단기세율 비교과세(§104① 후단·§104⑦ 후단)도 계산한다. 검증되지 않은 과거 연도는 계산을 거부하고, 미래 연도는 현행법 기준 추정임을 결과에 표시한다.

asset_type: "주택"(조합원입주권·분양권 포함) | "토지" | "분양권"(보유기간 무관 하한 60%) | "비사업용토지"(기본세율 +10%p).
heavy_home_count: §104⑦ 중과 주택수(조정대상지역 기준). 2면 +20%p, 3 이상이면 +30%p. surcharge_rate를 주면 그 값이 우선한다.

Args:
    purchase_price: 취득가액 (원)
    sale_price: 양도가액 (원)
    holding_years: 보유 기간 (년)
    necessary_expenses: 취득세·중개보수 등 필요경비 (원)
    year: 양도 연도. 상수표 조회 키이며 필수다.
    tax_brackets: 세율표를 직접 줄 때만 사용. 생략하면 상수표에서 읽는다.
    long_term_deduction_rate: 장기보유특별공제율 (0~1). 중과 대상이면 0.
    basic_deduction: 양도소득 기본공제 (기본 250만원, 연 1회)
    surcharge_rate: 중과세율 가산분 (0~1)

소득세법 §95②에 따라 §104⑦ 중과대상 주택은 장기보유특별공제가 배제되므로, surcharge_rate와 long_term_deduction_rate를 함께 주면 거부한다. 장기보유특별공제는 보유 3년 이상만 가능하다.

지원하지 않는 산식: 고가주택(양도가액 12억 초과) 1세대1주택의 과세 양도차익 안분(영 §160)은 안분한 양도차익을 넣어야 한다. 같은 과세기간 2회 이상 양도 시 합산 비교과세(§104⑤)는 계산하지 않는다.

Returns:
    양도차익·과세표준·산출세액 등 단계별 dict와 근거 조문""",

    "calc_acquisition_tax": """Korea acquisition tax (취득세) on real estate plus local education tax and rural special tax, by year and acquisition type.

취득세와 지방교육세·농어촌특별세를 계산한다. 세율은 year와 취득 유형으로 상수표에서 읽고, 부가세목 두 개의 산식(세율 치환 재계산)도 코드가 수행한다.

Args:
    acquisition_price: 취득가액(과세표준, 원)
    year: 취득 연도. 필수.
    acquisition_type: "주택유상"(§11①8호 구간세율 1~3%) | "유상.농지외"(4%) | "유상.농지"(3%) | "상속.농지외"(2.8%) | "상속.농지"(2.3%) | "무상"(3.5%) | "무상.비영리사업자"(2.8%) | "원시취득"(2.8%) | "공유물분할"(본인 지분 이내라 §15①4호 0.3% 자동 적용)
    heavy_type: §13의2 중과 유형. "" | "법인" | "2주택조정_또는_3주택비조정" | "3주택이상조정_또는_4주택이상비조정". 일시적 2주택은 §13의2①2호 괄호로 제외되므로 중과가 아니면 빈 문자열.
    exclusive_area: 전용면적(㎡). 85 이하면 농어촌특별세 비과세(농특세법 §4 11호).
    rate_special: 지방세법 §15①(세율의 특례) 해당 호. "" | "환매" | "상속1가구1주택" | "상속자경농지" | "적격합병" | "공유물분할" | "건축물이전" | "재산분할" | "형식적취득" | "없음". 공유물분할(본인 지분 이내) 0.3%, 상속 1가구1주택 0.8%, 재산분할 1.5%. heavy_type과 함께 줄 수 없다.
    standard_rate, heavy_surcharge_rate, ordinance_adjustment_rate, local_education_tax_rate, rural_special_tax_rate: 상수표 대신 세율을 직접 줄 때만 사용한다(조례 가감 등). 생략하면 상수표 값을 쓴다.

부가세목 산식(지방세법 §151①1호, 농특세법 §5①6호):
  · 지방교육세: 일반 (표준세율−2%)×20% / 주택 유상 취득세율×50%×20% / 중과(8·12%) 0.4% 고정
  · 농어촌특별세: 표준세율을 2%로 치환해 재계산한 취득세액×10% → 일반 0.2%, 8% 중과 0.6%, 12% 중과 1.0%. 전용 85㎡ 이하 주택은 비과세. 감면분 농특세(감면세액×20%)는 이 계산에 포함되지 않는다.

Returns:
    적용세율, 취득세, 지방교육세, 농어촌특별세, 총납부세액과 근거 조문""",

    "judge_transfer_reliefs": """Decide capital gains exemption, heavy-rate exclusions, long-term deduction rate and high-value apportionment ratio.

양도세 비과세·중과·장기보유특별공제·고가주택 안분을 판정한다.

소득세법 §89·§95(표1/표2, 중과 시 장특공 배제)·§104⑦·영 §159의4·§160·중과 한시배제(영 §167의3①12호의2)를 한 번에 판정한다. 세대·주택수와 비과세 요건 충족 여부는 입력으로 받는다.

sale_date는 중과 가산세율을 가른다. 2021-06-01 이후 양도분은 2주택 +20%p / 3주택 +30%p, 그 전은 +10%p / +20%p(법 17477호 부칙 §3).
중과 한시배제는 2022-05-10~2026-05-09 양도분이고 보유 2년 이상이 전제다. 그 기간을 넘겨 양도해도 2026-05-09까지 계약하고 계약금을 받았다면 계약일부터 4개월(일부 지역 6개월) 내 양도까지 배제된다 — contract_date·deposit_received·contract_months_limit로 판정한다.

Returns:
    surcharge_rate, long_term_deduction_rate(양도세 계산의 입력값), 과세대상_양도차익_비율(1 미만이면 고가주택 안분), 근거 조문""",

    "judge_temporary_two_homes": """Temporary two-home exemption test: one-year gap, disposal deadline, move-in requirement (Income Tax Decree art. 155(1)).

영 §155① 일시적 2주택 판정 — 1년 경과(§154①1~3호 해당 시 면제)·양도기한·전입요건.

양도기한은 양도일로 갈린다: 2023-01-12 이후 양도는 3년 단일, 2022-05-10~2023-01-11은 조정→조정 2년, 그 전은 신규취득일 구간별 3년/2년/1년. 1년 구간(2019-12-17 이후 조정→조정 취득)은 신규주택 취득일부터 1년 내 세대 전원 이사·전입신고가 추가 요건이고, 전 소유자 임대차가 남아 있으면 종료일까지(취득일+2년 한도) 연장된다.

prev_in_adjusted_area, new_in_adjusted_area: 각 취득일 기준 조정대상지역 여부.
날짜는 YYYY-MM-DD. prev_sale_date를 생략하면 현행법(3년) 기한만 산출한다. 취득세 일시적 2주택(영 §28의5, 1년 요건 없음)과는 별개라는 플래그를 함께 돌려준다.""",

    "judge_155_special": """Special one-home cases: marriage, caring for parents, inherited home, residence home (Income Tax Decree art. 155).

영 §155 특례 판정.

kind: "혼인"(⑤) | "동거봉양"(④) | "상속주택"(② 선순위·별도세대) | "거주주택"(⑳ 장기임대+거주 2년).

특례기간은 양도일 기준으로 갈린다 — 혼인은 2024-11-12 이후 양도분 10년(그 전 5년, 영 34990호 부칙 §2), 동거봉양은 2018-02-13 이후 양도분 10년(그 전 5년). 과거 양도분은 sale_date가 있어야 정확하다.
excluded_homes_mine, excluded_homes_spouse_or_parent: 공동상속(§155③)·농어촌주택(조특법 §99의4) 등 특례로 주택수에서 빠지는 수. 1+1 판정 전에 차감한다.
혼인 주택수는 양도일이 아니라 혼인합가 당시 기준이고 임대주택도 주택수에 든다. 2009-02-04 전 합가는 여성 직계존속 55세(parent_is_female).
상속주택은 동거봉양 합가로 동일세대가 된 경우 merged_for_parent_care·held_before_merge로 합가 전부터 보유하던 주택만 인정된다. §155 특례의 3중첩은 허용되지 않는다.""",

    "count_heavy_homes": """Count homes for heavy capital gains rates, excluding low-value provincial homes and other statutory exclusions.

양도세 중과 판정용 주택수를 센다 (영 §167의3~11 불산입 자동 적용 — 지방 3억 이하·§167의3①12호).

items 원소: {"종류": 주택|조합원입주권|분양권, "기준시가": 원(입주권=종전주택가·분양권=공급가), "지방소재": bool, "인구감소등_12호": bool, "정비구역": bool, "전용면적"·"취득가액"·"취득일"·"준공일"·"아파트": 소형 신축주택(영 §167의3①12호 가목) 판정용, "라벨": str}.

heavy_tier: 2(2주택 중과, 영 §167의10)면 기준시가 1억 이하(정비구역 제외) 불산입이 추가되고, 3(3주택 이상, 영 §167의3)에는 그 완화가 없다. 같은 주택이라도 계열에 따라 세는 수가 다르다.
반환 주택수는 중과 판정용이며 비과세 판정용 주택수와 다르다.""",

    "judge_inherited_house_priority": """When a decedent held several homes, pick the single inherited home that gets the special treatment.

피상속인이 여러 주택을 가졌을 때 선순위 상속주택 1개를 확정한다 (영 §155② 1~4호).

순위: ①피상속인 소유기간 최장 ②동률이면 피상속인 거주기간 최장 ③모두 동률이면 상속개시 당시 거주 ④거주사실 없고 소유기간 동률이면 기준시가 최고(동률이면 상속인 선택).
houses 원소: {"라벨", "피상속인_소유기간_년", "피상속인_거주기간_년", "상속개시당시_거주": bool, "기준시가": 원}.
선순위가 아닌 상속주택은 주택수에 그대로 산입된다.""",

    "judge_reconstruction_membership_transfer": """Can a redevelopment/reconstruction association membership be transferred in a speculation zone (Urban Renewal Act art. 39).

재건축·재개발 조합원 지위양도 제한 판정 (도시정비법 §39②③·영 §37①③).

투기과열지구에서 재건축은 조합설립인가 후, 재개발은 관리처분인가 후 양수자가 조합원이 될 수 없다(증여 포함, 상속·이혼 제외). 조합원이 되지 못한 매수인은 §39③→§73 준용 손실보상 대상이다.
in_speculation_overheated_zone: 거래 시점 투기과열지구 지정 여부.
transfer_notice_done=True(이전고시 후)면 제한이 풀린다. 1+1 소형 60㎡ 이하는 is_one_plus_one_small로 §76①7호라목 3년 전매금지를 따로 판정한다.
transferor_reason: "" | 세대이전 | 상속주택이전 | 해외이주 | 지분형주택 | 공공재개발양도 | 1세대1주택_소유10년_거주5년 | 시행령예외(decree_reason으로 §37③ 세목 지정).""",

    "judge_exemption_requirements": """Full one-household-one-home capital gains exemption test: holding, residence, price cap, adjusted area.

1세대1주택 비과세 요건 판정 (소법 §89①3호·영 §154·§155의3).

보유 2년, 취득 당시 조정대상지역이면 거주 2년, 배제 사유, 상생임대 대체, 고가주택 12억 안분 비율을 판정한다. 세대 판정과 주택수는 입력으로 받는다.
acquired_in_adjusted_area: 취득 당시 지정 이력 기준(승계 입주권·분양권은 사용승인일).
waiver_reason: "" | 건설임대5년거주 | 수용 | 해외이주2년 | 취학근무국외 | 부득이1년거주.

§154①5호(조정 공고 전 계약)는 사실 4개로 나눠 받는다 — 하나라도 틀리면 결론이 뒤집힌다:
contract_before_adjusted_announce(공고 전 계약) · deposit_paid_in_full(계약금 전액 지급, 일부면 배제 불가) · no_home_at_contract(계약금 지급일 세대 무주택) · acquisition_cause(매매|분양|증여|상속|자가건설|조합가입). 증여·상속은 same_household_succession=True(동일세대원 승계)일 때만 배제가 유지된다.
partial_non_residence_unavoidable: 세대원 일부가 부득이한 사유로 처음부터 거주하지 못한 경우.
sangsaeng_nonresident_contract: 비거주자가 체결한 임대차계약이면 상생임대 특례가 무효다.""",

    "judge_small_house_rental_reduction": """Small-home landlord income tax reduction (Special Taxation Act art. 96): eligibility and rate.

조특법 §96 소형주택 임대사업자 세액감면 판정.

감면율: 1호 임대 30%(공공지원·장기일반민간임대주택 75%) / 2호 이상 20%(장기일반 등 50%).
요건(영 §96): 소법 §168 사업자등록 + 민특법 §5 등록 + 국민주택규모 85㎡ 이하 + 임대개시일 기준시가 6억 이하 + 임대료 증가율 5% 이하. 일몰 2028-12-31.
기준시가 6억·85㎡ 요건은 소법 §64의2 분리과세 등록임대주택 요건에는 없다 — 필요경비 60%·공제 400만원은 되는데 §96 감면은 안 되는 구간이 있다.
추징: 4년(장기일반 10년) 미만 임대 시 감면세액 + 이자상당가산액.""",

    "judge_farmland_reduction": """Self-cultivated farmland capital gains exemption after 8 years (Special Taxation Act art. 69).

조특법 §69 자경농지 양도세 100% 감면 판정 (시행령 §66 요건 포함).

실질 관문은 소득 요건이다 — yearly_incomes([{"연도","사업소득금액","총급여액"}]) 합계가 3,700만원 이상인 과세기간은 경작기간에서 빠진다(영 §66⑭, 농업·임업·부동산임대·농가부업소득 제외). 겸업 농민은 달력상 8년을 채워도 탈락할 수 있다.
재촌 요건: 농지 소재 시·군·구 / 연접 시·군·구 / 직선 30km 이내(영 §66①).
주거·상업·공업지역 편입 후 3년이 지나면 감면 배제(영 §66④).
감면율이 100%여도 조특법 §133① 연간·5년 한도가 별도로 적용된다. 결과의 감면세액은 한도 적용 전이다.""",

    "judge_farmland_daeto": """Farmland substitution exemption (Special Taxation Act art. 70): distance, period, area and value ratios.

조특법 §70 농지대토 양도세 100% 감면 판정 (시행령 §67).

요건: ①종전 농지 양도일 현재 4년 이상 농지소재지(시군구·연접·직선 30km) 거주·경작 ②양도일부터 1년(수용은 2년) 내 새 농지 취득 ③취득일부터 1년 내 새 농지소재지 거주·경작 개시 ④종전+신규 합산 경작 8년 이상 ⑤신규 농지 면적이 종전의 2/3 이상 또는 가액이 1/2 이상.
자경농지(§69)와 달리 양도 시점에 8년을 채울 필요가 없고 사후 합산으로 채운다. 미달 시 §70④⑤로 2개월 내 추징 + 이자상당액. 재촌 요건 기간도 §69(8년)와 달리 4년이다.
감면율이 100%여도 §133①2호가목의 5개 과세기간 1억원 한도가 별도로 적용된다. 결과의 감면세액은 한도 적용 전이다.""",

    "format_consultation_report": """Format a consultation result as a report: conclusion, grounds mapped to sources, tailored Q&A.

상담 결과를 소비자용 리포트로 만든다 — 1.최종결론 / 2.근거(설명↔출처 1:1) / 3.맞춤 Q&A.

conclusion: 결론 문장.
evidences: [{"설명": str, "출처": str}] — 설명과 출처가 1:1이어야 한다. 출처 없는 설명이 하나라도 있으면 리포트 전체를 거부한다.
owner_qa: [{"질문": str, "답변": str, "근거": str}] — 추가 질문과 답변. 근거 없는 답변은 거부한다.
scenarios: 쟁점으로 세액이 갈릴 때 결론 아래 병기할 시나리오 목록(형식은 {"라벨","세액","전제","근거"}).
dividing_issue, issue_grade: 세액을 가르는 쟁점과 그 등급.

결과에는 쟁점·질문 문구에서 뽑은 해석례 검색어('추천검색')가 함께 들어간다.""",

    "judge_adjusted_area_at_date": """Was a location an adjusted (regulated) area on a given date, from the designation history.

특정 날짜 기준 조정대상지역 여부를 지정 이력에서 판정한다.

region 예: "서울 마포구", "성남시 분당구".
target_date: 판정 기준일 YYYY-MM-DD (취득일. 분양권·입주권 승계취득은 사용승인일).
이력은 근거를 확보한 구간만 들어 있다. 수록되지 않은 기간·지역은 '판단불가'를 돌려준다.

Returns:
    판정, acquired_in_adjusted_area(bool), 확신도, 근거""",

    "format_consultation_output": """Standard output formatter for a consultation result.

상담 결과 표준 출력 포맷터. 다음 규약을 강제한다:
①쟁점 등급이 D~F(해석·사실판단)면 시나리오 2개 이상 병기(성립/불성립 양쪽 세액)
②시나리오 간 세액 차액과 그 구간(하 <500만 < 중 < 3천만 < 상 < 1억 < 최상)
③근거 없는 시나리오는 등재 거부
④세무사법 안전선 문구 자동 포함(단정 금지)

scenarios 원소: {"라벨": str, "세액": int, "전제": str, "근거": [근거 조문·판정 인용]}.
dividing_issue, issue_grade: 세액을 가르는 쟁점과 등급. lead_threshold: 차액 표시 기준(원).""",

    "judge_156_3_special": """Home plus pre-sale right (분양권) one-home special case (Income Tax Decree art. 156-3).

주택+분양권 1세대1주택 특례 판정 (영 §156의3, 규칙 §75·§75의2).

분양권 전용이다(조합원입주권은 다루지 않는다). 판정범위는 ②③항(일시적 1주택+1분양권)뿐이고, 상속분양권(④⑤)·동거봉양/혼인 조합(⑥)·문화재/이농주택 조합(⑦⑧)은 미구현이며 반환 '판정범위' 필드에 표시된다.
2021-01-01 전에 취득한 분양권은 주택수에 들지 않아 "특례 불필요"를 돌려준다(탈락과 다르다).

판정 순서: ②항(분양권 취득 후 3년 내 종전주택 양도) → 규칙 §75① 부득이한 사유 → ③항(신축주택 완성 후 실입주).
- ②항 후단이 1년 요건을 면제하는 것은 §154① 제1호·제2호가목·제3호뿐이다. 해외이주(제2호나목)·국외 취학근무(다목)는 면제 대상이 아니다.
- ③항의 "완성 후 2년"은 2023-01-12 이후 양도분부터 3년이다(부칙 §8).
- ③항의 "종전주택 취득 1년 경과" 요건은 2022-02-15 이후 취득한 분양권부터다(부칙 §12).

Args:
    prior_home_acquired: 종전주택 취득일 YYYY-MM-DD
    bunyang_acquired: 분양권 취득일 YYYY-MM-DD (분양계약일)
    sale_date: 종전주택 양도일 YYYY-MM-DD
    new_home_completed: 분양권으로 취득하는 주택의 완성일 (③항)
    moved_in_date: 신축주택으로 세대 전원이 이사한 날
    continuous_residence_years: 신축주택 계속거주 기간(년) — 1년 이상이어야 한다
    holding_waiver_reason: "" | 건설임대5년거주 | 수용 | 해외이주2년 | 취학근무국외 | 부득이1년거주
    sale_delay_reason: "" | 캠코매각의뢰 | 법원경매신청 | 공매진행 (규칙 §75①)
    delay_state_at_3y: 분양권 취득일부터 3년이 되는 날 그 상태였는지
    sold_by_that_method: 실제로 그 방법으로 양도됐는지
    partial_move_reason: "" | 취학 | 근무 | 질병 | 학교폭력 — 세대원 일부가 못 옮긴 사유
    other_homes: 종전주택·분양권 외 보유 주택 수
    excluded_homes: 그중 주택수 제외 특례로 빠지는 수 — 농어촌주택(조특법 §99의4)·인구감소지역주택(§71의2)·준공후미분양(§98의9)
    bunyang_already_completed: 양도 당시 분양권이 이미 완공돼 주택이 된 경우""",

    "screen_relief_candidates": """List the tax reliefs and special cases worth checking for a given situation, to avoid omissions.

조특법·지특법 감면·특례 중 이 상황에서 검토할 조문 후보를 뽑는다.

판정이 아니라 후보 목록이다. 기계 추출 색인(C등급)이라 결과는 "이 조문을 검토할 것" 수준이며, 요건 충족 여부는 원문으로 확인해야 한다. 감면 누락은 납세자가 세금을 더 내는 방향이라 빠진 감면이 없는지 점검하는 용도다.

Args:
    tax_types: 세목 쉼표 구분 — "양도소득세,취득세,재산세,종합부동산세,증여세" 등
    situation: 상황 설명 문장. 생활어(첫집·다둥이·수용보상)를 법령 용어로 확장해 매칭한다
    assets: 자산 쉼표 구분 — "주택,농지,토지,임대주택,미분양주택,분양권·입주권" 등
    include_expired: 기한이 지난 조문까지 포함(경정청구·과거 취득분 검토 시)
    include_decree: 시행령 조문까지 포함
    include_corporate: 법인·기관 전용 조문까지 포함
    limit: 최대 표시 건수""",

    "judge_156_3_from_portfolio": """Home plus pre-sale right (분양권) one-home special case, counting homes from a holdings list.

보유 목록으로 영 §156의3 특례를 판정한다 — 주택수를 코드가 센다.

종전주택·분양권·나머지 주택 수를 목록에서 세고, 농어촌주택·상속주택 등 제외 특례를 자동 반영한 뒤 §156의3 ②③항을 판정한다. 반환의 '주택수산정'에 무엇을 몇 채로 셌는지와 제외 사유가 들어 있다.

Args:
    items: 보유 자산 목록. 원소는 {"종류": "주택"|"분양권"|"조합원입주권"|"오피스텔", "취득일": "YYYY-MM-DD", "라벨": str, "농어촌주택특례": bool, "상속특례주택": bool, ...}. 양도할 주택 하나에 "양도대상": true를 표시해야 한다. 분양권 취득일은 청약당첨일이 아니라 분양계약일(대법원 2024두54560).
    sale_date: 종전주택 양도일 YYYY-MM-DD
    new_home_completed: 분양권으로 취득하는 주택의 완성일 (③항)
    moved_in_date: 신축주택으로 세대 전원이 이사한 날
    continuous_residence_years: 신축주택 계속거주 기간(년)
    holding_waiver_reason: "" | 건설임대5년거주 | 수용 | 해외이주2년 | 취학근무국외 | 부득이1년거주
    sale_delay_reason: "" | 캠코매각의뢰 | 법원경매신청 | 공매진행 (규칙 §75①)
    delay_state_at_3y: 분양권 취득일부터 3년이 되는 날 그 상태였는지
    sold_by_that_method: 실제로 그 방법으로 양도됐는지
    partial_move_reason: "" | 취학 | 근무 | 질병 | 학교폭력""",

    "get_relief_catalog_entry": """Look up one relief catalog entry by statute reference.

감면 카탈로그 한 건을 조회한다 — "지특법 §36의5", "조특97의3", "§99의2" 같은 표기를 받는다.

조문 요지·감면율·기한을 돌려준다. 기계 추출(C등급) 값이라 확정 근거가 아니며, 요건은 원문으로 확인해야 한다.""",

    "search_tax_rulings": """Search official Korean tax rulings and tribunal decisions.

세무 해석례·심판례를 검색한다 (법제처 공동활용).

source: "국세청해석"(ntsCgmExpc — 예규 회신) | "조세심판원"(ttSpecialDecc — 재결례) | "행안부해석"(moisCgmExpc — 취득세·재산세) | "법령해석례"(expc — 법제처·기재부).

검색 방식이 소스마다 다르다: 조세심판원은 공백이 AND, 국세청·행안부는 공백이 OR다. 국세청·행안부에 공백이 든 쿼리가 오면 자동으로 따옴표를 씌워 구문 검색한다.
결과의 상세링크는 국세법령정보시스템(taxlaw)이다.""",
}
