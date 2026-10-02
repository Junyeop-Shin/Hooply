"""프로필: player_profiles / player_positions / skill_rating_history (설계서 6.2절, 9.2절).

한 참가자(players)의 "실력이 얼마인가 / 어떤 포지션을 뛰는가 / 실력값이 어떻게 변해 왔는가" 를 담는다.
세 테이블 모두 users 가 아니라 **players** 에 매달린다. 따라서 같은 사람이라도 팀마다 프로필이 따로
있다 (13.2절 4항) — 클럽마다 상대 수준이 다르기 때문에 의도된 설계다.

실력값의 두 층 (9.2절)
  - `prior_overall`   : 경기 데이터가 없을 때의 출발점. 설문(8.4절) + 매니저 정렬(8.5절) 또는
                        게스트 등급으로 만든다.
  - `skill_overall`   : 서비스가 실제로 배정에 쓰는 현재값. 쿼터 저장 때마다 잔차 기반 Elo 로 갱신되고
                        (층 1), 주 1회 배치 RAPM 이 보정한다 (층 2).
  값의 단위는 "쿼터당 득실 기여도(점)" 이다. +2.0 이면 이 선수가 코트에 있을 때 팀이 쿼터당 2점 유리.
  플레이어에게는 수치를 노출하지 않고 5등급으로만 보여준다 (FR-28).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK, CreatedAtMixin
from app.models.enums import Position, PriorSource, RatingSource, SelfRankLevel, db_enum
from app.models.team import Player


class PlayerProfile(Base):
    """players 1:1. skill_overall의 단위는 '쿼터당 득실 기여도(점)' (9.2절).

    PK 가 곧 FK(player_id) 인 1:1 확장 테이블. 참가자가 생길 때 함께 만들어지며, 게스트도 행을 갖는다
    (게스트는 prior_source=MANAGER 또는 DEFAULT, skill_confidence 0~0.25 로 시작).

    갱신 주체
      - 온보딩 설문 제출 / 매니저 정렬 저장  → prior_* 와 초기 skill_*
      - 쿼터 저장(PATCH/DELETE 포함)        → skill_overall, quarters_played, cumulative_residual
      - 피어 설문 집계                       → peer_vote_score
      - 관리자 콘솔                          → 어느 값이든 (skill_rating_history + audit_logs 에 기록)
    """

    __tablename__ = "player_profiles"
    __table_args__ = (
        # 신뢰도는 0(정보 없음)~1(충분한 표본) 사이의 비율
        CheckConstraint("skill_confidence BETWEEN 0 AND 1", name="ck_player_profiles_confidence"),
    )

    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    prior_overall: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 설문+매니저 정렬 / 게스트 등급
    prior_source: Mapped[PriorSource | None] = mapped_column(db_enum(PriorSource, 20))  # prior 가 어디서 왔는지
    # 현재 종합 실력 r (9.2절 Elo 의 r_i). 배정 목적함수와 기대 마진 계산에 쓰는 값. NULL = 아직 없음
    skill_overall: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    # 세부 6축 (8.4절). 표시·포지션 매칭용이며 배정 총점에는 skill_overall 만 쓴다
    skill_shooting: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 슛 ← B2, B1
    skill_ball_handling: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 볼핸들링 ← B3, B1
    skill_passing: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 패스 ← B1, E1
    skill_defense: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 수비 ← C1, C2
    skill_rebound_post: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 골밑 ← A1 키, B1, D3
    skill_stamina: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 체력 ← E2
    # 0~1. 표본(quarters_played) 이 쌓일수록 올라간다. < 0.3 이면 화면에 "데이터 부족" 배지
    skill_confidence: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal(0), server_default="0", nullable=False
    )  # 게스트 초기값 0 (등급 지정 시 0.25)
    # 출전 쿼터 수 n_i. Elo 학습률 K_i = 0.35 / (1 + n_i/20) 의 분모. 병합 시 합산
    quarters_played: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # 잔차 D = 실제 마진 − 기대 마진 의 누적. 원시 마진을 누적하면 제로섬으로 0에 수렴하므로 (9.1절)
    # 반드시 잔차만 누적한다. 쿼터 삭제 시 롤백돼야 하므로 라인업 원본으로 재계산 가능해야 한다
    cumulative_residual: Mapped[Decimal] = mapped_column(
        Numeric(7, 2), default=Decimal(0), server_default="0", nullable=False
    )  # 기대 마진 대비 잔차 누적 (원시 마진이 아님)
    # 대시보드 표시용. 정규화 마진의 평균이며 지표 갱신에는 쓰지 않는다
    avg_margin_per_quarter: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # 표시용 파생값
    # 피어 투표(BEST_PERFORMER) 를 함께 뛴 인원수로 정규화한 점수. 실력 반영 가중치 상한 0.3 (10장)
    peer_vote_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    # 관리자 보정 (0025). 재계산은 prior_overall + admin_adjust 에서 출발하므로 설문 · 정렬 · 쿼터를 다시 계산해도
    # 보정이 사라지거나 두 번 더해지지 않는다. 설문 · 정렬 재계산(prior)은 이 값을 건드리지 않는다
    admin_adjust: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal(0), server_default="0", nullable=False)
    # 팀 가입 후 답하는 "이 동호회에서 내 실력 위치" (구 설문 E3). NULL 이면 미응답 → prior 의 self_rank 성분 제외
    self_rank_level: Mapped[SelfRankLevel | None] = mapped_column(db_enum(SelfRankLevel, 5))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    player: Mapped[Player] = relationship(back_populates="profile")


class PlayerPosition(Base):
    """참가자별 포지션 가능/선호 정보 (players 1:N, 포지션당 1행이므로 최대 5행).

    온보딩 설문 D1(가능)·D2(선호)·D3(1번/5번 확인) 또는 게스트 등록 시 `playable_positions` 로 만든다.
    배정 알고리즘은 `can_play` 인 행만 보고 "팀당 PG 1명·C 1명 이상" 하드 제약을 검사하고,
    `preference_rank` 로 선호 포지션 미충족 페널티(w_role)를 계산한다.
    """

    __tablename__ = "player_positions"
    __table_args__ = (
        # 한 참가자에게 같은 포지션 행이 두 개 생기지 않도록
        # player_id 로 좁히는 조회도 이 유니크 인덱스가 맡는다 (단독 인덱스는 0025 에서 지웠다)
        UniqueConstraint("player_id", "position", name="uq_player_positions_player_position"),
        # 자기평가 1~5 등급 범위. NULL 은 미응답
        CheckConstraint("self_rating IS NULL OR self_rating BETWEEN 1 AND 5", name="ck_player_positions_self_rating"),
    )

    id: Mapped[BigPK]
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[Position] = mapped_column(db_enum(Position, 2), nullable=False)  # PG/SG/SF/PF/C
    can_play: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)  # 수행 가능
    preference_rank: Mapped[int | None] = mapped_column(SmallInteger)  # 1 = 가장 선호. NULL = 선호 순위 없음
    self_rating: Mapped[int | None] = mapped_column(SmallInteger)  # 그 포지션에서의 자기평가 1~5 (선택)

    player: Mapped[Player] = relationship(back_populates="positions")


class SkillRatingHistory(CreatedAtMixin, Base):
    """실력값(skill_overall)이 바뀔 때마다 한 줄씩 남기는 변동 이력 (append-only).

    관리자 콘솔의 원시 데이터 열람(S-18)과 "왜 이 값이 됐는가" 추적에 쓴다. 갱신 코드는 프로필을 바꿀 때
    반드시 이 테이블에도 기록해야 한다. `ref_type`/`ref_id` 는 FK 없는 다형 참조로, 어느 쿼터·설문·정렬
    때문에 바뀌었는지를 가리킨다.
    """

    __tablename__ = "skill_rating_history"

    id: Mapped[BigPK]
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[RatingSource] = mapped_column(db_enum(RatingSource, 20), nullable=False)  # 변동 원인
    before_value: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 변경 전 skill_overall (최초는 NULL)
    after_value: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 변경 후 skill_overall
    delta: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # after − before. 조회 편의용 중복 저장
    ref_type: Mapped[str | None] = mapped_column(String(30))  # 예: quarter / survey_response / ranking
    ref_id: Mapped[int | None]  # ref_type 테이블의 id. FK 를 걸지 않아 원본이 지워져도 이력은 남는다
    reason: Mapped[str | None] = mapped_column(Text)  # 수동 보정 시 사유 (ADMIN_ADJUST 는 필수 입력)
