"""공개 정책 페이지(/privacy, /terms). 실제 배포 설정(Cloud Run 서울)에 맞춘 내용만 적는다."""
import os
from html import escape

EFFECTIVE_DATE = "2026-10-13"
SUPPORT_NAME = "Budongsan Tax 고객지원"
# 문의 메일은 배포 환경변수로 바꾼다(코드 재배포 없이 Cloud Run 설정만 갱신).
CONTACT = os.environ.get("SUPPORT_EMAIL", "budongsantax.inquiry@gmail.com")

PRIVACY = [
    ("개요",
     ["Budongsan Tax(이하 '서비스')는 한국 부동산 세금 계산 도구입니다. "
      "ChatGPT 등 AI 서비스가 MCP 도구 호출로 전달한 값을 이용해 세액과 관련 요건을 계산합니다. "
      "이 방침은 서비스가 그 과정에서 처리하는 정보를 설명합니다."]),
    ("처리하는 정보",
     ["도구 입력값: 거래금액, 취득·양도일, 면적, 주택 수, 가족관계 등 이용자가 선택한 계산에 필요한 사실. "
      "AI 서비스가 도구를 호출할 때 전달한 인자만 받으며, 대화 전체를 받지 않습니다.",
      "접속 기록: 호스팅 플랫폼(Google Cloud Run)이 자동으로 남기는 요청 시각, 요청 경로, 응답 코드, "
      "접속 IP 주소, 브라우저·클라이언트 정보.",
      "문의 이메일: 이메일로 문의하면 발신 주소와 문의 내용.",
      "서비스는 회원가입·로그인·결제 기능이 없고, 주민등록번호·홈택스 계정·신분증을 요구하지 않습니다. "
      "이런 정보를 입력하지 마세요."]),
    ("이용 목적",
     ["요청한 세금 계산과 요건 판정 결과를 돌려주기 위해서만 입력값을 사용합니다.",
      "접속 기록은 장애 대응, 남용 차단, 보안 점검에 사용합니다.",
      "광고, 프로파일링, 제3자 판매에 사용하지 않습니다."]),
    ("보관 기간",
     ["도구 입력값과 계산 결과는 요청을 처리한 뒤 서버에 저장하지 않습니다. 계산 이력 데이터베이스가 없습니다.",
      "다만 처리 중 오류가 나면 오류 기록에 입력값 일부가 포함될 수 있습니다. "
      "접속 기록과 오류 기록은 Google Cloud Logging에 30일간 보관된 뒤 자동 삭제됩니다.",
      "문의 이메일은 처리를 마친 뒤 1년 안에 삭제합니다."]),
    ("처리 위탁과 외부 전송",
     ["Google LLC(Google Cloud): 서버 운영과 로그 보관. 서버 지역은 대한민국 서울(asia-northeast3)입니다.",
      "법제처 국가법령정보 공동활용(open.law.go.kr): 법령·해석례·조례 검색 도구를 호출하면 "
      "검색어와 조회 대상이 법제처로 전송됩니다. 계산 도구의 입력값은 전송되지 않습니다.",
      "도구 호출을 보낸 AI 서비스(예: OpenAI ChatGPT)의 정보 처리는 해당 서비스의 방침을 따릅니다."]),
    ("이용자의 권리",
     [f"개인정보의 열람·정정·삭제·처리정지를 {CONTACT}로 요청할 수 있습니다. "
      "서비스가 실제로 보관하는 정보는 위 접속·오류 기록과 문의 이메일뿐이며, 확인 후 지체 없이 처리합니다."]),
    ("개인정보 보호책임자",
     [f"{SUPPORT_NAME} · {CONTACT}"]),
    ("변경",
     [f"이 방침은 {EFFECTIVE_DATE}부터 적용됩니다. 내용이 바뀌면 이 페이지에 시행일과 함께 게시합니다."]),
]

TERMS = [
    ("서비스",
     ["Budongsan Tax는 이용자가 제공한 사실과 지원 연도의 세법 규칙에 따라 "
      "한국 부동산 관련 세금(취득세·재산세·종합부동산세·양도소득세·증여세·상속세 등)을 계산하고 "
      "관련 요건을 판정합니다. 이용료는 없습니다.",
      "세금 신고·납부 대행, 홈택스 등 계정 접속, 세무 대리는 하지 않습니다."]),
    ("결과의 성격",
     ["결과는 입력한 사실과 적용한 법 조문에 따른 계산이며, 결과마다 적용 조문과 입력 조건을 함께 표시합니다.",
      "입력이 빠졌거나 틀리면 결과도 달라집니다. 실제 신고·거래 전에는 입력 조건과 적용 규칙을 확인하고, "
      "필요하면 세무사 등 전문가의 검토를 받으세요.",
      "결과는 세무 자문이나 과세관청의 판단을 대신하지 않습니다."]),
    ("이용자의 의무",
     ["타인의 개인정보, 주민등록번호, 계정 비밀번호를 입력하지 마세요.",
      "서비스에 과도한 부하를 주거나 정상 운영을 방해하는 행위를 하지 마세요."]),
    ("서비스 변경과 중단",
     ["기능, 지원 세목과 연도는 바뀔 수 있습니다. 점검이나 장애로 서비스가 일시 중단될 수 있습니다."]),
    ("책임",
     ["운영자는 서비스를 정확하게 유지하려고 노력합니다. 운영자의 고의 또는 중대한 과실로 손해가 생긴 경우 "
      "관련 법령에 따라 책임을 집니다. 이 약관은 이용자의 법정 권리를 제한하지 않습니다."]),
    ("소스 코드",
     ["서비스의 소스 코드는 AGPL-3.0 라이선스로 https://github.com/taylee9809/budongsan-tax 에 공개되어 있습니다."]),
    ("문의",
     [f"{CONTACT}"]),
    ("시행",
     [f"이 약관은 {EFFECTIVE_DATE}부터 적용됩니다. 변경하면 이 페이지에 시행일과 함께 게시합니다."]),
]


def render(title: str, sections: list) -> str:
    body = "".join(
        f"<h2>{escape(h)}</h2>" + "".join(f"<p>{escape(p)}</p>" for p in paras)
        for h, paras in sections
    )
    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)} · Budongsan Tax</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 16px;"
        "line-height:1.6;color:#222;background:#fff}h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:1.6rem}"
        "a{color:#0b57d0}</style></head><body>"
        f"<h1>Budongsan Tax {escape(title)}</h1><p>시행일: {EFFECTIVE_DATE}</p>{body}"
        "<p><a href='/privacy'>개인정보처리방침</a> · <a href='/terms'>이용약관</a> · "
        "<a href='/support'>고객지원</a></p></body></html>"
    )


PRIVACY_HTML = render("개인정보처리방침", PRIVACY)
TERMS_HTML = render("이용약관", TERMS)
