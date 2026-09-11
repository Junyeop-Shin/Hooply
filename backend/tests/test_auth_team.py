"""9.8절 1순위: 인증 · 팀 · 참가자 흐름.

설계서 9.8절 개발 순서의 1순위(인증 · 팀 · 참가자)에 대한 통합 테스트. HTTP 요청으로
라우터 → 서비스 → Postgres까지 실제로 태우며, 응답의 `code` 필드(7.4절 에러 코드 체계)로
도메인 규칙이 지켜지는지 확인한다.

각 테스트 위의 주석에 검증 대상 요구사항(FR-xx) 또는 설계 규칙을 적어 두었다.
픽스처 `client`·`signup`은 `conftest.py` 참조. DB는 테스트마다 비워진다.
"""


# 검증: FR-01 이메일 회원가입·로그인, 7.4절 401 INVALID_CREDENTIALS / 409 EMAIL_DUPLICATED,
#       13.2절 6항(비밀번호 관련 값이 응답에 새지 않는다).
def test_signup_login_me(client, signup):
    headers = signup()
    r = client.get("/api/v1/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "a@example.com"
    # 이메일 가입은 auth_identities에 LOCAL identity 1건을 만든다 (6.2절 users 1:N identities)
    assert body["identities"][0]["provider"] == "LOCAL"
    # 해시조차 응답에 포함되면 안 된다 — UserDetail 스키마에 필드가 없어야 한다
    assert "password" not in body and "password_hash" not in body
    assert "birth_year" not in body  # 출생연도는 받지도, 보여주지도 않는다

    # 틀린 비밀번호 → 401. "계정 없음"과 같은 코드를 써서 가입 여부를 노출하지 않는다
    r = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS"

    # 같은 이메일 재가입 → 409 (users.email UNIQUE)
    r = client.post("/api/v1/auth/signup", json={"email": "a@example.com", "password": "password123", "name": "x"})
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_DUPLICATED"


# 검증: 7.4절 "형식 오류는 400 VALIDATION_ERROR" + 공통 ErrorResponse 형태 {code, message, details[]}.
#       FastAPI 기본값(422)이 아니라 설계서대로 400으로 내려오는지가 핵심이다.
def test_validation_error_shape(client):
    r = client.post("/api/v1/auth/signup", json={"email": "not-an-email", "password": "short", "name": ""})
    assert r.status_code == 400
    assert r.json()["code"] == "VALIDATION_ERROR"
    # details[]에 어느 필드가 왜 틀렸는지 담겨야 프론트가 인라인 에러를 그릴 수 있다 (5.4절)
    assert r.json()["details"]


# 검증: 3.3절 권한 매트릭스 — 미로그인은 401, 소속되지 않은 팀 조회는 403 NOT_A_MEMBER.
def test_unauthenticated_and_forbidden(client, signup):
    assert client.get("/api/v1/me").status_code == 401
    owner = signup("owner@example.com")
    team_id = client.post("/api/v1/teams", json={"name": "농구팀"}, headers=owner).json()["id"]
    # 로그인은 했지만 이 팀의 player가 아닌 사용자 → 403 (404가 아님: 팀 존재는 숨기지 않는다)
    stranger = signup("s@example.com", name="이정현")
    r = client.get(f"/api/v1/teams/{team_id}", headers=stranger)
    assert r.status_code == 403 and r.json()["code"] == "NOT_A_MEMBER"


# 검증: FR-04 팀 생성·코드 발급, FR-05 코드 가입, FR-06 5명 활성화(양방향), FR-07 권한 부여·
#       제외, 7.2절 PlayerCard/PlayerCardDetailed 마스킹, 7.4절 CANNOT_DEMOTE_LAST_MANAGER.
#       하나의 팀을 생성부터 팀원 제외까지 끝까지 끌고 가는 시나리오 테스트다.
def test_team_create_join_activate(client, signup):
    owner = signup("owner@example.com", name="매니저")
    r = client.post("/api/v1/teams", json={"name": "화요농구", "home_court": "서초체육관"}, headers=owner)
    assert r.status_code == 201
    team_id, code = r.json()["id"], r.json()["team_code"]
    # 6.2절 teams.team_code: CHAR(8), 대문자+숫자
    assert len(code) == 8 and code == code.upper()

    # 생성 직후: 회원 1명뿐이므로 PENDING, 생성자는 자동 MANAGER (FR-04)
    detail = client.get(f"/api/v1/teams/{team_id}", headers=owner).json()
    assert detail["status"] == "PENDING" and detail["my_role"] == "MANAGER" and detail["member_count"] == 1

    # 5.4절 예외: 없는 코드 → TEAM_CODE_NOT_FOUND, 이미 소속된 팀 재가입 → ALREADY_MEMBER
    assert client.post("/api/v1/teams/join", json={"team_code": "ZZZZZZZZ"}, headers=owner).json()["code"] == "TEAM_CODE_NOT_FOUND"
    assert client.post("/api/v1/teams/join", json={"team_code": code}, headers=owner).json()["code"] == "ALREADY_MEMBER"

    members = []
    for i in range(4):
        h = signup(f"m{i}@example.com", name=f"팀원{i}")
        members.append(h)
        r = client.post("/api/v1/teams/join", json={"team_code": code}, headers=h)
        assert r.status_code == 200, r.text
    # FR-06: 5명 이상이면 ACTIVE
    # 생성자 1명 + 가입 4명 = 활성 회원 5명 = teams.min_members 기본값. 이 시점에 일정 기능이 열린다.
    # (refresh_team_status가 join 때마다 COUNT를 다시 세므로 4명째까지는 PENDING이어야 한다)
    assert client.get(f"/api/v1/teams/{team_id}", headers=owner).json()["status"] == "ACTIVE"

    # 플레이어는 등급만, 매니저는 수치 필드 포함
    # 3.3절 "선수 상세 데이터 조회: MANAGER △(등급·요약), PLAYER ✕" — 플레이어 응답에는
    # skill_overall 키 자체가 없어야 한다 (값이 null인 것으로는 부족). 9.2절 표시 정책.
    p = client.get(f"/api/v1/teams/{team_id}/players", headers=members[0]).json()["items"]
    assert len(p) == 5 and "skill_overall" not in p[0]
    m = client.get(f"/api/v1/teams/{team_id}/players", headers=owner).json()["items"]
    assert "skill_overall" in m[0]

    # 플레이어가 매니저 API 호출 → 403
    # 13.4절 "권한: 플레이어 토큰으로 매니저 API를 호출해 403이 나오는지"
    r = client.patch(f"/api/v1/teams/{team_id}", json={"name": "x"}, headers=members[0])
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN_ROLE"

    # 마지막 매니저 강등 불가
    # 매니저가 0명이 되면 일정 등록·배정·기록을 아무도 못 하는 팀이 된다. 그래서 유일한
    # 매니저는 스스로도 PLAYER로 내려갈 수 없다 (7.3절 PATCH .../role, 422 도메인 규칙).
    my_pid = detail["my_player_id"]
    r = client.patch(f"/api/v1/teams/{team_id}/players/{my_pid}/role", json={"role": "PLAYER"}, headers=owner)
    assert r.status_code == 422 and r.json()["code"] == "CANNOT_DEMOTE_LAST_MANAGER"

    # 권한 위임 후 강등 가능
    # FR-07: 다른 플레이어에게 MANAGER를 부여하면 매니저가 2명이 되므로 이제 본인 강등이 통과한다.
    other_pid = next(x["id"] for x in m if x["id"] != my_pid)
    assert client.patch(f"/api/v1/teams/{team_id}/players/{other_pid}/role", json={"role": "MANAGER"}, headers=owner).status_code == 200
    assert client.patch(f"/api/v1/teams/{team_id}/players/{my_pid}/role", json={"role": "PLAYER"}, headers=owner).status_code == 200

    # /me/teams는 팀별 내 역할을 함께 돌려준다 (7.3절 GET /me/teams). 강등이 반영되어야 한다.
    teams = client.get("/api/v1/me/teams", headers=owner).json()["items"]
    assert teams[0]["role"] == "PLAYER" and teams[0]["member_count"] == 5

    # 팀장 승계: 팀장이 스스로 내려오면 남은 매니저(other)가 팀장이 된다. 이제 other 만 권한을 바꿀 수 있고,
    # 원래 팀장은 매니저로 다시 지정돼도(위임 매니저) 남의 역할을 바꿀 수 없다 (플레이어 < 매니저 < 팀장)
    other_user_id = next(x["user_id"] for x in m if x["id"] == other_pid)
    assert client.get(f"/api/v1/teams/{team_id}", headers=members[0]).json()["owner"]["id"] == other_user_id
    other_headers = next(h for h in members if client.get("/api/v1/me", headers=h).json()["id"] == other_user_id)
    assert client.patch(f"/api/v1/teams/{team_id}/players/{my_pid}/role", json={"role": "MANAGER"}, headers=other_headers).status_code == 200
    third_pid = next(x["id"] for x in m if x["id"] not in (my_pid, other_pid))
    r = client.patch(f"/api/v1/teams/{team_id}/players/{third_pid}/role", json={"role": "MANAGER"}, headers=owner)
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN_ROLE"  # 위임 매니저는 권한을 못 준다
    # 마지막 매니저는 제외도 안 된다: other(팀장) 를 PLAYER 로 내린 뒤 유일한 매니저(owner) 제외 시도
    assert client.patch(f"/api/v1/teams/{team_id}/players/{other_pid}/role", json={"role": "PLAYER"}, headers=other_headers).status_code == 200
    r = client.delete(f"/api/v1/teams/{team_id}/players/{my_pid}", headers=owner)
    assert r.status_code == 422 and r.json()["code"] == "CANNOT_DEMOTE_LAST_MANAGER"
    # other 가 내려오면서 팀장이 다시 owner 로 돌아왔으므로 owner 가 other 를 다시 매니저로 올릴 수 있다
    assert client.get(f"/api/v1/teams/{team_id}", headers=owner).json()["owner"]["id"] != other_user_id
    assert client.patch(f"/api/v1/teams/{team_id}/players/{other_pid}/role", json={"role": "MANAGER"}, headers=owner).status_code == 200

    # 새 매니저가 팀원 제외 → 4명 → PENDING (FR-06 역방향)
    # members 리스트는 가입 순서, m(플레이어 카드 목록)은 API 정렬 순서라 둘의 인덱스가 다를 수
    # 있다. other_pid가 m에서 몇 번째인지 찾아 같은 순번의 헤더를 꺼내 새 매니저 토큰을 얻는다.
    new_manager = members[[x["id"] for x in m if x["id"] != my_pid].index(other_pid)]
    r = client.delete(f"/api/v1/teams/{team_id}/players/{my_pid}", headers=new_manager)
    assert r.status_code == 204
    # 활성 회원이 4명으로 줄었으므로 refresh_team_status가 다시 PENDING으로 내린다
    assert client.get(f"/api/v1/teams/{team_id}", headers=new_manager).json()["status"] == "PENDING"
    # 제외된 사람(players.status=REMOVED)은 더 이상 팀원이 아니다 → 403 NOT_A_MEMBER
    assert client.get(f"/api/v1/teams/{team_id}", headers=owner).json()["code"] == "NOT_A_MEMBER"

    # 재가입: 기존 players 행이 되살아나(새 행 없음) 기록은 승계되지만, 역할은 PLAYER로 초기화된다.
    # (제외 전 MANAGER였던 사람이 코드만으로 매니저 권한을 되찾으면 안 된다)
    r = client.post("/api/v1/teams/join", json={"team_code": code}, headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["my_player_id"] == my_pid and r.json()["my_role"] == "PLAYER"
    assert r.json()["status"] == "ACTIVE" and r.json()["member_count"] == 5


# 검증: 아직 구현되지 않은 엔드포인트(카카오 OAuth, 온보딩 설문)는 404가 아니라
#       501 NOT_IMPLEMENTED로 응답한다. test_openapi가 "경로가 선언되어 있는가"를 보는 것과
#       짝을 이루어, 스텁이 조용히 사라지거나 엉뚱한 코드로 바뀌지 않았는지 지킨다.
def test_not_implemented_endpoints_return_501(client):
    # 남은 스텁이 없다 — 이 테스트는 "스텁이 조용히 사라지지 않았는지" 대신 헬스 체크만 확인한다
    assert client.get("/health").json() == {"status": "ok"}
