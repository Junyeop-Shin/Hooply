"""pytest 공통 픽스처 (설계서 11.2절 "pytest + httpx" · 13.4절 검증 방법).

테스트는 docker compose의 Postgres(hoops DB)를 그대로 사용한다. 각 테스트 전후로 테이블을 비운다.

왜 SQLite나 별도 테스트 DB를 쓰지 않는가:
- 스키마가 JSONB, 부분 유니크 인덱스, CHECK 제약 등 PostgreSQL 전용 기능을 쓴다 (6장).
  SQLite로 바꿔치기하면 제약 위반이 테스트에서 잡히지 않는다.
- 접속 정보는 앱과 같은 `Settings.database_url`을 쓴다. 즉 **테스트는 개발 DB를 비운다.**
  테이블은 `alembic upgrade head`로 미리 만들어져 있어야 한다 (테스트가 스키마를 만들지
  않는다).

이 파일의 픽스처는 모든 테스트 모듈에서 인자 이름만으로 주입된다.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.db.survey_seed import seed_active_survey
from app.main import app
from app.models import Base

# 설문 문항은 시드 데이터(참조 데이터)라 테스트 사이에 지우지 않는다. 응답 테이블은 지운다.
_REFERENCE_TABLES = {"survey_templates", "survey_questions", "survey_options"}


@pytest.fixture(autouse=True, scope="session")
def approval_off():
    """테스트 기본값: 팀 승인 절차를 끈다. 승인 흐름 자체는 test_admin_leaderboard 가 켜서 검증한다."""
    from app.core.config import get_settings

    get_settings().team_approval_required = False
    get_settings().rate_limit_enabled = False  # 픽스처가 가입·로그인을 수십 번 부른다. 제한 자체는 test_account_security 가 켜서 검증
    yield


@pytest.fixture(autouse=True)
def clean_db():
    """모든 테스트가 끝난 뒤 전 테이블을 비운다 (autouse → 명시 안 해도 적용).

    `yield` 앞에 아무것도 없으므로 테스트 **후**에만 정리한다. 실패한 테스트가 남긴
    데이터가 다음 테스트로 새지 않게 하려는 것이며, 테스트 간 순서 의존을 없앤다.

    - `Base.metadata.sorted_tables`는 FK 의존성 순서(부모→자식)로 정렬된 목록이다.
      `TRUNCATE ... CASCADE`라 순서가 필수는 아니지만, 역순으로 나열해 두면 의도가 분명하다.
    - `RESTART IDENTITY`: BIGSERIAL 시퀀스를 1부터 다시 시작한다. 테스트가 id 값을
      가정하지는 않지만, 디버깅할 때 id가 매번 같으면 읽기 편하다.
    - 앱의 세션이 아니라 `engine.begin()`으로 별도 커넥션을 열어 실행한다. 앱 세션이
      열어 둔 트랜잭션과 섞이지 않게 하기 위함이다.
    """
    yield
    tables = ", ".join(
        t.name for t in reversed(Base.metadata.sorted_tables) if t.name not in _REFERENCE_TABLES
    )
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        seed_active_survey(conn)  # 혹시 지워졌더라도 활성 설문(최신 버전)이 항상 있게 보장


@pytest.fixture
def client():
    """FastAPI 앱을 인프로세스로 호출하는 HTTP 클라이언트.

    실제 서버를 띄우지 않고 라우터 → 의존성 → 서비스 → DB까지 전 경로를 탄다.
    에러 핸들러(7.4절 `{code, message, details}` 형태)도 그대로 적용되므로,
    테스트는 `r.json()["code"]`로 에러 코드를 검증할 수 있다.
    """
    return TestClient(app)


@pytest.fixture
def signup(client):
    """회원가입을 수행하고 인증 헤더를 돌려주는 팩토리 픽스처.

    사용법: `headers = signup("owner@example.com", name="매니저")` → 이후 요청의
    `headers=`에 그대로 넘긴다. 한 테스트에서 여러 사용자를 만들 때 이메일만 바꿔 반복
    호출한다 (이메일은 UNIQUE라 같은 값으로 두 번 부르면 409가 나고 assert에 걸린다).

    가입 성공(201)까지를 이 안에서 검증하므로, 이 픽스처를 쓰는 테스트가 실패하면
    가입 자체가 깨진 것인지 그 다음 단계가 깨진 것인지 메시지(`r.text`)로 구분할 수 있다.
    """

    def _signup(email="a@example.com", name="최준용", password="password123"):
        r = client.post("/api/v1/auth/signup", json={"email": email, "password": password, "name": name})
        assert r.status_code == 201, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _signup
