# HOOPLY — API 명세

전체 명세(OpenAPI 3.0.3)는 `04-API명세-openapi.yaml` 에 있으며 FastAPI 가 코드에서 생성한 것을 그대로 옮긴 것이다. 이 문서는 규약과 엔드포인트 요약이다.

## 1. 공통 규약

- Base URL: `https://hooply-backend.onrender.com/api/v1` (로컬 `http://localhost:8000/api/v1`)
- 인증: `Authorization: Bearer <access_token>` (JWT, access 30분 / refresh 14일). 가입·로그인·카카오 로그인 URL/콜백·설문 템플릿 조회·헬스 체크만 인증 없이 호출.
- 본문: `application/json`, 필드명 `snake_case`, 시각은 ISO 8601(TIMESTAMPTZ).
- 목록: `{ items: [...] }` (ItemList) 또는 `{ items, meta: { page, size, total, has_next } }` (Page).
- 오류: 모든 4xx/5xx 본문은 `ErrorResponse { code, message, details[]{field, reason} }`. 프론트는 `code` 로 분기하고 `message` 를 그대로 노출한다.
- 액션형 경로는 `:동사` 접미사를 쓴다 (`/teams/{id}/code:regenerate`, `/assignments/candidates/{id}:adopt`, `/events/{id}/rsvp:close`).
- 관리자 콘솔(SQLAdmin)은 API 가 아닌 서버 페이지 `/admin` 이다.

## 2. HTTP 상태와 에러 코드

| HTTP | code | 상황 |
| --- | --- | --- |
| 400 | VALIDATION_ERROR, INVALID_LINEUP_SIZE, SELF_VOTE_NOT_ALLOWED, TOKEN_INVALID_OR_EXPIRED | 형식·범위 위반 |
| 401 | INVALID_CREDENTIALS, TOKEN_EXPIRED, KAKAO_AUTH_FAILED | 인증 실패 |
| 403 | FORBIDDEN_ROLE, NOT_A_MEMBER, NOT_ATTENDEE, SURVEY_NOT_OPEN, FORBIDDEN_NOT_OWNER | 권한 부족·아직 열리지 않음 |
| 404 | NOT_FOUND, TEAM_CODE_NOT_FOUND, NOT_ADOPTED_YET, NO_RANKING | 리소스 없음 |
| 409 | EMAIL_DUPLICATED, ALREADY_MEMBER, ALREADY_SUBMITTED, QUARTER_EXISTS, ALREADY_ADOPTED, IDENTITY_ALREADY_LINKED, ALREADY_MERGED | 상태 충돌 |
| 422 | TEAM_NOT_ACTIVE, NOT_ENOUGH_PLAYERS, RSVP_CLOSED, INVALID_SWAP, CANNOT_DEMOTE_LAST_MANAGER, PLAYER_NOT_IN_TEAM, MERGE_KIND_MISMATCH, LOCK_GROUP_TOO_LARGE, CONSTRAINT_CONFLICT, SEPARATE_INFEASIBLE, LOCK_PARTITION_INFEASIBLE, SQUAD_OVERFLOW | 도메인 규칙 위반 (배정 제약 오류는 details 에 문제 인원 포함) |
| 501 | NOT_IMPLEMENTED | 비밀번호 재설정 메일 (미구현) |
| 500 | INTERNAL_ERROR | 서버 오류 |

## 3. 공통 스키마 (`components/schemas`, `$ref` 재사용)

