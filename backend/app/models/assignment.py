"""배정 5개 테이블 (6.2절): runs → constraints / candidates → squads → slots.

제약(assignment_constraints)은 회차별이다 (v0.3). 한 테이블로 LOCK / SEPARATE / PIN을 모두 표현한다.
  LOCK     + group_no  → 반드시 같은 팀
  SEPARATE + group_no  → 반드시 다른 팀
  PIN      + squad_no  → 지정한 팀에 사전 배치

계층 구조와 각 계층의 의미 (설계서 6.3절 "1:N 체인")
  assignment_runs          "언제·누가·어떤 조건으로 배정을 돌렸나"  — 재배정마다 새 행 (이력 보존)
    ├─ assignment_constraints  그 실행에 걸린 묶기/분리/사전배치
    └─ assignment_candidates   전략별 후보안 (보통 SKILL / CHEMISTRY / BALANCED 3개)
         └─ assignment_squads    후보안 안의 팀 (2팀이면 블랙/화이트)
              └─ assignment_slots  팀에 배정된 선수 한 명 + 배정 포지션

매니저가 후보안 하나를 확정(`:adopt`)하면 그 candidate 의 `is_adopted` 만 true 가 되고, 플레이어는
`GET /events/{id}/assignment/adopted` 로 그 편성을 본다 (FR-23~24).

제약을 페널티가 아니라 자료구조로 처리하는 이유 (9.6절): LOCK 을 목적함수 페널티로 두면 "실력 우선"
전략에서 묶음이 깨질 수 있다. 알고리즘은 LOCK 그룹을 슈퍼노드로 축약해 통째로만 움직이므로 어떤
가중치에서도 위반이 원천적으로 불가능하다. 이 테이블은 그 입력을 저장할 뿐이다.
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK, CreatedAtMixin
from app.models.enums import ConstraintType, Position, Strategy, db_enum


class AssignmentRun(CreatedAtMixin, Base):
    """배정 실행 1회 (`POST /events/{id}/assignments`). events 1:N — 노쇼 등으로 재실행하면 행이 늘어난다.

    `roster_snapshot` 을 저장하는 이유: 실력값은 쿼터를 저장할 때마다 바뀐다. 나중에 "그때 왜 이렇게
    나눴는가" 를 설명하려면 실행 시점의 참석자와 실력값을 그대로 보관해야 한다.
    """

    __tablename__ = "assignment_runs"

    id: Mapped[BigPK]
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    executed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)  # 실행한 매니저
    team_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 팀 수 T. v1 은 2 고정 (Q4)
    # 요청 body 의 strategies 와 9.5절 가중치(w_skill 등) 등 실행 파라미터. 가중치 튜닝 이력 추적용
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)  # 가중치
    # 실행 시점 참석자 목록 [{player_id, display_name, skill, positions, is_guest, ...}]
    roster_snapshot: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)  # 실행 시점 참석자·실력

    constraints: Mapped[list["AssignmentConstraint"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["AssignmentCandidate"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AssignmentConstraint(Base):
    """회차별 배정 제약 한 줄 = (제약 유형, 선수 1명, 그룹 번호 또는 팀 번호).

    API 의 `lock_groups: [[12, 45, 78], [3, 9]]` 는 이 테이블에서
      (LOCK, player 12, group_no 1), (LOCK, 45, 1), (LOCK, 78, 1), (LOCK, 3, 2), (LOCK, 9, 2)
    다섯 행이 된다. `pins: [{player_id: 5, squad_no: 1}]` 는 (PIN, 5, squad_no 1) 한 행이다.
    group_no 는 run 안에서만 의미가 있는 임의 번호다.

    "직전 회차 제약 불러오기" 는 이전 run 의 행을 새 run 으로 복사하는 것이다. 다음 회차 배정 화면은
    항상 빈 상태로 시작한다 (FR-18).
    """

    __tablename__ = "assignment_constraints"
    __table_args__ = (
        # 유형별로 채워야 하는 컬럼을 강제: LOCK/SEPARATE 는 group_no 만, PIN 은 squad_no 만
        CheckConstraint(
            "(type IN ('LOCK','SEPARATE') AND group_no IS NOT NULL AND squad_no IS NULL)"
            " OR (type = 'PIN' AND squad_no IS NOT NULL AND group_no IS NULL)",
            name="ck_assignment_constraints_shape",
        ),
    )

    id: Mapped[BigPK]
    run_id: Mapped[int] = mapped_column(
        ForeignKey("assignment_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[ConstraintType] = mapped_column(db_enum(ConstraintType, 10), nullable=False)  # LOCK/SEPARATE/PIN
    group_no: Mapped[int | None] = mapped_column(SmallInteger)  # LOCK/SEPARATE: 같은 번호 = 같은 그룹. PIN 은 NULL
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    squad_no: Mapped[int | None] = mapped_column(SmallInteger)  # PIN: 배치할 팀 번호(1=블랙). 그 외 NULL

    run: Mapped[AssignmentRun] = relationship(back_populates="constraints")


class AssignmentCandidate(Base):
    """후보안 하나 = 전략 하나의 결과. runs 1:N (보통 3행).

    `PATCH /assignments/candidates/{id}` 로 매니저가 선수를 swap 하면 이 후보안의 squads/slots 와
    metrics 가 다시 계산된다 (FR-22). 확정(`:adopt`)되면 is_adopted = true, 같은 run 의 다른 후보안은 false.
    """

    __tablename__ = "assignment_candidates"
    __table_args__ = (
        # 한 run 안에서 is_adopted = true인 candidate는 최대 1개 (부분 유니크 인덱스)
        Index(
            "uq_assignment_candidates_adopted",
            "run_id",
            unique=True,
            postgresql_where=text("is_adopted"),
        ),
    )

    id: Mapped[BigPK]
    run_id: Mapped[int] = mapped_column(
        ForeignKey("assignment_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy: Mapped[Strategy] = mapped_column(db_enum(Strategy, 10), nullable=False)  # SKILL/CHEMISTRY/BALANCED
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))  # 목적함수 J (낮을수록 좋음)
    # FR-21 표시 지표: 팀별 평균 실력·실력 편차·포지션 커버리지·게스트 수 등. 화면 카드가 그대로 읽는다
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # 규칙 기반 템플릿으로 만든 설명 문장 (F6). 게스트 포함 시 "게스트 N명은 지정 등급으로 계산" 필수 명시
    explanation: Mapped[str | None] = mapped_column(Text)
    is_adopted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)  # 확정 여부

    run: Mapped[AssignmentRun] = relationship(back_populates="candidates")
    # squad_no 순(블랙 → 화이트)으로 로드
    squads: Mapped[list["AssignmentSquad"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="AssignmentSquad.squad_no"
    )


class AssignmentSquad(Base):
    """후보안 안의 팀 하나. candidates 1:N (team_count 개).

    squad_no 1 = 블랙, 2 = 화이트 가 기본이며 quarters 의 black/white 및 quarter_lineups.side 와 대응한다.
    """

    __tablename__ = "assignment_squads"
    # 한 후보안 안에서 팀 번호는 유일
    __table_args__ = (UniqueConstraint("candidate_id", "squad_no", name="uq_assignment_squads_no"),)

    id: Mapped[BigPK]
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("assignment_candidates.id", ondelete="CASCADE"), nullable=False
    )
    squad_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1부터. PIN 의 squad_no 와 같은 번호 체계
    squad_name: Mapped[str] = mapped_column(String(20), nullable=False)  # 기본 블랙 / 화이트 (Q6: 수정 가능)
    avg_skill: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))  # 팀원 skill_overall 평균. 매니저 화면에만 노출

    candidate: Mapped[AssignmentCandidate] = relationship(back_populates="squads")
    slots: Mapped[list["AssignmentSlot"]] = relationship(
        back_populates="squad", cascade="all, delete-orphan"
    )


class AssignmentSlot(Base):
    """팀에 들어간 선수 한 명. squads 1:N. 한 후보안에서 한 선수는 한 팀에만 있어야 한다.

    같은 candidate 의 다른 squad 에 같은 player 가 중복되지 않는 것은 squad 경계를 넘는 조건이라
    DB 유니크로 표현하지 못하고 서비스 계층이 보장한다.
    """

    __tablename__ = "assignment_slots"
    # 한 팀 안에 같은 선수가 두 번 들어가지 않도록
    __table_args__ = (UniqueConstraint("squad_id", "player_id", name="uq_assignment_slots_player"),)

    id: Mapped[BigPK]
    squad_id: Mapped[int] = mapped_column(
        ForeignKey("assignment_squads.id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)
    assigned_position: Mapped[Position | None] = mapped_column(db_enum(Position, 2))  # 알고리즘이 정한 포지션. 미정이면 NULL
    # 매니저가 swap 으로 손본 자리면 true (FR-22). 알고리즘 결과와 사람 판단을 구분해 품질 추적
    is_manual_override: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    squad: Mapped[AssignmentSquad] = relationship(back_populates="slots")
