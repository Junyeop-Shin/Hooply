"""인증 · 내 정보 스키마 — 7.3절 "인증 · 프로필" 엔드포인트의 요청/응답.

대상 엔드포인트: POST /auth/signup, /auth/login, /auth/refresh, /auth/password/forgot|reset,
GET /auth/kakao/login-url, GET /auth/kakao/callback, POST /auth/kakao/link,
GET|PATCH /me, GET /me/teams.

설계 결정 (11.5절):
- 카카오 로그인이 주 경로, 이메일/비밀번호는 보조 경로. 둘 다 `auth_identities` 로 한 계정에 연결된다.
- `users.email` 은 NULL 허용 — 카카오 계정에 이메일이 없을 수 있다. 그래서 응답의 email 이 None 일 수 있다.
- 비밀번호 필드는 `SecretStr` 로 받아 로그에 원문이 찍히지 않게 한다 (13.2절 6항).
  서비스에서는 `.get_secret_value()` 로 꺼내 bcrypt 해시한다.
"""

from pydantic import BaseModel, EmailStr, Field, SecretStr

from app.schemas.common import ORMModel


class SignupRequest(BaseModel):
    """이메일 회원가입 요청 — `POST /auth/signup` (비회원, S-02).

    성공 시 201 + `TokenPair` (가입 즉시 로그인 상태). 같은 이메일이 있으면 409 EMAIL_DUPLICATED.
    가입 후 `onboarding_completed=false` 이므로 프론트는 S-03 온보딩 설문으로 보낸다.
    숫자 범위 제약은 `users` 테이블의 CHECK 제약(6.2절)과 같다.
    """

    email: EmailStr = Field(description="로그인 ID 겸 비밀번호 재설정 메일 수신처")
    password: SecretStr = Field(
        min_length=8, max_length=72,
        description="8~72자. 상한 72는 bcrypt가 반영하는 최대 바이트 수 (11.5절)",
    )  # SecretStr: 로그에 원문이 찍히지 않게 (13.2절 6항)
    name: str = Field(min_length=1, max_length=50, description="실명 또는 팀에서 부르는 이름")
    nickname: str | None = Field(default=None, max_length=50)
    height_cm: int | None = Field(default=None, ge=120, le=250, description="키(cm). 설문의 골밑 축 계산에 쓰인다 (설문에서는 키를 다시 묻지 않는다)")


class LoginRequest(BaseModel):
    """이메일 로그인 요청 — `POST /auth/login` (S-01). 실패 시 401 INVALID_CREDENTIALS."""

    email: EmailStr
    password: SecretStr


class TokenPair(BaseModel):
    """로그인·가입·refresh 성공 응답. 7.1절: access 30분 / refresh 14일.

    프론트는 access 를 `Authorization: Bearer <access_token>` 헤더로 보내고,
    401 TOKEN_EXPIRED 를 받으면 refresh 로 `POST /auth/refresh` 를 호출해 새 쌍을 받는다.
    """

    access_token: str = Field(description="API 호출용 JWT. 짧게 산다 (기본 30분)")
    refresh_token: str = Field(description="access 재발급용 JWT (기본 14일). 헤더에 넣지 말고 refresh 요청 본문에만 쓴다")
    token_type: str = Field(default="bearer", description="항상 'bearer'. OAuth2 관례상 포함")


class KakaoTokenPair(TokenPair):
    """`GET /auth/kakao/callback` 응답. TokenPair + 신규 가입 여부."""

    is_new: bool = Field(description="이번 콜백으로 계정이 새로 만들어졌으면 true → 프론트는 온보딩 설문(S-03)으로 보낸다")


class KakaoLoginUrl(BaseModel):
    """`GET /auth/kakao/login-url` 응답. 프론트는 `url` 로 브라우저를 이동시킨다 (11.5절 흐름 1단계)."""

    url: str = Field(description="kauth.kakao.com/oauth/authorize?... 형태의 인가 URL")
    state: str = Field(description="CSRF 방지용 난수. 콜백의 state와 대조한다 (11.5절 '반드시 지켜야 할 것' 4항)")


