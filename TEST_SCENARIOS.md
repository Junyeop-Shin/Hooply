# 테스트 시나리오 — 백엔드 뼈대 검증

설계서 v0.3 기준으로 **현재 구현된 기능**이 제대로 동작하는지 손으로 확인하는 절차입니다.
각 시나리오는 "무엇을 확인하는가 → 어떻게 하는가 → 무엇이 나와야 하는가" 순서로 적혀 있습니다.

> 자동 테스트(`pytest`)가 같은 내용을 검증하지만, 이 문서는 Swagger UI에서 직접 눌러 보며 이해하기 위한 것입니다.

---

## 0. 준비

### 0-1. 서비스 실행

```bash
cd /Users/junyeop/Desktop/AI웹서비스미니프로젝트
docker compose up --build
```

터미널에 아래 두 줄이 보이면 준비된 것입니다.

```
api-1  | INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema (v0.3 ERD)
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000
```

> DB만 도커로 띄우고 API는 로컬에서 돌리고 싶다면:
> `docker compose up -d db` → `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload`

### 0-2. Swagger UI 열기

브라우저에서 **http://localhost:8000/docs**

- 왼쪽 태그(인증 · 프로필 / 팀 · 참가자 …)를 펼치면 엔드포인트 목록이 보입니다.
- 각 엔드포인트를 클릭하면 **설명 · 권한 · 오류 코드 · 구현 상태**가 적혀 있습니다.
- `Try it out` → 값 입력 → `Execute` 로 호출합니다.

### 0-3. 인증 토큰 넣는 법

로그인이 필요한 API는 상단 오른쪽 **Authorize** 버튼을 눌러 `access_token` 값을 붙여 넣습니다.
(앞에 `Bearer ` 를 붙일 필요 없이 토큰만 넣으면 됩니다.)

### 0-4. 데모 데이터로 바로 시작하기 (권장)

계정을 하나하나 만들 필요 없이 20명 동호회를 한 번에 만듭니다.

```bash
docker compose exec api python -m scripts.seed_demo      # 도커로 띄운 경우
# 또는  cd backend && uv run python -m scripts.seed_demo   # 로컬 실행 시
```

| 항목 | 내용 |
| --- | --- |
| 매니저 | **manager@demo.com / demo1234** (허재) |
| 팀원 | m01@demo.com ~ m19@demo.com / demo1234 (m04 문경은 = 게스트 초대자) |
| 팀 | 일요 코트메이트 · 회원 20명 · 전원 설문 + 자기 위치 완료 → 등급 계산됨 (매니저에게만 보임) |
| 지난주 일정 | 종료됨 · 배정 확정 완료 · 게스트 3명 (문경은→허웅, 김선형→허훈, 허재→송교창) |
| 이번 주 일정 | 일요일 10:00 "일요 정기전" · 회원 12명 참석 + 게스트 2명(허웅: 문경은과 같은 팀 요청 · 이승현: 실력 미지정) · 불참 3 · 미응답 5 |

게스트 **불러오기** 확인용 계정 (이번 주 일정 → 게스트 초대 시트 상단 칩):

| 계정 | 불러올 수 있는 게스트 |
| --- | --- |
| m07@demo.com (김선형) | 게스트 허훈 — 등급 3, SG, 같은 팀 요청 |
| manager@demo.com (허재) | 게스트 송교창 — 등급 5, C |
| m04@demo.com (문경은) | 게스트 허웅 · 게스트 이승현 (이미 이번 주에 등록되어 있으므로 고르면 정보만 갱신됨) |

이미 팀이 있으면 다시 만들지 않고 계정만 출력합니다. 처음부터 다시 만들려면 아래 0-5로 DB를 비운 뒤 실행하세요.

### 0-5. DB 초기화가 필요할 때

```bash
docker compose down -v      # 볼륨까지 삭제 → 다음 up 때 빈 DB로 시작
```

---

## 1. 인증 (FR-01, FR-02, 11.5절)

### S1-1. 회원가입이 된다

| 단계 | 요청 | 기대 결과 |
| --- | --- | --- |
| 1 | `POST /api/v1/auth/signup` body: `{"email":"manager@test.com","password":"password123","name":"매니저","height_cm":180}` | `201` · `access_token`, `refresh_token`, `token_type: bearer` (출생연도는 받지 않음) |
| 2 | 같은 이메일로 다시 signup | `409` · `code: EMAIL_DUPLICATED` |
| 3 | `{"email":"not-an-email","password":"short","name":""}` | `400` · `code: VALIDATION_ERROR` · `details[]`에 어떤 필드가 왜 틀렸는지 |

**확인 포인트**
- 응답 어디에도 비밀번호 원문이 없다.
- DB에서 확인하면 해시만 저장되어 있다:
  ```bash
  docker compose exec db psql -U hoops -d hoops -c "select email, left(password_hash, 7) from users"
  ```
  → `$2b$12$` 로 시작하는 bcrypt 해시가 보이면 정상.

### S1-2. 로그인과 토큰 갱신

| 단계 | 요청 | 기대 결과 |
| --- | --- | --- |
| 1 | `POST /auth/login` 올바른 이메일·비밀번호 | `200` · 토큰 쌍 |
| 2 | 틀린 비밀번호 | `401` · `INVALID_CREDENTIALS` |
| 3 | `POST /auth/refresh` body: `{"refresh_token": "<1번의 refresh_token>"}` | `200` · 새 토큰 쌍 |
| 4 | `refresh_token` 자리에 `access_token`을 넣어서 호출 | `401` · `TOKEN_EXPIRED` (토큰 종류 검사) |

### S1-3. 내 정보

| 단계 | 요청 | 기대 결과 |
| --- | --- | --- |
| 1 | Authorize 없이 `GET /me` | `401` · `TOKEN_EXPIRED` · message "로그인이 필요합니다." |
| 2 | Authorize 후 `GET /me` | `200` · `email`, `name`, `identities[0].provider = "LOCAL"`, `onboarding_completed = false` |
| 3 | `PATCH /me` body: `{"nickname":"총무","height_cm":181}` | `200` · 바뀐 값 반영. 응답에 `birth_year` 필드 없음 |
| 4 | `PATCH /me` body: `{"height_cm": 300}` | `400` · `VALIDATION_ERROR` (120~250 범위) |

### S1-4. 아직 안 된 것 (스켈레톤 확인)

`GET /auth/kakao/login-url` → `501` · `code: NOT_IMPLEMENTED`
설계서에 있으나 아직 구현되지 않은 엔드포인트는 모두 이 응답을 돌려줍니다. Swagger 설명의 **상태** 줄에도 "스켈레톤"이라고 적혀 있습니다.

---

## 2. 팀 생성 · 가입 · 활성화 (FR-04, FR-05, FR-06)

