"""일정·참석: events / event_attendances (설계서 6.2절 + 게스트 기능 설계).

게스트 참석은 매니저 또는 **게스트를 부른 플레이어** 가 대신 등록한다 (스펙으로 확장됨).

"모임 한 회차" 가 `events` 한 행이다. 회차에 매달리는 것들:
  - 참석 응답        event_attendances (이 파일)
  - 배정 실행 이력   assignment_runs   (assignment.py)
  - 쿼터 기록        quarters          (game.py)  — 초안의 games 계층을 없애고 events 에 직결
  - 경기 후 설문     post_game_surveys (peer.py)

흐름 B (5.3절): 매니저가 일정 등록(S-09) → 플레이어 RSVP(S-10) → 참석자 현황·게스트 추가(S-11)
→ 배정 → 쿼터 기록 → 피어 설문. 이 파일은 그중 앞의 두 단계를 담당한다.
"""

from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK, TimestampMixin
from app.models.enums import AttendanceStatus, EventStatus, db_enum


class Event(TimestampMixin, Base):
    """모임 일정 한 회차 (S-09 일정 등록 폼 = 이 테이블). teams 1:N.

    팀이 ACTIVE 가 아니면 만들 수 없다 (422 TEAM_NOT_ACTIVE). 취소는 행을 지우지 않고 status 를
    CANCELED 로 바꾼다 — 이미 달린 응답·배정 이력을 보존하기 위함.
    """

    __tablename__ = "events"

    # 일정 목록·실력 재계산이 모두 "팀으로 좁혀 날짜순" 이라 복합 인덱스로 정렬까지 인덱스가 맡게 한다
    # team_id 단독 조회도 이 인덱스(team_id 가 맨 앞)가 맡는다 — 단독 인덱스는 0025 에서 지웠다
    __table_args__ = (
        Index("ix_events_team_date", "team_id", "event_date", "id"),
        # 자정을 넘기는 일정은 받지 않는다 (event_service 와 같은 규칙). 시각이 하나라도 비면 검사하지 않는다
        CheckConstraint("start_time IS NULL OR end_time IS NULL OR end_time > start_time", name="ck_events_time_order"),
    )

    id: Mapped[BigPK]
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(100))  # 없으면 화면에서 날짜로 대체
    event_date: Mapped[date] = mapped_column(Date, nullable=False)  # 모임 날짜 (필수)
    start_time: Mapped[time | None] = mapped_column(Time)  # 시작 시각 (시간대 없는 벽시계 시간)
    end_time: Mapped[time | None] = mapped_column(Time)  # 종료 시각
    venue: Mapped[str | None] = mapped_column(String(100))  # 장소. 보통 teams.home_court
    rsvp_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 이후 응답 시 422 RSVP_CLOSED
    status: Mapped[EventStatus] = mapped_column(
        db_enum(EventStatus, 10), default=EventStatus.OPEN, server_default="OPEN", nullable=False
    )
    memo: Mapped[str | None] = mapped_column(Text)  # 매니저 메모 (준비물, 주차 안내 등)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)  # 등록한 매니저

    attendances: Mapped[list["EventAttendance"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventAttendance(Base):
    """회차별 참석 응답 (events M:N players 의 교차 테이블). 참가자당 회차별 1행.

    두 가지 경로로 만들어진다.
      - 플레이어 본인   `PUT /events/{id}/attendance`               → registered_by NULL
      - 매니저 대리     `PUT /events/{id}/attendances/{player_id}` → registered_by = 매니저 (게스트는 항상 이쪽)
    `status = ATTEND` 인 행이 배정 실행(assignment_runs)의 입력 명단이 된다.
    """

    __tablename__ = "event_attendances"
    __table_args__ = (
        # 한 회차에 한 참가자는 응답 1건. 응답 변경은 UPDATE
        UniqueConstraint("event_id", "player_id", name="uq_event_attendances_player"),
        Index("ix_event_attendances_event_status", "event_id", "status"),  # 6.4절: 참석자 조회
        Index("ix_event_attendances_lock_request", "team_lock_request_player_id"),
    )

    id: Mapped[BigPK]
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)
    status: Mapped[AttendanceStatus] = mapped_column(
        db_enum(AttendanceStatus, 10), default=AttendanceStatus.PENDING, server_default="PENDING", nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)  # "늦게 감" 등 응답자 메모
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = PENDING(미응답)
    registered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # 게스트 등록자 / 대리 응답한 매니저
    # 게스트 기능 설계: "이 게스트를 이 player 와 같은 팀으로 배정해 달라" 는 **요청**. 게스트 행에만 값이
    # 들어가며 강제 제약이 아니다. 매니저가 S-12 배정 화면에서 "묶기 제안" 으로 보고 승인해야 LOCK 제약이 된다.
    team_lock_request_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))

    event: Mapped[Event] = relationship(back_populates="attendances")
