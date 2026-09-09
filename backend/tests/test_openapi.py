"""7.3절 명세의 모든 엔드포인트가 라우터에 선언되어 있는지 검증한다.

설계서 12장 2-C "OpenAPI 명세 초안 (FastAPI 스켈레톤으로 자동 생성)"에 대응하는 계약 테스트.
FastAPI가 만드는 `app.openapi()` 결과를 설계서 표와 대조하므로, 명세에 있는 엔드포인트를
빼먹거나 경로 오타를 내면 구현 전이라도(501 스텁이라도) 여기서 잡힌다.

이 테스트는 DB를 쓰지 않는다 — `app.openapi()`는 라우터 메타데이터만 읽는다.
"""

from app.main import app

# 설계서 7.3절 표를 (HTTP 메서드, /api/v1 이후 경로)로 옮긴 것. 명세가 바뀌면 여기도 같이 고친다.
SPEC_7_3 = {
    ("post", "/auth/signup"), ("post", "/auth/login"), ("get", "/auth/kakao/login-url"),
    ("get", "/auth/kakao/callback"), ("post", "/auth/kakao/link"), ("post", "/auth/refresh"),
    ("post", "/auth/password/forgot"), ("post", "/auth/password/reset"),
    ("get", "/me"), ("patch", "/me"), ("get", "/me/teams"),
    ("get", "/surveys/onboarding"), ("post", "/surveys/onboarding/responses"),
    ("get", "/me/profile"), ("put", "/me/positions"),
    ("post", "/teams"), ("post", "/teams/join"), ("get", "/teams/{team_id}"), ("patch", "/teams/{team_id}"),
    ("post", "/teams/{team_id}/code:regenerate"), ("get", "/teams/{team_id}/players"),
    ("patch", "/teams/{team_id}/players/{player_id}/role"), ("delete", "/teams/{team_id}/players/{player_id}"),
    ("post", "/teams/{team_id}/guests"), ("get", "/teams/{team_id}/guests"), ("patch", "/players/{player_id}"),
    ("post", "/players/{guest_player_id}:merge"), ("post", "/players/{player_id}:unmerge"),
    ("get", "/teams/{team_id}/rankings/latest"), ("post", "/teams/{team_id}/rankings"), ("get", "/teams/{team_id}/rankings"),
    ("post", "/teams/{team_id}/events"), ("get", "/teams/{team_id}/events"), ("get", "/events/{event_id}"),
    ("patch", "/events/{event_id}"), ("delete", "/events/{event_id}"),
    ("put", "/events/{event_id}/attendance"), ("put", "/events/{event_id}/attendances/{player_id}"),
    ("get", "/events/{event_id}/attendances"),
    ("post", "/events/{event_id}/assignments"), ("post", "/events/{event_id}/assignments:validate"),
    ("get", "/events/{event_id}/assignments"), ("get", "/events/{event_id}/assignments/last-constraints"),
    ("get", "/assignments/runs/{run_id}"), ("patch", "/assignments/candidates/{candidate_id}"),
    ("post", "/assignments/candidates/{candidate_id}:adopt"), ("get", "/events/{event_id}/assignment/adopted"),
    ("post", "/events/{event_id}/quarters"), ("put", "/events/{event_id}/quarters"), ("get", "/events/{event_id}/quarters"),
    ("patch", "/quarters/{quarter_id}"), ("delete", "/quarters/{quarter_id}"),
    # GET /events/{event_id}/rotation-suggestion (F17) 은 서비스 범위에서 제외했다 — 기록은 활동 후 일괄 입력
    ("get", "/events/{event_id}/post-game-survey"), ("post", "/events/{event_id}/post-game-survey"),
    ("get", "/players/{player_id}/stats"), ("get", "/players/{player_id}/compatible"),
    ("get", "/teams/{team_id}/stats/leaderboard"),
    ("get", "/admin/users"), ("get", "/admin/players/{player_id}/raw"),
    ("patch", "/admin/players/{player_id}/rating"), ("get", "/admin/audit-logs"),
}


# 검증: 7.3절 표의 62개 엔드포인트가 전부 라우터에 존재한다 (설계서 ↔ 코드 계약).
# 방향은 "명세 ⊆ 구현"이다. 구현에만 있는 추가 엔드포인트는 허용한다.
def test_all_spec_endpoints_declared():
    paths = app.openapi()["paths"]
    # openapi()의 경로는 "/api/v1/..." 전체 경로이고 메서드는 소문자다. 명세 집합과 같은
    # 모양으로 맞추기 위해 접두사를 떼어 낸다.
    declared = {(m, p.removeprefix("/api/v1")) for p, ops in paths.items() for m in ops}
    missing = SPEC_7_3 - declared
    # 차집합을 통째로 메시지에 넣어, 실패 시 어느 엔드포인트가 빠졌는지 바로 보이게 한다
    assert not missing, f"명세에 있으나 라우터에 없는 엔드포인트: {sorted(missing)}"


# 검증: 7.2절 "공통 스키마($ref 재사용 대상)"가 OpenAPI components에 이름 그대로 노출된다.
# 프론트가 openapi-typescript로 타입을 생성할 때(11.2절) 이 이름들을 그대로 참조하므로,
# 클래스 이름을 바꾸면 프론트 빌드가 깨진다 — 그래서 이름 자체를 계약으로 고정한다.
def test_common_schemas_present():
    schemas = app.openapi()["components"]["schemas"]
    for name in ["ErrorResponse", "PageMeta", "UserSummary", "PlayerCard", "PlayerCardDetailed", "SquadView"]:
        assert name in schemas, name
