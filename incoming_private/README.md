# 비공개 원본에서 가져온 법인세 조문 노드 (통합 전 대기)

원본 저장소(korea-realestate-mcp, 커밋 89af477)의 `tax_nodes/beopin_*.py` 4개와 검증 스크립트
`scripts/experiments/verify_beopin_*.py` 4개다. 2026-10-16 에 원본에서 만든 것이고 공개 저장소에는 나온 적이 없다.

아직 `tax_nodes/` 에 넣지 않았다 — 공개 저장소의 `tax_nodes/beobin.py`·`beobin_bisaeop.py` 와 노드 id 가 겹쳐
(예: 법인세법-55-1-1) 같이 올리면 엔진이 "노드 id 중복"으로 멈춘다. 이 폴더는 통합 작업이 끝나면 없앤다.
