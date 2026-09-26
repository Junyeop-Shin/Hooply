"""시작 안내(튜토리얼) — 홈 체크리스트와 기능별 첫 안내의 상태.

- GET /me/tutorial   상태 + 체크리스트 단계(서버가 실제 데이터로 판정)
- PUT /me/tutorial   상태·경로 변경, 닫은 첫 안내 기록
"""

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.api.v1._docs import errors
from app.schemas.tutorial import TutorialUpdate, TutorialView
from app.services import tutorial_service

router = APIRouter(tags=["시작 안내"])


@router.get("/me/tutorial", response_model=TutorialView, summary="시작 안내 상태와 체크리스트")
def get_tutorial(db: DB, user: CurrentUser):
    """홈 체크리스트 카드가 쓰는 값. 경로(팀원/매니저)를 고르기 전이면 `steps` 는 비어 있다.

    - **권한:** 로그인 사용자.
    - **처리:** 팀원 경로 = 팀 코드로 가입 · 설문 · 내 실력 위치 · 첫 참석 응답. 매니저 경로 = 팀 만들기 · 설문 · 팀원 초대(팀 활성화) ·
      첫 일정 등록. 단계마다 DONE / TODO(링크·버튼 문구) / WAITING(다른 사람의 행동이 먼저 필요, 이유) 를 준다.
      참석 응답은 본인이 직접 한 것만 센다 (매니저 대리 응답 제외).
    - **오류:** `401 TOKEN_EXPIRED`.
    - **상태:** `구현됨`.
    """
    return tutorial_service.view(db, user)


@router.put("/me/tutorial", response_model=TutorialView, responses=errors(_400="VALIDATION_ERROR"), summary="시작 안내 상태 변경")
def put_tutorial(db: DB, user: CurrentUser, body: TutorialUpdate):
    """보낸 값만 바꾼다.

    - `state`: ACTIVE(안내 받기 · 다시 시작) · CLOSED(체크리스트 닫기) · DONE(다 마침) · DECLINED(팝업에서 거절 — 첫 안내도 끈다).
      `state=ACTIVE` 만 보내면 경로 선택부터 다시 시작한다.
    - `path`: PLAYER · MANAGER.
    - `tip_seen`: 닫은 기능별 첫 안내 id (assign · quarters · vote · adopted · records). 다시 뜨지 않는다.
    - **오류:** `400 VALIDATION_ERROR` — 모르는 안내 id. `401 TOKEN_EXPIRED`.
    - **상태:** `구현됨`.
    """
    tutorial_service.update(db, user, body)
    return tutorial_service.view(db, user)