여러 계정이 필요합니다. 아래 표대로 **6명**을 만들어 두면 이후 시나리오를 전부 돌릴 수 있습니다.

| 이메일 | 이름 | 역할(예정) |
| --- | --- | --- |
| manager@test.com | 매니저 | 팀 생성자 |
| p1@test.com ~ p4@test.com | 팀원1~4 | 일반 팀원 |
| stranger@test.com | 외부인 | 팀에 속하지 않은 사람 |

> Swagger에서 계정을 바꾸려면 Authorize → Logout → 다른 토큰 입력.
> 터미널이 편하면 아래 curl 예시를 쓰세요.

```bash
API=http://localhost:8000/api/v1
signup() { curl -s -X POST $API/auth/signup -H 'Content-Type: application/json' \
  -d "{\"email\":\"$1\",\"password\":\"password123\",\"name\":\"$2\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'; }
M=$(signup manager@test.com 매니저)
P1=$(signup p1@test.com 팀원1); P2=$(signup p2@test.com 팀원2)
P3=$(signup p3@test.com 팀원3); P4=$(signup p4@test.com 팀원4)
S=$(signup stranger@test.com 외부인)
```

### S2-1. 팀 생성 → 팀 코드 발급 → 생성자는 MANAGER

| 단계 | 계정 | 요청 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 매니저 | `POST /teams` body: `{"name":"화요농구","home_court":"서초체육관"}` | `201` · `id`, `team_code` (대문자+숫자 8자리) |
| 2 | 매니저 | `GET /teams/{id}` | `status: "PENDING"` · `member_count: 1` · `my_role: "MANAGER"` · `owner.name: "매니저"` |

```bash
TEAM=$(curl -s -X POST $API/teams -H "Authorization: Bearer $M" -H 'Content-Type: application/json' -d '{"name":"화요농구"}')
TEAM_ID=$(echo $TEAM | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
CODE=$(echo $TEAM | python3 -c 'import sys,json;print(json.load(sys.stdin)["team_code"])')
echo "team=$TEAM_ID code=$CODE"
```

### S2-2. 팀 코드로 가입, 오류 처리

| 단계 | 계정 | 요청 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 팀원1 | `POST /teams/join` body: `{"team_code":"ZZZZZZZZ"}` | `404` · `TEAM_CODE_NOT_FOUND` |
| 2 | 팀원1 | `{"team_code":"<실제 코드>"}` | `200` · `my_role: "PLAYER"` · `member_count: 2` |
| 3 | 팀원1 | 같은 코드로 다시 가입 | `409` · `ALREADY_MEMBER` |
| 4 | 팀원1 | 소문자로 입력 (`abcd1234` 형태) | `200` — 대문자로 변환해 찾는다 |

> **팀 승인 (사용자 결정):** 새 팀은 `approval_status = PENDING` 으로 시작하고, 관리자가 콘솔(`/admin` → 팀 → 승인 액션)이나 `POST /admin/teams/{id}:approve` 로 승인해야 5명 조건과 함께 `ACTIVE` 가 됩니다. 승인 전에는 일정 등록이 `422 TEAM_NOT_ACTIVE` "관리자 승인이 끝나면…" 으로 막히고, 팀 화면에 "관리자 승인을 기다리는 중이에요" 배너가 보입니다. 아래 S2-3 은 승인이 끝난 뒤 기준입니다 (자동 테스트는 `team_approval_required=false` 로 돌고, 승인 흐름은 16장에서 따로 검증).

### S2-3. 5명이 되면 ACTIVE (FR-06)

| 단계 | 계정 | 요청 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 팀원2, 팀원3 가입 후 | `GET /teams/{id}` | `member_count: 4` · `status: "PENDING"` |
| 2 | 팀원4 가입 후 | `GET /teams/{id}` | `member_count: 5` · **`status: "ACTIVE"`** |

```bash
for T in $P1 $P2 $P3 $P4; do curl -s -X POST $API/teams/join -H "Authorization: Bearer $T" -H 'Content-Type: application/json' -d "{\"team_code\":\"$CODE\"}" > /dev/null; done
curl -s $API/teams/$TEAM_ID -H "Authorization: Bearer $M" | python3 -m json.tool
```

### S2-4. 내 팀 목록

`GET /me/teams` (팀원1) → `items[0]`에 `team_name`, `team_code`, `role: "PLAYER"`, `member_count: 5`

---

## 3. 권한 (3.3절 권한 매트릭스, FR-07)

### S3-1. 외부인은 팀을 볼 수 없다

| 계정 | 요청 | 기대 결과 |
| --- | --- | --- |
| 외부인 | `GET /teams/{id}` | `403` · `NOT_A_MEMBER` |
| 외부인 | `GET /teams/{id}/players` | `403` · `NOT_A_MEMBER` |

### S3-2. 플레이어는 매니저 기능을 쓸 수 없다

| 계정 | 요청 | 기대 결과 |
| --- | --- | --- |
| 팀원1 | `PATCH /teams/{id}` body: `{"name":"x"}` | `403` · `FORBIDDEN_ROLE` |
| 팀원1 | `POST /teams/{id}/code:regenerate` | `403` · `FORBIDDEN_ROLE` |
| 팀원1 | `DELETE /teams/{id}/players/{아무 player_id}` | `403` · `FORBIDDEN_ROLE` |
| 매니저 | 위 세 요청 | 모두 `200` / `204` |

### S3-3. 실력 수치 마스킹 (FR-24, 13.1절 Q3)

같은 `GET /teams/{id}/players` 를 두 계정으로 호출해 응답 필드를 비교합니다.

| 계정 | 응답 항목 |
| --- | --- |
| 팀원1 (PLAYER) | `skill_grade`, `playable_positions` 등 — **`skill_overall` 없음** |
| 매니저 (MANAGER) | 위 + `skill_overall`, `prior_overall`, `skill_axes`, `avg_margin`, `quarters_played` |

> 아직 설문·경기 기록이 없어서 값은 대부분 `null`이지만, **필드 자체가 있고 없고**가 확인 대상입니다.

`?sort=skill` 은 매니저에게만 의미가 있고, `?kind=GUEST` 는 지금은 빈 목록이 나옵니다 (게스트 등록 미구현).

---

## 4. 매니저 권한 위임 · 회수 · 팀원 제외 (FR-07)

`GET /teams/{id}/players` (매니저)로 각자의 `id`(= player_id)를 먼저 확인하세요.
`GET /teams/{id}`의 `my_player_id` 가 내 player_id 입니다.

### S4-1. 마지막 매니저는 강등할 수 없다

