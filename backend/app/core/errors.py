import logging

"""7.4절 에러 코드 체계.

형식 오류 400 · 인증 401 · 권한 403 · 없음 404 · 상태 충돌 409 · 도메인 규칙 위반 422.
프론트는 `code`로 분기하고 `message`는 그대로 노출 가능한 한국어 문구로 유지한다.

이 모듈이 하는 일 세 가지:

1. 모든 에러 응답의 공통 본문 형태 `ErrorResponse = {code, message, details[]}` 를 정의한다
   (7.2절 공통 스키마).
2. 설계서 7.4절의 에러 코드 하나하나를 `AppError` 의 서브클래스로 만든다. 서비스/라우터에서는
   `raise errors.TeamCodeNotFound()` 처럼 던지기만 하면 된다. HTTP 상태·코드·기본 문구는
   클래스에 박혀 있다.
3. `install_error_handlers()` 로 FastAPI 에 핸들러를 등록해, 위 예외와 Pydantic 검증 실패를
   모두 같은 JSON 형태로 바꾼다.

사용 예::

    from app.core import errors as E
    raise E.NotEnoughPlayers()                          # 기본 문구
    raise E.NotEnoughPlayers("2팀을 만들려면 최소 10명이 필요해요 (현재 8명)")  # 문구 교체
    raise E.LockGroupTooLarge(details=[ErrorDetail(reason="...", context={"group_no": 1})])
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError

# 409 CONFLICT 로 바꾸는 SQLSTATE — 유니크 위반 · 외래키 위반 · 교착 · 직렬화 실패
_CONFLICT_STATES = {"23505", "23503", "40P01", "40001"}


class ErrorDetail(BaseModel):
    """에러 응답의 세부 항목 하나. `ErrorResponse.details[]` 의 원소.

    - 형식 오류(400 VALIDATION_ERROR)에서는 어떤 필드가 왜 틀렸는지를 담는다.
    - 배정 제약 오류(422 LOCK_* 등)에서는 어떤 그룹·어떤 선수가 문제인지를 담는다.
      "제약을 만족할 수 없습니다"만으로는 매니저가 무엇을 풀어야 할지 모르기 때문 (9.6절, 13.2절 5항).
    """

    field: str | None = None  # 문제가 된 요청 필드 경로. 예: "body.lineups.3.side". 필드 무관이면 None
    reason: str  # 사람이 읽을 수 있는 사유
    context: dict[str, Any] | None = None  # 기계가 쓸 부가 정보. 예: {"group_no": 1, "player_ids": [..]}


class ErrorResponse(BaseModel):
    """모든 4xx/5xx 응답의 본문 (7.2절 `ErrorResponse`).

    Swagger 의 에러 응답 예시에도 이 스키마가 쓰인다 (app/api/v1/_docs 의 `errors()` 헬퍼 참고).
    """

    code: str  # 7.4절 코드. 프론트는 이 값으로 분기한다 (예: "TEAM_CODE_NOT_FOUND")
    message: str  # 그대로 화면에 띄워도 되는 한국어 문구
    details: list[ErrorDetail] = []  # 없으면 빈 배열


class AppError(Exception):
    """서비스 전체에서 쓰는 도메인 예외의 부모.

    클래스 속성 `status_code / code / message` 가 기본값이고, 인스턴스를 만들 때 메시지·details 를
    바꿔 넣을 수 있다. 아래 `_error()` 팩토리가 이 클래스를 상속한 구체 예외들을 찍어낸다.

    직접 `AppError(...)` 를 던지면 400 VALIDATION_ERROR 로 나간다. 보통은 아래에 정의된
    구체 클래스를 쓰고, 정말 일회성 코드가 필요할 때만 `code=` / `status_code=` 를 넘긴다.
    """

    status_code: int = 400
    code: str = "VALIDATION_ERROR"
    message: str = "입력한 내용을 다시 확인해 주세요."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[ErrorDetail] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ):
        # message 만 위치 인자로 받고 나머지는 키워드 전용 — `E.NotFound("팀을 찾을 수 없어요.")`
        # 처럼 문구만 바꾸는 호출이 가장 흔하기 때문.
        self.message = message or self.message
        self.details = details or []
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        super().__init__(self.message)


def _error(status: int, code: str, message: str) -> type[AppError]:
    """에러 클래스 팩토리.

    `type()` 으로 `AppError` 를 상속한 새 클래스를 동적으로 만든다. 클래스 이름은 `code` 와 같게
    두어 traceback 에 `TEAM_CODE_NOT_FOUND` 처럼 찍히게 한다. 아래에 30개 남짓한 코드를 한 줄씩
    선언하기 위한 장치이며, `class TeamCodeNotFound(AppError): status_code = 404 ...` 를 손으로
    쓰는 것과 결과는 같다.

    반환값은 클래스이므로 `TeamCodeNotFound()` 로 인스턴스를 만들어 `raise` 한다.
    """
    return type(code, (AppError,), {"status_code": status, "code": code, "message": message})


# ---------------------------------------------------------------------------
# 400 — 요청 형식·값 자체가 틀림. 프론트가 입력 단계에서 막을 수 있는 종류.
# ---------------------------------------------------------------------------
# Pydantic 검증 실패의 기본 코드. 서비스에서 직접 던질 때는 문구를 바꿔 쓴다
# (예: "게스트에게는 매니저 권한을 줄 수 없어요.")
ValidationError = _error(400, "VALIDATION_ERROR", "입력한 내용을 다시 확인해 주세요.")
# 쿼터 저장 시 한쪽 사이드가 5명이 아님 — S-15 쿼터 기록
InvalidLineupSize = _error(400, "INVALID_LINEUP_SIZE", "쿼터마다 팀당 5명을 골라 주세요.")
# 피어 설문에서 본인을 target 으로 지정 — S-16
SelfVoteNotAllowed = _error(400, "SELF_VOTE_NOT_ALLOWED", "자기 자신은 고를 수 없어요.")
# 비밀번호 재설정 토큰이 없거나·30분 지났거나·이미 사용됨 — POST /auth/password/reset
TokenInvalidOrExpired = _error(400, "TOKEN_INVALID_OR_EXPIRED", "이 링크는 만료되었거나 이미 사용했어요. 다시 요청해 주세요.")

# ---------------------------------------------------------------------------
# 401 — 인증 실패. 로그인 화면으로 보내야 하는 종류.
# ---------------------------------------------------------------------------
# 이메일/비밀번호 불일치 — S-01. 어느 쪽이 틀렸는지는 알려주지 않는다(계정 존재 여부 노출 방지)
InvalidCredentials = _error(401, "INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않아요.")
# access/refresh 토큰이 없거나·만료·위조·type 불일치·탈퇴 계정 — app/api/deps.py get_current_user
TokenExpired = _error(401, "TOKEN_EXPIRED", "로그인이 풀렸어요. 다시 로그인해 주세요.")
# 카카오 인가 코드 → 토큰 교환 또는 사용자 정보 조회 실패, state 불일치 — GET /auth/kakao/callback
KakaoAuthFailed = _error(401, "KAKAO_AUTH_FAILED", "카카오 로그인에 실패했어요.")

# ---------------------------------------------------------------------------
# 403 — 로그인은 됐지만 이 자원에 대한 권한이 없음 (3.3절 권한 매트릭스).
# ---------------------------------------------------------------------------
# PLAYER 가 MANAGER 전용 API 호출, 비 ADMIN 이 /admin 호출 — deps.require_team_manager 등
ForbiddenRole = _error(403, "FORBIDDEN_ROLE", "이 기능은 매니저만 쓸 수 있어요.")
# 소속되지 않은 팀의 자원에 접근 — deps.require_team_member / require_event_member
NotAMember = _error(403, "NOT_A_MEMBER", "내가 속한 팀이 아니에요.")
# 매니저가 제외(REMOVED)한 팀에 팀 코드로 다시 가입 — POST /teams/join. 스스로 나간(LEFT) 사람은 다시 들어올 수 있다
RemovedFromTeam = _error(403, "REMOVED_FROM_TEAM", "매니저가 제외한 팀이에요. 매니저에게 문의해 주세요.")
# 그 일정에 참석하지 않은 사람이 피어 설문 조회 — GET /events/{id}/post-game-survey
NotAttendee = _error(403, "NOT_ATTENDEE", "이 일정에 참석한 사람만 볼 수 있어요.")
# 남이 등록한 게스트를 등록자도 매니저도 아닌 플레이어가 수정·삭제 — 게스트 기능 설계.
# 팀원 제외에서도 쓴다: 팀장이 아닌 매니저가 매니저를 제외하거나, 누가 팀장을 제외하려 할 때 (문구를 바꿔 던진다)
ForbiddenNotOwner = _error(403, "FORBIDDEN_NOT_OWNER", "이 게스트를 등록한 사람만 수정할 수 있어요.")
# 일정 종료 시각 전에 피어 투표 후보 조회·제출 — 피어 투표 설계 (종료 시각이 지나면 자동 오픈)
SurveyNotOpen = _error(403, "SURVEY_NOT_OPEN", "일정이 끝나면 투표할 수 있어요.")

# ---------------------------------------------------------------------------
# 404 — 리소스 없음.
# ---------------------------------------------------------------------------
# 범용. 문구를 바꿔 쓴다 ("팀을 찾을 수 없어요." 등) — deps.get_team_or_404 / get_event_or_404
NotFound = _error(404, "NOT_FOUND", "찾을 수 없어요. 이미 지워졌을 수 있어요.")
# 팀 코드 오타/재발급으로 만료 — S-06 팀 가입 (POST /teams/join)
TeamCodeNotFound = _error(404, "TEAM_CODE_NOT_FOUND", "없는 팀 코드예요. 다시 확인해 주세요.")
# 매니저가 아직 배정을 확정하지 않음 — S-14 플레이어 배정 결과 (GET /events/{id}/assignment/adopted)
NotAdoptedYet = _error(404, "NOT_ADOPTED_YET", "아직 확정된 팀 배정이 없어요.")
# 매니저 실력 정렬(F14)을 한 번도 저장하지 않음 — GET /teams/{id}/rankings/latest
NoRanking = _error(404, "NO_RANKING", "아직 저장된 실력 순서가 없어요.")

# ---------------------------------------------------------------------------
# 409 — 현재 상태와 충돌. "이미 ~했다" 류.
# ---------------------------------------------------------------------------
# 같은 이메일로 재가입 — POST /auth/signup
EmailDuplicated = _error(409, "EMAIL_DUPLICATED", "이미 가입된 이메일이에요.")
# 이미 소속된 팀에 팀 코드로 재가입 — POST /teams/join (프론트는 토스트 후 팀 상세로 이동)
AlreadyMember = _error(409, "ALREADY_MEMBER", "이미 들어가 있는 팀이에요.")
# 온보딩 설문 또는 경기 후 피어 설문을 두 번 제출 — POST /surveys/onboarding/responses, post-game-survey
AlreadySubmitted = _error(409, "ALREADY_SUBMITTED", "이미 제출했어요.")
# 같은 event 에 같은 quarter_no 를 다시 POST — POST /events/{id}/quarters (수정은 PATCH/PUT 사용)
QuarterExists = _error(409, "QUARTER_EXISTS", "이미 기록한 쿼터예요.")
# 한 run 안에서 후보안을 두 번 확정 — POST /assignments/candidates/{id}:adopt
AlreadyAdopted = _error(409, "ALREADY_ADOPTED", "이미 확정한 팀 배정이 있어요.")
# 그 카카오 회원번호가 이미 다른 users 에 연결됨 — POST /auth/kakao/link
IdentityAlreadyLinked = _error(409, "IDENTITY_ALREADY_LINKED", "다른 계정에 이미 연결된 카카오 계정이에요.")
# merged_into_player_id 가 이미 채워진 게스트를 또 병합 — POST /players/{id}:merge
AlreadyMerged = _error(409, "ALREADY_MERGED", "이미 기록을 이어 준 게스트예요.")
# 같은 행을 두 요청이 동시에 만들거나 바꿈 (DB 유니크 위반 · 교착) — 아래 install_error_handlers 가 IntegrityError 에서 바꾼다
Conflict = _error(409, "CONFLICT", "동시에 처리된 요청이 있어요. 다시 시도해 주세요.")

# ---------------------------------------------------------------------------
# 422 — 형식은 맞지만 도메인 규칙에 걸림.
# ---------------------------------------------------------------------------
# 팀원 5명 미만(PENDING)인 팀에서 일정 등록 — POST /teams/{id}/events (FR-06)
TeamNotActive = _error(422, "TEAM_NOT_ACTIVE", "팀 인원이 5명 이상 모이면 일정을 만들 수 있어요.")
# 참석자 < 팀 수 × 5 — 배정 실행/검증 (FR-33). 문구에 현재 인원을 넣어 던지는 것을 권장
NotEnoughPlayers = _error(422, "NOT_ENOUGH_PLAYERS", "팀을 나누기에 참석 인원이 부족해요.")
# rsvp_deadline 이 지난 뒤 본인 참석 응답 — PUT /events/{id}/attendance (FR-09)
RsvpClosed = _error(422, "RSVP_CLOSED", "응답이 마감되었어요.")
# 같은 팀끼리 교체, 후보안에 없는 선수, LOCK 그룹을 깨는 교체 등 — PATCH /assignments/candidates/{id}
InvalidSwap = _error(422, "INVALID_SWAP", "이렇게는 바꿀 수 없어요.")
# 팀의 유일한 MANAGER 를 PLAYER 로 내리려 함 — PATCH /teams/{id}/players/{pid}/role (팀이 관리 불능이 됨)
CannotDemoteLastManager = _error(422, "CANNOT_DEMOTE_LAST_MANAGER", "매니저가 한 명뿐이라 권한을 뺄 수 없어요.")
# 정렬·제약 등에 다른 팀의 player_id 가 섞임 — POST /teams/{id}/rankings 등
PlayerNotInTeam = _error(422, "PLAYER_NOT_IN_TEAM", "이 팀에 없는 사람이 섞여 있어요.")
# 전술 자리 배치에 그날 그 팀(블랙/화이트/레드)이 아닌 선수를 앉힘 — PUT /events/{id}/tactics/{play_key}/slots
PlayerNotInSquad = _error(422, "PLAYER_NOT_IN_SQUAD", "이 팀에 배정되지 않은 사람이 섞여 있어요.")
# 쿼터 기록이 있는 일정에서 배정 실행 · 확정 · 수정 — 기록이 그날 편성을 근거로 하므로 (POST /events/{id}/assignments 등)
AssignmentLocked = _error(422, "ASSIGNMENT_LOCKED", "경기 기록이 있는 일정은 팀을 다시 짤 수 없어요. 쿼터 기록을 먼저 지워 주세요.")
# 직접 만든 전술이 재생 가능성 검사(docs/07 FR-41)를 통과하지 못함 — details[] 에 "N단계: …" 문장
PlayNotPlayable = _error(422, "PLAY_NOT_PLAYABLE", "이대로는 전술판에서 재생할 수 없어요.")
# 병합 방향이 게스트 → 회원이 아님 (회원끼리, 게스트끼리 등) — POST /players/{id}:merge
MergeKindMismatch = _error(422, "MERGE_KIND_MISMATCH", "게스트 기록만 팀원에게 이어 줄 수 있어요.")

# --- 422 배정 제약 실현 불가 (9.6절 사전 실현가능성 검사) ---
# 이 그룹은 details[] 에 어떤 group_no·player_ids 가 문제인지 반드시 담는다.
# LOCK 그룹 인원 > 팀 정원 (예: 7명을 묶었는데 팀당 6명)
LockGroupTooLarge = _error(422, "LOCK_GROUP_TOO_LARGE", "묶은 인원이 한 팀 정원보다 많아요.")
# 같은 페어가 LOCK 과 SEPARATE 에 동시 지정, 또는 같은 LOCK 그룹의 두 사람이 서로 다른 팀에 PIN
ConstraintConflict = _error(422, "CONSTRAINT_CONFLICT", "서로 어긋나는 조건이 있어요.")
# SEPARATE 그래프를 팀 수(T)개의 색으로 칠할 수 없음 (예: 2팀인데 3명을 전부 갈라놓기)
SeparateInfeasible = _error(422, "SEPARATE_INFEASIBLE", "갈라놓기 조건을 지킬 수 있는 팀 구성이 없어요.")
# 슈퍼노드 크기 조합으로 각 팀 정원을 정확히 채우는 부분합이 없음 ("4명 그룹과 5명 그룹으로 6명씩 두 팀 불가")
LockPartitionInfeasible = _error(422, "LOCK_PARTITION_INFEASIBLE", "지금 묶음으로는 두 팀 인원을 맞출 수 없어요.")
# 한 팀 칸에 PIN 된 인원 > 정원 — S-12 에서는 드롭 자체를 거부하지만 API 도 막는다
SquadOverflow = _error(422, "SQUAD_OVERFLOW", "팀 정원을 넘겨 배치할 수 없어요.")

# ---------------------------------------------------------------------------
# 429 / 500
# ---------------------------------------------------------------------------
# 과다 요청 — app/core/ratelimit.check 가 던진다 (로그인 · 비밀번호 찾기 · AI 호출 · 전술 댓글 등)
RateLimited = _error(429, "RATE_LIMITED", "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.")
# 예상 못한 서버 오류. 실제 스택은 로그에만 남기고 클라이언트에는 이 문구만
InternalError = _error(500, "INTERNAL_ERROR", "문제가 생겼어요. 잠시 후 다시 시도해 주세요.")


def install_error_handlers(app: FastAPI) -> None:
    """FastAPI 앱에 예외 → `ErrorResponse` JSON 변환 핸들러를 등록한다 (app/main.py 에서 1회 호출).

    - `AppError` (및 모든 서브클래스): 예외에 박힌 status_code / code / message / details 를 그대로
      JSON 으로 내보낸다.
    - `RequestValidationError` (Pydantic 요청 검증 실패): FastAPI 기본은 422 + 자체 형식이지만,
      7.4절 원칙("형식 오류는 400")에 맞춰 400 VALIDATION_ERROR 로 바꾸고, 각 오류의 위치
      (`loc`)를 "body.email" 같은 점 표기로 `details[].field` 에 넣는다.

    이렇게 해야 프론트가 모든 에러를 `{code, message, details}` 하나의 형태로 처리할 수 있다.
    """

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        body = ErrorResponse(code=exc.code, message=exc.message, details=exc.details)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(DBAPIError)
    async def _db_error(request: Request, exc: DBAPIError) -> JSONResponse:
        # 검사 → 저장 사이에 다른 요청이 같은 행을 먼저 만든 경우(유니크 위반)나 교착이 500 으로 새지 않게.
        # 세션 롤백은 get_db 가 한다 (app/db/session.py)
        state = getattr(exc.orig, "sqlstate", None)
        if state == "23514":  # CHECK 위반 — 스키마 검증을 빠져나온 값
            err: AppError = ValidationError()
        elif state in _CONFLICT_STATES:
            err = Conflict()
        else:
            return await _unexpected(request, exc)
        logging.getLogger("hooply").warning("DB 충돌 %s %s: %s %s", request.method, request.url.path, state, type(exc.orig).__name__)
        body = ErrorResponse(code=err.code, message=err.message, details=[])
        return JSONResponse(status_code=err.status_code, content=body.model_dump())

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # 예상 못한 예외는 스택을 로그에 남기고 클라이언트에는 고정 문구만 (스택·SQL 이 새지 않게)
        logging.getLogger("hooply").exception("처리되지 않은 오류: %s %s", request.method, request.url.path)
        body = ErrorResponse(code="INTERNAL_ERROR", message=InternalError.message, details=[])
        return JSONResponse(status_code=500, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # exc.errors() 원소 예: {"loc": ("body", "password"), "msg": "String should have at least 8 characters", ...}
        details = [
            ErrorDetail(field=".".join(str(p) for p in e.get("loc", [])), reason=e.get("msg", ""))
            for e in exc.errors()
        ]
        body = ErrorResponse(code="VALIDATION_ERROR", message="입력한 내용을 다시 확인해 주세요.", details=details)
        return JSONResponse(status_code=400, content=body.model_dump())
