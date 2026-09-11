"""user_avatars — 프로필 사진을 DB 에 담는다 (Render 무료 플랜은 디스크가 재배포 때 사라지고, 외부 스토리지는 추가 계정이 필요).

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-11

프론트가 256px JPEG 로 줄여 보내므로 한 장당 보통 20~50KB. users.profile_image_url 에는
`/api/v1/users/{id}/avatar?v={key}` 형태의 주소가 들어가 목록 응답은 가볍게 유지된다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_avatars',
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('content_type', sa.String(length=30), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('cache_key', sa.String(length=16), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('user_avatars')
