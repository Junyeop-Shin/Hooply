"""app.core — 프레임워크에 가까운 공통 기반.

- config.py   : 환경 변수 → Settings (DB 주소, JWT, 카카오, CORS 등)
- errors.py   : 7.4절 에러 코드 체계 (AppError 계열 예외 + FastAPI 핸들러)
- security.py : 11.5절 인증 결정 (bcrypt 비밀번호 해시, JWT 발급/검증, 토큰 생성)

도메인 로직은 여기 두지 않는다. 도메인은 app.services, HTTP 진입점은 app.api에 있다.
"""
