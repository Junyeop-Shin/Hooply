"""앱 설정 — 환경 변수를 읽어 `Settings` 객체 하나로 모은다.

11.2절 기술 스택의 pydantic-settings를 사용한다. 각 값은 다음 우선순위로 결정된다.

  1. 프로세스 환경 변수            (예: `JWT_SECRET_KEY=...`, 필드명을 대문자로)
  2. backend/.env 파일             (같은 이름. 대소문자 구분 없음)
  3. 아래 클래스에 적힌 기본값     (로컬 개발 편의용. 운영에서는 반드시 덮어쓴다)

`.env`에 우리가 모르는 키가 있어도 무시한다(`extra="ignore"`). 그래서 프론트용 변수를
같은 파일에 두어도 백엔드가 깨지지 않는다.

관련 설계서 절: 7.1절(Base URL·토큰 수명), 11.3절(컨테이너·DB), 11.5절(카카오 로그인),
13.2절 1항(첫 2회 모임 데이터 미반영).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """런타임 설정. 코드에서 직접 만들지 말고 `get_settings()`로 받는다."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- 앱 식별 ---
    # Swagger UI(/docs) 상단 제목으로 쓰인다 (app/main.py `FastAPI(title=...)`).
    # 서비스명이 확정되면(13.1절 Q1) 여기만 바꾸면 된다.
    app_name: str = "HOOPLY — 농구 동호회 팀 매칭 서비스"
    # 모든 라우터 앞에 붙는 경로 (7.1절 Base URL). /health 는 이 prefix 밖에 있다.
    api_prefix: str = "/api/v1"

    # --- 데이터베이스 ---
    # SQLAlchemy 접속 URL. app/db/session.py 의 engine 이 이 값으로 만들어진다.
    # 형식: postgresql+psycopg://<user>:<password>@<host>:<port>/<db>
    # 기본값은 docker-compose 의 db 컨테이너(11.3절) 기준. 운영에서는 DATABASE_URL 로 덮어쓴다.
    database_url: str = "postgresql+psycopg://hoops:hoops@localhost:5432/hoops"

    # --- JWT (7.1절 · security.py) ---
    # 토큰 서명 키. 이 값이 새면 누구나 토큰을 위조할 수 있으므로 운영에서는 반드시
    # 길고 무작위한 값으로 교체한다. 바꾸면 기존에 발급된 토큰은 전부 무효가 된다.
    jwt_secret_key: str = "change-me"
    # 서명 알고리즘. HS256 = 대칭키(HMAC). 서버 한 대가 발급·검증을 모두 하므로 충분하다.
    jwt_algorithm: str = "HS256"
    # access 토큰 수명(분). API 호출마다 Authorization 헤더로 보내는 짧은 토큰.
    jwt_access_minutes: int = 30  # 7.1절: access 30분
    # refresh 토큰 수명(일). access 가 만료되면 POST /auth/refresh 로 재발급받을 때 쓴다.
    jwt_refresh_days: int = 14  # 7.1절: refresh 14일

    # --- 카카오 로그인 (11.5절) ---
    # 카카오 디벨로퍼스 콘솔의 [앱 키] → REST API 키. 인가 URL의 client_id 로 들어간다.
    kakao_client_id: str = ""
    # [카카오 로그인] → [보안] 에서 발급하는 Client Secret. 토큰 교환 시 함께 보낸다 (선택 설정).
    kakao_client_secret: str = ""
    # 콘솔에 등록한 Redirect URI 와 글자 단위로 같아야 한다.
    # 개발 중에는 localhost 주소를 등록해 테스트한다. 비어 있으면 카카오 경로는 동작하지 않는다.
    kakao_redirect_uri: str = ""

    # --- CORS ---
    # 브라우저에서 API 를 호출할 수 있는 프론트 주소 목록 (app/main.py CORSMiddleware).
    # 기본값은 Vite 개발 서버. 배포 시 Vercel 도메인을 추가한다.
    # 환경 변수로 줄 때는 JSON 배열 문자열: CORS_ORIGINS='["https://example.com"]'
    cors_origins: list[str] = ["http://localhost:5173"]
    # 사용자에게 보여줄 프론트 주소 — 피어 투표 독려 메시지의 survey_link 등 (피어 투표 설계)
    frontend_base_url: str = "http://localhost:5173"
    # --- 메일 (비밀번호 재설정) --- 키가 없으면 링크를 서버 로그에만 찍는다 (로컬·테스트)
    resend_api_key: str = ""
    mail_from: str = "HOOPLY <onboarding@resend.dev>"
    password_reset_minutes: int = 30
    # 일정의 날짜·시간(event_date, end_time)은 이 시간대의 벽시계 값이다. 컨테이너 로컬(UTC)이 아니라 이걸로 해석한다
    timezone: str = "Asia/Seoul"
    # 팀 생성 후 관리자 승인이 있어야 활성화되는지. 테스트에서는 끈다 (conftest)
    team_approval_required: bool = True
    # --- 배포 ---
    docs_enabled: bool = True  # 운영에서는 False 로 두면 /docs, /openapi.json 이 닫힌다
    rate_limit_enabled: bool = True  # 로그인·가입·비밀번호 경로 요청 제한 (core/ratelimit.py). 테스트에서는 끈다
    admin_cookie_secure: bool = False  # HTTPS 배포에서는 True (SQLAdmin 세션 쿠키 https_only + same_site=lax)

    # --- AI 설명 (docs/07 D1·D2) --- LangChain 으로 부른다. 키가 없거나 꺼져 있으면 모든 AI 카드가 규칙 문장(폴백)을 보여 준다
    llm_enabled: bool = True
    # init_chat_model 형식 "<공급자>:<모델명>". 다른 모델로 바꿀 때는 이 값·LLM_API_KEY·공급자 패키지(langchain-openai 등)만 바꾼다
    # 기본값은 특정 버전이 아니라 Google 이 최신 Flash 로 유지하는 별칭 — 버전 모델(gemini-2.5-flash 등)은 은퇴하면 404 가 난다
    llm_model: str = "google_genai:gemini-flash-latest"
    llm_api_key: str = ""  # 서버 전용. 비우면 공급자 기본 환경 변수(GOOGLE_API_KEY 등)를 본다
    # 넘으면 폴백 (FR-50). 명세는 8초였지만 Gemini 는 10초 미만 마감을 거절하고(400), 최신 Flash 는 답 전에 생각하는 시간이 있어 15초로
    llm_timeout_seconds: float = 15.0
    llm_rate_per_minute: int = 5  # 사용자당 실제 호출 횟수 (캐시 적중은 세지 않는다)

    # --- 실력 지표 ---
    # 13.2절 1항: 첫 2회 모임 데이터는 실력 지표에 미반영
    # 팀 생성 직후의 노이즈가 설문 사전값을 망치지 않도록, 팀의 처음 N회 모임(events)은
    # 쿼터 기록만 저장하고 잔차 갱신(9.2절)에는 넣지 않는다. 잊지 않도록 상수로 뽑아둔 것.
    rating_warmup_events: int = 2

    # 월간 코트 마진 랭킹에 오르려면 그 달 팀이 뛴 전체 쿼터의 이 비율 이상 출전해야 한다 (기록 탭).
    # 절대 횟수 대신 비율로 두어 한 달에 2회 모인 달과 5회 모인 달의 기준이 자동으로 달라진다.
    margin_rank_min_share: float = 0.30


@lru_cache
def get_settings() -> Settings:
    """설정 싱글턴. 첫 호출에서 .env 를 읽고 이후에는 캐시된 객체를 돌려준다.

    테스트에서 값을 바꾸고 싶으면 `get_settings.cache_clear()` 후 환경 변수를 바꾸고 다시 부른다.
    """
    return Settings()


def db_host_for_log() -> str:
    """로그용 DB 호스트 (비밀번호 제외). 배포 환경에서 DATABASE_URL 이 전달됐는지 바로 확인하려는 용도."""
    from urllib.parse import urlsplit

    try:
        url = get_settings().database_url
        u = urlsplit(url)
        if not u.hostname or "@" in u.path:
            # 호스트를 못 읽으면 형식 오류. 경로에 자격증명이 섞여 있을 수 있으니 절대 출력하지 않는다
            return "(형식 오류 — 'postgresql+psycopg://' 처럼 스킴 뒤에 '://' 가 있는지 확인)"
        db = u.path.lstrip("/").split("?")[0]
        return f"{u.hostname}:{u.port or 5432}/{db}"
    except Exception:  # noqa: BLE001 — 로그용이라 어떤 오류도 삼킨다
        return "(파싱 실패)"
