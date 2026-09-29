"""팀이 직접 만든 전술 · AI 역할 태깅 · 전술 댓글 (docs/07 FR-57 ~ FR-60, 8.3절).

- GET    /teams/{team_id}/plays                               팀 전술 목록 (팀원)
- POST   /teams/{team_id}/plays                               만들기 (팀원, v1.7)
- POST   /teams/{team_id}/plays:check                         재생 가능성 검사 + 규칙 역할 추출, 저장 안 함 (팀원)
- POST   /teams/{team_id}/plays:ai-roles                      AI 역할 태깅 — LangChain 체인 D (팀원)
- GET    /teams/{team_id}/plays/{play_id}                     보기 (팀원)
- PUT    /teams/{team_id}/plays/{play_id}                     고치기 (만든 사람 · 매니저)
- DELETE /teams/{team_id}/plays/{play_id}                     지우기 — 그 전술의 자리 배치·댓글·별표도 (만든 사람 · 매니저)
- GET    /teams/{team_id}/tactics/stars                       별표한 전술 (팀원)
- PUT    /teams/{team_id}/tactics/{play_key}/star             별표 달기 (매니저)
- DELETE /teams/{team_id}/tactics/{play_key}/star             별표 떼기 (매니저)
- GET    /teams/{team_id}/tactics/{play_key}/comments         전술 댓글 (팀원)
- POST   /teams/{team_id}/tactics/{play_key}/comments         댓글 쓰기 (팀원)
- DELETE /teams/{team_id}/tactic-comments/{comment_id}        댓글 지우기 (쓴 사람 · 매니저)
"""

from fastapi import APIRouter, status

from app.api.deps import DB, CurrentUser, TeamManager, TeamMember
from app.api.v1._docs import errors
from app.schemas.tactic import (
    PlayCheck,
    RoleSuggestion,
    TacticCommentIn,
    TacticCommentList,
    TacticCommentView,
    TacticStars,
    TeamPlayIn,
    TeamPlayList,
    TeamPlayView,
)
from app.services import team_play_service as svc

router = APIRouter(tags=["전술"])


@router.get("/teams/{team_id}/plays", response_model=TeamPlayList, responses=errors(_403="NOT_A_MEMBER", _404="NOT_FOUND"), summary="팀 전술 목록")
def list_plays(db: DB, me: TeamMember, team_id: int):
    """그 팀이 직접 만든 전술 (만든 순서). 프리셋과 같은 `Play` 모양이라 전술판에서 그대로 재생된다.

    - **권한:** 팀원 · ADMIN. `can_edit` 는 매니저만 true.
    - **상태:** `구현됨`. **설계서:** docs/07 FR-57.
    """
    return svc.list_plays(db, team_id, me)


@router.post(
    "/teams/{team_id}/plays", response_model=TeamPlayView, status_code=status.HTTP_201_CREATED,
    responses=errors(_400="VALIDATION_ERROR", _403="NOT_A_MEMBER", _422="PLAY_NOT_PLAYABLE"), summary="팀 전술 만들기",
)
def create_play(db: DB, user: CurrentUser, me: TeamMember, team_id: int, body: TeamPlayIn):
    """편집기에서 그린 전술을 저장한다. `roles` 를 비우면 규칙으로 뽑은 역할을 쓴다.

    - **권한:** 팀원 · ADMIN (v1.7 — 매니저만이 아니다). 고치기 · 지우기는 만든 사람과 매니저.
    - **검사:** 이름 · 한 단계 이상(400), 재생 가능성(FR-41) — 어긋나면 `422 PLAY_NOT_PLAYABLE` 과 `details[]` 에 "N단계: …".
    - **상태:** `구현됨`. **설계서:** docs/07 FR-57 · FR-58.
    """
    return svc.create(db, team_id, body, user, me)


@router.post("/teams/{team_id}/plays:check", response_model=PlayCheck, responses=errors(_400="VALIDATION_ERROR", _403="NOT_A_MEMBER"), summary="전술 검사 · 역할 자동 추출")
def check_play(me: TeamMember, team_id: int, body: TeamPlayIn):
    """저장하지 않고 재생 가능성 검사 결과와 규칙으로 뽑은 역할(자리마다 이유 한 줄)을 돌려준다. 편집기가 그릴 때마다 부른다.

    - **권한:** 팀원 · ADMIN.
    - **상태:** `구현됨`. **설계서:** docs/07 FR-58.
    """
    return svc.check(body)


@router.post(
    "/teams/{team_id}/plays:ai-roles", response_model=RoleSuggestion,
    responses=errors(_400="VALIDATION_ERROR", _403="NOT_A_MEMBER", _422="PLAY_NOT_PLAYABLE", _429="RATE_LIMITED"),
    summary="AI 역할 태깅",
)
def ai_roles(db: DB, user: CurrentUser, me: TeamMember, team_id: int, body: TeamPlayIn):
    """직접 그린 전술의 자리마다 역할을 AI 가 붙인다 (LangChain · 체인 D). 선수 정보는 보내지 않고 전술 모양(자리 이름 · 동작)만 보낸다.

    - **권한:** 팀원 · ADMIN. 사용자당 분당 10회.
    - **처리:** 규칙 추출 결과를 힌트로 함께 보낸다. 역할이 7개 밖이거나 자리가 빠지면 버리고 규칙 결과(`fallback=true`).
    - **상태:** `구현됨`. **설계서:** docs/07 FR-59.
    """
    return svc.ai_roles(db, body, user)