class KakaoLinkRequest(BaseModel):
    """이미 로그인한 계정에 카카오를 추가로 연결 — `POST /auth/kakao/link`.

    카카오 콜백에서 받은 인가 코드를 그대로 넘긴다. 그 카카오 회원번호가 이미 다른 계정에
    연결돼 있으면 409 IDENTITY_ALREADY_LINKED. 성공 시 `UserDetail` (identities 에 KAKAO 추가).
    """

    code: str = Field(description="카카오가 redirect_uri로 전달한 인가 코드")
    state: str = Field(description="login-url에서 받은 state. 불일치하면 401 KAKAO_AUTH_FAILED")
    redirect_uri: str | None = Field(default=None, description="login-url 때 보낸 것과 같은 값")


class RefreshRequest(BaseModel):
    """`POST /auth/refresh` 요청. 만료·위조·type 불일치면 401 TOKEN_EXPIRED."""

    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    """`POST /auth/password/forgot` 요청. 재설정 메일 발송.

    가입 여부와 무관하게 **항상 202** 를 돌려준다 — 응답이 달라지면 계정 존재 여부를 확인하는
    통로가 되기 때문 (7.4절). 카카오 전용 계정(email=None)은 이 경로를 쓸 수 없다.
    """

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """`POST /auth/password/reset` 요청.

    서버는 `token` 을 SHA-256 해시해 `password_reset_tokens.token_hash` 로 조회한다.
    없거나·30분 지났거나·이미 썼으면 400 TOKEN_INVALID_OR_EXPIRED.
    """

    token: str = Field(description="메일 링크에 담긴 원문 토큰 (security.generate_reset_token의 첫 번째 값)")
    new_password: SecretStr = Field(min_length=8, max_length=72, description="새 비밀번호. 제약은 SignupRequest.password와 동일")


class IdentityView(ORMModel):
    """계정에 연결된 로그인 수단 하나 (`auth_identities` 행). `UserDetail.identities` 원소."""

    provider: str = Field(description="LOCAL(이메일/비밀번호) / KAKAO")
    linked_at: object = Field(description="연결 시각(datetime). 타입을 느슨하게 둔 것은 ORM 값을 그대로 통과시키기 위함")


class UserDetail(ORMModel):
    """내 계정 정보 — `GET /me`, `PATCH /me`, `POST /auth/kakao/link` 응답. **본인만** 본다.

    다른 사람에게 보여주는 정보는 `UserSummary` / `PlayerCard` 를 쓴다.
    """

    id: int = Field(description="users.id")
    email: str | None = Field(description="카카오 전용 계정이면 None일 수 있다 (11.5절)")
    name: str
    nickname: str | None
    profile_image_url: str | None
    height_cm: int | None
    global_role: str = Field(description="ADMIN / USER. 전역 권한 (팀 단위 MANAGER/PLAYER와 별개, 3.1절)")
    onboarding_completed: bool = Field(description="false면 프론트가 온보딩 설문(S-03)으로 보낸다")
    primary_team_id: int | None = Field(default=None, description="메인 팀. 여러 팀에 속했을 때 프로필이 먼저 보여줄 팀 (홈에서 설정)")
    identities: list[IdentityView] = Field(default=[], description="연결된 로그인 수단 목록")


class UserUpdate(BaseModel):
    """`PATCH /me` 요청. 보낸 필드만 바꾼다 (None 은 '변경 없음'). 이메일·비밀번호는 여기서 못 바꾼다."""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    nickname: str | None = Field(default=None, max_length=50)
    profile_image_url: str | None = None
    height_cm: int | None = Field(default=None, ge=120, le=250)
    primary_team_id: int | None = Field(default=None, description="메인 팀으로 설정할 팀. 내가 ACTIVE 로 속한 팀이어야 한다")


class TeamMembershipView(BaseModel):
    """내가 속한 팀 하나 — `GET /me/teams` 의 items 원소. 홈(S-04)의 '내 팀 목록' 카드.

    같은 사람이 팀마다 다른 역할일 수 있으므로(3.1절) 팀별로 role 과 player_id 를 함께 준다.
    """

    team_id: int
    team_name: str
    team_code: str = Field(description="팀 초대 코드 8자. 팀원이면 누구나 공유할 수 있다")
    team_status: str = Field(description="PENDING(5명 미만 또는 승인 전) / ACTIVE / ARCHIVED")
    approval_status: str = Field(default="APPROVED", description="관리자 승인: PENDING / APPROVED / REJECTED")
    player_id: int = Field(description="이 팀에서의 players.id. 팀 관련 API에 넘길 내 식별자")
    role: str = Field(description="이 팀에서의 역할. MANAGER / PLAYER")
    member_count: int = Field(description="현재 활성 참가자 수. 5명 이상이면 팀이 활성화된다 (FR-06)")
