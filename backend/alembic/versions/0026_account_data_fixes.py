"""계정 데이터 정리: 탈퇴 회원 비식별화 소급 · 이메일 소문자 CHECK.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-02

1) 탈퇴한 계정(users.deleted_at IS NOT NULL)의 players 행은 상태와 상관없이(예전에는 ACTIVE 만 바꿨다), 그리고
   그 행으로 병합된 게스트 행도 이름을 '탈퇴한 회원' 으로, 키를 NULL 로 바꾼다 (auth_service.delete_account 와 같은 처리).
   여러 번 돌려도 결과가 같다. 지운 이름은 되살릴 수 없으므로 downgrade 는 아무것도 하지 않는다.
2) users.email 을 소문자로 맞추고(겹치는 행이 생기면 그 행은 건드리지 않는다 — 0016 과 같은 규칙) CHECK 를 붙인다.
   대소문자만 다른 두 계정이 남아 있으면 CHECK 는 NOT VALID 로 두고 로그를 남긴다 (새 행만 검사).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0026'
down_revision: str | None = '0025'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANON = '탈퇴한 회원'


def upgrade() -> None:
    # 1) 탈퇴 회원 본인 행 → 그 행으로 병합된 게스트 행
    op.execute(
        sa.text(
            """
            UPDATE players p SET display_name = :anon, height_cm = NULL
            FROM users u
            WHERE p.user_id = u.id AND u.deleted_at IS NOT NULL
              AND (p.display_name <> :anon OR p.height_cm IS NOT NULL)
            """
        ).bindparams(anon=ANON)
    )
    op.execute(
        sa.text(
            """
            UPDATE players g SET display_name = :anon, height_cm = NULL
            FROM players m JOIN users u ON u.id = m.user_id
            WHERE g.merged_into_player_id = m.id AND u.deleted_at IS NOT NULL
              AND (g.display_name <> :anon OR g.height_cm IS NOT NULL)
            """
        ).bindparams(anon=ANON)
    )

    # 2) 이메일 소문자 — 겹치지 않는 것만 바꾼다
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
    op.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_email_lower')
    op.execute('ALTER TABLE users ADD CONSTRAINT ck_users_email_lower CHECK (email IS NULL OR email = lower(email)) NOT VALID')
    bad = op.get_bind().execute(sa.text('SELECT count(*) FROM users WHERE email <> lower(email)')).scalar()
    if bad:
        print(f'[0026] users.email: 대소문자만 다른 계정과 겹쳐 소문자로 바꾸지 못한 행 {bad}개 — CHECK 를 NOT VALID 로 둔다. 정리한 뒤 VALIDATE 하세요')
    else:
        op.execute('ALTER TABLE users VALIDATE CONSTRAINT ck_users_email_lower')


def downgrade() -> None:
    op.execute('ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_email_lower')
    # 1) 의 비식별화와 소문자 변환은 되돌리지 않는다 (원래 값이 남아 있지 않다)
