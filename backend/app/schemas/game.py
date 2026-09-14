"""쿼터 기록 스키마 — 7.3절 "경기 기록(F8)" 엔드포인트의 요청/응답 (S-15).

대상 엔드포인트: POST /events/{id}/quarters (1건), PUT /events/{id}/quarters (일괄),
GET /events/{id}/quarters, PATCH|DELETE /quarters/{id}.
(로테이션 자동 제안 F17 은 서비스 범위에서 제외 — 기록은 활동이 끝난 뒤 한 번에 입력하므로 제안이 쓸모없다.)

운영 전제 (2.5절): 그날 팀은 고정(블랙/화이트), 쿼터 수는 7~10회로 유동, 팀당 5명 출전하고
나머지는 로테이션으로 쉰다. 기록은 매니저가 **경기 후** 한 번에 입력한다.

서버가 하는 계산 (6.2절):
    raw_margin        = 내 팀 득점 − 상대 팀 득점
    normalized_margin = raw_margin × (10 / duration_min)        ← 쿼터 길이가 달라도 비교 가능하게
쿼터 저장 시 출전 10명 전원에 대해 일괄 계산한다. 개인 스탯 입력은 없다. 실력 지표에는 이 마진이
아니라 "기대 마진 대비 잔차"가 들어간다 (9.1절·9.2절). 쿼터를 삭제하면 그 마진은 롤백된다.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import Position, Side

# 쿼터 길이(분) — 동호회 쿼터는 보통 8분이고, 시간이 모자라면 짧게 끊는다. 10분을 넘기는 운영은 받지 않는다.
DEFAULT_DURATION_MIN = 8
MIN_DURATION_MIN = 1
MAX_DURATION_MIN = 10


class LineupIn(BaseModel):
    """한 쿼터의 출전자 1명. `QuarterIn.lineups` 원소."""

    player_id: int = Field(description="players.id. 게스트 포함")
    side: Side = Field(description="BLACK / WHITE — 그날 확정된 팀")
    position: Position | None = Field(default=None, description="그 쿼터에 실제로 맡은 포지션. 모르면 생략 (선택)")


class QuarterIn(BaseModel):
    """쿼터 1건 입력 — `POST /events/{id}/quarters`, `QuarterBulkSave.quarters` 원소 (MANAGER 전용, FR-25).

    사이드별 인원이 5명이 아니면 400 INVALID_LINEUP_SIZE ("블랙 팀 4명이 선택되었어요"),
    같은 quarter_no 를 POST 로 다시 보내면 409 QUARTER_EXISTS (수정은 PATCH 나 일괄 PUT).
    """

    quarter_no: int = Field(ge=1, le=30, description="1부터. 회차마다 개수가 다를 수 있다 (하루 최대 30쿼터)")
    black_score: int = Field(ge=0, le=200, description="블랙 팀 득점")
    white_score: int = Field(ge=0, le=200, description="화이트 팀 득점")
    duration_min: int = Field(default=DEFAULT_DURATION_MIN, ge=MIN_DURATION_MIN, le=MAX_DURATION_MIN, description="쿼터 길이(분). 기본 8분, 1~10분. 마진을 10분 기준으로 정규화하는 데 쓴다")
    lineups: list[LineupIn] = Field(min_length=10, max_length=10, description="팀당 5명, 총 10명")


class QuarterUpdate(BaseModel):
    """쿼터 수정 — `PATCH /quarters/{id}` (MANAGER 전용). 보낸 필드만 바꾸고 마진을 재계산한다.

    `lineups` 는 부분 수정이 아니라 통째로 교체다 (보내면 10명 전부).
    """

    black_score: int | None = Field(default=None, ge=0, le=200)
    white_score: int | None = Field(default=None, ge=0, le=200)
    duration_min: int | None = Field(default=None, ge=MIN_DURATION_MIN, le=MAX_DURATION_MIN)
    lineups: list[LineupIn] | None = Field(default=None, min_length=10, max_length=10, description="보내면 10명 전체로 교체")


class QuarterBulkSave(BaseModel):
    """경기 후 한 번에 저장. 목록에 없는 기존 쿼터는 삭제(마진 롤백)된다.

    `PUT /events/{id}/quarters` 요청 (MANAGER 전용). S-15 의 "경기 후 일괄 저장" 버튼이 이걸 부른다.
    `quarter_no` 기준으로 있으면 수정, 없으면 생성, 목록에서 빠졌으면 삭제 — 즉 이 목록이 그 회차
    쿼터의 전체 상태가 된다. 체육관 통신이 불량해도 localStorage 에 모아뒀다 한 번에 보낼 수 있다.
    """

    quarters: list[QuarterIn] = Field(description="그 회차의 모든 쿼터. quarter_no 중복 불가")


class LineupView(BaseModel):
    """출전자 1명의 기록 (서버 계산값 포함). `QuarterView.lineups` 원소."""

    player_id: int
    display_name: str
    side: Side
    position: Position | None
    raw_margin: int = Field(description="내 팀 득점 − 상대 팀 득점. 같은 사이드 5명은 값이 같다")
    normalized_margin: Decimal = Field(description="raw_margin × (10 / duration_min). 10분 환산 코트 마진")


class QuarterView(BaseModel):
    """쿼터 1건 — `POST /events/{id}/quarters` 201, `PATCH /quarters/{id}`, `GET /events/{id}/quarters` items 원소.

    소속 팀원이면 누구나 볼 수 있다 (수치가 실력 지표가 아니라 스코어라 마스킹하지 않는다).
    """

    id: int = Field(description="quarters.id. PATCH/DELETE 의 대상")
    quarter_no: int
    black_score: int
    white_score: int
    duration_min: int
    lineups: list[LineupView] = Field(description="10명. 사이드별 5명")


class QuarterBulkResult(BaseModel):
    """`PUT /events/{id}/quarters` 응답 — 일괄 저장이 실제로 한 일의 개수."""

    created: int = Field(description="새로 만든 쿼터 수")
    updated: int = Field(description="기존 quarter_no 를 덮어쓴 수")
    deleted: int = Field(description="목록에 없어 삭제(마진 롤백)한 수")


class PlayerQuarterCount(BaseModel):
    """참가자별 출전 쿼터 수 — 매니저가 출전 시간 균형을 눈으로 확인하는 용도."""

    player_id: int
    display_name: str
    side: Side
    quarters: int


class QuarterSummary(BaseModel):
    """회차 기록 요약 — S-15 상단과 일정 상세의 결과 카드."""

    quarter_count: int
    black_total: int = Field(description="블랙 팀 총 득점")
    white_total: int
    black_wins: int = Field(description="블랙이 이긴 쿼터 수")
    white_wins: int
    per_player: list[PlayerQuarterCount] = Field(default=[], description="출전 쿼터 수, 사이드별·많은 순")


class QuarterListView(BaseModel):
    """`GET /events/{id}/quarters` 응답."""

    items: list[QuarterView] = Field(description="quarter_no 순")
    summary: QuarterSummary
