"""DB 엔진·세션 팩토리와 FastAPI 의존성 `get_db`.

접속 문자열은 `app.core.config.Settings.database_url` (환경변수 DATABASE_URL, 기본은
docker-compose 의 postgres) 에서 읽는다. 설계서 11.2절: PostgreSQL 16 + SQLAlchemy 2.0.

세션을 얻는 방법
  - 라우터/서비스: `db: DB` (app/api/deps.py 의 `Annotated[Session, Depends(get_db)]`) 로 주입받는다.
    요청 하나당 세션 하나가 만들어지고, 응답 후 `finally` 에서 반드시 닫힌다.
  - 스크립트/테스트: `SessionLocal()` 을 직접 열고 `with` 로 감싼다.

세션 옵션의 의미
  - autoflush=False : 쿼리를 날리기 전에 SQLAlchemy가 대기 중인 INSERT/UPDATE 를 자동으로 DB에
    밀어 넣지 않는다. 따라서 **방금 add()/수정한 행을 같은 세션에서 SELECT(count 등)로 세려면
    호출자가 먼저 `db.flush()` 를 호출해야 한다.** 예) team_service.refresh_team_status 는
    회원 수를 세기 전에 flush 한다. 이 옵션을 켠 이유는 flush 시점을 코드에서 명시적으로
    통제해 "언제 DB에 반영됐는지" 를 읽기 쉽게 하기 위함이다.
  - expire_on_commit=False : commit 후에도 객체 속성이 만료되지 않아, 응답 직렬화 시 추가
    SELECT(lazy load) 가 발생하지 않는다. 대신 commit 뒤의 값은 DB와 다를 수 있음을 염두에 둔다.
  - pool_pre_ping=True : 풀에서 커넥션을 꺼낼 때 살아 있는지 먼저 확인한다. 배포 환경(Railway 등)
    에서 유휴 커넥션이 끊겼을 때 첫 요청이 실패하는 것을 막는다.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# 프로세스 전체가 공유하는 엔진(커넥션 풀). 모듈 import 시 한 번만 생성된다.
engine = create_engine(get_settings().database_url, pool_pre_ping=True)
# 세션 팩토리. 옵션의 의미는 모듈 docstring 참조.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """요청 단위 세션을 제공하는 FastAPI 의존성.

    commit/rollback 은 서비스 계층이 결정한다. 여기서는 예외가 나더라도 세션을 닫기만 하며,
    닫히지 않은 트랜잭션은 close() 시점에 롤백된다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
