"""전술 추천 · 전술판 (docs/07, F20·F21).

DB 와 무관한 순수 계산만 둔다. 화면·API 는 이 모듈을 불러 쓴다.

  court.py     코트 좌표 판정 (FR-40)          — 프론트 `src/lib/court.ts` 와 상수가 같다
  play.py      전술 데이터 모델과 재생 가능성 검사 (FR-38, FR-39, FR-41)
  roles.py     선수별 역할 점수 (FR-43, 7절)
  matching.py  슬롯 최적 배치 · 전술 순위 (FR-44, FR-45)
"""