| 스키마 | 용도 |
| --- | --- |
| ErrorResponse, ErrorDetail | 모든 오류 응답 |
| ItemList[T], Page[T], PageMeta | 목록 응답 |
| TokenPair, KakaoTokenPair | 로그인·갱신 결과 (`is_new` 포함) |
| UserSummary, UserDetail, IdentityView | 계정 |
| PlayerCard | 참가자 카드 — 이름·역할·포지션·키·등급(매니저에게만)·신뢰도. 팀원 목록, 참석자, 배정 팀원, 투표 후보 등 어디서나 재사용 |
| PlayerCardDetailed | PlayerCard + 실력 수치·사전값·6축·평균 마진·출전 쿼터·참여 횟수 (MANAGER/ADMIN 전용) |
| TeamDetail, TeamMembershipView, TeamCreated | 팀 |
| EventView, EventCreate/Update, AttendanceView, AttendanceList, AttendanceSummary | 일정·참석 |
| EventGuestCreate/Update, GuestSimilar, GuestPresetView, MergeCandidate | 게스트 |
| SurveyTemplate, SurveyQuestion, SurveyOption, SurveyResponseIn, MyProfile, TeamProfileSummary | 설문·프로필 |
| RankingCreate, RankingView | 매니저 정렬 |
| AssignmentRunRequest, ConstraintSet, PinConstraint, ValidateResult, ConstraintViolation, AssignmentRunView, CandidateView, SquadView, CandidateUpdate, AdoptedAssignment | 배정 |
| QuarterIn, LineupIn, QuarterUpdate, QuarterBulkSave, QuarterBulkResult, QuarterView, QuarterListView, QuarterSummary | 경기 기록 |
| VoteTargets, VoteCandidate, VoteIn, PostGameSurveyIn, ShareMessage, PlayerStats, MarginPoint, QuarterRecord, RatingChange, LeaderboardEntry | 투표·통계 |
| AdminUserRow, PlayerRawData, RatingAdjust, AuditLogView | 관리자 |

## 4. 엔드포인트 요약 (81개)

응답 코드 열의 `200/201/204` 는 성공, 나머지는 위 에러 코드 표의 HTTP 상태다. Path 파라미터는 `{…}`, Query 는 각 엔드포인트의 `parameters`(yaml 참조).

### 인증 · 프로필

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| POST | `/auth/signup` | 이메일 회원가입 | 201 · 409 |
| POST | `/auth/login` | 이메일 로그인 | 200 · 401 |
| GET | `/auth/kakao/login-url` | 카카오 인가 URL 생성 | 200 · 401 |
| GET | `/auth/kakao/callback` | 카카오 콜백 (가입/로그인) | 200 · 401 |
| POST | `/auth/kakao/link` | 기존 계정에 카카오 연결 | 200 · 401 · 409 |
| POST | `/auth/refresh` | 토큰 갱신 | 200 · 401 |
| POST | `/auth/password/forgot` | 비밀번호 재설정 요청 | 202 |
| POST | `/auth/password/reset` | 비밀번호 재설정 | 200 · 400 · 501 |
| GET | `/me` | 내 정보 조회 | 200 |
| PATCH | `/me` | 내 프로필 수정 | 200 |
| POST | `/me/avatar` | 프로필 사진 등록 · 교체 | 200 · 400 |
| DELETE | `/me/avatar` | 프로필 사진 삭제 | 200 |
| GET | `/users/{user_id}/avatar` | 프로필 사진 이미지 (주소의 키로 확인) | 200 · 404 |
| GET | `/me/teams` | 내 소속 팀 목록 | 200 |

### 온보딩 설문

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| GET | `/surveys/onboarding` | 온보딩 설문 템플릿 조회 | 200 |
| POST | `/surveys/onboarding/responses` | 온보딩 설문 응답 제출 | 201 · 400 · 409 |
| GET | `/me/profile` | 내 실력·포지션 프로필 | 200 |
| PUT | `/me/positions` | 가능/선호 포지션 수정 | 200 |
| PUT | `/teams/{team_id}/self-rank` | 이 동호회에서 내 실력 위치 응답 | 200 · 403 |

### 팀 · 참가자

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| POST | `/teams` | 팀 생성 | 201 |
| POST | `/teams/join` | 팀 코드로 가입 | 200 · 404 · 409 |
| GET | `/teams/{team_id}` | 팀 상세 조회 | 200 · 403 |
| PATCH | `/teams/{team_id}` | 팀 정보 수정 | 200 · 403 |
| POST | `/teams/{team_id}/code:regenerate` | 팀 코드 재발급 | 200 · 403 |
| GET | `/teams/{team_id}/players` | 팀원 목록 조회 | 200 |
| PATCH | `/teams/{team_id}/players/{player_id}/role` | 매니저 권한 부여/회수 | 200 · 403 |
| DELETE | `/teams/{team_id}/players/{player_id}` | 팀원 제외 | 204 · 403 |

