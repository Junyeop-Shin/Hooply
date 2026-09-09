"""팀 생성 승인 — teams.approval_status / approved_at / approved_by. 관리자 콘솔(SQLAdmin)에서 승인해야 팀이 활성화된다.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-09

기존 팀은 APPROVED 로 채운다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('teams', sa.Column('approval_status', sa.String(length=10), server_default='PENDING', nullable=False))
    op.add_column('teams', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('teams', sa.Column('approved_by', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_teams_approved_by', 'teams', 'users', ['approved_by'], ['id'], ondelete='SET NULL')
    op.create_check_constraint('ck_teams_approval_status', 'teams', "approval_status IN ('PENDING','APPROVED','REJECTED')")
    op.execute("UPDATE teams SET approval_status = 'APPROVED', approved_at = created_at")


def downgrade() -> None:
    op.drop_constraint('ck_teams_approval_status', 'teams', type_='check')
    op.drop_constraint('fk_teams_approved_by', 'teams', type_='foreignkey')
    op.drop_column('teams', 'approved_by')
    op.drop_column('teams', 'approved_at')
    op.drop_column('teams', 'approval_status')
