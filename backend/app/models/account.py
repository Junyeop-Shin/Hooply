"""계정·인증: users / auth_identities / password_reset_tokens (설계서 6.2절, 11.5절).

이 파일의 세 테이블은 "로그인할 수 있는 사람" 만 다룬다. 팀 소속·실력·경기 기록은 전부
`players`(team.py) 쪽이며, 게스트는 여기(users)에 행이 없다.

설계 요점
  - 계정 식별자는 `users.id` 다. 이메일은 식별자가 아니며 NULL 일 수 있다 (카카오 계정에 이메일
    동의항목이 없을 수 있음). 이 하나를 NOT NULL 로 잡으면 카카오 로그인이 막힌다 (13.2절 7항).
  - 로그인 수단(카카오/이메일)은 `auth_identities` 로 분리해 한 계정에 여러 수단을 연결한다.
  - 비밀번호는 복호화 불가능한 bcrypt 해시만 저장한다. 재설정 토큰도 원문이 아닌 SHA-256 해시만
    저장한다.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK, TimestampMixin
from app.models.enums import AuthProvider, GlobalRole, TutorialPath, TutorialState, db_enum


class User(TimestampMixin, Base):
    """로그인 계정 (S-02 회원가입 폼의 필드 = 이 테이블).

    - 한 사용자는 여러 팀에 참가할 수 있고, 팀마다 별도의 `players` 행을 갖는다 (users 1:N players).
    - `global_role` 은 전역 권한(ADMIN/USER) 이며, 팀 안에서의 매니저/플레이어 구분은
      `players.role` 이다. 관리자도 팀에서는 플레이어일 수 있다.
    - soft delete: `deleted_at` 이 채워지면 탈퇴한 계정. 행은 남겨 과거 경기 기록의 참조를 지킨다.
    """

    __tablename__ = "users"
    __table_args__ = (
        # S-02 입력값 범위 검증. NULL 은 통과 (선택 입력)
        # 키(cm). 120~250 밖은 오입력으로 간주
        CheckConstraint("height_cm IS NULL OR height_cm BETWEEN 120 AND 250", name="ck_users_height_cm"),
    )

    id: Mapped[BigPK]
    # 11.5절: 카카오 계정에 이메일이 없을 수 있으므로 NULL 허용. 이메일은 식별자가 아니다.
    # UNIQUE 이므로 같은 이메일로 두 계정을 만들 수는 없다 (409 EMAIL_DUPLICATED).
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))  # bcrypt 해시. 소셜 전용 계정은 NULL
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(50))  # 카카오 닉네임 또는 직접 입력
    profile_image_url: Mapped[str | None] = mapped_column(Text)  # 카카오 CDN URL(만료 가능) 또는 업로드 경로
    height_cm: Mapped[int | None] = mapped_column(SmallInteger)  # 설문 A1 과 동일 값. 골밑 축 계산에 사용
    global_role: Mapped[GlobalRole] = mapped_column(
        db_enum(GlobalRole, 10), default=GlobalRole.USER, server_default="USER", nullable=False
    )
    # FR-03: 온보딩 설문(POST /surveys/onboarding/responses) 제출 시 true. 미완료면 설문 화면으로 유도
    # 여러 팀에 속했을 때 프로필이 우선 보여줄 팀 (홈 "메인으로"). 팀이 지워지면 NULL
    primary_team_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("teams.id", ondelete="SET NULL"), index=True)
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # 사용자 단위 선호 포지션 (선호 순서 배열, 예: ["SF","PG"]). 팀별 player_positions 의 원본이며,
    # 팀이 하나도 없어도 프로필에서 수정·표시할 수 있게 계정에 둔다. 팀 가입 시 이 값으로 행을 만든다.
    position_prefs: Mapped[list[str] | None] = mapped_column(JSONB)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # soft delete. NULL = 정상
    # 시작 안내 (0019). 새 가입자는 PENDING 으로 시작해 홈에서 팝업을 본다. 기능 도입 전 가입자는 DECLINED 로 채웠다.
    # tips_seen = 이미 닫은 기능별 첫 안내 id 목록 (app/services/tutorial_service.TIP_IDS)
    tutorial_state: Mapped[TutorialState] = mapped_column(
        db_enum(TutorialState, 10), default=TutorialState.PENDING, server_default="PENDING", nullable=False
    )
    tutorial_path: Mapped[TutorialPath | None] = mapped_column(db_enum(TutorialPath, 10))
    tutorial_tips_seen: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]", nullable=False)

    # 연결된 로그인 수단들. 계정 삭제 시 함께 삭제 (delete-orphan)
    identities: Mapped[list["AuthIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthIdentity(Base):
    """한 계정에 카카오와 이메일을 모두 연결할 수 있게 로그인 수단을 분리한다 (users 1:N).

    로그인 흐름: (provider, provider_uid) 로 이 테이블을 조회 → 있으면 해당 user 로 로그인,
    없으면 신규 가입 (11.5절 카카오 흐름 5단계). `POST /auth/kakao/link` 는 기존 계정에 행을 추가한다.
    """

    __tablename__ = "auth_identities"
    # 같은 카카오 회원번호(또는 같은 이메일)가 두 계정에 연결되는 것을 막는다 (409 IDENTITY_ALREADY_LINKED)
    __table_args__ = (UniqueConstraint("provider", "provider_uid", name="uq_auth_identities_provider_uid"),)

    id: Mapped[BigPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[AuthProvider] = mapped_column(db_enum(AuthProvider, 10), nullable=False)
    provider_uid: Mapped[str] = mapped_column(String(64), nullable=False)  # 카카오 회원번호 / LOCAL이면 email
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 연결 시각(앱에서 설정)

    user: Mapped[User] = relationship(back_populates="identities")


class PasswordResetToken(Base):
    """비밀번호 재설정 토큰 (LOCAL 계정 전용, FR-02).

    `POST /auth/password/forgot` 이 난수 토큰을 발급해 메일로 보내고, DB 에는 그 토큰의 SHA-256 해시만
    남긴다. `POST /auth/password/reset` 은 받은 토큰을 다시 해시해 조회하며,
    `expires_at` 이 지났거나 `used_at` 이 채워져 있으면 400 TOKEN_INVALID_OR_EXPIRED 다.
    한 토큰은 한 번만 쓸 수 있다.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[BigPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # SHA-256 hex(64자)만 저장
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 발급 후 30분
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = 아직 미사용


class UserAvatar(Base):
    """프로필 사진 원본 바이트. users 1:1 (없으면 이니셜 아바타로 표시).

    `cache_key` 는 사진을 바꿀 때마다 새로 만드는 짧은 난수다. 두 가지 일을 한다.
    ① 주소(`?v=키`)가 바뀌므로 브라우저 캐시가 저절로 갱신된다 ② 키를 모르면 남의 사진을 볼 수 없어
    순번 id 로 훑는 것을 막는다 (이미지 태그는 Authorization 헤더를 보낼 수 없어 토큰 인증을 쓸 수 없다).
    """

    __tablename__ = "user_avatars"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(30), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    cache_key: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RevokedToken(Base):
    """로그아웃하거나 회전(refresh)으로 버려진 refresh 토큰의 `jti`.

    refresh 토큰은 14일짜리라 로그아웃 뒤에도 유효하면 기기 분실 시 위험하다. 폐기 목록에 있는 jti 로는
    재발급을 거부한다. `expires_at` 이 지난 행은 어차피 서명 만료로 막히므로 지워도 된다.
    """

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa_text("now()"))
