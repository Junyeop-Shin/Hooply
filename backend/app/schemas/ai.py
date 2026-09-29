"""AI 배정 설명 응답 (docs/07 8.3절, FR-51)."""

from pydantic import BaseModel, Field


class AiExplanation(BaseModel):
    """체인 A (매니저용). `fallback=true` 면 AI 문장 대신 `text`(기존 규칙 설명)를 보여 준다."""

    summary: str = Field(description="팀들의 색깔을 대비한 핵심 한 문장")
    key_players: list[str] = Field(description="활약이 기대되는 선수 (팀 · 선수 · 기대 장면)")
    chemistry: list[str] = Field(description="호흡이 좋을 조합 (두 사람 · 이유)")
    gaps: list[str] = Field(description="부족한 역할이 있는 팀")
    watch_point: str
    fallback: bool
    text: str | None = Field(default=None, description="폴백일 때 보여 줄 규칙 설명")
    cached: bool = False
    fail_reason: str | None = Field(default=None, description="폴백 사유 코드 (timeout · leak · schema · error:… · disabled)")


class AiMessage(BaseModel):
    """체인 B (팀원용) — 내 것만. 배정에 들지 않았으면 in_assignment=false."""

    in_assignment: bool = True
    why_position: str = ""  # 왜 이 포지션을 맡았는지
    role: str = ""  # 이 팀에서 기대하는 역할
    partner: str = ""  # 호흡을 맞추면 좋을 동료
    fallback: bool
    text: str | None = Field(default=None, description="폴백일 때 보여 줄 규칙 설명")
    cached: bool = False
    fail_reason: str | None = None


class AiTacticItem(BaseModel):
    play_key: str
    reason: str  # 폴백이면 규칙 문장 ("적합도 81 · 허재 볼 핸들러(볼 운반) …")
    key_roles: list[str]
    caution: str


class AiTactics(BaseModel):
    """체인 C — 한 팀의 추천 전술 설명. 추천 순서·전술은 규칙 추천과 같다."""

    squad_no: int
    one_liner: str
    items: list[AiTacticItem]
    fallback: bool
    cached: bool = False
    fail_reason: str | None = None
