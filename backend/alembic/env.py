"""Alembic 마이그레이션 실행 환경 (설계서 11.2절 "SQLAlchemy 2.0 + Alembic" · 12장 2-B).

`alembic upgrade/downgrade/revision` 명령이 실행될 때 Alembic이 가장 먼저 import하는
파일이다. 여기서 하는 일은 세 가지뿐이다.

1. **DB 접속 문자열을 앱 설정에서 가져온다.** `alembic.ini`의 `sqlalchemy.url`은 비워
   두고, `app.core.config.get_settings().database_url`(= `.env`의 `DATABASE_URL`)로
   덮어쓴다. 접속 정보를 앱과 마이그레이션 두 곳에 따로 적어 두면 반드시 어긋나기
   때문이다.
2. **모든 ORM 모델을 `Base.metadata`에 등록한다.** `from app.models import Base`가
   `app/models/__init__.py`를 실행하면서 모든 모델 클래스를 import하므로, 그 부수 효과로
   28개 테이블이 metadata에 실린다. `alembic revision --autogenerate`가 이 metadata와
   실제 DB를 비교해 마이그레이션 초안을 만든다. 새 모델을 만들고 `__init__.py`에
   등록하지 않으면 autogenerate가 그 테이블을 **보지 못한다** — 가장 흔한 실수.
3. offline / online 두 모드 중 하나로 마이그레이션을 실행한다 (아래 함수 참조).

일상적인 사용법 (backend 디렉터리에서, Postgres가 떠 있는 상태):
    alembic upgrade head                        # 최신 스키마로
    alembic revision --autogenerate -m "설명"   # 모델 변경 → 새 리비전 초안 생성
    alembic downgrade -1                        # 한 단계 되돌리기
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import db_host_for_log, get_settings
from app.models import Base  # noqa: F401 — 모든 모델을 metadata에 등록

# Alembic이 alembic.ini를 파싱해 넘겨주는 설정 객체
config = context.config
# alembic.ini의 [loggers]/[handlers]/[formatters] 섹션으로 파이썬 logging을 구성한다.
# (테스트 등에서 ini 없이 프로그램적으로 부를 때는 config_file_name이 None일 수 있다)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ini 파일의 빈 sqlalchemy.url을 앱 설정값으로 덮어쓴다 (모듈 docstring 1항)
config.set_main_option("sqlalchemy.url", get_settings().database_url)
print(f"[alembic] DB → {db_host_for_log()}  (localhost 로 나오면 DATABASE_URL 환경 변수가 전달되지 않은 것)")
# autogenerate가 비교 기준으로 삼는 "코드 쪽 스키마"
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """오프라인 모드 — DB에 접속하지 않고 SQL 스크립트만 출력한다.

    `alembic upgrade head --sql` 처럼 `--sql` 플래그를 주면 이 경로를 탄다.
    DBA에게 검토용 SQL을 넘기거나, 접속 권한이 없는 환경에서 무엇이 실행될지 미리 볼 때
    쓴다. 이 프로젝트의 일상 개발에서는 거의 쓰지 않는다.

    - `literal_binds=True`: 바인드 파라미터를 SQL 문자열 안에 직접 박아 넣는다
      (실행이 아니라 출력이 목적이므로).
    - `compare_type=True`: autogenerate 시 컬럼 타입 변경(예: VARCHAR(50)→(100))도
      감지한다. 기본값은 타입 변경을 무시하므로 켜 두는 편이 안전하다.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """온라인 모드 — 실제 DB에 접속해 마이그레이션을 실행한다. 평소에 쓰는 경로.

    `alembic.ini`의 `[alembic]` 섹션에서 `sqlalchemy.` 접두사가 붙은 키(여기서는
    `sqlalchemy.url` 하나, 위에서 주입됨)로 엔진을 만든다.
    `NullPool`을 쓰는 이유: 마이그레이션은 한 번 실행되고 끝나는 프로세스라 커넥션
    풀을 유지할 필요가 없고, 풀에 남은 커넥션이 프로세스 종료를 막는 일을 피하기 위해서다.

    `context.begin_transaction()`은 PostgreSQL에서 마이그레이션 전체를 하나의 트랜잭션으로
    감싼다. 즉 리비전 중간에 실패하면 그 리비전의 DDL이 통째로 롤백된다 (Postgres는 DDL도
    트랜잭션 대상이라 이것이 가능하다).
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


# Alembic CLI가 --sql 플래그 여부에 따라 모드를 정해 준다
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
