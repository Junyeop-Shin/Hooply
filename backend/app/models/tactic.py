"""전술 이름표: event_play_assignments — 그날 블랙/화이트에서 전술 슬롯마다 앉힌 선수 (docs/07 FR-47).

전술 자체는 DB 에 없고 `app/tactics/presets.py` 가 정본이다. 여기에는 `play_key`("preset:high_pnr") 로만 잇는다.
한 일정 · 한 팀 · 한 전술 안에서 슬롯은 한 번만 (UNIQUE). 저장은 그 조합의 행을 통째로 바꿔 끼운다.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

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
