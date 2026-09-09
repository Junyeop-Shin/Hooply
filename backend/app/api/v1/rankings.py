"""7.3절 매니저 실력 정렬 (F14) — 버전으로 쌓는다.

설계서: 7.3절 매니저 실력 정렬, FR-14, 8.5절 (설문 0.5 + 정렬 0.5), 6.2절 manager_rankings, S-19.

엔드포인트
- GET  /teams/{team_id}/rankings/latest  현재 활성 정렬 (구현됨)
- POST /teams/{team_id}/rankings         새 정렬 버전 저장 (구현됨)
- GET  /teams/{team_id}/rankings         정렬 이력 (구현됨)
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DB, CurrentUser, TeamManager, get_team_or_404
from app.api.v1._docs import errors
from app.models import Team
from app.schemas.common import ItemList
from app.schemas.team import RankingCreate, RankingView
from app.services import ranking_service

router = APIRouter(tags=["매니저 실력 정렬"])


@router.get(
    "/teams/{team_id}/rankings/latest", response_model=RankingView,
    responses=errors(_403="FORBIDDEN_ROLE", _404="NO_RANKING"), summary="현재 활성 정렬 조회",
)
def latest_ranking(db: DB, me: TeamManager, team: Annotated[Team, Depends(get_team_or_404)]):
    """지금 사전 실력값 계산에 쓰이는 정렬 버전을 돌려준다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** `manager_rankings.is_active=true`인 버전의 항목을 rank_no 순으로 (탈퇴한 참가자는 제외).
    - **오류:** `404 NO_RANKING` — 아직 정렬한 적 없음. `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, F14, S-19.
    """
    return ranking_service.latest(db, team)


@router.post(
    "/teams/{team_id}/rankings", status_code=201, response_model=RankingView,
    responses=errors(_403="FORBIDDEN_ROLE", _422="PLAYER_NOT_IN_TEAM"), summary="새 정렬 버전 저장",
)
def create_ranking(db: DB, me: TeamManager, user: CurrentUser, team: Annotated[Team, Depends(get_team_or_404)], body: RankingCreate):
    """매니저가 늘어놓은 순서(상위 → 하위)를 새 버전으로 저장하고 사전 실력값을 다시 계산한다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 이전 활성 버전을 `is_active=false`로 내리고 새 버전을 만든다. 순위를 z-score로 바꿔
      설문 z와 반반 결합해 `prior_overall`을 갱신한다 (8.5절). 설문이 없는 참가자·게스트는 정렬만으로
      `prior_source=MANAGER` 값을 받는다. 목록에 없는 팀원은 정렬 영향 없이 설문값만 유지된다.
    - **오류:** `422 PLAYER_NOT_IN_TEAM` — 다른 팀·비활성 참가자 포함. `400 VALIDATION_ERROR` — 중복.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-14, 8.5절, 6.2절 (버전 관리 이유).
    """
    return ranking_service.create(db, team, user, body.player_ids)


@router.get("/teams/{team_id}/rankings", response_model=ItemList[RankingView], responses=errors(_403="FORBIDDEN_ROLE"), summary="정렬 이력 목록")
def list_rankings(db: DB, me: TeamManager, team: Annotated[Team, Depends(get_team_or_404)]):
    """정렬 버전 전체를 최신순으로 돌려준다 (되돌리기·품질 추적용).

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** `manager_rankings(team_id)` 최신순.
    - **오류:** `403 FORBIDDEN_ROLE`, `404 NOT_FOUND`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, 6.2절 "정렬을 덮어쓰지 않고 버전으로 쌓는다".
    """
    return ItemList(items=ranking_service.history(db, team))
