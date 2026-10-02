"""공통 의존성 — DB 세션, 현재 사용자, 전역/팀 단위 권한 (3.1절 액터 정의, 3.3절 권한 매트릭스).

권한은 **전역 권한**(`users.global_role`: ADMIN/USER)과 **팀 단위 권한**(`players.role`:
MANAGER/PLAYER)으로 나뉜다. 한 사람이 A팀에서는 매니저, B팀에서는 플레이어일 수 있으므로 팀 권한은
항상 "이 팀에서의 `players` 행"을 통해 판단한다.

의존성 체인 (라우터에서는 `Annotated` 별칭으로 사용)

    Bearer 토큰 ──get_current_user──▶ User (CurrentUser)
        ├─ require_admin ─────────────▶ User (AdminUser)          global_role == ADMIN
        ├─ get_team_or_404(team_id) ──▶ Team
        │     └─ require_team_member ─▶ Player (TeamMember)       이 팀의 ACTIVE players 행
        │           └─ require_team_manager ▶ Player (TeamManager) role == MANAGER
        └─ get_event_or_404(event_id) ▶ Event
              └─ require_event_member ▶ Player (EventMember)      event.team_id 기준 동일 흐름
                    └─ require_event_manager ▶ Player (EventManager)

각 단계가 던지는 오류 (7.4절)
- 토큰 없음·만료·위조·삭제된 계정        → `401 TOKEN_EXPIRED`
- ADMIN이 아님                            → `403 FORBIDDEN_ROLE`
- 팀/일정 없음                            → `404 NOT_FOUND`
- 그 팀의 활성 참가자가 아님              → `403 NOT_A_MEMBER`
- 팀원이지만 매니저가 아님                → `403 FORBIDDEN_ROLE`

ADMIN "가상 매니저": 전역 ADMIN이 소속되지 않은 팀의 리소스에 접근하면 DB에 없는 임시
`Player(role=MANAGER, id=None)` 객체를 돌려주어 매니저 검사를 통과시킨다. 라우터는 `me.id`가 비어
있으면 "이 팀의 실제 참가자가 아님"으로 해석해야 한다 (예: `teams.get_team`의 `my_player_id`).
"""

from typing import Annotated

from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.security import decode_token
from app.db.session import get_db
from app.models import Event, Player, Team, User
from app.models.enums import GlobalRole, PlayerStatus, TeamRole

# auto_error=False: 토큰이 없어도 FastAPI 기본 403 대신 우리 규약의 401 TOKEN_EXPIRED를 낸다.
_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]
"""요청 단위 SQLAlchemy 세션. 라우터가 직접 commit 한다."""


