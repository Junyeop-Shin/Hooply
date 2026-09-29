"""AI 배정 설명 응답 (docs/07 8.3절, FR-51)."""

from pydantic import BaseModel, Field


class AiExplanation(BaseModel):
    """체인 A (매니저용). `fallback=true` 면 AI 문장 대신 `text`(기존 규칙 설명)를 보여 준다."""

    summary: str
    reasons: list[str]
    watch_point: str
    fallback: bool
    text: str | None = Field(default=None, description="폴백일 때 보여 줄 규칙 설명")
    cached: bool = False


class AiMessage(BaseModel):
    """체인 B (팀원용) — 내 것만. 배정에 들지 않았으면 message=None."""

    message: str | None
    fallback: bool
