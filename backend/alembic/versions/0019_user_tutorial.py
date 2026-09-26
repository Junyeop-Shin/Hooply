"""시작 안내(튜토리얼) 상태 — users.tutorial_state · tutorial_path · tutorial_tips_seen.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-26

새 가입자는 PENDING 으로 시작해 홈에서 "안내를 받을까요?" 팝업을 본다. 이 기능 전에 가입한 사람은
이미 앱을 쓰고 있으므로 DECLINED 로 채워 팝업도 기능별 첫 안내도 띄우지 않는다 (도움말에서 다시 켤 수 있다).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE tutorial_state_enum AS ENUM ('PENDING', 'ACTIVE', 'CLOSED', 'DONE', 'DECLINED')")
    op.execute("CREATE TYPE tutorial_path_enum AS ENUM ('PLAYER', 'MANAGER')")
    op.add_column('users', sa.Column('tutorial_state', postgresql.ENUM(name='tutorial_state_enum', create_type=False), nullable=False, server_default='DECLINED'))
    op.add_column('users', sa.Column('tutorial_path', postgresql.ENUM(name='tutorial_path_enum', create_type=False), nullable=True))
    op.add_column('users', sa.Column('tutorial_tips_seen', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    # 기존 행은 위 기본값(DECLINED)으로 채워졌다. 이제부터 새 가입자는 PENDING
    op.execute("ALTER TABLE users ALTER COLUMN tutorial_state SET DEFAULT 'PENDING'::tutorial_state_enum")


def downgrade() -> None:
    op.drop_column('users', 'tutorial_tips_seen')
    op.drop_column('users', 'tutorial_path')
    op.drop_column('users', 'tutorial_state')
    op.execute("DROP TYPE tutorial_path_enum")
    op.execute("DROP TYPE tutorial_state_enum")
