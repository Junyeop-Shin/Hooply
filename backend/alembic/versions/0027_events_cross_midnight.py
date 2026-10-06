"""자정을 넘기는 일정 허용: events 의 ck_events_time_order CHECK 삭제.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-06

0025 가 붙인 `end_time > start_time` CHECK 는 22:00~00:30 같은 야간 일정을 막았다. 이제 종료 시각이 시작 시각보다
같거나 빠르면 **다음 날**로 해석한다 (event_service.ends_at — 경기 후 투표도 그 시각에 열린다). 데이터는 바꾸지 않는다.

downgrade 는 0025 와 같은 방식으로 CHECK 를 되돌린다: 그 사이 들어온 자정 넘김 일정은 end_time 을 비우고(종료 시각을
잃는다 — 날짜 · 시작 시각 · 기록은 남는다) NOT VALID 로 붙인 뒤 어긋난 행이 없을 때만 VALIDATE 한다.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0027'
down_revision: str | None = '0026'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK_NAME = 'ck_events_time_order'
CHECK_EXPR = 'start_time IS NULL OR end_time IS NULL OR end_time > start_time'


def upgrade() -> None:
    op.execute(f'ALTER TABLE events DROP CONSTRAINT IF EXISTS {CHECK_NAME}')


def downgrade() -> None:
    # 자정을 넘기는 일정의 종료 시각은 예전 규칙에 맞지 않으므로 비운다 (0025 의 repair 와 같은 처리)
    op.execute('UPDATE events SET end_time = NULL WHERE start_time IS NOT NULL AND end_time IS NOT NULL AND end_time <= start_time')
    op.execute(f'ALTER TABLE events DROP CONSTRAINT IF EXISTS {CHECK_NAME}')
    op.execute(f'ALTER TABLE events ADD CONSTRAINT {CHECK_NAME} CHECK ({CHECK_EXPR}) NOT VALID')
    bad = op.get_bind().execute(sa.text(f'SELECT count(*) FROM events WHERE NOT ({CHECK_EXPR})')).scalar()
    if bad:
        print(f'[0027] events.{CHECK_NAME}: 조건에 맞지 않는 행 {bad}개 — NOT VALID 로 둔다 (새 행만 검사)')
    else:
        op.execute(f'ALTER TABLE events VALIDATE CONSTRAINT {CHECK_NAME}')