def get_current_user(
    db: DB, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    """`Authorization: Bearer <access_token>`을 검증해 로그인 사용자를 돌려준다.

    access 토큰(30분)의 서명·만료·`type=access`를 확인하고 `sub`의 user_id로 `users`를 조회한다.
    삭제된 계정(`deleted_at` 있음)은 유효한 토큰이라도 거부한다.

    오류: `401 TOKEN_EXPIRED` — 헤더 없음, 만료, 위조, refresh 토큰을 잘못 보냄, 삭제된 계정,
    비밀번호를 바꾸기 전에 발급된 토큰(`users.token_version` 불일치).
    """
    if cred is None:
        raise errors.TokenExpired("로그인이 필요합니다.")
    decoded = decode_token(cred.credentials, "access")
    if decoded is None:
        raise errors.TokenExpired()
    user_id, version = decoded
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None or user.token_version != version:
        raise errors.TokenExpired()  # 세대가 다르면 비밀번호를 바꾸기 전에 받은 토큰 (다른 기기 로그아웃)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
"""로그인 사용자. 401 TOKEN_EXPIRED 가능."""


def require_admin(user: CurrentUser) -> User:
    """전역 ADMIN만 통과시킨다 (관리자 라우터 전용).

    오류: `403 FORBIDDEN_ROLE` — `users.global_role != ADMIN`.
    """
    if user.global_role != GlobalRole.ADMIN:
        raise errors.ForbiddenRole()
    return user


AdminUser = Annotated[User, Depends(require_admin)]
"""전역 관리자. 401 TOKEN_EXPIRED / 403 FORBIDDEN_ROLE 가능."""


def _active_player(db: Session, team_id: int, user: User) -> Player | None:
    """이 팀에서 사용자의 ACTIVE `players` 행. 탈퇴(LEFT)·제외(REMOVED)면 None."""
    return db.scalar(
        select(Player).where(
            Player.team_id == team_id, Player.user_id == user.id, Player.status == PlayerStatus.ACTIVE
        )
    )


def get_team_or_404(db: DB, team_id: Annotated[int, Path()]) -> Team:
    """경로의 `team_id`로 팀을 찾는다. 소속 여부는 검사하지 않는다.

    오류: `404 NOT_FOUND` — 팀 없음.
    """
    team = db.get(Team, team_id)
    if team is None:
        raise errors.NotFound("팀을 찾을 수 없어요.")
    return team


def require_team_member(db: DB, user: CurrentUser, team: Annotated[Team, Depends(get_team_or_404)]) -> Player:
    """소속 팀원(또는 ADMIN)만 통과. 반환값은 이 팀에서의 `players` 행.

    ADMIN이 비소속 팀에 접근하면 DB에 없는 가상 매니저 `Player(role=MANAGER)`를 돌려준다
    (`id`가 None이므로 라우터에서 실제 참가자와 구분 가능).

    오류: `404 NOT_FOUND` — 팀 없음. `403 NOT_A_MEMBER` — 활성 참가자가 아니고 ADMIN도 아님.
    """
    player = _active_player(db, team.id, user)
    if player is None:
        if user.global_role == GlobalRole.ADMIN:
            return Player(team_id=team.id, user_id=user.id, role=TeamRole.MANAGER)  # 가상 매니저
        raise errors.NotAMember()
    return player


def require_team_manager(player: Annotated[Player, Depends(require_team_member)]) -> Player:
    """팀 매니저(또는 ADMIN 가상 매니저)만 통과.

    오류: `403 FORBIDDEN_ROLE` — 팀원이지만 `players.role != MANAGER`.
    (`require_team_member`의 404/403 NOT_A_MEMBER가 먼저 적용된다.)
    """
    if player.role != TeamRole.MANAGER:
        raise errors.ForbiddenRole()
    return player


TeamMember = Annotated[Player, Depends(require_team_member)]
"""경로 `{team_id}` 팀의 활성 참가자(또는 ADMIN 가상 매니저). 404 / 403 NOT_A_MEMBER 가능."""
TeamManager = Annotated[Player, Depends(require_team_manager)]
"""경로 `{team_id}` 팀의 매니저(또는 ADMIN). 404 / 403 NOT_A_MEMBER / 403 FORBIDDEN_ROLE 가능."""


def get_event_or_404(db: DB, event_id: Annotated[int, Path()]) -> Event:
    """경로의 `event_id`로 일정을 찾는다. 소속 여부는 검사하지 않는다.

    오류: `404 NOT_FOUND` — 일정 없음.
    """
    event = db.get(Event, event_id)
    if event is None:
        raise errors.NotFound("일정을 찾을 수 없어요.")
    return event


def require_event_member(db: DB, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)]) -> Player:
    """일정이 속한 팀(`event.team_id`)의 팀원(또는 ADMIN)만 통과. `require_team_member`와 같은 규칙.

    오류: `404 NOT_FOUND` — 일정 없음. `403 NOT_A_MEMBER` — 그 팀의 활성 참가자가 아님.
    """
    player = _active_player(db, event.team_id, user)
    if player is None:
        if user.global_role == GlobalRole.ADMIN:
            return Player(team_id=event.team_id, user_id=user.id, role=TeamRole.MANAGER)
        raise errors.NotAMember()
    return player


def require_event_manager(player: Annotated[Player, Depends(require_event_member)]) -> Player:
    """일정이 속한 팀의 매니저(또는 ADMIN)만 통과.

    오류: `403 FORBIDDEN_ROLE` — 팀원이지만 매니저가 아님.
    """
    if player.role != TeamRole.MANAGER:
        raise errors.ForbiddenRole()
    return player


EventMember = Annotated[Player, Depends(require_event_member)]
"""경로 `{event_id}` 일정의 팀 참가자(또는 ADMIN). 404 / 403 NOT_A_MEMBER 가능."""
EventManager = Annotated[Player, Depends(require_event_manager)]
"""경로 `{event_id}` 일정의 팀 매니저(또는 ADMIN). 404 / 403 NOT_A_MEMBER / 403 FORBIDDEN_ROLE 가능."""
