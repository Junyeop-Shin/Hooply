# 농구 동호회 팀 매칭 서비스

설계서: [CLAUDE.md](CLAUDE.md) (v0.3). 이 저장소는 그 설계서의 **6장 데이터 모델**과 **7장 API 명세**를 코드로 옮긴 백엔드 뼈대와, 5장 화면 설계를 따른 프론트엔드 초안입니다.

## 구성

```
docker-compose.yml          db(postgres:16) + api(FastAPI) + web(nginx)
frontend/                   React + TS + Vite + Tailwind — 자세한 내용은 frontend/README.md
backend/
  alembic/versions/0001_initial_schema.py   6장 ERD 전체 (28 테이블)
  alembic/versions/0002_*.py                게스트 묶기 요청 컬럼 + 설문 테이블(스펙 구조) + 설문 v1 시드
  alembic/versions/0003_*.py                설문 v2(활성) · 팀별 자기 위치 컬럼 · users.birth_year 삭제
  alembic/versions/0004_*.py                users.position_prefs (프로필 포지션 수정의 원본)
  alembic/versions/0005_*.py                guest_invite_presets (이전 초대 게스트 불러오기)
  alembic/versions/0016_*.py                revoked_tokens(로그아웃 토큰 폐기) · 이메일 소문자 정규화
  alembic/versions/0017_*.py                상태값 21종을 PostgreSQL ENUM 타입으로 · 조회·삭제 경로의 외래키 인덱스 9개
  scripts/simulate_rating.py                실력 지표 시뮬레이션 — 원시 마진 vs 잔차 모델 (설계서 9.1·9.3절 근거 재현, 참고 문헌 포함)
  scripts/seed_demo.py                      데모 데이터 (21명 동호회 · 지난 10회차 배정/쿼터/투표 · 배정 전 일정 2건 · 실력 정렬 · 두 번째 팀)
  app/db/survey_seed.py                     설문 문항·선택지 시드 데이터 (v1 이력 + v2 현재)
  app/
    core/      config · errors(7.4절 에러 코드) · security(bcrypt/JWT)
    db/        Base · 세션
    models/    account · team · profile · ranking · survey · event · assignment · game · peer · audit
    schemas/   7.2절 공통 스키마 + 그룹별 요청/응답
    api/v1/    7.3절 엔드포인트를 명세 순서대로 (auth → surveys → teams → guests → rankings → events → assignments → quarters → peer → admin)
    services/  auth · team · player · survey · guest · event · ranking · assignment(배정 엔진) · quarter · rating(잔차 Elo)
  tests/       명세 커버리지 검사 + 인증·팀 흐름
```

## 실행

```bash
# 1. DB
docker compose up -d db

# 2. 백엔드 (uv 사용)
cd backend
uv sync
cp .env.example .env            # 필요 시 수정
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
# → http://localhost:8000/docs

# 3. 프론트엔드
cd frontend
npm install
npm run dev
# → http://localhost:5173  (/api 요청은 8000으로 프록시)
```

전부 도커로 띄우려면 `docker compose up --build` 후 http://localhost:5173 으로 접속합니다.

데모 데이터(21명 동호회 + 지난 10회차 기록 + 배정 전 일정 2건 + 게스트). 전 기능을 둘러보는 순서는 [docs/05-데모시나리오.md](docs/05-데모시나리오.md):

```bash
docker compose exec api python -m scripts.seed_demo          # 이미 있으면 건너뜀. 다시 만들려면 --reset (전 데이터 삭제)
# 관리자 콘솔: http://localhost:8000/admin  (admin@demo.com / demo1234)
# 운영 DB 에 데모 팀을 올릴 때:  DATABASE_URL=<Neon> python -m scripts.seed_demo --no-admin   /  지울 때: python -m scripts.remove_demo --yes
# 날짜는 실행일 기준(이번 주 일요일)이라 시간이 지나면 '배정 전 일정'이 과거가 된다 → .github/workflows/demo-refresh.yml 이 매주 월요일 00:30(KST) 자동으로 지우고 다시 만든다 (수동: Actions → Demo data refresh, --anchor 로 기준 일요일 지정 가능)
#   --reset 은 로컬 DB 에서만 동작 (운영 DB 전체 삭제 방지)
# 의존성 변경 시: cd backend && uv add <pkg> && uv export --no-dev --no-hashes --no-emit-project -o requirements.txt  (Render·Docker 는 requirements.txt 로 설치)
# 카카오: 백엔드 KAKAO_CLIENT_ID(REST API 키)·KAKAO_CLIENT_SECRET·KAKAO_REDIRECT_URI(<프론트>/auth/kakao/callback), 프론트 VITE_KAKAO_JS_KEY(JavaScript 키, 공개용)
# 운영 배포 전 확인: JWT_SECRET_KEY 교체 · DOCS_ENABLED=false · ADMIN_COOKIE_SECURE=true · CORS_ORIGINS/FRONTEND_BASE_URL 을 실제 도메인으로 · RATE_LIMIT_ENABLED 는 기본 true(단일 인스턴스 메모리 기준) ·
# DB 백업: .github/workflows/backup.yml 이 매일 04:00(KST) pg_dump 를 아티팩트로 30일 보관 — 저장소 Secrets 에 BACKUP_DATABASE_URL 필요. 처리되지 않은 오류는 스택과 함께 서버 로그(Render Logs)에 남는다 · 운영 DB 에는 seed_demo 를 --no-admin 없이 실행하지 않기
# 매니저: manager@demo.com / demo1234   팀원: m01@demo.com ~ m20@demo.com / demo1234 (m19 설문 전 · m20 게스트 출신 가입자)
# 게스트 불러오기 확인: m04@demo.com(허웅·이승현), m07@demo.com(허훈), manager@demo.com(송교창)
```

