"""쿼터 길이 기본값 8분 + 카카오 로그인이 덮어쓴 프로필 사진 주소 복구.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-14

1) quarters.duration_min 기본값 10 → 8. 동호회 쿼터는 보통 8분이고 시간이 모자라면 짧게 끊는다.
   기존 기록은 건드리지 않으며, 입력 범위(1~10분)는 API 검증(app/schemas/game.py)으로만 둔다.
2) 직접 올린 사진(user_avatars)이 있는데 users.profile_image_url 이 다른 곳(카카오 CDN)을 가리키면
   업로드한 사진 주소로 되돌린다. 카카오 로그인이 매번 덮어써서 올린 사진이 사라지던 문제의 뒷정리다.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AVATAR_URL = "'/api/v1/users/' || u.id || '/avatar?v=' || a.cache_key"


def upgrade() -> None:
    op.alter_column('quarters', 'duration_min', server_default='8')
    op.execute(
        f"UPDATE users u SET profile_image_url = {_AVATAR_URL} FROM user_avatars a "
        f"WHERE a.user_id = u.id AND u.profile_image_url IS DISTINCT FROM {_AVATAR_URL}"
    )


def downgrade() -> None:
    op.alter_column('quarters', 'duration_min', server_default='10')