@router.get("/teams/{team_id}/plays/{play_id}", response_model=TeamPlayView, responses=errors(_403="NOT_A_MEMBER", _404="NOT_FOUND"), summary="팀 전술 보기")
def get_play(db: DB, me: TeamMember, team_id: int, play_id: int):
    """- **권한:** 팀원 · ADMIN. - **상태:** `구현됨`."""
    return svc.get(db, team_id, play_id, me)


@router.put(
    "/teams/{team_id}/plays/{play_id}", response_model=TeamPlayView,
    responses=errors(_400="VALIDATION_ERROR", _403=("NOT_A_MEMBER", "FORBIDDEN_ROLE"), _404="NOT_FOUND", _422="PLAY_NOT_PLAYABLE"), summary="팀 전술 고치기",
)
def update_play(db: DB, user: CurrentUser, me: TeamMember, team_id: int, play_id: int, body: TeamPlayIn):
    """통째로 바꿔 저장한다. 역할이 바뀌면 일정마다 저장해 둔 이 전술의 자리 배치를 지운다(다시 자동 추천).

    - **권한:** 만든 사람 · 매니저 · ADMIN (그 밖은 403 FORBIDDEN_ROLE). - **상태:** `구현됨`.
    """
    return svc.update(db, team_id, play_id, body, user, me)


@router.delete("/teams/{team_id}/plays/{play_id}", status_code=status.HTTP_204_NO_CONTENT, responses=errors(_403=("NOT_A_MEMBER", "FORBIDDEN_ROLE"), _404="NOT_FOUND"), summary="팀 전술 지우기")
def delete_play(db: DB, me: TeamMember, team_id: int, play_id: int):
    """그 전술의 자리 배치 · 댓글 · 별표도 함께 지운다. - **권한:** 만든 사람 · 매니저 · ADMIN. - **상태:** `구현됨`."""
    svc.remove(db, team_id, play_id, me)


@router.get("/teams/{team_id}/tactics/{play_key}/comments", response_model=TacticCommentList, responses=errors(_403="NOT_A_MEMBER", _404="NOT_FOUND"), summary="전술 댓글")
def list_comments(db: DB, me: TeamMember, team_id: int, play_key: str):
    """팀 안에서 전술 하나(프리셋 `preset:<key>` 또는 팀 전술 `team:<id>`)에 달린 댓글, 오래된 순.

    - **권한:** 팀원 · ADMIN. - **상태:** `구현됨`. **설계서:** docs/07 FR-60.
    """
    return svc.comments(db, team_id, play_key, me)


@router.post(
    "/teams/{team_id}/tactics/{play_key}/comments", response_model=TacticCommentView, status_code=status.HTTP_201_CREATED,
    responses=errors(_400="VALIDATION_ERROR", _403="NOT_A_MEMBER", _404="NOT_FOUND", _429="RATE_LIMITED"), summary="전술 댓글 쓰기",
)
def add_comment(db: DB, me: TeamMember, team_id: int, play_key: str, body: TacticCommentIn):
    """- **권한:** 활성 팀원 (팀원이 아닌 ADMIN 은 403). 사람당 분당 10개. 500자까지. - **상태:** `구현됨`."""
    return svc.add_comment(db, team_id, play_key, body.body, me)


@router.delete(
    "/teams/{team_id}/tactic-comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT,
    responses=errors(_403=("NOT_A_MEMBER", "FORBIDDEN_ROLE"), _404="NOT_FOUND"), summary="전술 댓글 지우기",
)
def delete_comment(db: DB, me: TeamMember, team_id: int, comment_id: int):
    """- **권한:** 쓴 사람 · 매니저 · ADMIN. - **상태:** `구현됨`."""
    svc.delete_comment(db, team_id, comment_id, me)


@router.get("/teams/{team_id}/tactics/stars", response_model=TacticStars, responses=errors(_403="NOT_A_MEMBER"), summary="별표한 전술")
def list_stars(db: DB, me: TeamMember, team_id: int):
    """매니저가 별표한 전술의 `play_key` (별표한 순서). 전술 탭은 이 전술들을 맨 위 "별표 전술"에 모은다.

    - **권한:** 팀원 · ADMIN. `can_edit` 는 매니저만 true. - **상태:** `구현됨`. **설계서:** docs/07 FR-61.
    """
    return svc.stars(db, team_id, me)


@router.put("/teams/{team_id}/tactics/{play_key}/star", response_model=TacticStars, responses=errors(_403=("NOT_A_MEMBER", "FORBIDDEN_ROLE"), _404="NOT_FOUND"), summary="별표 달기")
def add_star(db: DB, user: CurrentUser, me: TeamManager, team_id: int, play_key: str):
    """기본 전술(`preset:<key>`) · 팀 전술(`team:<id>`) 모두. 이미 달려 있으면 그대로. - **권한:** 매니저 · ADMIN."""
    return svc.set_star(db, team_id, play_key, True, user, me)


@router.delete("/teams/{team_id}/tactics/{play_key}/star", response_model=TacticStars, responses=errors(_403=("NOT_A_MEMBER", "FORBIDDEN_ROLE"), _404="NOT_FOUND"), summary="별표 떼기")
def remove_star(db: DB, user: CurrentUser, me: TeamManager, team_id: int, play_key: str):
    """- **권한:** 매니저 · ADMIN."""
    return svc.set_star(db, team_id, play_key, False, user, me)
