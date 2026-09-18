"""7.3절 인증 · 프로필 — 회원가입/로그인/토큰/카카오/비밀번호 재설정과 내 정보.

설계서: 7.3절 인증 · 프로필, FR-01 · FR-02, 11.5절 인증 방식 결정.

엔드포인트
- POST  /auth/signup            이메일 회원가입 (구현됨)
- POST  /auth/login             이메일 로그인 (구현됨)
- GET   /auth/kakao/login-url   카카오 인가 URL 생성 (구현됨)
- GET   /auth/kakao/callback    카카오 콜백 → 가입/로그인 (구현됨)
- POST  /auth/kakao/link        기존 계정에 카카오 연결 (구현됨)
- POST  /auth/refresh           토큰 갱신 (구현됨)
- POST  /auth/password/forgot   비밀번호 재설정 요청 (구현됨 · 메일 발송)
- POST  /auth/password/reset    비밀번호 재설정 (구현됨)
- GET   /me                     내 정보 조회 (구현됨)
- PATCH /me                     내 프로필 수정 (구현됨)
- POST  /me/avatar              프로필 사진 등록·교체 (구현됨)
- DELETE /me/avatar             프로필 사진 삭제 (구현됨)
- GET   /users/{id}/avatar      프로필 사진 이미지 (구현됨, 주소의 키로 확인)
- GET   /me/teams               내 소속 팀 목록 (구현됨)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.api.v1._docs import errors
from app.core import errors as E
from app.core import ratelimit
from app.models import Player, Team
from app.models.enums import PlayerKind, PlayerStatus
from app.schemas.auth import (
    AvatarIn,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    KakaoLinkRequest,
    KakaoLoginUrl,
    KakaoTokenPair,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    TeamMembershipView,
    TokenPair,
    UserDetail,
    UserUpdate,
)
from app.schemas.common import ItemList
from app.services import auth_service, avatar_service, kakao_service

router = APIRouter(tags=["인증 · 프로필"])


@router.post(
    "/auth/signup", dependencies=[Depends(ratelimit.SIGNUP)], status_code=201, response_model=TokenPair,
    responses=errors(_409="EMAIL_DUPLICATED"), summary="이메일 회원가입",
)
def signup(db: DB, body: SignupRequest):
    """이메일/비밀번호로 계정을 만들고 즉시 로그인 토큰을 발급한다.

    - **권한:** 비회원 (인증 불필요).
    - **처리:** 이메일 중복을 확인한 뒤 `users` 행을 만들고, 비밀번호는 bcrypt 단방향 해시로만
      저장한다. 동시에 `auth_identities`에 `LOCAL` 로그인 수단을 연결하고
      access/refresh 토큰 쌍을 돌려준다. 온보딩 설문은 아직 미완료 상태다.
    - **오류:** `409 EMAIL_DUPLICATED` — 이미 가입된 이메일. `400 VALIDATION_ERROR` — 형식 위반.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 인증, FR-01 · FR-02, 11.5절 (bcrypt 해시).
    """
    return auth_service.signup(db, body)


@router.post(
    "/auth/login", dependencies=[Depends(ratelimit.LOGIN)], response_model=TokenPair,
    responses=errors(_401="INVALID_CREDENTIALS"), summary="이메일 로그인",
)
def login(db: DB, body: LoginRequest):
    ratelimit.LOGIN.by_email(body.email)
    """이메일/비밀번호를 검증하고 토큰 쌍을 발급한다.

    - **권한:** 비회원 (인증 불필요).
    - **처리:** 삭제되지 않은 계정을 이메일로 찾고, 입력한 비밀번호를 같은 방식으로 해시해
      저장된 해시와 비교한다. 소셜 전용 계정(`password_hash` 없음)은 이 경로로 로그인할 수 없다.
      성공하면 access 30분 / refresh 14일 JWT를 발급한다.
    - **오류:** `401 INVALID_CREDENTIALS` — 이메일 또는 비밀번호 불일치 (어느 쪽이 틀렸는지
      구분하지 않는다).
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 인증, FR-01, 11.5절.
    """
    return auth_service.login(db, body)


@router.get("/auth/kakao/login-url", response_model=KakaoLoginUrl, responses=errors(_401="KAKAO_AUTH_FAILED"), summary="카카오 인가 URL 생성")
def kakao_login_url(
    redirect_uri: Annotated[str | None, Query(description="프론트 출처 기준 콜백 주소 (예: https://…/auth/kakao/callback). 생략 시 KAKAO_REDIRECT_URI. 허용 목록 밖이면 401")] = None,
):
    """프론트가 이동할 카카오 인가 URL과 CSRF 방지용 `state`를 생성한다.

    - **권한:** 비회원 (인증 불필요).
    - **처리:** `state` 는 서버가 서명한 10분짜리 토큰이라 별도 세션 저장 없이 콜백에서 검증한다.
      프론트는 받은 `state` 를 sessionStorage 에 두었다가 콜백의 값과 한 번 더 대조한다.
    - **오류:** `401 KAKAO_AUTH_FAILED` — 카카오 설정 없음 또는 허용되지 않은 redirect_uri.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 인증, 11.5절 카카오 로그인 흐름 1단계.
    """
    url, state = kakao_service.login_url(redirect_uri)
    return KakaoLoginUrl(url=url, state=state)


@router.get(
    "/auth/kakao/callback", response_model=KakaoTokenPair,
    responses=errors(_401="KAKAO_AUTH_FAILED"), summary="카카오 콜백 (가입/로그인)",
)
def kakao_callback(
    db: DB,
    code: Annotated[str, Query(description="카카오가 redirect_uri로 전달한 인가 코드 (1회용)")],
    state: Annotated[str, Query(description="login-url에서 발급한 state. 서명·만료 검증에 실패하면 401")],
    redirect_uri: Annotated[str | None, Query(description="login-url 때 보낸 것과 같은 값 (토큰 교환에 필요)")] = None,
):
    """카카오가 돌려준 인가 코드를 받아 가입 또는 로그인을 완료한다.

    - **권한:** 비회원 (카카오 리다이렉트 후 프론트가 호출).
    - **처리:** `state` 검증 → 인가 코드를 카카오 토큰으로 교환 → 회원번호·닉네임·프로필 사진 조회 →
      `auth_identities(provider=KAKAO)` 조회. 있으면 로그인, 없으면 `users` 생성(이메일은 없을 수 있어 NULL) → JWT 발급.
      `is_new` 가 true 면 프론트는 온보딩 설문(S-03)으로 보낸다.
    - **오류:** `401 KAKAO_AUTH_FAILED` — state 불일치·만료, 토큰 교환 실패, 탈퇴 계정.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 인증, 11.5절 흐름 2~6단계, 5.4절 "카카오 계정에 이메일 없음".
    """
    kakao_service.verify_state(state)
    profile = kakao_service.fetch_profile(code, kakao_service.resolve_redirect_uri(redirect_uri))
    pair, is_new = kakao_service.login_or_signup(db, profile)
    return KakaoTokenPair(**pair.model_dump(), is_new=is_new)


@router.post(
    "/auth/kakao/link", response_model=UserDetail,
    responses=errors(_401="KAKAO_AUTH_FAILED", _409="IDENTITY_ALREADY_LINKED"), summary="기존 계정에 카카오 연결",
)
def kakao_link(db: DB, user: CurrentUser, body: KakaoLinkRequest):
    """이메일로 가입한 계정에 카카오 로그인 수단을 추가로 연결한다.

    - **권한:** 로그인 사용자.
    - **처리:** 인가 코드를 교환해 회원번호를 얻고 현재 계정의 `auth_identities` 에 `KAKAO` 행을 추가한다.
      이후 카카오·이메일 어느 쪽으로도 로그인 가능.
    - **오류:** `409 IDENTITY_ALREADY_LINKED` — 그 카카오 계정이 이미 다른 계정에 연결됨. `401 KAKAO_AUTH_FAILED`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 인증, 6.2절 `auth_identities` (users 1:N), 11.5절.
    """
    kakao_service.verify_state(body.state)
    profile = kakao_service.fetch_profile(body.code, kakao_service.resolve_redirect_uri(body.redirect_uri))
    return kakao_service.link(db, user, profile)


@router.post(
    "/auth/refresh", response_model=TokenPair,
    responses=errors(_401="TOKEN_EXPIRED"), summary="토큰 갱신",
)
def refresh(db: DB, body: RefreshRequest):
    """refresh 토큰으로 새 access/refresh 토큰 쌍을 발급한다.

    - **권한:** 비회원 (본문의 refresh 토큰으로 인증).
    - **처리:** 토큰의 `type`이 `refresh`인지와 서명·만료를 검증하고, 계정이 삭제되지 않았으면
      새 토큰 쌍을 발급한다. 이전 refresh 토큰은 별도로 무효화하지 않는다 (만료까지 유효).
    - **오류:** `401 TOKEN_EXPIRED` — 토큰 만료·위조·타입 불일치, 또는 삭제된 계정.
    - **상태:** `구현됨`.
    - **설계서:** 7.1절 공통 규약 (access 30분 / refresh 14일), 7.3절 인증.
    """
    return auth_service.refresh(db, body.refresh_token)


@router.post("/auth/logout", status_code=204, summary="로그아웃 (refresh 토큰 폐기)")
def logout(db: DB, body: LogoutRequest):
    """보낸 refresh 토큰을 폐기해 이 기기에서 더는 재발급받지 못하게 한다. access 토큰은 30분 안에 스스로 만료된다.

    - **권한:** 누구나 (토큰이 무효해도 204 — 로그아웃은 실패하지 않는다).
    - **상태:** `구현됨`.
    """
    auth_service.logout(db, body.refresh_token)
    return Response(status_code=204)


@router.post(
    "/auth/password/forgot", dependencies=[Depends(ratelimit.PASSWORD)], status_code=status.HTTP_202_ACCEPTED,
    summary="비밀번호 재설정 요청",
)
def forgot_password(db: DB, body: ForgotPasswordRequest):
    """비밀번호 재설정 메일 발송을 요청한다. 가입 여부와 무관하게 항상 202를 돌려준다.

    - **권한:** 비회원 (인증 불필요).
    - **처리:** 계정이 있으면 `password_reset_tokens` 에 토큰의 SHA-256 해시만 저장(30분 만료·1회 사용)하고
      원문 토큰을 담은 링크(`FRONTEND_BASE_URL/password/reset?token=…`)를 메일로 보낸다(Resend, 키가 없으면 서버 로그).
      계정이 없으면 아무것도 하지 않는다. 응답이 계정 존재 여부에 따라 달라지면 계정 탐색 통로가 되므로 항상 202.
    - **오류:** `400 VALIDATION_ERROR` — 이메일 형식 위반.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 인증 (항상 202), 7.4절 설계 원칙, 6.2절 `password_reset_tokens`, 11.5절.
    """
    auth_service.forgot_password(db, body.email)
    return {"accepted": True}


@router.post(
    "/auth/password/reset", dependencies=[Depends(ratelimit.PASSWORD)],
    responses=errors(_400="TOKEN_INVALID_OR_EXPIRED"),
    summary="비밀번호 재설정",
)
def reset_password(db: DB, body: ResetPasswordRequest):
    """메일로 받은 토큰과 새 비밀번호로 비밀번호를 바꾼다.

    - **권한:** 비회원 (본문의 재설정 토큰으로 인증).
    - **처리:** 토큰을 SHA-256 해시해 `password_reset_tokens` 에서 찾고, 만료 전이며 `used_at` 이 비어 있으면
      `users.password_hash` 를 새 bcrypt 해시로 교체하고 토큰을 사용 처리한다. 카카오 전용 계정이면 이메일 로그인
      수단(LOCAL)을 함께 추가한다.
    - **오류:** `400 TOKEN_INVALID_OR_EXPIRED` — 토큰 없음·만료·이미 사용됨.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 인증, FR-02, 6.2절 `password_reset_tokens`, 11.5절.
    """
    auth_service.reset_password(db, body.token, body.new_password.get_secret_value())
    return {"ok": True}


@router.get("/me", response_model=UserDetail, summary="내 정보 조회")
def get_me(user: CurrentUser):
    """로그인한 계정의 기본 정보, 연결된 로그인 수단, 온보딩 완료 여부를 돌려준다.

    - **권한:** 로그인 사용자.
    - **처리:** Bearer 토큰에서 얻은 `users` 행을 그대로 직렬화한다. `identities[]`에
      카카오/이메일 연결 목록, `onboarding_completed`로 설문 이동 여부를 판단한다.
      `global_role`이 `ADMIN`이면 관리자 계정이다.
    - **오류:** `401 TOKEN_EXPIRED` — 토큰 없음·만료·삭제된 계정.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 인증 · 프로필 (`GET /me`), 6.2절 `users` · `auth_identities`.
    """
    return user


@router.patch("/me", response_model=UserDetail, summary="내 프로필 수정")
def update_me(db: DB, user: CurrentUser, body: UserUpdate):
    """이름·닉네임·프로필 이미지·키·메인 팀을 부분 수정한다.

    - **권한:** 로그인 사용자.
    - **처리:** 본문에 포함된 필드만(`exclude_unset`) `users` 행에 덮어쓰고 커밋한다.
      이메일·비밀번호·권한은 이 경로로 바꿀 수 없다. 팀별 `players.display_name`은 갱신하지
      않는다 (가입 시점의 닉네임이 유지됨).
    - **오류:** `400 VALIDATION_ERROR` — 범위 위반 (출생년도 1940~, 키 120~250cm 등).
      `401 TOKEN_EXPIRED`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`PATCH /me`), 6.2절 `users`, S-17 내 프로필.
    """
    data = body.model_dump(exclude_unset=True)
    if data.get("primary_team_id") is not None:
        from sqlalchemy import select

        from app.models import Player
        from app.models.enums import PlayerStatus

        ok = db.scalar(select(Player.id).where(Player.user_id == user.id, Player.team_id == data["primary_team_id"], Player.status == PlayerStatus.ACTIVE))
        if ok is None:
            raise E.PlayerNotInTeam("내가 속한 팀만 메인 팀으로 설정할 수 있어요.")
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    return user


@router.post("/me/password", status_code=204, responses=errors(_401="INVALID_CREDENTIALS", _400="VALIDATION_ERROR"), summary="비밀번호 변경")
def change_password(db: DB, user: CurrentUser, body: ChangePasswordRequest):
    """로그인 상태에서 현재 비밀번호를 확인하고 새 비밀번호로 바꾼다.

    - **오류:** `401 INVALID_CREDENTIALS` — 현재 비밀번호 불일치. `400 VALIDATION_ERROR` — 카카오 전용 계정(비밀번호 없음).
    - **상태:** `구현됨`.
    """
    auth_service.change_password(db, user, body.current_password.get_secret_value(), body.new_password.get_secret_value())
    return Response(status_code=204)


@router.delete("/me", status_code=204, responses=errors(_422="CANNOT_DEMOTE_LAST_MANAGER"), summary="계정 삭제")
def delete_me(db: DB, user: CurrentUser):
    """계정을 삭제한다. 행은 남기되 이메일·비밀번호·이름·사진·로그인 수단을 지우고, 소속 팀에서 나간다.

    - **처리:** 경기 기록은 '탈퇴한 회원' 이름으로 남는다. 같은 이메일로 다시 가입할 수 있다.
    - **오류:** `422 CANNOT_DEMOTE_LAST_MANAGER` — 다른 팀원이 있는 팀의 유일한 매니저.
    - **상태:** `구현됨`.
    """
    auth_service.delete_account(db, user)
    return Response(status_code=204)


@router.post("/me/avatar", response_model=UserDetail, responses=errors(_400="VALIDATION_ERROR"), summary="프로필 사진 등록 · 교체")
def set_my_avatar(db: DB, user: CurrentUser, body: AvatarIn):
    """프로필 사진을 올리거나 바꾼다. 팀원 목록·참석자·배정 결과의 동그란 아바타에 그대로 쓰인다.

    - **권한:** 로그인 사용자 (본인 사진만).
    - **처리:** 데이터 URL 을 디코드해 종류(JPG·PNG·WEBP)와 크기(512KB)를 확인하고 `user_avatars` 에 저장한 뒤,
      `users.profile_image_url` 을 `/api/v1/users/{id}/avatar?v={키}` 로 갱신한다. 키가 매번 바뀌므로 브라우저가
      옛 사진을 계속 보여 주는 일이 없다.
    - **오류:** `400 VALIDATION_ERROR` — 형식·종류·크기 위반.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`PATCH /me`), 6.2절 `users.profile_image_url`, S-17 내 프로필.
    """
    return avatar_service.set_avatar(db, user, body.data_url)


@router.delete("/me/avatar", response_model=UserDetail, summary="프로필 사진 삭제")
def delete_my_avatar(db: DB, user: CurrentUser):
    """프로필 사진을 지운다. 이후에는 이름 첫 글자 아바타로 보인다.

    - **권한:** 로그인 사용자. **상태:** `구현됨`.
    """
    return avatar_service.clear_avatar(db, user)


@router.get(
    "/users/{user_id}/avatar", response_class=Response, responses={200: {"content": {"image/jpeg": {}}}, 404: {}},
    summary="프로필 사진 이미지",
)
def get_avatar(db: DB, user_id: int, v: Annotated[str | None, Query(description="사진 주소에 붙는 키. 틀리면 404")] = None):
    """프로필 사진 원본을 돌려준다. `<img src>` 는 토큰을 실을 수 없어 주소의 키로 확인한다.

    - **권한:** 주소(키)를 아는 사람. 키는 사진을 바꿀 때마다 새로 발급된다.
    - **처리:** 키가 맞으면 이미지 바이트와 1년짜리 캐시 헤더를 준다 (주소가 바뀌면 새로 받는다).
    - **오류:** `404 NOT_FOUND` — 사진 없음 또는 키 불일치.
    - **상태:** `구현됨`.
    """
    row = avatar_service.get_avatar(db, user_id, v)
    return Response(content=row.data, media_type=row.content_type, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/me/teams", response_model=ItemList[TeamMembershipView], summary="내 소속 팀 목록")
def my_teams(db: DB, user: CurrentUser):
    """내가 속한 팀 목록을 팀별 역할(MANAGER/PLAYER)과 함께 돌려준다.

    - **권한:** 로그인 사용자.
    - **처리:** `players`에서 내 `user_id`이고 `status=ACTIVE`인 행을 팀과 조인해 최근 가입순으로
      나열한다. 각 항목에 이 팀에서의 `player_id`·`role`과, 팀 활성화 판단 기준인 활성 회원 수
      (`member_count`, 게스트 제외)를 포함한다. 홈 화면(S-04)의 팀 카드 데이터다.
    - **오류:** `401 TOKEN_EXPIRED`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`GET /me/teams`), 3.1절 팀 단위 권한, 6.2절 `players`, S-04 홈.
    """
    rows = db.execute(
        select(Team, Player)
        .join(Player, Player.team_id == Team.id)
        .where(Player.user_id == user.id, Player.status == PlayerStatus.ACTIVE)
        .order_by(Player.joined_at.desc())
    ).all()
    # 팀별 회원 수는 팀마다 세지 않고 한 번에 세어 온다 (팀이 늘어도 쿼리는 그대로)
    team_ids = [t.id for t, _ in rows]
    counts = dict(
        db.execute(
            select(Player.team_id, func.count())
            .where(Player.team_id.in_(team_ids), Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE)
            .group_by(Player.team_id)
        ).all()
    ) if team_ids else {}
    items = []
    for team, player in rows:
        count = counts.get(team.id, 0)
        items.append(
            TeamMembershipView(
                team_id=team.id, team_name=team.name, team_code=team.team_code, team_status=team.status, approval_status=team.approval_status,
                player_id=player.id, role=player.role, member_count=count or 0,
            )
        )
    return ItemList(items=items)