| 계정 | 요청 | 기대 결과 |
| --- | --- | --- |
| 매니저 | `PATCH /teams/{id}/players/{매니저 본인 player_id}/role` body: `{"role":"PLAYER"}` | `422` · `CANNOT_DEMOTE_LAST_MANAGER` |

### S4-2. 권한 부여 후에는 강등 가능

| 단계 | 계정 | 요청 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 매니저 | `PATCH .../players/{팀원1 player_id}/role` `{"role":"MANAGER"}` | `200` · `role: "MANAGER"` |
| 2 | 매니저 | `PATCH .../players/{본인 player_id}/role` `{"role":"PLAYER"}` | `200` — 이제 팀원1이 매니저 |
| 3 | 원래 매니저 | `PATCH /teams/{id}` | `403` · `FORBIDDEN_ROLE` (권한이 사라졌는지 확인) |
| 4 | 팀원1 | `PATCH /teams/{id}` `{"name":"목요농구"}` | `200` |

### S4-3. 팀원 제외 → 인원 미달이면 PENDING으로 되돌아감

| 단계 | 계정 | 요청 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 팀원1(현 매니저) | `DELETE /teams/{id}/players/{원래 매니저 player_id}` | `204` |
| 2 | 팀원1 | `GET /teams/{id}` | `member_count: 4` · **`status: "PENDING"`** |
| 3 | 원래 매니저 | `GET /teams/{id}` | `403` · `NOT_A_MEMBER` (제외됐으므로) |
| 4 | 원래 매니저 | `POST /teams/join` 같은 코드 | `200` · 재가입되며 `member_count: 5`, 다시 `ACTIVE`. **`my_role: "PLAYER"`** (제외 전 매니저였어도 권한은 돌아오지 않음) · `my_player_id`는 제외 전과 동일 (기록 승계) |

**DB에서 보는 법** — 제외는 행 삭제가 아니라 상태 변경입니다.
```bash
docker compose exec db psql -U hoops -d hoops -c "select id, display_name, role, status from players order by id"
```
재가입 전에는 `REMOVED`, 재가입 후 같은 행이 `ACTIVE`로 바뀌어야 합니다 (새 행이 생기지 않음).

### S4-4. 팀 코드 재발급

| 단계 | 계정 | 요청 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 매니저 | `POST /teams/{id}/code:regenerate` | `200` · 새 `team_code` |
| 2 | 외부인 | 옛 코드로 `POST /teams/join` | `404` · `TEAM_CODE_NOT_FOUND` |
| 3 | 외부인 | 새 코드로 가입 | `200` |

---

## 5. 스키마 · 마이그레이션 확인 (6장)

### S5-1. 테이블 28개가 있다

```bash
docker compose exec db psql -U hoops -d hoops -c "\dt"
```
`alembic_version` 을 제외하고 28개. 설계서 6.1절 표의 엔터티가 전부 보여야 합니다.

### S5-2. 제약이 실제로 걸려 있다

아래 INSERT는 **모두 실패해야** 정상입니다.

```bash
# 게스트인데 user_id가 있음 → CHECK 위반
docker compose exec db psql -U hoops -d hoops -c \
 "insert into players (team_id,user_id,kind,display_name,joined_at) values (1,1,'GUEST','x',now())"

# 허용되지 않은 열거값 → CHECK 위반
docker compose exec db psql -U hoops -d hoops -c \
 "update teams set status='FOO' where id=1"

# chemistry 쌍은 a < b 여야 함
docker compose exec db psql -U hoops -d hoops -c \
 "insert into chemistry_scores (player_a_id,player_b_id) values (2,1)"
```

### S5-3. 마이그레이션 왕복

```bash
cd backend
uv run alembic downgrade base   # 전부 삭제
uv run alembic upgrade head     # 다시 생성
uv run alembic current          # → 0001 (head)
```

---

## 6. 자동 테스트로 한 번에 확인 (1~4장)

위 1~4장을 코드로 옮긴 것이 `backend/tests/` 입니다.

```bash
docker compose up -d db
cd backend
uv run pytest -q
```

| 테스트 | 검증 내용 |
| --- | --- |
| `test_all_spec_endpoints_declared` | 설계서 7.3절의 엔드포인트 62개가 전부 라우터에 있음 |
| `test_common_schemas_present` | 7.2절 공통 스키마가 OpenAPI에 노출됨 |
| `test_signup_login_me` | S1-1, S1-2, S1-3 |
| `test_validation_error_shape` | 400 응답 형식 |
| `test_unauthenticated_and_forbidden` | S1-3 1번, S3-1 |
| `test_team_create_join_activate` | S2 전체, S3-2, S3-3, S4 전체 |
| `test_not_implemented_endpoints_return_501` | S1-4 |

> 주의: 테스트는 각 케이스가 끝날 때 **모든 테이블을 비웁니다.** Swagger로 만든 데이터가 있는 상태에서 돌리면 사라집니다.

---

## 7. 온보딩 설문 (F1, survey-feature-spec)

### S7-1. 설문 화면 흐름 (프론트: http://localhost:5173/survey)

| 단계 | 조작 | 기대 결과 |
| --- | --- | --- |
| 1 | 새 계정으로 회원가입 (키 입력, 출생연도 항목 없음) | 가입 직후 설문 화면으로 이동. 진행률 바 1/11 |
| 2 | 단일선택 문항에서 답 하나 선택 | 잠깐 뒤 **자동으로 다음 문항**으로 넘어감 (다음 버튼을 누를 필요 없음) |
| 3 | "수행 가능한 포지션을 선호하는 순서대로" 에서 SF → PG 순으로 탭 | 칩에 1, 2 순번 배지. 다중선택이라 자동 넘김 없음 → 다음 |
| 4 | "희소 자원 확인" 화면에서 1번·5번 둘 다 답함 | 두 줄 모두 답하면 자동 넘김 |
| 5 | 마지막 체력 문항 답하고 **제출하기** | 홈으로 이동, 홈 상단 "설문 안 함" 배너가 사라짐. 설문에 "동호회 내 위치" 문항은 없음 |
| 6 | 주소창에 `/survey` 다시 입력 | 즉시 홈으로 리다이렉트 (재응답 UI 노출 안 함) |

### S7-1b. 팀 가입 직후 "이 동호회에서 내 실력 위치"

| 단계 | 조작 | 기대 결과 |
| --- | --- | --- |
| 1 | 팀 코드로 가입 | 팀 상세가 아니라 **"이 동호회에서 본인의 실력 위치는?"** 한 문항 화면으로 이동 |
| 2 | 상위 30% 선택 | 저장 후 팀 상세로 이동 |
| 3 | "나중에 할게요"로 건너뛴 경우 | 팀 상세 상단에 주황색 안내 카드가 남아 있고, 프로필 탭 팀별 등급에도 "아직 안 알려줬어요" 링크 |
| 4 | 프로필 → 팀별 등급 → "바꾸기" | 같은 화면에서 수정 가능 (팀마다 따로) |

