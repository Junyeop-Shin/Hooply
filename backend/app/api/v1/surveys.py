"""7.3절 온보딩 설문 — 설문 템플릿 조회·응답 제출, 내 실력/포지션 프로필 (F1, 설문 설계).

설계서: 7.3절 온보딩 설문, FR-03, 8장 (8.3절 14문항, 8.4절 prior 변환), 스펙 5절 z-score 규칙.

엔드포인트
- GET  /surveys/onboarding           활성 설문 템플릿 조회 (구현됨)
- POST /surveys/onboarding/responses 설문 응답 제출 → prior 계산 (구현됨)
- GET  /me/profile                   내 실력·포지션 프로필 (구현됨)
- PUT  /me/positions                 가능/선호 포지션 수정 (구현됨)
- PUT  /teams/{team_id}/self-rank    팀 가입 후 "이 동호회에서 내 실력 위치" 응답 (구현됨)
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, TeamMember, get_team_or_404
from app.api.v1._docs import errors
from app.models import Player, PlayerPosition, Team
from app.models.enums import PlayerStatus
from app.schemas.survey import (
    MyProfile,
    PositionsUpdate,
    SelfRankIn,
    SurveyResponseIn,
    SurveyTemplateView,
)
from app.services import survey_service

router = APIRouter(tags=["온보딩 설문"])


@router.get("/surveys/onboarding", response_model=SurveyTemplateView, summary="온보딩 설문 템플릿 조회")
def get_onboarding_survey(db: DB):
    """현재 활성화된 온보딩 설문의 문항·선택지를 돌려준다.

    - **권한:** 누구나 (인증 불필요).
    - **처리:** `survey_templates.is_active=true`인 버전을 문항(`display_order` 순)·선택지
      (`option_order` 순)와 함께 돌려준다. 8.3절 14문항이며 D3(희소 자원)은 D3A·D3B 두 행으로 내려가고
      `group_label`이 같으므로 프론트가 한 화면에 묶는다. `answer_type`으로 위젯을 고른다.
    - **오류:** `404 NOT_FOUND` — 활성 템플릿 없음 (`alembic upgrade head` 전).
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, 8.2절 척도, 8.3절 문항, 8.6절 버전 관리, 스펙 3~4절, S-03.
    """
    tpl = survey_service.get_active_template(db)
    return SurveyTemplateView(template_id=tpl.id, version=tpl.version, name=tpl.name, questions=tpl.questions)


@router.post(
    "/surveys/onboarding/responses", status_code=201, response_model=MyProfile,
    responses=errors(_400="VALIDATION_ERROR", _409="ALREADY_SUBMITTED"), summary="온보딩 설문 응답 제출",
)
def submit_onboarding_survey(db: DB, user: CurrentUser, body: SurveyResponseIn):
    """설문 응답을 저장하고 초기 실력·포지션 프로필을 만든다. 1인 1회.

    - **권한:** 로그인 사용자.
    - **처리:** 15개 문항 전부 응답했는지, 유형별 형식(STEPPER는 숫자만, MULTI_CHIP은 1개 이상,
      나머지는 정확히 1개)이 맞는지 검사한다. 저장 후 `users.onboarding_completed=true`, A1(키)을
      `users.height_cm`에 반영한다. 이미 소속된 팀이 있으면 D1~D3로 `player_positions`를 채우고 팀별
      `prior_overall`을 재계산한다 (스펙 5절: 팀 내 응답자 5명 이상일 때 z-score, 미만이면 0).
      아직 팀이 없으면 응답만 저장되고, 팀에 가입하는 순간 같은 계산이 돌아간다.
    - **오류:** `409 ALREADY_SUBMITTED` — 재제출. `400 VALIDATION_ERROR` — 누락·형식 (`details[]`에 문항 코드).
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-03, F1, 8.4절, 스펙 5절 · 7절, 6.2절 `player_profiles`.
    """
    survey_service.submit(db, user, body)
    return survey_service.my_profile(db, user)


@router.get("/me/profile", response_model=MyProfile, summary="내 실력·포지션 프로필")
def my_profile(db: DB, user: CurrentUser):
    """설문 완료 여부, 포지션, 소속 팀별 실력 등급을 돌려준다.

    - **권한:** 로그인 사용자.
    - **처리:** 설문 제출 시각·키·가능/선호 포지션과, 소속된 팀마다 `skill_grade`(A~E, 수치 아님)·
      `prior_source`·`survey_sample_size`(그 팀 응답자 수)를 돌려준다. 팀이 없으면 `teams=[]`.
    - **오류:** 없음.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`GET /me/profile`), FR-28 (등급만 표시), 13.2절 4항 (players는 팀 단위), S-17.
    """
    return survey_service.my_profile(db, user)


@router.put("/me/positions", response_model=MyProfile, summary="가능/선호 포지션 수정")
def update_positions(db: DB, user: CurrentUser, body: PositionsUpdate):
    """가능 포지션·선호 순위·자기 평가를 통째로 교체한다. 소속된 모든 팀에 같은 값을 적용한다.

    - **권한:** 로그인 사용자.
    - **처리:** 내 활성 `players` 행 각각의 `player_positions`를 본문 목록으로 전량 교체한다.
      목록 순서를 그대로 선호 순서로 쓴다 (`preference_rank`를 안 보내면 1, 2, 3…).
      1번(PG)·5번(C) 가능 여부는 배정의 하드 제약 입력이므로 다음 배정부터 반영된다.
    - **오류:** `400 VALIDATION_ERROR` — 중복 포지션·5개 초과.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`PUT /me/positions`), 6.2절 `player_positions`, 9.5절 5단계 하드 제약.
    """
    seen = set()
    for p in body.positions:
        if p.position in seen:
            from app.core import errors as E

            raise E.ValidationError(f"{p.position} 포지션을 두 번 골랐어요.")
        seen.add(p.position)
    user.position_prefs = [p.position.value for p in body.positions]  # 팀이 없어도 저장되는 원본
    players = db.scalars(select(Player).where(Player.user_id == user.id, Player.status == PlayerStatus.ACTIVE)).all()
    for pl in players:
        for old in list(pl.positions):
            db.delete(old)
        db.flush()  # 같은 flush 안에서는 INSERT 가 DELETE 보다 먼저 나가 UNIQUE(player_id, position) 에 걸린다
        pl.positions = [
            PlayerPosition(
                player_id=pl.id, position=p.position, can_play=p.can_play,
                preference_rank=p.preference_rank if p.preference_rank is not None else i + 1,
                self_rating=p.self_rating,
            )
            for i, p in enumerate(body.positions)
        ]
    db.commit()
    return survey_service.my_profile(db, user)


@router.put(
    "/teams/{team_id}/self-rank", response_model=MyProfile,
    responses=errors(_403="NOT_A_MEMBER"), summary="이 동호회에서 내 실력 위치 응답",
)
def set_self_rank(db: DB, user: CurrentUser, me: TeamMember, team: Annotated[Team, Depends(get_team_or_404)], body: SelfRankIn):
    """팀 가입 직후 "이 동호회에서 본인의 실력 위치"(상위 10% … 하위 10%)를 답한다.

    - **권한:** 그 팀의 팀원 본인.
    - **처리:** `player_profiles.self_rank_level`에 저장하고 팀의 prior를 재계산한다. 온보딩 설문의
      다른 응답과 합쳐져 가중치 0.30(가장 큰 성분)으로 들어간다. 팀마다 따로 답하며 언제든 바꿀 수 있다.
    - **오류:** `403 NOT_A_MEMBER`, `404 NOT_FOUND`.
    - **상태:** `구현됨`.
    - **설계서:** 8.3절 E3 ("단일 최고 정보량 문항"), 8.4절 가중치 0.30. 팀을 알아야 답할 수 있어 설문 v2 에서 분리.
    """
    player = db.get(Player, me.id) if me.id else None
    if player is None:
        from app.core import errors as E

        raise E.NotAMember()
    survey_service.set_self_rank(db, player, body.level)
    return survey_service.my_profile(db, user)
