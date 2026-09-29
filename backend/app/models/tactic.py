"""전술 테이블 (docs/07 8.2절).

- event_play_assignments  그날 블랙/화이트에서 전술 슬롯마다 앉힌 선수 (FR-47). 전술은 `play_key` 로만 잇는다
                          ("preset:high_pnr" — 정본 app/tactics/presets.py, "team:12" — team_plays).
                          한 일정 · 한 팀 · 한 전술 안에서 슬롯은 한 번만 (UNIQUE). 저장은 그 조합의 행을 통째로 바꿔 끼운다.
- team_plays              팀이 직접 만든 전술 (FR-57)
- tactic_comments         전술 댓글 (FR-60)
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK


class EventPlayAssignment(Base):
    __tablename__ = "event_play_assignments"
    __table_args__ = (
        UniqueConstraint("event_id", "squad_no", "play_key", "slot", name="uq_event_play_assignments_slot"),
        CheckConstraint("slot BETWEEN 1 AND 5", name="ck_event_play_assignments_slot"),
    )

    id: Mapped[BigPK]
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    squad_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1 블랙 · 2 화이트 (확정 배정의 squad_no)
    play_key: Mapped[str] = mapped_column(String(40), nullable=False)  # "preset:high_pnr"
    slot: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1~5
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TeamPlay(Base):
    """팀이 직접 만든 전술 (docs/07 FR-57). play_key 는 "team:<id>", Play.key 는 "team_<id>".

    시작 위치 · 공 · 단계는 `body`(JSON) 에, 역할은 `roles` 에 둔다. 저장할 때 app/tactics/play.py 의 Play 검증과
    재생 가능성 검사(FR-41)를 통과해야 한다. 역할은 규칙 추출 → AI 태깅 → 매니저 수정 중 마지막 것이 남는다(`role_source`).
    """

    __tablename__ = "team_plays"

    id: Mapped[BigPK]
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[str] = mapped_column(String(80), nullable=False)
    defense: Mapped[str] = mapped_column(String(4), nullable=False)  # man · zone · any
    situation: Mapped[str] = mapped_column(String(12), nullable=False, default="half_court")  # half_court · inbound
    counter: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # {start: [{x,y}×5], ball, steps: [...]}
    roles: Mapped[list[str]] = mapped_column(JSONB, nullable=False)  # 자리 1~5 역할
    role_source: Mapped[str] = mapped_column(String(10), nullable=False, default="RULE")  # RULE · AI · MANAGER
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TacticComment(Base):
    """전술 댓글 (docs/07 FR-60). 팀 안에서 전술(프리셋 · 팀 전술) 하나에 다는 의견. 팀원만 읽고 쓴다."""

    __tablename__ = "tactic_comments"
    __table_args__ = (Index("ix_tactic_comments_team_play", "team_id", "play_key", "created_at"),)

    id: Mapped[BigPK]
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    play_key: Mapped[str] = mapped_column(String(40), nullable=False)  # "preset:high_pnr" · "team:12"
    author_player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    author: Mapped["Player"] = relationship()  # noqa: F821 — app.models.team