### S7-2. API로 확인

| 요청 | 기대 결과 |
| --- | --- |
| `GET /surveys/onboarding` (인증 불필요) | `version: 2`, `questions` 12개 (A2 A3 B1 B2 B3 C1 C2 D1 D3A D3B E1 E2). 키·선호 포지션·동호회 내 위치 문항 없음 |
| `PUT /teams/{id}/self-rank` body `{"level":"TOP30"}` | `200` · `teams[].self_rank_level: "TOP30"`. 다른 팀 id 로 호출하면 `403 NOT_A_MEMBER` |
| `POST /surveys/onboarding/responses` 문항 하나 빼고 제출 | `400 VALIDATION_ERROR` · `details[].field`에 빠진 문항 코드 |
| 단일선택 문항에 선택지 2개 | `400` |
| 정상 제출 | `201` · `onboarding_completed: true`, `playable_positions`가 D1 에서 고른 **순서 그대로** |
| 같은 계정으로 다시 제출 | `409 ALREADY_SUBMITTED` |

### S7-3. 팀 내 z-score (스펙 5절)

전제: 2장에서 만든 팀(매니저 + 팀원 4명). **응답자가 5명 미만이면 등급이 계산되지 않습니다.**

| 단계 | 조작 | 기대 결과 |
| --- | --- | --- |
| 1 | 팀원 1~4가 설문 제출 + 팀 가입 후 자기 위치를 서로 다르게 (상위 10% / 상위 30% / 중간 / 하위 30%) | `GET /me/profile` → `teams[0].survey_sample_size: 4`, 등급은 아직 C(0점) |
| 2 | 매니저도 설문 제출 + 자기 위치 하위 10% → 응답자 5명 | 매니저로 `GET /teams/{id}/players?sort=skill` → `prior_overall`이 양수~음수로 갈리고 상위 10% 응답자가 첫 줄 |
| 3 | 팀원 1로 같은 API 호출 | `skill_grade`만 있고 `prior_overall` 필드 없음 (마스킹) |
| 4 | 프로필 탭 → "팀별 등급" | 등급 원형 배지, "응답자 5명 기준" 문구, 내 위치 표시 |
| 5 | 프로필 탭 → 포지션 → **수정** → C, SF 순으로 탭 → 저장 | 배지가 "C 선호 · SF" 순으로 바뀜. `GET /me/profile` → `playable_positions: ["C","SF"]` |

DB에서 보기:
```bash
docker compose exec db psql -U hoops -d hoops -c "select p.display_name, pr.prior_overall, pr.prior_source, pr.skill_confidence from players p join player_profiles pr on pr.player_id=p.id order by pr.prior_overall desc nulls last"
```

---

## 8. 일정 · RSVP (F4)

### S8-1. 일정 등록과 응답

| 단계 | 계정 | 조작 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 매니저 | 팀 상세 → 일정 탭 → **+ 일정 등록** (팀이 PENDING이면 버튼 비활성) | 등록 화면 |
| 2 | 매니저 | 날짜·시간·장소 입력 → 등록 | 일정 상세로 이동, "응답 중" 배지, 참석 0 / 미응답 N |
| 3 | 팀원1 | 홈 → 다가오는 일정 카드(미응답 배지) → 상세 → **참석** | 배지가 참석으로, 참석 수 +1 |
| 4 | 팀원1 | **불참** 눌러 변경 | 즉시 반영 (마감 전이므로) |
| 5 | 매니저 | 일정 수정으로 응답 마감을 과거로 → 팀원1이 다시 참석 | 토글 비활성 + "응답이 마감되었어요" (`422 RSVP_CLOSED`) |
| 6 | 매니저 | 참석자 목록에서 회원 카드의 **참석 처리** | 매니저 대리 응답은 마감과 무관하게 성공 |
| 7 | 매니저 | 우측 상단 **취소** | 상태 "취소됨", 목록에 취소 배지 |

### S8-2. 참석 현황 요약

참석자가 늘어날 때 요약 카드를 확인합니다.
- 포지션 칩(PG/SG/SF/PF/C)에 인원 수. **사람당 가장 선호하는 포지션 하나만** 세므로 합이 참석 인원을 넘지 않는다. 참석자 카드에도 선호 포지션 하나만 보인다.
- 게스트 수·"클럽 평균 가정" 문구는 표시하지 않는다 (초대 시트에서 안내).
- 참석 / 미응답 / 불참 목록은 제목을 탭해 접고 펼 수 있다 (불참은 기본 접힘).
- 경고: 참석 10명 미만 / 1번 가능자 2명 미만 / 빅맨(4·5번) 2명 미만 — '가능' 기준.
- **실력 등급은 매니저에게만** 보인다. 플레이어 계정에서는 참석자·팀원·프로필 어디에도 등급이 없다.

---

## 9. 게스트 (F13, guest-feature-spec)

### S9-1. 플레이어가 게스트 초대 (FR-10 · FR-11 · FR-11a)

| 단계 | 계정 | 조작 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 팀원1 | 일정 상세 → **+ 게스트로 초대할 사람이 있어요** | 바텀시트: 오른쪽 위 × 닫기, 이름, 실력 1~5, 선호 포지션, 가능 포지션, "나와 같은 팀으로" 토글 |
| 1b | 팀원1 | 예전에 초대한 적이 있으면 시트 상단 "이전에 초대한 사람 불러오기" 칩 탭 | 이름·실력·포지션·같은 팀 요청이 그대로 채워지고 수정 후 추가 가능. 같은 게스트 레코드가 재사용됨 |
| 2 | 팀원1 | 이름 "김게스트", 실력 4, SF, 토글 ON → 참석자에 추가 | 참석 목록에 게스트 배지 + "팀원1 초대 · 팀원1와 같은 팀 희망" |
| 3 | 팀원1 | 이름만 "박무명"으로 추가 | 카드에 `?` 배지 (실력 정보 없음), 요약 경고에 "게스트 1명은 클럽 평균" |
| 4 | 팀원2 | 같은 일정에서 "김게스트"를 다시 등록 | "같은 이름의 게스트가 있어요" 목록 → 선택하면 재사용, "다른 사람이에요"면 새 레코드 |

### S9-2. 권한 (FR-10a)