### 게스트 관리

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| POST | `/teams/{team_id}/guests` | 게스트 레코드 등록 | 201 · 200 |
| GET | `/teams/{team_id}/guests` | 기존 게스트 검색 | 200 |
| GET | `/teams/{team_id}/guests/merge-candidates` | 게스트–회원 병합 후보 | 200 · 403 |
| PATCH | `/players/{player_id}` | 게스트 정보 수정 | 200 · 403 |
| POST | `/players/{guest_player_id}:merge` | 게스트를 회원 계정에 병합 | 200 · 403 · 409 |
| GET | `/me/guest-claims` | 내 것일 수 있는 게스트 기록 | 200 |
| POST | `/players/{guest_player_id}:claim` | 게스트 기록 본인 확인 (병합 / 거절) | 200 · 403 · 409 |
| POST | `/players/{player_id}:unmerge` | 게스트 병합 되돌리기 | 200 · 403 · 404 |

### 매니저 실력 정렬

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| GET | `/teams/{team_id}/rankings/latest` | 현재 활성 정렬 조회 | 200 · 403 · 404 |
| POST | `/teams/{team_id}/rankings` | 새 정렬 버전 저장 | 201 · 403 |
| GET | `/teams/{team_id}/rankings` | 정렬 이력 목록 | 200 · 403 |

### 일정 · 참석

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| POST | `/teams/{team_id}/events` | 일정 등록 | 201 |
| GET | `/teams/{team_id}/events` | 일정 목록 조회 | 200 |
| GET | `/events/{event_id}` | 일정 상세 조회 | 200 |
| PATCH | `/events/{event_id}` | 일정 수정 | 200 |
| DELETE | `/events/{event_id}` | 일정 취소 | 204 |
| POST | `/events/{event_id}/rsvp:close` | 응답 미리 마감 | 200 |
| PUT | `/events/{event_id}/attendance` | 내 참석 응답 | 200 |
| PUT | `/events/{event_id}/attendances/{player_id}` | 매니저 대리 참석 등록 | 200 · 403 |
| GET | `/events/{event_id}/attendances` | 참석 현황 · 포지션 분포 | 200 |
| POST | `/events/{event_id}/guests` | 회차에 게스트 등록 | 201 · 200 |
| PATCH | `/events/{event_id}/guests/{player_id}` | 회차 게스트 수정 | 200 · 403 |
| DELETE | `/events/{event_id}/guests/{player_id}` | 회차 게스트 삭제 (불참 처리) | 204 · 403 |
| GET | `/events/{event_id}/guests/presets` | 이전에 초대한 게스트 목록 | 200 |

### 팀 배정

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| GET | `/events/{event_id}/assignment/suggestions` | 게스트 묶기 제안 목록 | 200 · 403 |
| POST | `/events/{event_id}/assignments` | 팀 배정 실행 | 201 |
| GET | `/events/{event_id}/assignments` | 배정 실행 이력 | 200 |
| POST | `/events/{event_id}/assignments:validate` | 배정 제약 실현가능성 검사 | 200 |
| GET | `/events/{event_id}/assignments/last-constraints` | 직전 회차 제약 불러오기 | 200 · 404 |
| GET | `/assignments/runs/{run_id}` | 배정 실행 결과 조회 | 200 |
| PATCH | `/assignments/candidates/{candidate_id}` | 후보안 선수 교체 | 200 · 409 |
| POST | `/assignments/candidates/{candidate_id}:reset` | 수동 수정 초기화 | 200 · 409 |
| POST | `/assignments/candidates/{candidate_id}:adopt` | 후보안 확정 | 200 · 409 |
| GET | `/events/{event_id}/assignment/adopted` | 확정된 배정 결과 | 200 · 404 |

### 경기 기록

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| POST | `/events/{event_id}/quarters` | 쿼터 1건 추가 | 201 · 400 · 409 |
| PUT | `/events/{event_id}/quarters` | 쿼터 일괄 저장 | 200 · 400 |
| GET | `/events/{event_id}/quarters` | 쿼터 기록 조회 | 200 |
| PATCH | `/quarters/{quarter_id}` | 쿼터 수정 | 200 · 400 · 403 |
| DELETE | `/quarters/{quarter_id}` | 쿼터 삭제 (마진 롤백) | 204 · 403 |

