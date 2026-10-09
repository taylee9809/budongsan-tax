"""budongsan-tax 배포 패키지 루트.

저장소는 평면 모듈(tax_params, tax_judgment, tax_nodes/ ...)을 그대로 쓴다. pip로 설치하면 이 디렉터리가
site-packages/budongsan_tax/ 가 되므로, 같은 import가 설치본에서도 풀리도록 패키지 디렉터리를 sys.path 앞에 둔다.
저장소 안에서 실행할 때는 이 파일이 하는 일이 없다.
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
