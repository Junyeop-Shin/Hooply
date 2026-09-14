"""경기 기록: quarters / quarter_lineups (6.2절). games 계층 없이 events → quarters 직결.

코트 마진 (쿼터 수·길이가 유동적이라 정규화 필수):
  raw_margin        = 내 팀 득점 − 상대 팀 득점
  normalized_margin = raw_margin × (10 / duration_min)
실력 지표에 반영되는 값은 이 마진이 아니라 기대 마진 대비 잔차다 (9.2절).

왜 games 테이블이 없는가 (2.5절 운영 프로토콜): 하루의 경기는 "고정된 두 팀이 7~10쿼터를 연속으로
뛰는" 형태다. 쿼터 사이에 팀이 바뀌지 않으므로 경기라는 중간 계층은 불필요하고, 쿼터가 곧 관측 단위다.
쿼터 수가 유동적이므로 추가·삭제가 실제로 일어나며, 삭제 시 지표를 롤백해야 한다 (13.2절 2항).
그래서 잔차를 증분으로만 갱신하지 말고, 라인업 원본(이 테이블)으로 언제든 재계산할 수 있게 둔다.

매니저는 경기 *후* S-15 에서 여러 쿼터를 한 번에 입력한다 (`PUT /events/{id}/quarters` 일괄 저장).
개인 스탯은 전혀 받지 않는다 — "누가 뛰었는지 + 팀 점수" 만으로 계산하는 것이 핵심 가치 4 다.
"""

from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK, CreatedAtMixin
from app.models.enums import Position, Side, db_enum


class Quarter(CreatedAtMixin, Base):
    """쿼터 1개 = 실력 모델의 관측치 1개 (9.2절 RAPM 의 행 하나). events 1:N.

    저장 시 서버가 출전 10명 전원의 quarter_lineups 마진을 일괄 계산한다. 한 팀 출전이 5명이 아니면
    400 INVALID_LINEUP_SIZE. `rating_warmup_events`(첫 2회 모임) 안의 쿼터는 지표 갱신에서 제외한다
    (13.2절 1항) — 기록 자체는 저장한다.
    """

    __tablename__ = "quarters"
    __table_args__ = (
        # 한 회차 안에서 쿼터 번호는 유일 (409 QUARTER_EXISTS)
        UniqueConstraint("event_id", "quarter_no", name="uq_quarters_event_no"),
        # 점수는 음수가 될 수 없다
        CheckConstraint("black_score >= 0 AND white_score >= 0", name="ck_quarters_score_nonneg"),
        # 정규화 식의 분모이므로 0 이면 안 된다
        CheckConstraint("duration_min > 0", name="ck_quarters_duration_positive"),
    )

    id: Mapped[BigPK]
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    quarter_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1부터. 삭제 후 번호가 비어도 됨
    black_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 블랙(squad_no 1) 팀 득점
    white_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 화이트(squad_no 2) 팀 득점
    # 쿼터 길이(분). 기본 8, 입력은 1~10분(app.schemas.game). 시간 정규화 기준이며, 마지막 쿼터를 짧게 뛴 경우 등에 바꾼다
    duration_min: Mapped[int] = mapped_column(SmallInteger, default=8, server_default="8", nullable=False)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)  # 입력한 매니저

    # 출전 10명 (블랙 5 + 화이트 5). 쿼터 삭제 시 함께 삭제 → 마진 롤백 재계산
    lineups: Mapped[list["QuarterLineup"]] = relationship(
        back_populates="quarter", cascade="all, delete-orphan"
    )


class QuarterLineup(Base):
    """그 쿼터에 출전한 선수 한 명의 기록. quarters 1:N (정확히 10행), 선수별 코트 마진의 원천.

    raw_margin / normalized_margin 은 클라이언트가 보내지 않고 서버가 Quarter 점수로 계산해 넣는다.
    스코어·라인업 수정(PATCH) 시에도 다시 계산된다. 게스트도 여기 포함된다 (기록의 대상).
    """

    __tablename__ = "quarter_lineups"
    # 한 쿼터에 같은 선수가 두 번(또는 양 팀에) 들어가지 않도록
    __table_args__ = (UniqueConstraint("quarter_id", "player_id", name="uq_quarter_lineups_player"),)

    id: Mapped[BigPK]
    quarter_id: Mapped[int] = mapped_column(ForeignKey("quarters.id", ondelete="CASCADE"), nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)  # 6.4절: 개인 마진 집계
    side: Mapped[Side] = mapped_column(db_enum(Side, 5), nullable=False)  # BLACK / WHITE
    position: Mapped[Position | None] = mapped_column(db_enum(Position, 2))  # 실제로 뛴 포지션 (선택 입력)
    # 내 팀 득점 − 상대 팀 득점. 같은 쿼터의 BLACK 행과 WHITE 행은 부호만 다르다
    raw_margin: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # raw_margin × (10 / duration_min). 10분 환산값. 지표 갱신·대시보드 추이는 이 값을 쓴다
    normalized_margin: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    # 이 쿼터가 이 사람의 실력에 남긴 몫 = (실제 마진 − 기대 마진). rating_service 가 팀 전체를 재생하며 채운다.
    # 기간별 기여 점수(리더보드 월별)를 내려면 회차 단위로 쪼개진 값이 필요하다 — 프로필의 누적 총합만으로는
    # "9월에 얼마나 기여했나" 를 답할 수 없다. 지표에 반영하지 않는 첫 두 일정은 0 이다.
    residual: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default="0")

    quarter: Mapped[Quarter] = relationship(back_populates="lineups")
