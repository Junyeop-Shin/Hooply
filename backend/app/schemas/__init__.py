"""app.schemas — 7장 API 명세의 요청/응답 Pydantic 모델.

FastAPI 는 이 모델들로 요청을 검증하고, 응답을 직렬화하고, OpenAPI(/docs) 문서를 자동 생성한다.
즉 여기 적힌 docstring 과 `Field(description=...)` 이 곧 프론트가 보는 API 문서다 (11.4절).

- common.py     : 7.2절 공통 스키마 (페이징, PlayerCard 계열, SquadView)
- auth.py       : 인증·내 정보          (/auth/*, /me, /me/teams)
- survey.py     : 온보딩 설문·포지션    (/surveys/onboarding, /me/profile, /me/positions)
- team.py       : 팀·게스트·매니저 정렬 (/teams/*, /players/*, /rankings)
- event.py      : 일정·참석             (/events/*, attendances)
- assignment.py : 팀 배정·제약          (/assignments/*)
- game.py       : 쿼터 기록             (/quarters/*)
- peer.py       : 피어 설문·통계        (post-game-survey, stats, compatible, leaderboard)
- admin.py      : 관리자 콘솔           (/admin/*)

이름 규칙: `...Request`/`...In`/`...Create`/`...Update` 는 요청 본문, `...View`/`...Detail` 은
응답. ORM 행을 그대로 응답으로 바꾸는 모델은 `common.ORMModel` 을 상속한다.
"""
