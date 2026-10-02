"""팀 생성·가입·활성화 서비스 (설계서 F2 · FR-04~06 · 6.2절 `teams`/`players`).

이 모듈은 "팀"과 "팀에 속한 참가자(`players`)"의 생애주기를 다룬다.
새 개발자가 알아야 할 구조적 전제 두 가지:

1. **팀 소속 테이블이 따로 없다.** v0.3 ERD에서 `team_memberships`는 `players`에
   흡수되었다. 회원이 팀에 들어오면 `Player(kind=MEMBER, user_id=...)` 행이 생기고,
   역할(`role`)과 소속 상태(`status`)도 그 행이 갖는다. 게스트는 같은 테이블에
   `kind=GUEST, user_id=NULL`로 들어오지만, 이 모듈은 회원 경로만 담당한다
   (게스트 등록은 F13 / guests 라우터).
2. **실력 지표는 팀 단위다.** 같은 사람이 두 팀에 있으면 `player_id`가 둘이고
   `PlayerProfile`도 둘이다 (13.2절 4항). 그래서 `_add_member`가 매번 빈 프로필을
   같이 만든다.

세션 설정(`app/db/session.py`)이 `autoflush=False`라는 점이 이 파일의 몇몇 `db.flush()`
호출을 설명한다. 자세한 이유는 `refresh_team_status` docstring 참조.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import errors
from app.core.security import generate_team_code
from app.models import Player, PlayerProfile, Team, User
from app.models.enums import ApprovalStatus, PlayerKind, PlayerStatus, TeamRole, TeamStatus
from app.schemas.team import TeamCreate


def _unique_code(db: Session) -> str:
    """DB에 없는 팀 코드를 하나 만들어 돌려준다 (FR-04).

    `generate_team_code()`는 대문자+숫자 8자(혼동되는 0/O/1/I 제외, 32^8 ≈ 1.1조 가지)를
    무작위로 만든다. 충돌 확률은 사실상 0이지만 `teams.team_code`가 UNIQUE라서
    INSERT가 터지면 트랜잭션 전체가 롤백되므로, 루프로 **미리 존재 여부를 확인**하고
    없는 코드만 반환한다. 루프는 거의 항상 1회로 끝난다.

    부수 효과: 없음 (SELECT만). 검사와 INSERT 사이의 경쟁 조건은 UNIQUE 제약이 최종
    방어선이 되므로 여기서 따로 잠그지 않는다.
    """
    while True:
        code = generate_team_code()
        if not db.scalar(select(Team.id).where(Team.team_code == code)):
            return code


def member_count(db: Session, team_id: int) -> int:
    """팀의 **활성 회원** 수를 센다. 게스트·탈퇴자·제외자는 제외.

    조건: `kind == MEMBER` AND `status == ACTIVE`.
    게스트(`kind=GUEST`)는 5명 활성화 기준(FR-06)에 포함되지 않는다 — 계정 없는
    사람으로 팀을 "활성"으로 만들 수는 없기 때문이다.

    API 응답의 `member_count` 필드(S-07 팀 상세, `/me/teams`)와 `refresh_team_status`가
    함께 쓴다. COUNT가 NULL을 돌려줄 일은 없지만 타입 안전을 위해 `or 0`을 붙였다.
    """
    return db.scalar(
        select(func.count()).select_from(Player).where(
            Player.team_id == team_id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE
        )
    ) or 0


def refresh_team_status(db: Session, team: Team) -> None:
    """FR-06: 회원 5명 이상이면 ACTIVE, 미만이면 PENDING으로 팀 상태를 다시 계산한다.

    팀원 수가 바뀌는 모든 지점(생성·가입·제외)에서 호출해야 한다. 양방향이다:
    5명이 되면 ACTIVE로 올라가고, 제외로 4명이 되면 다시 PENDING으로 내려간다
    (일정 등록이 다시 잠긴다 — `422 TEAM_NOT_ACTIVE`).
    `ARCHIVED`는 관리자가 강제 비활성화한 상태이므로 인원과 무관하게 건드리지 않는다.

    **왜 `db.flush()`를 먼저 부르는가.**
    `SessionLocal`이 `autoflush=False`로 만들어져 있다. 즉 `existing.status = ACTIVE`처럼
    ORM 객체를 바꿔도, 명시적으로 flush/commit하기 전까지는 DB로 전송되지 않는다.
    그런데 `member_count`는 ORM 객체가 아니라 **SQL COUNT 쿼리**로 세므로, 대기 중인
    변경을 flush하지 않으면 재가입 직후에도 예전 인원수(재가입 전)를 읽게 된다.
    `db.flush()`는 같은 트랜잭션 안에서 대기 중인 INSERT/UPDATE를 DB로 보내기만 하고
    커밋은 하지 않으므로, 실패 시 롤백 가능성은 그대로 유지된다.

    부수 효과: `db.flush()` + `team.status` 변경. **커밋은 호출자 책임**이다.
    임계값은 `team.min_members`(기본 5)를 읽으므로 팀별로 다르게 둘 수도 있다.
    """
    if team.status == TeamStatus.ARCHIVED:
        return
    db.flush()  # autoflush=False이므로 대기 중인 status 변경을 먼저 반영
    approved = team.approval_status == ApprovalStatus.APPROVED  # 관리자 승인 전에는 인원이 차도 PENDING
    team.status = TeamStatus.ACTIVE if approved and member_count(db, team.id) >= team.min_members else TeamStatus.PENDING


def create_team(db: Session, owner: User, req: TeamCreate) -> Team:
    """팀 생성 (FR-04). `POST /teams`. 생성자는 자동으로 MANAGER가 된다.

    처리 순서:
    1. 고유 팀 코드를 뽑아 `Team` 행을 만든다 (status 기본값 PENDING).
    2. `db.flush()`로 `team.id`를 확보한다 — 다음 단계의 `Player.team_id`에 필요하다.
    3. `_add_member(role=MANAGER)`로 생성자를 첫 참가자로 넣는다.
    4. `refresh_team_status` — 1명이므로 사실상 PENDING 확정. 그래도 호출하는 이유는
       "인원이 바뀌면 반드시 상태를 재계산한다"는 규칙을 한 곳도 빠뜨리지 않기 위함.

    입력: 소유자 `User`, `TeamCreate` (name, description?, home_court?)
    출력: 생성된 `Team` (라우터가 `id`·`team_code`를 응답으로 꺼낸다)
    부수 효과: `db.commit()` — teams 1행, players 1행, player_profiles 1행 INSERT.
    에러: 없음 (검증 오류는 스키마 단계에서 `400 VALIDATION_ERROR`로 처리됨).
    """
    from app.core.config import get_settings

    team = Team(
        name=req.name,
        description=req.description,
        home_court=req.home_court,
        team_code=_unique_code(db),
        owner_user_id=owner.id,
        approval_status=ApprovalStatus.PENDING if get_settings().team_approval_required else ApprovalStatus.APPROVED,
        approved_at=None if get_settings().team_approval_required else datetime.now(UTC),
    )
    db.add(team)
    db.flush()
    _add_member(db, team, owner, role=TeamRole.MANAGER)
    refresh_team_status(db, team)
    db.commit()
    return team


def join_team(db: Session, user: User, team_code: str) -> Team:
    """팀 코드로 가입 (FR-05). `POST /teams/join`.

    팀 코드는 대문자로 정규화해서 찾는다 (카카오톡으로 받은 코드를 소문자로 입력해도
    통과). ARCHIVED 팀은 존재해도 "없는 코드"로 취급해 가입을 막는다.

    **재가입 경로(`LEFT`).**
    `players`에는 `UNIQUE (team_id, user_id)` 제약이 있어 같은 사람의 행을 두 번 만들 수
    없다. 그래서 이 사람의 `Player` 행이 이미 있으면 상태로 분기한다:
    - `ACTIVE`  → 이미 소속됨. `409 ALREADY_MEMBER`.
    - `REMOVED` → 매니저가 제외한 사람. 팀 코드만으로는 돌아올 수 없다 — `403 REMOVED_FROM_TEAM`.
      (팀 코드는 카카오톡으로 퍼져 있어, 막지 않으면 제외가 의미가 없다)
    - `LEFT` → 스스로 나간 사람. **기존 행을 되살린다** (status를 ACTIVE로, `joined_at` 갱신).
      새 행을 만들지 않으므로 그 행에 묶인 `PlayerProfile`·쿼터 기록·투표 이력이
      그대로 승계된다. "나갔다 돌아온 사람의 실력 데이터가 0으로 리셋되지 않는다"는
      의도된 동작이다.
      단, **역할은 PLAYER로 초기화한다.** 제외 API(`DELETE .../players/{id}`)는 status만
      REMOVED로 바꾸고 role을 남겨 두므로, 여기서 되돌리지 않으면 제외된 매니저가 코드만
      알면 다시 매니저로 복귀하는 구멍이 생긴다. 권한은 현재 매니저가 다시 부여해야 한다.
    - 행이 없음 → `_add_member(role=PLAYER)`로 새 참가자 생성.

    마지막에 `refresh_team_status`로 5명 도달 여부를 재계산한다.

    입력: 가입자 `User`, 팀 코드 문자열
    출력: 가입된 `Team`
    부수 효과: `db.commit()`.
    에러: `404 TEAM_CODE_NOT_FOUND`, `409 ALREADY_MEMBER` (같은 코드로 동시에 두 번 가입해도 하나만 성공),
    `403 REMOVED_FROM_TEAM`.
    """
    team = db.scalar(select(Team).where(Team.team_code == team_code.upper()))
    if team is None or team.status == TeamStatus.ARCHIVED:
        raise errors.TeamCodeNotFound()
    existing = db.scalar(select(Player).where(Player.team_id == team.id, Player.user_id == user.id))
    if existing is not None:
        if existing.status == PlayerStatus.ACTIVE:
            raise errors.AlreadyMember()
        if existing.status == PlayerStatus.REMOVED:
            raise errors.RemovedFromTeam()
        existing.status = PlayerStatus.ACTIVE  # 탈퇴 후 재가입 — 기록은 승계
        existing.joined_at = datetime.now(UTC)
        existing.role = TeamRole.PLAYER  # 권한은 승계하지 않음 (제외된 매니저의 자동 복귀 방지)
        existing.role_granted_by = None
        db.flush()
        from app.services import survey_service

        survey_service.on_member_joined(db, existing)
    else:
        try:
            _add_member(db, team, user, role=TeamRole.PLAYER)
        except IntegrityError:  # 검사와 저장 사이에 같은 사람이 먼저 가입했다 (uq_players_team_user)
            db.rollback()
            raise errors.AlreadyMember() from None
    refresh_team_status(db, team)
    db.commit()
    return team


def _add_member(db: Session, team: Team, user: User, *, role: TeamRole) -> Player:
    """회원을 팀의 참가자(`Player`, kind=MEMBER)로 추가하고 빈 프로필을 함께 만든다.

    `display_name`은 닉네임이 있으면 닉네임, 없으면 이름을 복사한다 — 배정 화면·
    쿼터 기록에서 매번 `users`를 조인하지 않기 위한 비정규화이며, 게스트(이름만 있는
    참가자)와 같은 컬럼을 쓰기 위한 것이기도 하다.
    `role_granted_by`는 매니저로 들어오는 경우(팀 생성자)에만 본인 id로 채운다.

    **`PlayerProfile`을 지금 비어 있는 채로 만드는 이유.**
    `player_profiles`는 `players`와 1:1이고, 이후 모든 지표 갱신(설문 → 사전값,
    매니저 정렬, 쿼터 잔차)이 "이미 있는 프로필 행을 UPDATE"하는 방식으로 짜여 있다.
    가입 시점에 행을 만들어 두면 뒤의 코드가 "프로필이 없을 수도 있다"를 걱정하지
    않아도 된다. `prior_overall`·`skill_overall`은 이 시점에 NULL이고, `PlayerCard`
    변환은 그 경우 `skill_grade=None`("데이터 부족")으로 표시한다.
    실제 값은 온보딩 설문(F1, 8.4절)과 매니저 정렬(F14, 8.5절) 단계에서 채운다 —
    아래 TODO가 그 자리다.

    부수 효과: `db.add` + `db.flush()` (player.id 확보). 커밋은 호출자 책임.
    이 함수는 회원 전용이다. 게스트는 `user_id=NULL`이라 별도 경로에서 만든다.
    """
    player = Player(
        team_id=team.id,
        user_id=user.id,
        kind=PlayerKind.MEMBER,
        display_name=user.nickname or user.name,
        role=role,
        joined_at=datetime.now(UTC),
        role_granted_by=user.id if role == TeamRole.MANAGER else None,
    )
    player.profile = PlayerProfile()
    db.add(player)
    db.flush()
    # 설문 응답이 있으면 포지션을 채우고, 이 팀의 prior 를 다시 계산한다 (8.4절 — 팀 단위 z-score)
    from app.services import (
        survey_service,  # 순환 import 회피 (survey_service 가 player_service 를 쓴다)
    )

    survey_service.on_member_joined(db, player)
    return player


def regenerate_code(db: Session, team: Team) -> Team:
    """팀 코드 재발급 (MANAGER). `POST /teams/{team_id}/code:regenerate`.

    코드가 외부에 퍼져 원치 않는 가입이 생길 때 쓴다. 이전 코드는 즉시 무효가 되며
    (같은 컬럼을 덮어쓰므로) 이력은 남지 않는다. 기존 팀원에게는 영향이 없다.

    부수 효과: `db.commit()`. 권한 검사(매니저인지)는 라우터의 의존성에서 끝난 상태로
    들어온다.
    """
    team.team_code = _unique_code(db)
    db.commit()
    return team


def attended_event_counts(db: Session, team_id: int) -> dict[int, int]:
    """player_id → 참석(ATTEND)한 지난 회차 수. 취소된 일정과 아직 오지 않은 일정은 제외 (팀원 관리 화면 참여 횟수)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.core.config import get_settings
    from app.models import Event, EventAttendance
    from app.models.enums import AttendanceStatus, EventStatus

    rows = db.execute(
        select(EventAttendance.player_id, func.count())
        .join(Event, Event.id == EventAttendance.event_id)
        .where(
            Event.team_id == team_id, Event.status != EventStatus.CANCELED, Event.event_date <= datetime.now(ZoneInfo(get_settings().timezone)).date(),
            EventAttendance.status == AttendanceStatus.ATTEND,
        )
        .group_by(EventAttendance.player_id)
    ).all()
    return {pid: n for pid, n in rows}


