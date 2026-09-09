"""FastAPI 앱 팩토리 — 라우터·CORS·에러 핸들러 조립과 OpenAPI 메타데이터 (7.1절 공통 규약)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers

APP_DESCRIPTION = """\
농구 동호회 팀 매칭 서비스 백엔드 — 설계서 v0.3 **7장 API 명세**의 구현입니다.

### 공통 규약 (7.1절)
- **Base URL:** `/api/v1` (아래 경로는 모두 이 접두사 뒤에 붙습니다. `/health`만 예외)
- **인증:** `Authorization: Bearer <access_token>` — JWT, access 30분 / refresh 14일.
  `POST /auth/login` 또는 `POST /auth/signup`으로 발급받고, 만료되면 `POST /auth/refresh`로 갱신합니다.
  Swagger UI에서는 우측 상단 **Authorize** 버튼에 access 토큰을 넣으면 됩니다.
- **본문:** `application/json`, 필드명은 `snake_case`.
- **목록 응답:** `{ "items": [...] }` 또는 페이징 시 `{ "items": [...], "meta": { page, size, total, has_next } }`.

### 오류 응답 (7.4절)
모든 4xx/5xx는 같은 형태입니다.

```json
{ "code": "NOT_ENOUGH_PLAYERS", "message": "팀을 만들기에 참석 인원이 부족합니다.", "details": [] }
```

- 형식 오류 `400` · 인증 `401` · 권한 `403` · 없음 `404` · 상태 충돌 `409` · **도메인 규칙 위반 `422`**
- 프론트는 `code`로 분기하고 `message`는 그대로 노출 가능한 한국어 문구입니다.
- 배정 제약 오류(`422 LOCK_*`, `CONSTRAINT_CONFLICT` 등)는 `details[]`에 어떤 그룹·선수가 문제인지 담습니다.

### 구현 상태
- 각 엔드포인트 설명의 **상태** 항목이 `구현됨` / `스켈레톤`을 표시합니다.
- **`501 NOT_IMPLEMENTED`** 응답은 명세만 잡혀 있고 아직 로직이 없는 스켈레톤 엔드포인트입니다.
  요청·응답 스키마와 권한 검사는 이미 동작하므로 프론트 타입 생성(openapi-typescript)에는 그대로 쓸 수 있습니다.