### 경기 후 설문 · 통계

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| GET | `/events/{event_id}/post-game-survey` | 피어 투표 후보 명단 · 내 상태 | 200 · 403 |
| POST | `/events/{event_id}/post-game-survey` | 피어 투표 제출 | 201 · 400 · 403 · 409 |
| GET | `/events/{event_id}/post-game-survey/candidates` | 피어 투표 후보 명단 | 200 · 403 |
| GET | `/events/{event_id}/post-game-survey/share-message` | 피어 투표 독려 메시지 (매니저) | 200 · 403 |
| GET | `/players/{player_id}/compatible` | 나와 잘 맞는 참여자 | 200 · 403 |
| GET | `/players/{player_id}/stats` | 선수 통계 (참여 이력 · 쿼터 기록 · 실력 지표) | 200 · 403 |
| GET | `/teams/{team_id}/stats/leaderboard` | 팀 리더보드 | 200 · 403 |

### 관리자

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| GET | `/admin/users` | 전체 사용자 검색 | 200 |
| GET | `/admin/players/{player_id}/raw` | 선수 원시 데이터 열람 | 200 · 403 |
| PATCH | `/admin/players/{player_id}/rating` | 실력 지표 수동 보정 | 200 · 403 |
| GET | `/admin/audit-logs` | 감사 로그 조회 | 200 |
| GET | `/admin/teams` | 팀 목록 (승인 대기 우선) | 200 |
| POST | `/admin/teams/{team_id}:approve` | 팀 승인 | 200 |
| POST | `/admin/teams/{team_id}:reject` | 팀 승인 거절 | 200 |

### 시스템

| Method | Path | 기능 | 응답 코드 |
| --- | --- | --- | --- |
| GET | `/health` | 헬스 체크 | 200 |

## 5. 화면 ↔ API 대응

| 화면 | 사용 API |
| --- | --- |
| S-01/02/24 인증 | POST /auth/signup, POST /auth/login, POST /auth/refresh, GET /auth/kakao/login-url, GET /auth/kakao/callback, POST /auth/kakao/link |
| S-03 설문 · S-23 내 위치 | GET /surveys/onboarding, POST /surveys/onboarding/responses, PUT /teams/{id}/self-rank |
| S-04 홈 · S-17 프로필 | GET /me, PATCH /me, GET /me/teams, GET /me/profile, PUT /me/positions, GET /players/{id}/stats |
| S-17 프로필 사진 | POST /me/avatar, DELETE /me/avatar, GET /users/{id}/avatar |
| S-04/S-07 게스트 기록 확인 | GET /me/guest-claims, POST /players/{id}:claim |
| S-05/06/07 팀 | POST /teams, POST /teams/join, GET /teams/{id}, GET /teams/{id}/players, GET /teams/{id}/events, GET /events/{id}/assignment/adopted |
| S-08 팀 관리 · S-19 정렬 · S-20 지표 · S-21 리더보드 | PATCH /teams/{id}, POST …/code:regenerate, PATCH …/players/{pid}/role, DELETE …/players/{pid}, GET …/guests/merge-candidates, POST /players/{id}:merge, GET/POST /teams/{id}/rankings, GET /players/{id}/stats, GET /teams/{id}/stats/leaderboard |
| S-09/10/11 일정·참석·게스트 | POST /teams/{id}/events, GET/PATCH/DELETE /events/{id}, POST /events/{id}/rsvp:close, PUT /events/{id}/attendance, PUT /events/{id}/attendances/{pid}, GET /events/{id}/attendances, POST/PATCH/DELETE /events/{id}/guests…, GET /events/{id}/guests/presets |
| S-12/13/14 배정 | GET /events/{id}/assignment/suggestions, POST /events/{id}/assignments:validate, POST /events/{id}/assignments, GET /events/{id}/assignments/last-constraints, GET /assignments/runs/{id}, PATCH /assignments/candidates/{id}, POST …:reset, POST …:adopt, GET /events/{id}/assignment/adopted |
| S-15 쿼터 · S-22 지난 기록 | GET/PUT/POST /events/{id}/quarters, PATCH/DELETE /quarters/{id} (+ 일정·참석·게스트 API) |
| S-16 투표 | GET/POST /events/{id}/post-game-survey, GET …/candidates, GET …/share-message |
| S-18 관리자 | GET /admin/users, GET /admin/teams, POST /admin/teams/{id}:approve|:reject, GET /admin/players/{id}/raw, PATCH /admin/players/{id}/rating, GET /admin/audit-logs |
