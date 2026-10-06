"""7.3절 팀 · 참가자 — 팀 생성/가입/조회/수정, 팀 코드, 팀원 목록·권한·제외 (F2, F3).

설계서: 7.3절 팀 · 참가자, FR-04 ~ FR-07, 3.3절 권한 매트릭스, 6.2절 `teams` · `players`.

엔드포인트
- POST   /teams                                    팀 생성 (구현됨)
- POST   /teams/join                               팀 코드로 가입 (구현됨)
- GET    /teams/{team_id}                          팀 상세 (구현됨)
- PATCH  /teams/{team_id}                          팀 정보 수정 (구현됨)
- POST   /teams/{team_id}/code:regenerate          팀 코드 재발급 (구현됨)
- GET    /teams/{team_id}/players                  팀원 목록 (구현됨)
- PATCH  /teams/{team_id}/players/{player_id}/role 매니저 권한 부여/회수 (구현됨)
- DELETE /teams/{team_id}/players/{player_id}      팀원 제외 (구현됨)
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, TeamManager, TeamMember, get_team_or_404
from app.api.v1._docs import errors
from app.core import errors as E
from app.models import Player, Team, User
from app.models.enums import GlobalRole, PlayerKind, PlayerStatus, TeamRole
from app.schemas.common import ItemList, PlayerCard, PlayerCardDetailed, UserSummary
from app.schemas.team import (
    RoleUpdate,
    TeamCodeView,
    TeamCreate,
    TeamCreated,
    TeamDetail,
    TeamJoinRequest,
    TeamUpdate,
)
from app.services import player_service, team_service

router = APIRouter(tags=["팀 · 참가자"])


def _detail(db: DB, team: Team, me: Player | None) -> TeamDetail:
    return TeamDetail(
        id=team.id, name=team.name, description=team.description, team_code=team.team_code,
        status=team.status, approval_status=team.approval_status, min_members=team.min_members, home_court=team.home_court,
        owner=UserSummary.model_validate(db.get(User, team.owner_user_id)),
        member_count=team_service.member_count(db, team.id),
        my_role=me.role if me else None, my_player_id=me.id if me else None, created_at=team.created_at,
    )


@router.post("/teams", status_code=201, response_model=TeamCreated, summary="팀 생성")
def create_team(db: DB, user: CurrentUser, body: TeamCreate):
    """팀을 만들고 8자리 팀 코드를 발급한다. 생성자는 자동으로 MANAGER가 된다.

    - **권한:** 로그인 사용자.
    - **처리:** 팀명·소개·홈 코트로 `teams` 행을 만들고, 혼동 문자(0/O/1/I)를 뺀 대문자+숫자
      8자리 코드를 중복 없이 발급한다. 생성자를 `players(kind=MEMBER, role=MANAGER)`로 넣고
      빈 `player_profiles`를 붙인다. 회원 수가 `min_members`(기본 5) 미만이므로 팀은 `PENDING`
      상태로 시작한다. 응답의 `team_code`를 카카오톡으로 공유해 팀원을 모은다.
    - **오류:** `400 VALIDATION_ERROR` — 팀명 길이 등 형식 위반. `401 TOKEN_EXPIRED`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`POST /teams`), FR-04, F2, 6.2절 `teams`, S-05 팀 생성.
    """
    team = team_service.create_team(db, user, body)
    return TeamCreated(id=team.id, team_code=team.team_code)


@router.post(
    "/teams/join", response_model=TeamDetail,
    responses=errors(_403="REMOVED_FROM_TEAM", _404="TEAM_CODE_NOT_FOUND", _409="ALREADY_MEMBER"), summary="팀 코드로 가입",
)
def join_team(db: DB, user: CurrentUser, body: TeamJoinRequest):
    """팀 코드를 입력해 팀에 PLAYER로 가입한다.

    - **권한:** 로그인 사용자.
    - **처리:** 코드를 대문자로 정규화해 팀을 찾는다 (`ARCHIVED` 팀은 없는 것으로 취급).
      이미 `ACTIVE`로 소속돼 있으면 거부하고, 스스로 나간(`LEFT`) 이력이 있으면 그 행을
      다시 `ACTIVE`로 되살린다(과거 기록 승계, 역할은 PLAYER). 매니저가 제외한(`REMOVED`) 사람은 코드가 재발급되기 전까지 돌아올 수 없다. 가입 후 활성 회원이 5명 이상이 되면 팀을
      `ACTIVE`로 전환한다 (FR-06). 응답은 팀 상세 + 이 팀에서의 내 `player_id`·`role`.
    - **오류:** `404 TEAM_CODE_NOT_FOUND` — 존재하지 않거나 보관된 팀의 코드.
      `409 ALREADY_MEMBER` — 이미 소속된 팀. `403 REMOVED_FROM_TEAM` — 매니저가 제외한 팀.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`POST /teams/join`), FR-05 · FR-06, 5.4절 잘못된 팀 코드·중복 가입,
      S-06 팀 가입.
    """
    team = team_service.join_team(db, user, body.team_code)
    me = db.scalar(select(Player).where(Player.team_id == team.id, Player.user_id == user.id))
    return _detail(db, team, me)


@router.get(
    "/teams/{team_id}", response_model=TeamDetail,
    responses=errors(_403="NOT_A_MEMBER"), summary="팀 상세 조회",
)
def get_team(db: DB, me: TeamMember, team: Annotated[Team, Depends(get_team_or_404)]):
    """팀 기본 정보, 상태 배지, 활성 회원 수, 이 팀에서의 내 역할을 돌려준다.

    - **권한:** 팀원 (이 팀의 `ACTIVE` player) 또는 ADMIN.
    - **처리:** `team_id`로 팀을 찾고 소속 여부를 확인한 뒤 `TeamDetail`을 조립한다.
      `status`가 `PENDING`이면 일정 기능이 아직 잠겨 있음을 뜻한다. ADMIN이 비소속 팀을 조회하면
      `my_role`/`my_player_id`는 `null`이다.
    - **오류:** `404 NOT_FOUND` — 팀 없음. `403 NOT_A_MEMBER` — 소속되지 않은 팀.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`GET /teams/{team_id}`), 3.3절 권한 매트릭스, S-07 팀 상세.
    """
    return _detail(db, team, me if me.id else None)


@router.patch(
    "/teams/{team_id}", response_model=TeamDetail,
    responses=errors(_403="FORBIDDEN_ROLE"), summary="팀 정보 수정",
)
def update_team(db: DB, me: TeamManager, team: Annotated[Team, Depends(get_team_or_404)], body: TeamUpdate):
    """팀명·소개·홈 코트 등 팀 정보를 부분 수정한다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 본문에 포함된 필드만 `teams` 행에 덮어쓰고 커밋한다. `team_code`·`status`·
      `owner_user_id`는 이 경로로 바꿀 수 없다.
    - **오류:** `404 NOT_FOUND` — 팀 없음. `403 NOT_A_MEMBER` — 비소속.
      `403 FORBIDDEN_ROLE` — 매니저가 아님. `400 VALIDATION_ERROR`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`PATCH /teams/{team_id}`), 3.2절 팀 매니저 기능.
    """
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(team, k, v)
    db.commit()
    return _detail(db, team, me if me.id else None)


@router.post(
    "/teams/{team_id}/code:regenerate", response_model=TeamCodeView,
    responses=errors(_403="FORBIDDEN_ROLE"), summary="팀 코드 재발급",
)
def regenerate_code(db: DB, me: TeamManager, team: Annotated[Team, Depends(get_team_or_404)]):
    """팀 코드를 새로 발급한다. 이전 코드는 즉시 무효가 된다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 새 8자리 코드를 중복 없이 생성해 `teams.team_code`를 교체한다. 코드가 원치 않는
      곳에 퍼졌을 때 쓴다. 기존 팀원의 소속에는 영향이 없다. 제외됐던(`REMOVED`) 사람은 `LEFT` 로
      풀려, 새 코드를 받으면 다시 가입할 수 있다(옛 코드는 무효).
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`POST /teams/{team_id}/code:regenerate`), 3.2절 팀 매니저 기능.
    """
    return TeamCodeView(team_code=team_service.regenerate_code(db, team).team_code)


@router.get(
    "/teams/{team_id}/players", response_model=ItemList[PlayerCard | PlayerCardDetailed],
    summary="팀원 목록 조회",
)
def list_players(
    db: DB, me: TeamMember, team: Annotated[Team, Depends(get_team_or_404)],
    kind: Annotated[
        PlayerKind | None, Query(description="참가자 종류 필터. 기본 MEMBER(회원만). 게스트는 회차 화면에서만 보이므로 GUEST 를 명시해야 나온다")
    ] = PlayerKind.MEMBER,
    status: Annotated[
        PlayerStatus | None,
        Query(description="소속 상태 필터. 기본 ACTIVE. LEFT(탈퇴)·REMOVED(제외) 이력을 보려면 지정"),
    ] = PlayerStatus.ACTIVE,
    sort: Annotated[
        Literal["skill", "name"],
        Query(description="정렬 기준. skill=실력 내림차순(매니저/ADMIN만 유효), name=이름순(기본)"),
    ] = "name",
):
    """팀의 참가자(회원+게스트) 목록. 호출자 역할에 따라 실력 수치 노출 범위가 다르다.

    - **권한:** 팀원 또는 ADMIN.
    - **처리:** `players`를 프로필·포지션과 함께 조회한 뒤, 호출자가 MANAGER/ADMIN이면
      `PlayerCardDetailed`(`skill_overall`·6축·`skill_confidence`·평균 마진 포함), PLAYER면
      `PlayerCard`(5등급 `skill_grade`·포지션만)로 변환한다. `sort=skill`은 수치가 있는
      매니저 뷰에서만 적용되고, 그 외에는 이름순이다.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`, `400 VALIDATION_ERROR` — 잘못된 enum 값.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`GET /teams/{team_id}/players`), 3.3절 "선수 상세 데이터 조회"
      (MANAGER △ 등급·요약, PLAYER ✕), 7.2절 `PlayerCard` / `PlayerCardDetailed`, S-08 팀원 관리.
    """
    stmt = select(Player).where(Player.team_id == team.id).options(
        selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user)
    )
    if kind:
        stmt = stmt.where(Player.kind == kind)
    if status:
        stmt = stmt.where(Player.status == status)
    players = list(db.scalars(stmt).all())
    detailed = me.role == TeamRole.MANAGER
    if detailed:
        attended = team_service.attended_event_counts(db, team.id)
        cards = [player_service.to_card_detailed(p, attended_events=attended.get(p.id, 0)) for p in players]
    else:
        cards = [player_service.to_card(p) for p in players]
    if sort == "skill" and detailed:
        cards.sort(key=lambda c: (c.skill_overall is None, -(c.skill_overall or 0)))
    else:
        cards.sort(key=lambda c: c.display_name)
    return ItemList(items=cards)


@router.patch(
    "/teams/{team_id}/players/{player_id}/role", response_model=PlayerCard,
    responses=errors(_403="FORBIDDEN_ROLE", _422="CANNOT_DEMOTE_LAST_MANAGER"),
    summary="매니저 권한 부여/회수",
)
def update_role(db: DB, me: TeamManager, team: Annotated[Team, Depends(get_team_or_404)], player_id: int, body: RoleUpdate):
    """팀원의 역할을 MANAGER 또는 PLAYER로 바꾼다.

    - **권한:** **팀장**(팀을 만든 사람, `teams.owner_user_id`) 또는 ADMIN. 위임받은 매니저는 역할을 바꿀 수 없다
      (플레이어 < 매니저 < 팀장 3단계).
    - **처리:** 대상이 이 팀의 참가자인지 확인한다. 게스트에게는 매니저 권한을 줄 수 없다.
      MANAGER → PLAYER 회수 시 팀에 다른 활성 매니저가 남아 있어야 한다. 팀장이 스스로 내려오면 가장 먼저
      매니저가 된 사람(players.id 최소)에게 팀장 권한이 넘어간다. 부여 시 `role_granted_by`에 부여한 사용자를 기록한다.
    - **오류:** `404 NOT_FOUND` — 팀 또는 팀원 없음. `403 FORBIDDEN_ROLE` — 매니저가 아님.
      `400 VALIDATION_ERROR` — 게스트에게 권한 부여 시도.
      `422 CANNOT_DEMOTE_LAST_MANAGER` — 마지막 매니저의 권한 회수.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`PATCH .../players/{player_id}/role`), FR-07, F3, 3.1절 액터 정의.
    """
    target = db.get(Player, player_id)
    if target is None or target.team_id != team.id:
        raise E.NotFound("이 사람을 찾을 수 없어요.")
    if target.kind == PlayerKind.GUEST:
        raise E.ValidationError("게스트에게는 매니저 권한을 줄 수 없어요.")
    # 권한 부여·회수는 팀장(팀을 만든 사람, teams.owner_user_id)만. 위임받은 매니저는 다른 사람의 역할을 바꿀 수 없다
    if me.user_id != team.owner_user_id and (me.id is not None):  # id 가 None 이면 비소속 ADMIN 의 가상 매니저
        raise E.ForbiddenRole("팀장(팀을 만든 매니저)만 매니저 권한을 바꿀 수 있어요.")
    if body.role == TeamRole.PLAYER and target.role == TeamRole.MANAGER:
        others = db.scalars(
            select(Player).where(
                Player.team_id == team.id, Player.role == TeamRole.MANAGER,
                Player.status == PlayerStatus.ACTIVE, Player.id != target.id,
            ).order_by(Player.id)
        ).all()
        if not others:
            raise E.CannotDemoteLastManager("매니저가 1명뿐이라 해제할 수 없어요. 먼저 다른 팀원을 매니저로 지정해 주세요.")
        if target.user_id == team.owner_user_id:
            # 팀장이 스스로 내려오면 가장 먼저 매니저가 된 사람(players.id 가 가장 작은 매니저)에게 팀장 권한이 넘어간다
            team.owner_user_id = others[0].user_id
    target.role = body.role
    target.role_granted_by = me.user_id if body.role == TeamRole.MANAGER else None
    db.commit()
    return player_service.to_card(target, include_grade=True)


@router.post("/teams/{team_id}:leave", status_code=204, responses=errors(_422="CANNOT_DEMOTE_LAST_MANAGER"), summary="팀 나가기")
def leave_team(db: DB, me: TeamMember, team: Annotated[Team, Depends(get_team_or_404)]):
    """내가 팀에서 나간다. 기록은 남고 `status=LEFT`. 팀 코드로 다시 들어오면 복원된다.

    - **오류:** `422 CANNOT_DEMOTE_LAST_MANAGER` — 다른 팀원이 있는데 유일한 매니저. `403 NOT_A_MEMBER` — 비소속 ADMIN.
    - **상태:** `구현됨`.
    """
    if me.id is None:
        raise E.NotAMember("이 팀에 속해 있지 않아요.")
    team_service.leave_team(db, team, me)


@router.delete(
    "/teams/{team_id}/players/{player_id}", status_code=204,
    responses=errors(_403=("FORBIDDEN_ROLE", "FORBIDDEN_NOT_OWNER"), _422="CANNOT_DEMOTE_LAST_MANAGER"), summary="팀원 제외",
)
def remove_player(db: DB, me: TeamManager, user: CurrentUser, team: Annotated[Team, Depends(get_team_or_404)], player_id: int):
    """팀원(회원 또는 게스트)을 팀에서 제외한다. 기록은 보존된다.

    - **권한:** 팀 매니저 또는 ADMIN. **매니저를 제외하는 것은 팀장(또는 ADMIN)만** 할 수 있다 — 위임받은 매니저끼리
      서로 내보내지 못하게 (플레이어 < 매니저 < 팀장 3단계, 권한 바꾸기와 같은 규칙). **팀장은 누구도 제외할 수 없다** —
      팀장이 먼저 다른 매니저에게 넘기거나(권한 회수 시 자동 승계) 스스로 나가야 한다.
    - **처리:** 물리 삭제가 아니라 `players.status=REMOVED`로 바꾼다. 과거 쿼터 기록·배정·투표는
      `player_id`를 그대로 참조하므로 유지된다. 제외 후 활성 회원이 5명 미만이 되면 팀 상태를
      `PENDING`으로 되돌린다. 제외된 회원은 팀 코드로 다시 가입할 수 없다(`403 REMOVED_FROM_TEAM`) —
      스스로 나간 사람(LEFT)만 코드로 돌아올 수 있다. 매니저가 코드를 재발급하면 제외가 풀려 새 코드로는 돌아올 수 있다.
    - **오류:** `404 NOT_FOUND` — 팀 또는 팀원 없음. `403 FORBIDDEN_ROLE` — 매니저가 아님.
      `403 FORBIDDEN_NOT_OWNER` — 팀장이 아닌 매니저가 매니저를 제외, 또는 팀장을 제외하려 함.
      `422 CANNOT_DEMOTE_LAST_MANAGER` — 마지막 매니저 제외.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`DELETE .../players/{player_id}`), FR-07, F3, 6.2절 `players.status`.
    """
    target = db.get(Player, player_id)
    if target is None or target.team_id != team.id:
        raise E.NotFound("이 사람을 찾을 수 없어요.")
    if target.user_id is not None and target.user_id == team.owner_user_id:
        raise E.ForbiddenNotOwner("팀장은 제외할 수 없어요. 팀장이 먼저 다른 매니저에게 팀장을 넘기거나 팀을 나가야 해요.")
    if target.role == TeamRole.MANAGER and target.status == PlayerStatus.ACTIVE:
        is_owner = me.user_id == team.owner_user_id
        if not is_owner and user.global_role != GlobalRole.ADMIN:
            raise E.ForbiddenNotOwner("매니저는 팀장만 제외할 수 있어요.")
        other = db.scalar(
            select(Player.id).where(
                Player.team_id == team.id, Player.role == TeamRole.MANAGER, Player.status == PlayerStatus.ACTIVE, Player.id != target.id,
            ).order_by(Player.joined_at, Player.id).limit(1)
        )
        if other is None:
            raise E.CannotDemoteLastManager("팀에 매니저가 한 명은 남아 있어야 해요. 먼저 다른 팀원에게 매니저 권한을 넘겨 주세요.")
    target.status = PlayerStatus.REMOVED
    team_service.refresh_team_status(db, team)
    db.commit()
