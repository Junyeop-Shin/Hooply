"""AI 설명 (docs/07 F19 · F20). LangChain 으로 모델을 부르고, 모든 호출은 llm_guard 를 거친다.

  model.py      모델 만들기 — 설정 한 곳(LLM_MODEL · LLM_API_KEY)만 바꾸면 다른 공급자로 바뀐다
  llm_guard.py  가명화 · 호출 · 출력 검증 · 실명 복원 · 캐시 · 폴백 (FR-48 ~ FR-50, 명세 9절)
"""