| 계정 | 조작 | 기대 결과 |
| --- | --- | --- |
| 팀원2 | 팀원1이 등록한 게스트 카드 | 수정/삭제 버튼 없음 |
| 팀원2 | API `PATCH /events/{id}/guests/{pid}` | `403 FORBIDDEN_NOT_OWNER` · "이 게스트를 등록한 사람만 수정할 수 있어요" |
| 팀원1 | 수정 → 실력 5로 변경 | 등급 배지 변경 |
| 매니저 | 같은 카드 | 수정/삭제 버튼 보임, 수정 가능 |
| 팀원1 | 삭제 | 참석 목록에서 사라짐. `GET /teams/{id}/guests?q=김` 에는 여전히 있음 (레코드 보존, FR-12) |
| 누구나 | 팀 상세 → 팀원 탭 / 팀원 관리 | 게스트는 **보이지 않음** (해당 일정 화면에서만 보임) |

### S9-3. 묶기 제안 (매니저용 API)

| 요청 | 기대 결과 |
| --- | --- |
| 매니저 `GET /events/{id}/assignment/suggestions` | 토글 ON인 게스트와 등록자 쌍 (둘 다 참석일 때만) |
| 등록자(팀원1)가 불참으로 바꾼 뒤 재조회 | 빈 목록 (대상 불참 → 제안 자동 무효) |
| 팀원1로 호출 | `403 FORBIDDEN_ROLE` |

> 배정 화면(S-12)은 아직 초안이라 제안 배지는 API로만 확인합니다.

### S9-4. 게스트가 회원가입했을 때 기록 이어받기 (FR-13)

| 단계 | 계정 | 조작 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 팀원1 | 게스트 "최단골" 등록 | — |
| 2 | 신규 | 이름 "최단골"로 회원가입 → 팀 코드로 가입 | — |
| 3 | 매니저 | 팀원 관리 화면 | 상단에 "기록 이어받기 제안: 게스트 최단골 → 회원 최단골" 카드 |
| 4 | 매니저 | **병합** | 게스트 목록에서 사라지고, `GET /players/{guest}:merge` 재호출 시 `409 ALREADY_MERGED` |
| 5 | 매니저 | API `POST /players/{guest}:unmerge` | 게스트가 다시 목록에 나타남 (되돌리기) |

이름이 같아도 자동 병합하지 않습니다. 동명이인일 수 있어서 매니저 확인이 필요합니다.

---

## 10. 자동 테스트 (전체)

```bash
cd backend && uv run pytest -q     # 15개
```

| 파일 | 검증 내용 |
| --- | --- |
| `test_openapi.py` | 명세 엔드포인트 전부 선언, 공통 스키마 |
| `test_auth_team.py` | 1~4장 |
| `test_survey_guest_event.py` | 7~9장 (템플릿 시드, 검증·1회 제출, 팀 내 z-score, 포지션, 일정·RSVP·마감, 게스트 등록·권한·재사용·동명이인, 묶기 제안, 병합 후보·병합·되돌리기) |

---

## 11. 매니저 실력 정렬 (F14)

매니저(manager@demo.com)로 로그인해서 진행합니다.

| 단계 | 조작 | 기대 결과 |
| --- | --- | --- |
| 1 | 팀 상세 → 매니저 도구 → **실력 정렬** | 20명 카드가 실력순으로 나열. 처음이라 "현재 활성 정렬" 문구 없음 |
| 2 | 카드를 드래그하거나 ↑↓로 순서 변경 (예: 맨 아래 사람을 1위로) → **이 순서로 저장** | 팀 상세로 이동 |
| 3 | `GET /teams/1/players?sort=skill` (매니저) | 1위로 올린 사람의 `prior_overall`이 이전보다 올라감 (설문 0.5 + 정렬 0.5) |
| 4 | 다시 실력 정렬 화면 | "현재 활성 정렬: 오늘 저장본" 표시, 저장 버튼에 "(새 버전)" |
| 5 | `GET /teams/1/rankings` | 이력 2개, 최신만 `is_active: true` |
| 6 | 팀원 계정으로 `GET /teams/1/rankings/latest` | `403 FORBIDDEN_ROLE` |

---

## 12. 팀 배정 (F5 · F6 · F7 · F15)

### S12-1. 배정 실행 화면 (S-12)

| 단계 | 조작 | 기대 결과 |
| --- | --- | --- |
| 1 | 홈 → 일요 정기전 → **팀 배정하러 가기** | 대기 칸에 참석자 14명 칩 (등급 배지 · 선호 포지션 · 게스트 G). 상단에 "묶기 제안 1: 게스트 허웅를 문경은님과 같은 팀으로" |
| 2 | 제안 **승인** (또는 **무시** → 카드가 흐려진 채 남고 "무시 취소"로 되돌림) | 두 칩에 같은 색 테두리, 아래 "묶음: 게스트 허웅 · 문경은" |
| 2b | 상단 **직전 회차 제약** | 지난주 배정에 쓴 묶음(허웅·문경은)이 불러와짐 |
| 3 | 칩 2개 탭 → **같은 팀으로 묶기** | 두 번째 묶음 생성 |
| 4 | 칩 7개를 묶어 보기 | 빨간 경고 "묶음 그룹 인원(7명)이 팀 정원(7명)을 넘어요" 는 아님 → 8개 묶으면 경고 + 실행 버튼 비활성 (FR-20) |
| 5 | 칩 1개 탭 → **블랙에 배치** | 블랙 사전 배치 칸으로 이동 |
| 5b | 칩 3개 탭 → **갈라놓기 (최대 2명)** | 가장 먼저 고른 사람은 빠지고 나중 2명만 갈라놓기 |
| 5d | 사전 배치 칸의 **화이트로 →** / **← 블랙으로** | 반대 팀 칸으로 이동. **빼기**는 대기 칸으로 |
| 5c | 대기 칸 제목 옆 **설정 초기화** | 묶기·갈라놓기·사전 배치가 모두 비워짐 |
| 6 | 하단 경고 "게스트 1명은 실력 정보가 없어 클럽 평균으로 가정해요" 확인 후 **3가지 안으로 팀 짜기** | 결과 화면으로 이동 |

### S12-2. 결과 화면 (S-13)

