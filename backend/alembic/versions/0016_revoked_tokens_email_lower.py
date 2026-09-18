"""로그아웃한 refresh 토큰 폐기 목록 · 이메일 소문자 정규화.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-18

1) revoked_tokens — 로그아웃하거나 회전으로 버려진 refresh 토큰의 jti. 만료 시각이 지나면 지워도 된다.
   지금까지는 로그아웃해도 refresh 토큰이 14일간 유효했다.
2) users.email 을 소문자로 맞춘다. 앞으로는 가입·로그인에서 항상 소문자로 다루므로
   `Test@a.com` 과 `test@a.com` 이 다른 계정이 되지 않는다. 대소문자만 다른 두 계정이 이미
   있으면 그 쌍은 건드리지 않는다 (UNIQUE 충돌) — 그런 행은 로그에 남겨 사람이 정리한다.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'revoked_tokens',
        sa.Column('jti', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_revoked_tokens_expires', 'revoked_tokens', ['expires_at'])
    # 소문자로 바꿨을 때 다른 행과 겹치지 않는 것만 바꾼다
    op.execute(
        """
        UPDATE users u SET email = lower(u.email)
        WHERE u.email IS NOT NULL AND u.email <> lower(u.email)
          AND NOT EXISTS (SELECT 1 FROM users o WHERE o.id <> u.id AND lower(o.email) = lower(u.email))
        """
    )
    op.execute(
        """
        UPDATE auth_identities i SET provider_uid = lower(i.provider_uid)
        WHERE i.provider = 'LOCAL' AND i.provider_uid <> lower(i.provider_uid)
          AND NOT EXISTS (SELECT 1 FROM auth_identities o WHERE o.id <> i.id AND o.provider = 'LOCAL' AND lower(o.provider_uid) = lower(i.provider_uid))
        """
    )


def downgrade() -> None:
    op.drop_index('ix_revoked_tokens_expires', table_name='revoked_tokens')
    op.drop_table('revoked_tokens')