def set_approval(db: Session, team: Team, admin: User | None, approved: bool) -> Team:
    """관리자 승인/거절. 승인되면 인원 조건에 따라 바로 ACTIVE 가 될 수 있다. commit 까지."""
    team.approval_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
    team.approved_at = datetime.now(UTC) if approved else None
    team.approved_by = admin.id if (admin and approved) else None
    refresh_team_status(db, team)
    db.commit()
    return team


def leave_team(db: Session, team: Team, me: Player) -> None:
    """팀에서 스스로 나간다 (`POST /teams/{id}:leave`). 기록은 남고 `status=LEFT`.

    유일한 매니저는 다른 활성 회원이 있으면 나갈 수 없다 (매니저 없는 팀 방지). 팀장이 나가면 남은 매니저 중
    가장 먼저 매니저가 된 사람에게 팀장이 넘어간다. 마지막 남은 사람이 나가면 팀은 PENDING 이 된다. commit 까지.
    """
    if me.status != PlayerStatus.ACTIVE:
        raise errors.NotAMember("이미 이 팀에 속해 있지 않아요.")
    others_active = db.scalar(
        select(Player.id).where(Player.team_id == team.id, Player.status == PlayerStatus.ACTIVE, Player.kind == PlayerKind.MEMBER, Player.id != me.id).limit(1)
    )
    if me.role == TeamRole.MANAGER:
        heir = db.scalar(
            select(Player).where(Player.team_id == team.id, Player.status == PlayerStatus.ACTIVE, Player.role == TeamRole.MANAGER, Player.id != me.id).order_by(Player.id)
        )
        if heir is None and others_active is not None:
            raise errors.CannotDemoteLastManager("유일한 매니저는 나갈 수 없어요. 먼저 다른 팀원을 매니저로 지정해 주세요.")
        if heir is not None and team.owner_user_id == me.user_id:
            team.owner_user_id = heir.user_id
    me.status = PlayerStatus.LEFT
    user = db.get(User, me.user_id) if me.user_id else None
    if user is not None and user.primary_team_id == team.id:
        user.primary_team_id = None
    db.flush()
    refresh_team_status(db, team)
    db.commit()