| 단계 | 조작 | 기대 결과 |
| --- | --- | --- |
| 1 | 실력 우선 / 친화도 우선 / 종합 탭 | 세 안의 편성이 서로 다름. 상단에 "예상 평균 차이 N점/쿼터"와 "균형 점수 (낮을수록 좋음)" |
| 2 | 각 안에서 | 묶은 두 사람이 항상 같은 팀(🔗), 사전 배치(📌)가 지정한 팀, 갈라놓은 사람(✂)이 다른 팀, 양 팀에 PG와 PF/C 가능자가 있음, 게스트가 한쪽에 몰리지 않음 |
| 3 | "이렇게 나눈 이유" | 팀별 평균, 묶음 반영, 게스트 계산 방식이 문장으로 |
| 4 | 한 명만 탭 → **선택한 1명을 화이트로 옮기기 →** | 한 명이 일방 이동(홀수 인원 대응). "손으로 수정됐어요" 안내 + 이름 옆 ↔ |
| 4a | 🔗 묶인 사람을 탭 | 묶음 전체가 함께 선택되고, 옮기기·맞교체 시 그룹이 통째로 움직임 (예: "블랙 3명 ↔ 화이트 1명") |
| 4b | 양 팀에서 골라 **맞교체 ↔** | 선택한 사람들이 서로 팀을 바꾸고 예상 평균 차이 재계산 |
| 4e | 팀 카드 제목 아래 | "평균 신장 NNN.Ncm" (키를 입력한 회원 기준, 게스트 제외) |
| 4c | 안내 줄의 **수동 수정 초기화** | 알고리즘이 낸 원래 편성으로 복원 |
| 4d | 한 팀이 5명이 되도록 옮기려고 시도 | "팀에 최소 5명은 남아야 해요" (`422 INVALID_SWAP`) |
| 5 | 묶인 사람을 골라 옮기기 | "같은 팀으로 묶인 사람은 개별로 옮길 수 없어요" (`422 INVALID_SWAP`) |
| 5b | 갈라놓은(✂) 사람을 탭 | 상대 팀의 짝이 자동으로 함께 선택되고 "두 명의 팀을 서로 바꾸기"만 가능 (한 명 이동 불가) |
| 6 | **이 안으로 확정** | 확정 결과 화면으로 이동. 일정 상태가 "마감"으로 바뀜 |

### S12-3. 확정 결과 (S-14)

| 계정 | 조작 | 기대 결과 |
| --- | --- | --- |
| 팀원 (m01 서장훈) | 홈 → 일정 → "팀 배정이 확정됐어요 — 결과 보기" | 상단에 내 팀·배정 포지션, 우리 팀·상대 팀 명단. **평균 실력·등급 없음**, 문장 설명만 |
| 팀원 | 팀 상세 → 일정 탭 | 일정 카드 아래 확정 결과 패널: 왼쪽 "우리 팀 블랙" 카드(팀원 한 줄씩, 나 강조), 오른쪽 "상대 팀 화이트" 카드, 아래에 예상 평균 차이 · 균형 점수 · 평균 신장 |
| 팀원 | 홈 일정 카드 | "배정 확정 · 화이트 SF" 한 줄 |
| 매니저 | 같은 화면 | 팀별 평균 배지와 등급 배지 보임. 우측 상단 "재배정" |
| 매니저 | 재배정 → 실행 → 다른 안 확정 | 새 결과로 교체. `GET /events/1/assignments` 에 실행 이력 2개 |
| 매니저 | 확정된 후보안에 교체 시도 (API) | `409 ALREADY_ADOPTED` |

### S12-4. 실현 불가능한 제약 (API)

`POST /events/1/assignments:validate` 로 확인합니다 (참석 14명 → 7/7).

| 제약 | 기대 코드 |
| --- | --- |
| `lock_groups: [8명]` | `LOCK_GROUP_TOO_LARGE` |
| 같은 두 사람을 lock 과 separate 에 | `CONSTRAINT_CONFLICT` |
| `pins` 로 한 팀에 8명 | `SQUAD_OVERFLOW` |
| `lock_groups: [6명, 5명, 3명]` | `LOCK_PARTITION_INFEASIBLE` (7명씩 두 팀을 만들 조합 없음) |
| 참석하지 않은 사람 id | `PLAYER_NOT_IN_TEAM` |

---

## 13. 쿼터 기록 · 실력 갱신 (F8 · F10)

기록은 활동이 끝난 뒤 매니저가 한 번에 입력합니다. 로테이션 자동 제안(F17)은 서비스에 넣지 않았습니다.

### S13-1. 기록 입력 (S-15)

| 단계 | 계정 | 조작 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 매니저 | 일요 정기전(지난주, 배정 확정됨) 상세 → **경기 후 쿼터 기록하기** (일정 시작 시각 전에는 버튼이 없음) | 1쿼터 카드에 블랙/화이트 출전 체크 그리드가 확정 팀원으로 미리 5명씩 체크됨 |
| 2 | 매니저 | 스코어 −/+ 또는 키패드로 12 : 9 입력 (두 자리까지), 쿼터 길이 12분 | 상단 합계 "블랙 12 : 9 화이트" |
| 3 | 매니저 | **+ 쿼터 추가** | 직전 라인업이 복사된 2쿼터 카드. 체크를 바꿔 로테이션 반영 |
| 4 | 매니저 | 한쪽 체크를 4명으로 | 빨간 "4/5"와 하단 경고, 저장 버튼 비활성 |
| 5 | 매니저 | 화면을 벗어났다 돌아오기 | "저장하지 않은 입력을 되살렸어요" (이 기기 임시 보관) |
| 6 | 매니저 | **경기 후 일괄 저장** | 일정 상세로 이동, 일정 상태 "종료", "경기 기록 N쿼터 — 보기 · 수정" 버튼 |
| 7 | 팀원 | 같은 일정 → 결과 보기 | 총점, 쿼터별 스코어와 라인업, 출전 쿼터 수. 실력 수치는 없음 |

### S13-2. API로 확인

| 요청 | 기대 결과 |
| --- | --- |
| `POST /events/{id}/quarters` 블랙 4명·화이트 6명 | `400 INVALID_LINEUP_SIZE` · "블랙 팀 4명이 선택되었어요" |
| 같은 quarter_no 로 다시 POST | `409 QUARTER_EXISTS` |
| 12분 쿼터 12:9 | 블랙 라인업 `raw_margin 3`, `normalized_margin 2.5` (= 3 × 10/12), 화이트는 −3 / −2.5 |
| `PUT /events/{id}/quarters` 3개 → 2개 | `{created:3,…}` 다음 `{updated:2, deleted:1}` |
| `DELETE /quarters/{id}` 로 전부 삭제 | 일정 상태 `CLOSED` 로 복귀 |

### S13-3. 실력 갱신과 롤백 (9.2절 · 13.2절)

매니저로 `GET /teams/1/players?sort=skill` 을 보며 확인합니다.

| 단계 | 조작 | 기대 결과 |
| --- | --- | --- |
| 1 | 팀에서 쿼터가 기록된 **첫 두 회차**에 하위 팀이 크게 이기는 기록 저장 | `skill_overall` 은 그대로 (사전값과 동일), `quarters_played` 만 증가 |
| 2 | 세 번째 회차 기록 저장 | 이긴 팀 5명은 상승, 진 팀 5명은 하락, 안 뛴 사람은 그대로. `skill_confidence` 상승 |
| 3 | 30점 차 쿼터와 15점 차 쿼터를 각각 추가해 비교 | 같은 변화량 (±15 클리핑) |
| 4 | 방금 추가한 쿼터 삭제 | 모든 수치가 삭제 전과 **정확히** 같아짐 (팀 전체 재계산) |
| 5 | 게스트로 뛴 사람이 가입해 병합 | 회원의 `quarters_played` 에 게스트 시절 출전이 합산 |

