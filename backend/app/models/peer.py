"""피어 평가: post_game_surveys / post_game_votes / chemistry_scores (6.2절, 9.4절).

교차 테이블 규칙은 DB CHECK로 표현할 수 없어 서비스 계층에서 강제한다:
  - post_game_surveys.respondent는 kind = 'MEMBER'여야 한다 (게스트는 응답 주체가 아님)
  - post_game_votes.target은 survey.respondent와 달라야 한다 (SELF_VOTE_NOT_ALLOWED)

이 파일이 담는 것은 "케미(친화도)" 데이터다. 9.4절의 결론: 케미를 코트 마진으로 *측정* 하는 것은
표본 부족(페어당 20회 모임에 평균 6쿼터)으로 불가능하므로, 경기 후 설문으로 *선언* 받는다.
  - post_game_surveys / post_game_votes : 경기 후 "잘한 사람 / 또 뛰고 싶은 사람" 각 2명 투표 (F9)
  - chemistry_scores                    : 투표를 페어 단위로 집계한 결과 + (참고용) 관찰 시너지

배정의 CHEMISTRY 전략과 F11 "나와 잘 맞는 참여자" 는 전부 투표 기반(pref_*)만 쓴다. 통계적 시너지
(synergy_*)는 매우 엄격한 3조건을 통과할 때만 화면에 노출하고, 배정 가중치 상한은 0.1 이다.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK
from app.models.enums import ReasonTag, TargetSide, VoteType, db_enum


class PostGameSurvey(Base):
    """한 참가자의 경기 후 설문 제출 1건 (S-16). events 1:N, 응답자당 회차별 1회.

    응답자는 그 회차 참석자(ATTEND)이면서 회원(kind=MEMBER)이어야 한다 — 게스트에게는 설문 링크를
    보내지 않는다. 재제출은 409 ALREADY_SUBMITTED. 응답은 선택 사항이라 참석자 전원이 행을 갖지는 않는다.
    """

    __tablename__ = "post_game_surveys"
    __table_args__ = (
        # 한 회차에 한 응답자는 한 번만 제출
        UniqueConstraint("event_id", "respondent_player_id", name="uq_post_game_surveys_respondent"),
        Index("ix_post_game_surveys_respondent", "respondent_player_id"),
    )

    id: Mapped[BigPK]
    # event_id 조회는 uq_post_game_surveys_respondent(event_id 가 맨 앞)가 맡는다 — 단독 인덱스는 0025 에서 지웠다
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    respondent_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)  # 회원만 (서비스 검증)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 제출 시각(앱 설정)

    # 최대 8행: (잘한 사람 / 또 뛰고 싶은 사람) × (같은 팀 2명 / 상대 팀 2명)
    votes: Mapped[list["PostGameVote"]] = relationship(back_populates="survey", cascade="all, delete-orphan")


class PostGameVote(Base):
    """설문 안의 지목 한 건 = "응답자가 target 을 vote_type 으로 골랐다". surveys 1:N.

    target 은 그 회차 참석자이면 게스트도 가능하다(투표의 대상). 응답자 본인은 불가 (400).
    `target_side` 는 같은 팀/상대 팀 각 2명씩이라는 UI 규칙을 사후 검증·집계하기 위해 저장한다.
    """

    __tablename__ = "post_game_votes"
    __table_args__ = (
        # 같은 설문에서 같은 사람을 같은 항목으로 두 번 지목하지 못하게 (BEST 와 PLAY_AGAIN 둘 다는 가능)
        UniqueConstraint("survey_id", "target_player_id", "vote_type", name="uq_post_game_votes_target"),
    )

    id: Mapped[BigPK]
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("post_game_surveys.id", ondelete="CASCADE"), nullable=False
    )
    target_player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)  # 게스트 가능
    vote_type: Mapped[VoteType] = mapped_column(db_enum(VoteType, 15), nullable=False)  # BEST_PERFORMER / PLAY_AGAIN
    # 같은 팀/상대 팀 — 확정 배정으로 서버가 계산한다. 배정이 없던 회차는 알 수 없어 NULL (피어 투표 설계)
    target_side: Mapped[TargetSide | None] = mapped_column(db_enum(TargetSide, 10))
    # PLAY_AGAIN 을 고른 이유 (선택). BEST_PERFORMER 는 항상 NULL
    reason_tag: Mapped[ReasonTag | None] = mapped_column(db_enum(ReasonTag, 20))

    survey: Mapped[PostGameSurvey] = relationship(back_populates="votes")


class ChemistryScore(Base):
    """players M:N players. 선언된 선호(pref_*)와 관찰된 시너지(synergy_*)를 분리해 저장한다.

    두 참가자 쌍(페어)당 1행이며, `player_a_id < player_b_id` 로 정렬해 (A,B)/(B,A) 중복을 막는다.
    조회할 때도 항상 작은 id 를 a 에 놓고 찾아야 한다. 배치 작업이 투표·라인업을 집계해 갱신한다.

    두 신호를 한 숫자로 합치지 않는 이유 (9.4절 "데이터 모델 변경"): 근거가 다른 값을 뭉개면 "왜 이
    조합을 추천했는가" 를 설명할 수 없다. 초안의 단일 chemistry 컬럼은 그래서 삭제됐다.

    표시 규칙: 표본이 부족한 페어는 synergy 를 0으로 두지 않고 NULL 로 두어 **아예 표시하지 않는다**.
    "케미 0점" 은 "사이가 나쁘다" 로 오독되기 때문이다.
    """

    __tablename__ = "chemistry_scores"
    __table_args__ = (
        # 페어당 1행
        UniqueConstraint("player_a_id", "player_b_id", name="uq_chemistry_scores_pair"),
        # (A,B) 와 (B,A) 가 따로 생기지 않도록 항상 작은 id 를 a 에 둔다. a = b (자기 자신)도 차단
        CheckConstraint("player_a_id < player_b_id", name="ck_chemistry_scores_ordered_pair"),
        # 6.4절: 한 선수가 a 쪽이든 b 쪽이든 빠르게 찾기 위한 양방향 인덱스. a 쪽은 uq_chemistry_scores_pair(a 가 맨 앞)가
        # 맡으므로 b 쪽만 따로 둔다 (ix_chemistry_scores_a 는 0025 에서 지웠다)
        Index("ix_chemistry_scores_b", "player_b_id"),
        # 선호 점수는 0~1 비율 (peer_service._directional_pref 양방향 평균)
        CheckConstraint("pref_score IS NULL OR pref_score BETWEEN 0 AND 1", name="ck_chemistry_scores_pref_range"),
    )

    id: Mapped[BigPK]
    player_a_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)  # 작은 id
    player_b_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)  # 큰 id
    # 두 사람이 같은 팀으로 함께 코트에 있던 쿼터 수. F11 "함께 뛴 횟수" 와 synergy 노출 조건(≥ 20)에 사용
    together_quarters: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # 함께 참석한 회차 수 — pref_score 의 분모 (피어 투표 설계). together_quarters 와는 용도가 다르다
    together_events: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # PLAY_AGAIN 투표를 함께 참석한 회차 수로 정규화하고 최근 회차에 가중(0.9^k)한 선호도 (양방향 평균). CHEMISTRY 전략(w_pref)의 주 입력. NULL = 투표 없음
    pref_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))  # 0~1
    # 서로를 PLAY_AGAIN 으로 지목한 적이 있으면 true — 가장 강한 신호. F11 "상호 선호" 목록의 기준
    pref_mutual: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # ── 이하 관찰된 시너지: 배치 RAPM 상호작용항 γ_jk (점/쿼터). v1 에서는 계산하지 않아 NULL ──
    synergy_est: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))  # 참고용
    synergy_ci_low: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))  # 부트스트랩 95% 구간 하한
    synergy_ci_high: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))  # 부트스트랩 95% 구간 상한
    # 9.4절 3조건(함께 뛴 쿼터 ≥ 20 AND CI 가 0 제외 AND |γ̂| ≥ 4) 통과 시에만 true → 화면 노출
    synergy_significant: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
