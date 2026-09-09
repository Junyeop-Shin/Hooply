"""SQLAlchemy 선언적 베이스(Base)와 공통 컬럼 믹스인.

app/models/* 의 모든 테이블 클래스는 여기의 `Base`를 상속한다. Alembic은 `app.models` 패키지를
import해 `Base.metadata`에 등록된 테이블 전체를 autogenerate 대상으로 삼는다 (alembic/env.py).

설계서 6장 ERD에서 거의 모든 테이블이 공유하는 요소를 한 곳에 모았다.
  - BIGSERIAL PK                → `BigPK`
  - TIMESTAMPTZ 컬럼            → `TimestampTZ`
  - created_at / updated_at     → `CreatedAtMixin` / `TimestampMixin`

믹스인은 "테이블에 어떤 타임스탬프 컬럼이 있는가"를 클래스 선언부에서 바로 읽히게 하려는 것이다.
예) `class Team(TimestampMixin, Base)` → created_at + updated_at 둘 다 있음
    `class Player(CreatedAtMixin, Base)` → created_at 만 있음 (joined_at 등 별도 컬럼 사용)
"""

from datetime import datetime
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 공통 타입 별칭 — `id: Mapped[BigPK]` 처럼 쓰면 mapped_column(...)을 매번 반복하지 않아도 된다.
# BigPK: 6장 ERD의 BIGSERIAL PK. autoincrement=True 이므로 INSERT 시 값을 주지 않는다.
BigPK = Annotated[int, mapped_column(BigInteger, primary_key=True, autoincrement=True)]
# TimestampTZ: ERD의 TIMESTAMPTZ. 항상 timezone=True 로 두어 naive datetime 혼입을 막는다.
TimestampTZ = Annotated[datetime, mapped_column(DateTime(timezone=True))]


class Base(DeclarativeBase):
    """모든 ORM 모델의 공통 부모. `Base.metadata`가 전체 테이블 정의를 보유한다."""


class CreatedAtMixin:
    """`created_at` 한 컬럼만 추가하는 믹스인.

    이력·로그 성격이라 생성 후 수정되지 않는 테이블(players, quarters, audit_logs 등)에 쓴다.
    값은 DB의 now() 로 채워지므로 애플리케이션에서 넣지 않는다.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    """`created_at` + `updated_at` 을 추가하는 믹스인.

    수정이 일어나는 마스터 성격 테이블(users, teams, events)에 쓴다.
    `updated_at`은 server_default 로 초기값을, `onupdate` 로 UPDATE 때마다 갱신값을 받는다.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
