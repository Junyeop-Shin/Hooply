"""팀·참가자: teams / players (설계서 6.2절).

설계 원칙: 로그인 계정(users)과 경기 참가자(players)를 분리한다.
게스트는 user_id가 NULL인 players 행이며, 경기 기록·배정·투표는 모두 player_id를 참조한다.

왜 분리하는가 (6.2절 "설계 원칙")
  - 게스트는 계정이 없지만 기록·배정·투표의 *대상* 이 된다. 같은 테이블에 두면 게스트마다 가짜 계정을
    만들어야 하고, 나중에 정식 가입하면 기록이 두 갈래로 갈라진다.
  - 부수 효과로 초안의 `team_memberships` 가 `players` 에 흡수되어 팀 소속·역할도 여기서 관리한다.
  - 실력 지표(player_profiles)는 players 에 매달리므로 **팀 단위** 로 관리된다. 클럽마다 상대 수준이
    다르기 때문이며, 이것은 버그가 아니라 의도다 (13.2절 4항).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK, CreatedAtMixin, TimestampMixin
from app.models.enums import (
    ApprovalStatus,
    ClaimStatus,
    PlayerKind,
    PlayerStatus,
    TeamRole,
    TeamStatus,
    db_enum,
)


class Team(TimestampMixin, Base):
    """동호회(팀). 팀 코드로 가입하고, 회원이 min_members 이상 모이면 ACTIVE 가 된다 (F2, FR-04~06).

    - `owner_user_id` 는 팀 생성자. 생성자는 자동으로 MANAGER 역할의 players 행을 갖는다.
    - 매니저 권한 자체는 owner 가 아니라 `players.role` 로 판단한다 (매니저는 여러 명일 수 있음).
    - status 전이는 team_service.refresh_team_status 가 회원 수를 세어 결정한다.
    """

    __tablename__ = "teams"

    id: Mapped[BigPK]
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 초대용 코드 8자리(대문자+숫자). 카카오톡으로 공유되며 재발급(code:regenerate) 가능
    team_code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)  # 대문자+숫자
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)  # 팀 생성자
    status: Mapped[TeamStatus] = mapped_column(
        db_enum(TeamStatus, 10), default=TeamStatus.PENDING, server_default="PENDING", nullable=False
    )
    # 팀 활성화에 필요한 최소 회원 수 (FR-06). 게스트는 세지 않는다
    min_members: Mapped[int] = mapped_column(SmallInteger, default=5, server_default="5", nullable=False)
    # 관리자 승인 (사용자 결정): 생성 직후 PENDING → 콘솔에서 승인해야 5명 조건과 함께 ACTIVE 가 된다
    approval_status: Mapped[ApprovalStatus] = mapped_column(db_enum(ApprovalStatus, 10), default=ApprovalStatus.PENDING, server_default="PENDING", nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    home_court: Mapped[str | None] = mapped_column(String(100))  # 주 활동 체육관. 일정 venue 기본값 용도

    # 회원 + 게스트 전부. 팀 삭제 시 참가자 행도 함께 삭제
    players: Mapped[list["Player"]] = relationship(back_populates="team", cascade="all, delete-orphan")


class Player(CreatedAtMixin, Base):
    """특정 팀에 속한 참가자. 회원이면 user_id가 채워지고, 게스트면 NULL.

    같은 사람이 두 팀에 있으면 player_id가 다르다. 실력 지표는 팀 단위로 관리된다 (13.2절 4항).

    불변 조건
      - `kind = GUEST` ⇔ `user_id IS NULL` (CHECK 로 강제). 게스트는 로그인·설문·투표 응답을 할 수 없고
        기록·배정·투표의 대상만 된다 (3.3절 권한 매트릭스).
      - 회원은 한 팀에 players 행이 하나뿐 (부분 유니크). 게스트는 동명이인이 여러 명 있을 수 있다.
      - 게스트의 `role` 은 항상 PLAYER (서비스 계층에서 고정).
      - 회원 수 집계·배정 대상은 `status = ACTIVE` 인 행만.

    게스트 → 회원 병합 (6.2절 "병합 절차", F13/FR-13)
      게스트가 팀 코드로 가입하면 새 players 행이 생긴다. 매니저가 S-08 에서 둘을 연결하면 게스트 행의
      `merged_into_player_id` 에 새 행 id 를 적고 `status` 를 LEFT 로 바꾼다. 행을 물리적으로 합치지
      않으므로 지표 계산 시 이 포인터를 따라 올라가 기록을 합산하고, 잘못 병합해도 되돌릴 수 있다.

    관계: profile(1:1), positions(1:N) 은 여기서 정의하고, 경기·배정·투표 쪽 테이블은 player_id FK 만
    갖고 역방향 relationship 을 두지 않는다 (필요할 때 명시적으로 조회).
    """

    __tablename__ = "players"
    __table_args__ = (
        CheckConstraint("height_cm IS NULL OR height_cm BETWEEN 120 AND 250", name="ck_players_height_cm"),
        # 회원은 한 팀에 한 번만. 게스트(NULL)는 제외되는 부분 유니크
        # (Postgres 는 NULL 을 서로 다른 값으로 취급하지만, WHERE 절로 의도를 명시한다)
        Index(
            "uq_players_team_user",
            "team_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        # 게스트 ⇔ 계정 없음. kind 와 user_id 가 어긋난 행을 DB 수준에서 차단
        CheckConstraint("(kind = 'GUEST') = (user_id IS NULL)", name="ck_players_guest_has_no_user"),
        Index("ix_players_user_status", "user_id", "status"),  # 6.4절: 내 팀 목록 (GET /me/teams)
        # 병합된 게스트를 거슬러 올라가는 조회 — 값이 있는 행만 담아 인덱스를 작게 유지한다
        Index("ix_players_merged_into", "merged_into_player_id", postgresql_where=text("merged_into_player_id IS NOT NULL")),
    )

    id: Mapped[BigPK]
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # NULL = 게스트
    kind: Mapped[PlayerKind] = mapped_column(db_enum(PlayerKind, 10), nullable=False)  # MEMBER / GUEST
    # 화면에 보이는 이름. 회원은 가입 시 users.name/nickname 에서 복사, 게스트는 매니저가 입력
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[TeamRole] = mapped_column(
        db_enum(TeamRole, 10), default=TeamRole.PLAYER, server_default="PLAYER", nullable=False
    )
    status: Mapped[PlayerStatus] = mapped_column(
        db_enum(PlayerStatus, 10), default=PlayerStatus.ACTIVE, server_default="ACTIVE", nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # 게스트 등록자(매니저). 회원은 NULL
    # 매니저 권한을 준 사람. 팀 생성자(자동 부여)나 일반 플레이어는 NULL
    role_granted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # 게스트→회원 병합 시 흡수처. 행을 물리적으로 합치지 않으므로 되돌릴 수 있다 (13.2절 3항)
    merged_into_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    # 팀 합류 시각. created_at 과 달리 앱이 명시적으로 넣는다 (가입/게스트 등록 시각)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    team: Mapped[Team] = relationship(back_populates="players")
    # 회원이면 로그인 계정. 게스트는 None. (user_id FK 가 셋이라 어느 것인지 명시)
    height_cm: Mapped[int | None] = mapped_column(SmallInteger)  # 게스트 키 (회원은 users.height_cm). 평균 신장 계산용
    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])  # noqa: F821
    # 실력·포지션 프로필. 문자열 참조는 profile.py 가 team.py 를 import 하므로 순환을 피하기 위함
    profile: Mapped["PlayerProfile | None"] = relationship(  # noqa: F821
        back_populates="player", uselist=False, cascade="all, delete-orphan"
    )
    positions: Mapped[list["PlayerPosition"]] = relationship(  # noqa: F821
        back_populates="player", cascade="all, delete-orphan"
    )


class GuestInvitePreset(CreatedAtMixin, Base):
    """게스트 초대 이력 — "이전에 초대한 게스트 불러오기" 용 (사용자 요청, 2026-09-08).

    플레이어(매니저 포함)가 회차에 게스트를 등록할 때마다 (팀, 등록자, 이름) 단위로 upsert 된다.
    다음 일정에서 목록을 불러오면 이름·실력·선호/가능 포지션·같은 팀 요청이 그대로 채워지고,
    `last_player_id` 로 같은 게스트 레코드를 재사용해 기록이 누적된다 (FR-12).
    """

    __tablename__ = "guest_invite_presets"
    __table_args__ = (
        UniqueConstraint("team_id", "created_by", "display_name", name="uq_guest_invite_presets_owner_name"),
    )

    id: Mapped[BigPK]
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(50), nullable=False)
    skill_grade: Mapped[int | None] = mapped_column(SmallInteger)  # 1~5, 미지정 NULL
    height_cm: Mapped[int | None] = mapped_column(SmallInteger)  # 마지막으로 입력한 키
    preferred_position: Mapped[str | None] = mapped_column(String(2))
    playable_positions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    team_lock_request: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    last_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="SET NULL"), index=True)  # 마지막 게스트 레코드
    use_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GuestClaim(CreatedAtMixin, Base):
    """회원이 같은 이름의 게스트 기록을 "내 것" 으로 확인하거나 거절한 이력 (사용자 요청 기능).

    가입 직후 홈에 "이전 모임 기록이 있어요. 본인이 맞나요?" 카드가 뜨고, 확인하면 `players.merged_into_player_id`
    로 병합(매니저 병합과 같은 처리), 거절하면 그 게스트는 이 사용자에게 다시 묻지 않는다.
    """

    __tablename__ = "guest_claims"
    __table_args__ = (
        UniqueConstraint("guest_player_id", "user_id", name="uq_guest_claims_guest_user"),
        CheckConstraint("status IN ('CONFIRMED','DECLINED')", name="ck_guest_claims_status"),
    )

    id: Mapped[BigPK]
    guest_player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[ClaimStatus] = mapped_column(db_enum(ClaimStatus, 10), nullable=False)
