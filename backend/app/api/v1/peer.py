"""7.3절 경기 후 설문 · 통계 — 피어 투표(재설계), 잘 맞는 참여자, 개인 통계·리더보드 (F9, F10, F11).

케미는 코트 마진으로 "측정"하지 않고 경기 후 투표로 "선언"받는다 (9.4절). 피어 투표 설계재설계:
카테고리당 0~2명, 후보는 그날 참석자 전원(본인 제외) 한 리스트, PLAY_AGAIN 에 이유 태그(선택),
일정 종료 시각이 지나면 자동 오픈, 독려는 매니저가 카카오톡에 수동 공유. "잘한 사람" 은 표시 전용.

설계서: 7.3절 경기 후 설문 · 통계, FR-29 ~ FR-31, 9.4절, 6.2절 post_game_* / chemistry_scores.

엔드포인트
- GET  /events/{event_id}/post-game-survey                 내 상태 + 후보 명단 (구현됨)
- GET  /events/{event_id}/post-game-survey/candidates      후보 명단 (구현됨, 위와 같은 응답)
- POST /events/{event_id}/post-game-survey                 피어 투표 제출 (구현됨)
- GET  /events/{event_id}/post-game-survey/share-message   매니저 독려 메시지 + 응답 현황 (구현됨)
- GET  /players/{player_id}/compatible                     나와 잘 맞는 참여자 (구현됨)
- GET  /players/{player_id}/stats                          참여 이력·쿼터 기록·마진 추이 (+매니저: 실력 지표 근거) (구현됨)
- GET  /teams/{team_id}/stats/leaderboard                  팀 리더보드 (구현됨)
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import selectinload

from app.api.deps import (
    DB,
    CurrentUser,
    EventManager,
    EventMember,
    TeamMember,
    get_event_or_404,
    get_team_or_404,
)
from app.api.v1._docs import errors
from app.core import errors as E
from app.models import Event, Player, Team
from app.schemas.common import ItemList
from app.schemas.peer import (
    CompatiblePlayer,
    LeaderboardEntry,
    PlayerStats,
    PostGameSurveyIn,
    ShareMessage,
    VoteTargets,
)
from app.services import guest_service, peer_service

_PLAYER_LOAD = [selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user)]

router = APIRouter(tags=["경기 후 설문 · 통계"])

_TARGET_DOC = """그날 참석자 전원(본인 제외, 게스트 포함)을 한 리스트로 돌려준다. 팀은 배지로만 구분한다.

    - **권한:** 이 일정에 참석(ATTEND)한 회원. 게스트는 응답자가 될 수 없다.
    - **처리:** 일정 종료 시각(`event_date + end_time`)이 지나야 열린다 (쿼터 기록 여부와 무관). 확정 배정이 있으면
      각 후보에 `squad_no / squad_name / is_same_team` 을 붙인다. 이미 제출했으면 `already_submitted=true` 와 `my_votes`.
    - **오류:** `403 SURVEY_NOT_OPEN` — 종료 전. `403 NOT_ATTENDEE`, `404 NOT_FOUND`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** FR-29, F9, 9.4절, 피어 투표 설계, S-16.
    """


@router.get(
    "/events/{event_id}/post-game-survey", response_model=VoteTargets,
    responses=errors(_403=("SURVEY_NOT_OPEN", "NOT_ATTENDEE")), summary="피어 투표 후보 명단 · 내 상태",
)
def vote_targets(db: DB, me: EventMember, event: Annotated[Event, Depends(get_event_or_404)]):
    """피어 투표 후보 명단과 내 제출 상태.

    """ + _TARGET_DOC
    return peer_service.targets(db, event, me)


@router.get(
    "/events/{event_id}/post-game-survey/candidates", response_model=VoteTargets,
    responses=errors(_403=("SURVEY_NOT_OPEN", "NOT_ATTENDEE")), summary="피어 투표 후보 명단",
)
def vote_candidates(db: DB, me: EventMember, event: Annotated[Event, Depends(get_event_or_404)]):
    """피어 투표 후보 명단 (피어 투표 설계).

    """ + _TARGET_DOC
    return peer_service.targets(db, event, me)


@router.post(
    "/events/{event_id}/post-game-survey", status_code=201, response_model=VoteTargets,
    responses=errors(_400=("SELF_VOTE_NOT_ALLOWED", "VALIDATION_ERROR"), _403=("SURVEY_NOT_OPEN", "NOT_ATTENDEE"), _409="ALREADY_SUBMITTED"),
    summary="피어 투표 제출",
)
def submit_votes(db: DB, me: EventMember, event: Annotated[Event, Depends(get_event_or_404)], body: PostGameSurveyIn):
    """'다음에 같이 뛰고 싶은 사람'(0~2명, 이유 태그 선택)과 '오늘 잘한 사람'(0~2명)을 제출한다. 빈 제출도 가능.

    - **권한:** 이 일정에 참석한 회원, 회차당 1회.
    - **처리:** 본인·비참석자·같은 항목 중복·3명 이상·BEST 에 이유 태그는 400. `target_side` 는 확정 배정에서
      서버가 계산한다 (배정 없으면 NULL). 저장 후 팀의 `chemistry_scores.pref_score / pref_mutual / together_events`
      를 재계산한다 (함께 참석 회차 대비 지목 비율 + 최근 가중 0.9^k). BEST_PERFORMER 는 `peer_vote_score`(표시 전용)
      에만 집계되고 실력 산출에는 절대 입력되지 않는다.
    - **오류:** `409 ALREADY_SUBMITTED`, `403 SURVEY_NOT_OPEN`, `403 NOT_ATTENDEE`, `400 SELF_VOTE_NOT_ALLOWED / VALIDATION_ERROR`.
    - **상태:** `구현됨`.
    - **설계서:** FR-29 · FR-30, F9 · F10, 9.4절 채택 정책, 피어 투표 설계, S-16.
    """
    peer_service.submit(db, event, me, body)
    return peer_service.targets(db, event, me)


@router.get(
    "/events/{event_id}/post-game-survey/share-message", response_model=ShareMessage,
    responses=errors(_403="FORBIDDEN_ROLE"), summary="피어 투표 독려 메시지 (매니저)",
)
def share_message(db: DB, me: EventManager, event: Annotated[Event, Depends(get_event_or_404)]):
    """카카오톡 단체방에 붙여 넣을 독려 문구·링크와 응답 현황(`responded/total`)을 돌려준다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 시스템은 자동 발송·리마인더를 하지 않는다 (스펙 3.3절). 매니저가 현황을 보고 필요할 때만 공유한다.
    - **오류:** `403 FORBIDDEN_ROLE`, `404 NOT_FOUND`.
    - **상태:** `구현됨`.
    - **설계서:** 피어 투표 설계, S-05 카카오 공유 패턴.
    """
    return peer_service.share_message(db, event)


@router.get(
    "/players/{player_id}/compatible", response_model=ItemList[CompatiblePlayer],
    responses=errors(_403="FORBIDDEN_ROLE"), summary="나와 잘 맞는 참여자",
)
def compatible_players(db: DB, user: CurrentUser, player_id: int):
    """투표 데이터만으로 만든 "잘 맞는 참여자" 목록. 성과 지표는 넣지 않는다.

    - **권한:** 본인 / 팀 매니저 / ADMIN.
    - **처리:** (1) 상호 PLAY_AGAIN 지목, (2) 나를 BEST 로 뽑아준 횟수 / 내가 뽑은 횟수, (3) 같은 팀으로 함께 출전한
      쿼터 수를 모아 상호 선호 → 투표 수 → 함께 뛴 횟수 순으로 정렬한다. 투표가 하나도 없는 사람은 목록에 없다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** FR-31, F11, 9.4절 "F11은 어떻게 만드나", S-17.
    """
    player = db.get(Player, player_id, options=_PLAYER_LOAD)  # 카드·프로필을 만들 때 쓰이므로 한 번에 읽는다
    if player is None:
        raise E.NotFound("이 사람을 찾을 수 없어요.")
    if player.user_id != user.id and not guest_service.is_manager(db, user, player.team_id):
        raise E.ForbiddenRole()
    return ItemList(items=peer_service.compatible(db, player))


@router.get(
    "/players/{player_id}/stats", response_model=PlayerStats,
    responses=errors(_403="FORBIDDEN_ROLE"), summary="선수 통계 (참여 이력 · 쿼터 기록 · 실력 지표)",
)
def player_stats(db: DB, user: CurrentUser, player_id: int):
    """참여 이력, 내가 뛴 쿼터 기록, 회차별 마진 추이, 포지션 분포. 매니저/ADMIN 에게는 실력 지표의 근거까지.

    - **권한:** 본인 / 팀 매니저 / ADMIN.
    - **처리:** `quarter_lineups(player_id)` 를 회차별로 묶는다 (병합된 게스트 행 포함). 매니저/ADMIN 이면
      `skill_overall`·`prior_overall`·신뢰도·6축·활성 정렬 순위·PLAY_AGAIN 지목 수·`skill_rating_history` 를 더한다.
      플레이어 본인에게는 수치·등급이 내려가지 않는다 (FR-28).
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** FR-28 · FR-31, F11, 9.1절(원시 마진은 실력이 아님), 9.2절 표시 정책, 13.1절 Q3, S-17.
    """
    player = db.get(Player, player_id, options=_PLAYER_LOAD)  # 카드·프로필을 만들 때 쓰이므로 한 번에 읽는다
    if player is None:
        raise E.NotFound("이 사람을 찾을 수 없어요.")
    is_mgr = guest_service.is_manager(db, user, player.team_id)
    if player.user_id != user.id and not is_mgr:
        raise E.ForbiddenRole()
    return peer_service.player_stats(db, player, detailed=is_mgr)


@router.get("/teams/{team_id}/stats/periods", response_model=ItemList[str], summary="리더보드에서 고를 수 있는 달")
def leaderboard_periods(db: DB, me: TeamMember, team: Annotated[Team, Depends(get_team_or_404)]):
    """기록이 있는 달만 최신순으로 돌려준다 (`["2026-09", "2026-08"]`).

    - **권한:** 팀원 또는 ADMIN.
    - **처리:** 취소되지 않은 지난 일정이 하나라도 있는 달. 화면의 월 선택 목록이 이 값을 그대로 쓰므로
      기록이 없는 달은 아예 고를 수 없다.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, S-08 리더보드.
    """
    return ItemList(items=peer_service.leaderboard_periods(db, team.id))


@router.get(
    "/teams/{team_id}/stats/leaderboard", response_model=ItemList[LeaderboardEntry],
    responses=errors(_403="FORBIDDEN_ROLE"), summary="팀 리더보드",
)
def leaderboard(
    db: DB, me: TeamMember, team: Annotated[Team, Depends(get_team_or_404)],
    metric: Annotated[Literal["residual", "attendance", "quarters"], Query(description="attendance=참여율(전원), quarters=출전 쿼터 수(전원), residual=기여 점수(매니저/ADMIN)")] = "attendance",
    period: Annotated[str | None, Query(description="집계 기간. 예: 2026-09(월), 2026-Q3(분기). 생략하면 전체. 고를 수 있는 달은 /stats/periods 로 조회")] = None,
):
    """팀원을 참여율·출전 쿼터·기여 점수 기준으로 순위 매긴다.

    - **권한:** 팀원 또는 ADMIN. `metric=residual` 은 팀 매니저/ADMIN 전용 (플레이어에게는 실력 수치를 보이지 않는다, FR-28).
    - **처리:** 세 지표 모두 `period` 로 좁힌다. attendance = 참석한 지난 회차 ÷ 기간 내 지난 회차 수(가입 이후만),
      quarters = 출전 쿼터 수, residual = 그 기간 쿼터에 남긴 몫의 합(`quarter_lineups.residual`).
      병합된 게스트의 기록은 회원 쪽으로 합산한다. 값 내림차순, 같으면 이름순.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, 9.1절 코트 마진의 함정, 9.2절 표시 정책.
    """
    from app.models.enums import TeamRole

    is_mgr = me.role == TeamRole.MANAGER
    if metric == "residual" and not is_mgr:
        raise E.ForbiddenRole("기여도 순위는 매니저만 볼 수 있어요.")
    return ItemList(items=peer_service.leaderboard(db, team.id, metric=metric, period=period, include_grade=is_mgr))