### 권한 (3장)
- **ADMIN** — 전역 권한 (`users.global_role`). 모든 팀에 매니저처럼 접근합니다.
- **MANAGER / PLAYER** — 팀 단위 권한 (`players.role`). 한 사람이 팀마다 다른 역할을 가질 수 있습니다.
- **게스트** — 계정이 없으므로 API를 호출하지 않습니다. 매니저가 대신 등록하며, 기록·배정·투표의 *대상*만 됩니다.
"""

OPENAPI_TAGS = [
    {
        "name": "인증 · 프로필",
        "description": (
            "이메일/카카오 회원가입·로그인, JWT 갱신, 비밀번호 재설정, 내 정보와 소속 팀 목록. "
            "비밀번호는 bcrypt 단방향 해시로만 저장하고, `users.email`은 NULL 허용(카카오 계정에 이메일이 "
            "없을 수 있음). — FR-01 · FR-02, 11.5절"
        ),
    },
    {
        "name": "온보딩 설문",
        "description": (
            "가입 직후 14문항 설문(8.3절)으로 초기 실력·가능/선호 포지션 프로필을 만든다. "
            "응답은 클럽 내 z-score로 표준화해 사전 실력값(prior)이 되며, 첫 2~3개월 배정 품질을 책임진다. "
            "— F1, FR-03, 8장"
        ),
    },
    {
        "name": "팀 · 참가자",
        "description": (
            "팀 생성 시 8자리 팀 코드 발급, 코드로 가입, 회원 5명 이상이면 팀 활성화. "
            "팀원 목록 조회(역할에 따라 실력 수치 마스킹), 매니저 권한 부여/회수, 팀원 제외. "
            "— F2 · F3, FR-04 ~ FR-07"
        ),
    },
    {
        "name": "게스트 관리",
        "description": (
            "계정 없는 게스트를 이름(+대략적 실력 등급 1~5, 가능 포지션)만으로 참가자에 추가한다. "
            "재방문 시 기존 레코드를 검색해 기록을 누적하고, 정식 가입하면 회원 계정에 병합(되돌리기 가능). "
            "게스트는 기록·배정·투표의 대상이지만 주체는 아니다. — F13, FR-10 ~ FR-13"
        ),
    },
    {
        "name": "매니저 실력 정렬",
        "description": (
            "매니저가 팀원 카드를 드래그해 실력 순서를 한 번 매기면 그 순위가 사전 실력값에 반영된다 "
            "(설문 0.5 + 순위 0.5). 정렬은 버전으로 쌓아 되돌릴 수 있다. "
            "초기 6개월간 배정 품질을 좌우하는 가장 저렴한 장치. — F14, FR-14, 8.5절"
        ),
    },
    {
        "name": "일정 · 참석",
        "description": (
            "매니저가 일정(날짜·시간·장소·응답 마감)을 등록하면 플레이어가 참석/불참을 응답한다. "
            "게스트 참석은 매니저가 대신 등록. 참석 현황과 포지션 분포·빅맨/핸들러 부족 경고를 제공한다. "
            "— F4, FR-08 · FR-09 · FR-15 · FR-34"
        ),
    },
    {
        "name": "팀 배정",
        "description": (
            "참석 확정자를 실력·포지션·선호 조합 기준으로 나눠 전략 3종(실력 우선/친화도 우선/종합) "
            "후보안을 만든다. 회차별 제약 — 묶기(LOCK)·분리(SEPARATE)·사전 배치(PIN) — 은 Union-Find "
            "슈퍼노드로 축약해 어떤 전략에서도 위반 불가. 12~14명 2팀은 완전 탐색으로 전역 최적을 보장한다. "
            "매니저가 후보안을 수정·확정하면 플레이어에게 공개된다. "
            "— F5 · F6 · F7 · F15 · F16, FR-16 ~ FR-24 · FR-33, 9.5 ~ 9.7절"
        ),
    },
    {
        "name": "경기 기록",
        "description": (
            "쿼터별로 양 팀 출전 5명과 스코어만 입력하면 서버가 출전 10명의 코트 마진을 계산하고 "
            "기대 마진 대비 잔차로 실력 지표를 갱신한다(원시 마진 누적은 쓰지 않음). 쿼터 수는 회차마다 "
            "유동적이며 삭제·수정 시 마진을 롤백한다(팀 전체 재계산). 첫 2회 모임은 지표에 미반영. "
            "로테이션 자동 제안(F17)은 범위에서 제외. — F8 · F10, FR-25 ~ FR-27, 9.1 ~ 9.2절, 13.2절"
        ),
    },
    {
        "name": "경기 후 설문 · 통계",
        "description": (
            "경기 후 같은 팀·상대 팀에서 '오늘 잘한 사람'·'다음에 같이 뛰고 싶은 사람'을 각 2명 뽑는 "
            "피어 투표. 상호 지목은 선호 조합으로 배정에 반영된다(통계적 시너지 주장은 하지 않음). "
            "개인 통계, 나와 잘 맞는 참여자, 팀 리더보드. — F9 · F10 · F11, FR-29 ~ FR-31, 9.4절"
        ),
    },
    {
        "name": "관리자",
        "description": (
            "전역 ADMIN 전용. 전체 사용자 검색, 선수 원시 데이터(설문 원본·쿼터별 마진·투표 수신·지표 변동 "
            "이력) 열람, 실력 지표 수동 보정(감사 로그 기록). 일반 CRUD 화면은 SQLAdmin(/admin)이 대신한다. "
            "— F12, FR-32"
        ),
    },
    {
        "name": "시스템",
        "description": "헬스 체크 등 서비스 상태 확인용 엔드포인트. 인증 불필요, `/api/v1` 접두사 없음.",
    },
]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=APP_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    from app.core.config import db_host_for_log

    print(f"[startup] DB → {db_host_for_log()} · docs={'on' if settings.docs_enabled else 'off'} · cors={settings.cors_origins}")
    from app.admin_ui import mount_admin

    mount_admin(app)  # S-18 관리자 콘솔: /admin (ADMIN 계정만)

    @app.get("/health", tags=["시스템"], summary="헬스 체크")
    def health() -> dict[str, str]:
        """서비스가 살아 있는지 확인한다.

        - **권한:** 누구나 (인증 불필요).
        - **처리:** 항상 `{"status": "ok"}`를 돌려준다. 배포 환경(Railway/Render)의 상태 점검과
          Docker Compose healthcheck에 쓴다. DB 연결은 검사하지 않는다.
        - **오류:** 없음.
        - **상태:** `구현됨`.
        - **설계서:** 11.3절 컨테이너 구성, 11.2절 배포.
        """
        return {"status": "ok"}

    return app


app = create_app()
