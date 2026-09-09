"""운영 DB 에 관리자(global_role=ADMIN) 계정을 만들거나, 이미 있는 계정을 관리자로 올린다.

사용 (DATABASE_URL 은 환경 변수로):
  DATABASE_URL=postgresql+psycopg://... python -m scripts.create_admin admin@example.com '비밀번호' [이름]

- 계정이 없으면 이메일 가입과 같은 경로(auth_service.signup)로 만든 뒤 ADMIN 으로 올린다 (bcrypt 해시 저장).
- 이미 있으면 역할만 ADMIN 으로 바꾼다 (비밀번호는 바꾸지 않는다).
- seed_demo 와 달리 다른 데이터는 만들지 않으므로 운영 DB 에 써도 된다.
"""

from __future__ import annotations

import sys

from pydantic import SecretStr
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import User
from app.models.enums import GlobalRole
from app.schemas.auth import SignupRequest
from app.services import auth_service


def main() -> None:
    if len(sys.argv) < 3:
        print("사용법: python -m scripts.create_admin <email> <password> [name]")
        sys.exit(1)
    email, password = sys.argv[1].strip(), sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else "관리자"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            auth_service.signup(db, SignupRequest(email=email, password=SecretStr(password), name=name))
            user = db.scalar(select(User).where(User.email == email))
            created = True
        else:
            created = False
        user.global_role = GlobalRole.ADMIN
        db.commit()
    print(f"{'생성' if created else '승격'} 완료: {email} → ADMIN. 관리자 콘솔 /admin 에서 이 계정으로 로그인하세요.")


if __name__ == "__main__":
    main()