> 데모 데이터에는 지난 5주 동안 회차 5개(쿼터 8·8·8·8·6개)가 기록되어 있습니다. 앞의 두 회차는 게이트 안이고 세 번째 회차부터 실력 지표에 반영되어, 팀 관리 화면에서 실력 수치가 사전값과 달라진 것을 볼 수 있습니다.

---

## 14. 피어 투표 · 선수 통계 (F9 · F10 · F11, peer-vote-spec + 사용자 결정)

케미는 코트 마진으로 측정하지 않고 투표로 선언받습니다 (9.4절). 투표는 **일정 종료 시각이 지나면 자동으로 열리고**, 쿼터 기록 여부와 무관합니다. 받는 항목은 **"다음에 같이 뛰고 싶은 사람"만** — 같은 팀 최대 2명 + 상대 팀 최대 2명 (배정이 없던 회차는 합계 4명). 빈 제출도 응답으로 칩니다. "오늘 잘한 사람" 투표는 받지 않습니다.

### S14-1. 투표 화면 (S-16, http://localhost:5173/events/{id}/vote)

| 단계 | 계정 | 조작 | 기대 결과 |
| --- | --- | --- | --- |
| 0 | 아무나 | 홈 "다가오는 일정" | 아직 진행하지 않은 일정만. 지난 일정은 팀 화면 일정 탭에서 5개씩 페이지로 (예정 먼저, 지난 일정은 흐리게) |
| 1 | m01 | 이번 주 일정(아직 안 끝남) 상세 | 투표 버튼이 없음. 주소로 직접 `/events/{id}/vote` 진입 시 "일정이 끝나면 투표할 수 있어요" 안내만 |
| 2 | m07 (미응답자) | **팀 화면** 일정 탭 | 지난주 일정 카드 **위에** 주황 배너 "9/6 (일) 10:00~12:00 - 경기 후 투표하기". 일정 상세에는 투표 카드가 없음 (매니저 독려 카드만) |
| 3 | m07 | 배너 탭 | "같은 팀에서 0/2" · "상대 팀에서 0/2" 두 그룹. 후보는 그날 참석자 전원(본인 제외, 게스트 포함), 블랙/화이트 배지 |
| 4 | m07 | 우리 팀에서 2명 선택 + 각각 이유 칩 선택 | 이유까지 고르면 그 팀 목록이 접히고 선택한 이름 칩 + **수정** 버튼만 남음(이유를 고르기 전에는 접히지 않음, 헤더의 **접기**로 수동 접기 가능). 상대 팀 이유 칩은 "패스 플레이가 인상적이었어요"처럼 상대 맥락 문구 |
| 5 | m07 | 선택한 사람 칩 아래 이유 칩 "패스가 좋았어요" 탭 | 주황으로 선택. 다시 탭하면 해제 |
| 6 | m07 | **N명 제출** | 완료 화면(내 선택과 이유 표시). 팀 화면 배너가 사라짐 |
| 7 | m09 | 아무도 선택하지 않고 **선택 없이 제출** | 확인 후 빈 제출. 응답 완료로 처리되고 다시 열 수 없음 (건너뛰기 버튼은 없음) |
| 8 | m01 | 이미 응답한 사람으로 재진입 | 폼 대신 완료 화면 |

### S14-2. 매니저 독려 (스펙 3.3절)

| 단계 | 계정 | 조작 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 매니저 | 지난주 일정 상세 | "피어 투표 현황 8/12명 응답" 카드와 진행 막대 (데모 데이터 기준). 게스트는 분모에서 제외 |
| 2 | 매니저 | **독려 메시지 공유** | 모바일: 공유 시트 열림 · 데스크톱: 클립보드에 "🏀 오늘 경기 어떠셨나요? … 👉 링크" 복사 안내 |
| 3 | — | 기다려 보기 | 자동 발송·리마인더는 없음. 매니저가 누를 때만 |

### S14-3. API로 확인

| 요청 | 기대 결과 |
| --- | --- |
| `GET /events/{아직 안 끝난 id}/post-game-survey` | `403 SURVEY_NOT_OPEN` |
| `GET /events/{지난주 id}/post-game-survey/candidates` (불참자 토큰) | `403 NOT_ATTENDEE` |
| `POST …/post-game-survey` 본인 지목 | `400 SELF_VOTE_NOT_ALLOWED` |
| 같은 팀 3명 | `400` "같은 팀에서는 최대 2명" |
| `vote_type: BEST_PERFORMER` | `400` "'다음에 같이 뛰고 싶은 사람' 투표만 받아요" |
| 정상 제출 후 다시 제출 | `409 ALREADY_SUBMITTED` |
| `GET /events/{id}/post-game-survey/share-message` (플레이어 토큰) | `403 FORBIDDEN_ROLE` |
| `GET /players/{남의 id}/stats` (플레이어 토큰) | `403 FORBIDDEN_ROLE` · 본인/매니저는 200 |

### S14-4. 선호 점수 집계 (스펙 4.1절)

`chemistry_scores` 를 DB 에서 확인합니다 (`docker compose exec db psql -U app -d app -c "select * from chemistry_scores"`).

| 상황 | 기대 결과 |
| --- | --- |
| A→B, B→A 서로 지목, 함께 참석 1회 | `pref_score 1.00`, `pref_mutual true`, `together_events 1` |
| A→B 한 방향만 | `pref_score 0.50` (양방향 평균), `pref_mutual false` |
| 두 사람이 한 회차 더 함께 참석했지만 지목 없음 | 분모 2 → 최신 회차 지목이면 `0.50`, 오래된 회차 지목이면 `0.45` (0.9 가중) |

### S14-5. 내 기록 (S-17 프로필)

| 단계 | 계정 | 기대 결과 |
| --- | --- | --- |
| 1 | m01 | 프로필 "기록": 참석 회차 · 출전 쿼터 · 이긴 쿼터, 회차별 평균 점수 차 막대(플러스 오렌지 · 마이너스 로즈), 내가 뛴 쿼터 목록 **10개씩 페이지 이동**(팀·스코어·포지션, +/− 배지). **실력 수치·등급은 없음** |
| 3 | 허재 · m01 · m03~m06 (두 팀 소속) | 홈 팀 목록에 "일요 코트메이트"와 "수요 픽업" 두 카드. **기본 팀으로 설정하기**를 누르면 기본 배지가 옮겨지고, 프로필 상단 팀 선택 칩의 기본 선택이 바뀜 (`PATCH /me {primary_team_id}`) |
| 4 | m01 | 기록 목록이 20개 이상이라 "‹ 최근 / 이전 ›" 페이지 이동이 보임 |
| 2 | m15 (지난주 불참) | "아직 경기 기록이 없어요" |

