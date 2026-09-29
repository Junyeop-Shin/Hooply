"""AI 설명 결과 캐시 겸 호출 기록 llm_results (docs/07 8.2절).

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-29

명세 8.2 는 0020 에 함께 두었지만, 0020(event_play_assignments)이 먼저 배포되어 따로 나눴다. 새 표만 만든다.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0021'
down_revision: str | None = '0020'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'llm_results',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('chain', sa.String(length=10), nullable=False),
        sa.Column('cache_key', sa.String(length=64), nullable=False),
        sa.Column('output', postgresql.JSONB(), nullable=False),
        sa.Column('fallback', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('fail_reason', sa.String(length=40), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('model', sa.String(length=60), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('cache_key', name='uq_llm_results_cache_key'),
    )


def downgrade() -> None:
    op.drop_table('llm_results')