테스트 (docker의 Postgres를 그대로 사용하며 테이블을 비웁니다):

```bash
cd backend && uv run pytest -q
```

## 구현 상태

| 구분 | 상태 |
| --- | --- |
| 스키마 / 마이그레이션 | 완료 (upgrade/downgrade 왕복 검증) |
| 인증(이메일, 대소문자 무시) · 로그아웃(refresh 폐기·회전) · 로그인/가입/비밀번호 경로 요청 제한(429) · 비밀번호 변경 · 계정 삭제(비식별화) · /me · 팀 생성(관리자 승인 후 활성화)/가입/나가기/활성화/정보 수정 · 팀원 목록/권한(팀장만 부여·회수, 팀장 자진 해제 시 승계)/제외(마지막 매니저 보호) | 구현 |
| 온보딩 설문 v2 (11문항, 1인 1회, 팀 내 z-score → prior) + 팀 가입 후 "동호회 내 내 위치" | 구현 |
| 일정 등록(지난 일정 불러오기: 날짜·마감 +7일)·목록·상세·수정·삭제(참석·배정·투표 함께, 경기 기록 있으면 불가)·응답 미리 마감 · RSVP · 참석 현황/포지션 요약/경고 · 지난 기록 추가(과거 일정 + 참석 + 쿼터) | 구현 |
| 게스트: 회차별 등록(팀원 누구나, 키 포함)·수정·삭제 권한·동명이인·재사용·묶기 요청·병합 후보·병합/되돌리기·**본인 확인 병합**(같은 이름의 회원이 가입하면 홈에서 직접 확인해 기록 승계) | 구현 |
| 매니저 실력 정렬 (버전 관리, 설문 0.5 + 정렬 0.5 결합) | 구현 |
| 팀 배정: 실현가능성 검사, Union-Find 묶음, 2팀 완전 탐색, 전략 3안, 설명, 교체, 확정, 플레이어 마스킹, 직전 회차 제약 | 구현 |
| 쿼터 기록 · 잔차 기반 Elo 실력 갱신 (첫 2회 게이트, 삭제 롤백 = 팀 전체 재계산, 병합 게스트 합산) | 구현 |
| 피어 투표 (종료 시각 자동 오픈, '다음에 같이 뛰고 싶은 사람' 같은 팀 2 + 상대 팀 2, 이유 태그, 함께 참석 대비 정규화 + 최근 가중 선호 점수, 매니저 독려 메시지) | 구현 |
| 선수 통계 (`/players/{id}/stats`: 본인은 쿼터 기록·마진, 매니저는 실력 지표 근거까지) · 팀 리더보드 (참여율/출전 쿼터/잔차) | 구현 |
| 팀 화면 **기록 탭** — 활동일별 추세 그래프 · 월간 코트 마진 랭킹 (출전 비율 기준, 접기 가능) · 행동 배지 19종 (`/me/badges`) | 구현 |
| 관리자: SQLAdmin 콘솔 `/admin` (ADMIN 계정, 팀 승인/거절 액션) + 사용자 검색·팀 승인·원시 데이터·지표 보정(이력+감사 로그)·감사 로그 API | 구현 |
| 카카오 로그인 (인가 URL · 서명 state · 콜백 가입/로그인 · 기존 계정 연결) · 카카오톡 공유 (팀 초대 · 투표 독려 · **확정된 팀 구성 이미지**(캔버스 → 카카오 이미지 업로드 → 피드), SDK 없으면 OS 공유 시트/파일 저장) | 구현 |
| 비밀번호 재설정 메일 (토큰 해시 저장 · 30분 · 1회, Resend 발송, 키 없으면 로그) | 구현 |
| 로테이션 자동 제안(F17) | 범위에서 제외 |
| 프론트: 로그인·가입·설문·홈·팀·팀원 관리·일정/RSVP·게스트·프로필(메인 팀 · 내 기록)·실력 정렬·배정 실행/결과/확정 결과·쿼터 기록·피어 투표·매니저 실력 지표 화면 | API 연결됨 |

501 `NOT_IMPLEMENTED`를 반환하는 엔드포인트는 `/docs`에서 요청·응답 스키마를 확인할 수 있고, 각 함수 docstring에 설계서의 해당 절과 구현 메모가 있습니다.

## 다음 작업 (9.8절 순서)

1. 배치 RAPM(100쿼터 이후) · 앵커 재보정(150쿼터 이후)

## 테스트

| 종류 | 명령 | 내용 |
| --- | --- | --- |
| 백엔드 | `cd backend && uv run pytest -q` | 47개 — 권한·팀 승인·배정 제약·쿼터 롤백·투표·카카오·비밀번호 재설정 (개발 DB 를 비우고 돌리므로 끝나면 `seed_demo --reset`) |
| 프론트 단위·컴포넌트 | `cd frontend && npm test` | Vitest + Testing Library — 날짜/이유 문구 헬퍼, 로그인 시 캐시 초기화, 투표 화면(2명 제한·자동 접힘·종료 전 안내) |
| E2E | `docker compose up -d && cd frontend && npm run test:e2e` | Playwright(모바일 Chromium) — 로그인·홈, 팀 배정 실행→확정, 쿼터 기록 화면, 플레이어 프로필 기록 (데모 데이터 필요) |
| CI | `.github/workflows/ci.yml` | 푸시·PR 마다 위 세 가지를 GitHub Actions 에서 실행 (PostgreSQL 서비스 컨테이너 + 마이그레이션 + 데모 시드) |

메일 발송은 `RESEND_API_KEY` 와 `MAIL_FROM` 을 넣으면 Resend 로 나가고, 없으면 재설정 링크가 서버 로그에 찍힌다 (로컬 확인용).