### S14-6. 매니저 실력 지표 화면 (팀 관리 → 지표 보기)

| 단계 | 계정 | 조작 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | 매니저 | 팀 화면 우측 상단 **팀 관리** | 팀 코드 · 실력 정렬 카드 · 회원 목록. 정렬 칩(실력/포지션/참여)은 한 번 누르면 내림차순 ▼, 다시 누르면 오름차순 ▲. 각 행에 "실력 x.x · 참여 N회", 매니저는 이름 옆 작은 배지, 오른쪽 ⋯(관리) 버튼 |
| 1-c | 매니저 | 유일한 매니저를 ⋯ → 팀에서 제외 | `422 CANNOT_DEMOTE_LAST_MANAGER` "팀에 매니저가 한 명은 남아 있어야 해요" |
| 1-b | 매니저(팀장) | 본인 행 ⋯ → **매니저 해제** | 매니저가 1명뿐이면 "매니저가 1명뿐이라 해제할 수 없어요" 팝업. 다른 매니저가 있으면 "팀장 권한이 OO님에게 넘어가요" 확인 팝업 → 확인 시 팀장이 바뀌고 팀 화면으로 이동 |
| 1-d | m03 (매니저로 지정받은 사람) | 팀 관리 → ⋯ | 매니저 지정·해제 자리에 **팀장 전용** 표시. 지표 보기·제외는 가능. 팀장 행에는 "팀장" 배지 |
| 1-e | 매니저 | 팀 관리 맨 위 팀 이름 카드 **수정** | 팀 이름·소개·홈 코트 수정 후 저장 |
| 1-f | 매니저 | **지난 기록 추가** → 날짜·시간 입력 → 회원 체크 + 게스트 이름 추가 | 같은 이름의 지난 게스트가 있으면 "같은 사람 / 새 게스트로 추가" 확인. 10명 이상이면 쿼터 기록 화면으로 이동해 기록 저장 → 실력 지표에 반영 |
| 2 | 매니저 | 회원 행의 ⋯ → **지표 보기** | 종합 실력(점/쿼터) + 사전값 / 경기 반영 후 / 신뢰도 카드 |
| 3 | 매니저 | 아래로 | "어떻게 계산됐나": 설문 사전값 · 매니저 정렬 순위(N명 중 k위) · 코트 마진 잔차 · 피어 투표 지목 수. 세부 6축, 회차별 마진, 최근 쿼터, 실력값 변동 이력(10개씩 페이지) |
| 4 | m01 | 같은 주소 직접 접근 | 403 → "매니저만 볼 수 있어요" |

> 승률·케미 점수 같은 성과 지표는 의도적으로 넣지 않습니다 (9.4절 F11). 배정의 `CHEMISTRY` 전략은 `pref_score` 를 읽습니다.

---

## 15. 자동 테스트 (전체)

```bash
cd backend && uv run pytest -q     # 36개
```

| 파일 | 검증 내용 |
| --- | --- |
| `test_openapi.py` | 명세 엔드포인트 전부 선언(로테이션 제안 제외), 공통 스키마 |
| `test_auth_team.py` | 1~4장 |
| `test_survey_guest_event.py` | 7~9장 |
| `test_ranking_assignment.py` | 11~12장 |
| `test_quarters.py` | 13장 — 라인업 검증·마진 정규화·권한, 일괄 저장 개수, 첫 2회 게이트·갱신 방향·클리핑·삭제 롤백, 병합 게스트 기록 합산 |
| `test_admin_leaderboard.py` | 16장 — 관리자 권한·검색·원시 데이터·보정 이력·감사 로그, 리더보드 참여율/잔차 권한, 팀 승인 흐름 |
| `test_peer_votes.py` | 14장 — 오픈 시점·후보 명단·비참석자, 같은 팀/상대 팀 2명 제한·이유 태그·재제출 규칙, 선호 점수·상호 지목, 독려 메시지, 선수 통계(본인 마스킹·매니저 수치) |

---

## 16. 관리자 콘솔 · 리더보드 (F12 · F11)

### S16-1. 관리자 콘솔 (SQLAdmin, http://localhost:8000/admin)

| 단계 | 계정 | 조작 | 기대 결과 |
| --- | --- | --- | --- |
| 1 | admin@demo.com / demo1234 | 로그인 | 사용자·팀·참가자·실력 프로필·일정·쿼터·투표·정렬·변동 이력·감사 로그 메뉴 |
| 2 | manager@demo.com | 같은 주소 로그인 | 거부 (ADMIN 만) |
| 3 | admin | 실력 프로필·쿼터 출전·변동 이력·감사 로그 | 읽기 전용 (수정 버튼 없음) |
| 4 | admin | 팀 → "목요 픽업"(승인 대기) 체크 → **승인** 액션 | approval_status APPROVED. 회원 5명 이상이면 status ACTIVE. 감사 로그에 TEAM_APPROVE |
| 5 | m08 (목요 픽업 팀장) | 승인 전 팀 화면 | "관리자 승인을 기다리는 중이에요" 배너, 일정 등록 버튼 "(관리자 승인 후 가능)" |

### S16-2. 관리자 API (`/docs` 관리자 태그)

| 요청 | 기대 결과 |
| --- | --- |
| `GET /admin/users?q=서장훈` (admin 토큰) | 1명 · 매니저 토큰이면 `403 FORBIDDEN_ROLE` |
| `GET /admin/players/{id}/raw` | 설문 원본·쿼터별 마진·투표 수신·변동 이력 전체 |
| `PATCH /admin/players/{id}/rating` `{skill_overall: 3.5, reason: "..."}` | `skill_overall`·`prior_overall` 이 3.5, `skill_rating_history(ADMIN_ADJUST)` 와 `audit_logs` 한 줄 추가 |
| `GET /admin/audit-logs` | 최신순 감사 로그 |

### S16-3. 리더보드 (팀 화면 → 팀원 탭 → 리더보드)

| 단계 | 계정 | 기대 결과 |
| --- | --- | --- |
| 1 | m01 | 참여율 · 출전 쿼터 탭. 기간 칩(전체 / 최근 3개월). 등급·잔차는 없음 |
| 2 | 매니저 | 잔차 누적 탭 추가 (플러스 초록 · 마이너스 로즈, 등급 배지) |

---

## 17. 다음 구현 단계에서 추가될 시나리오 (지금은 501)

| 기능 | 핵심 확인 항목 |
| --- | --- |
| 카카오 로그인 · 비밀번호 재설정 | 11.5절 |
