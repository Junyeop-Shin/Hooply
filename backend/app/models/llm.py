"""AI 설명 결과: llm_results — 내용 캐시 겸 호출 기록 (docs/07 FR-48 · FR-49, 9절 8항).

같은 입력(체인 · 배정 명단 · 전략 · 형식 버전 …)이면 같은 `cache_key` 가 되어 LLM 을 다시 부르지 않는다.
입력 원문과 가명 대응표는 저장하지 않는다 — 실명이 LLM 경로에 남지 않게. `output` 은 가명을 실명으로 되돌린 최종 결과다.
실패(폴백)도 한 줄 남겨 두고, 잠깐(`app/llm/llm_guard.RETRY_AFTER`) 지나면 다시 시도한다.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigPK


class LlmResult(Base):
    __tablename__ = "llm_results"

    id: Mapped[BigPK]
    chain: Mapped[str] = mapped_column(String(10), nullable=False)  # A 배정 설명(매니저) · B 팀원 안내 · C 전술 추천
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # sha256 hex
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # 실명으로 복원한 결과 (폴백이면 폴백 내용)
    fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # timeout · error · unknown_alias · unknown_number · leak · schema (성공이면 NULL)
    fail_reason: Mapped[str | None] = mapped_column(String(40))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
