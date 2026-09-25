"""경기 후 설문 · 통계 스키마 — 7.3절 "경기 후 설문 · 통계" 엔드포인트의 요청/응답 (F9 · F10 · F11, S-16 · S-17,
피어 투표 설계재설계 반영).

대상 엔드포인트:
- GET  /events/{id}/post-game-survey             내 투표 상태 + 후보 명단 (candidates 와 같은 응답)
- GET  /events/{id}/post-game-survey/candidates  후보 명단 (스펙 5절 신규 경로)
- POST /events/{id}/post-game-survey             투표 제출 (카테고리당 0~2명, 이유 태그 선택)
- GET  /events/{id}/post-game-survey/share-message  매니저 독려 메시지 (카카오톡 공유용)
- GET  /players/{id}/compatible                  나와 잘 맞는 참여자
- GET  /players/{id}/stats, GET /teams/{id}/stats/leaderboard  (스켈레톤)

케미 정책 (9.4절): 케미는 코트 마진으로 **측정하지 않고** 피어 투표로 **선언받는다**. "잘한 사람" 투표는
표시 전용이며 실력 산출에 입력하지 않는다 (스펙 4.2절). 게스트는 투표의 대상은 되지만 응답자는 될 수 없다.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import ReasonTag, VoteType
from app.schemas.common import PlayerCard


class VoteCandidate(BaseModel):
    """투표 후보 한 명 — 그날 참석자(본인 제외, 게스트 포함). 팀은 배지로만 구분한다 (스펙 3.1절)."""

    player: PlayerCard
    squad_no: int | None = Field(default=None, description="확정 배정의 팀 번호 (1=블랙, 2=화이트). 배정이 없으면 None")
    squad_name: str | None = None
    is_same_team: bool | None = Field(default=None, description="응답자와 같은 팀이었는지. 배정이 없으면 None")


class VoteView(BaseModel):
    target_player_id: int
    vote_type: VoteType
    reason_tag: ReasonTag | None = None


class VoteTargets(BaseModel):
    """`GET /events/{id}/post-game-survey` · `.../candidates` 응답 (S-16)."""

    open: bool = Field(description="투표가 열렸는지. 종료 전이면 이 응답 대신 403 SURVEY_NOT_OPEN")
    opens_at: datetime = Field(description="투표가 열리는 시각 = 일정 종료 시각")
    already_submitted: bool = Field(description="이미 제출했으면 true → 프론트는 폼 대신 완료 화면")
    my_votes: list[VoteView] = Field(default=[], description="이미 제출했다면 내가 고른 것")
    candidates: list[VoteCandidate] = Field(description="그날 참석자 전원(본인 제외), 이름순")


class VoteIn(BaseModel):
    """지목 한 건. 카테고리당 최대 2명, 0명도 가능 (스펙 2절)."""

    target_player_id: int = Field(description="지목한 사람의 players.id. 본인이면 400 SELF_VOTE_NOT_ALLOWED")
    vote_type: VoteType = Field(description="PLAY_AGAIN(다음에 같이 뛰고 싶은 사람) / BEST_PERFORMER(오늘 잘한 사람)")
    reason_tag: ReasonTag | None = Field(default=None, description="PLAY_AGAIN 에만. PASS / DEFENSE_HELP / TEMPO / OTHER")


class PostGameSurveyIn(BaseModel):
    """투표 제출 — `POST /events/{id}/post-game-survey`. `votes` 가 비어 있어도 제출(=응답 완료)로 친다."""

    votes: list[VoteIn] = Field(default=[], max_length=4, description="PLAY_AGAIN 0~2명 + BEST_PERFORMER 0~2명")


class ShareMessage(BaseModel):
    """매니저 독려 메시지 — `GET /events/{id}/post-game-survey/share-message` (스펙 3.3절). 자동 발송은 없다."""

    text: str = Field(description="카카오톡 공유 시트에 그대로 넣을 문구 (링크 포함)")
    link: str
    responded: int = Field(description="제출한 사람 수")
    total: int = Field(description="투표 대상 = 참석한 회원 수 (게스트 제외)")
    open: bool
    opens_at: datetime


class MarginPoint(BaseModel):
    """회차 하나의 출전 요약 — 마진 추이 차트의 점 하나."""

    event_id: int
    event_date: str = Field(description="YYYY-MM-DD. 차트 x축")
    title: str | None = None
    quarters: int = Field(description="그 회차에 출전한 쿼터 수")
    avg_normalized_margin: Decimal = Field(description="그 회차 출전 쿼터의 10분 환산 마진 평균 (표시용, 실력 지표 아님)")
    wins: int = Field(default=0, description="출전 쿼터 중 이긴 쿼터 수")
    losses: int = Field(default=0, description="출전 쿼터 중 진 쿼터 수")


class QuarterRecord(BaseModel):
    """내가 뛴 쿼터 한 개 (S-17 기록)."""

    event_id: int
    event_date: str
    quarter_no: int
    side: str = Field(description="BLACK / WHITE")
    my_score: int
    their_score: int
    black_score: int
    white_score: int
    raw_margin: int
    normalized_margin: Decimal
    position: str | None = None


class RankInfo(BaseModel):
    rank_no: int = Field(description="활성 매니저 정렬에서의 순위 (1 = 최상위)")
    total: int
    ranked_at: datetime


class AxisRank(BaseModel):
    """세부 능력 한 축의 팀 내 상대 위치. 절대 점수(0~10)는 축마다 계산식이 달라 비교가 안 되므로 위치로 보여 준다."""

    level: Literal["HIGH", "MID", "LOW"] | None = Field(description="상위 1/3 · 중간 · 하위 1/3. 비교 인원이 부족하면 None")
    percentile: int | None = Field(description="0~100. 팀에서 이 값보다 낮은 사람의 비율 (높을수록 상위)")
    sample: int = Field(description="비교에 쓴 팀원 수 (본인 포함)")


class RatingChange(BaseModel):
    """skill_rating_history 한 줄 (매니저 전용)."""

    source: str
    before_value: Decimal | None
    after_value: Decimal | None
    delta: Decimal | None
    reason: str | None
    created_at: datetime


class PlayerStats(BaseModel):
    """`GET /players/{id}/stats` 응답. 본인은 기록·마진만, 매니저/ADMIN 은 실력 수치·근거까지 (FR-28 · FR-31, 13.1절 Q3)."""

    player: PlayerCard
    events_attended: int = Field(description="참석한 지난 회차 수")
    quarters_played: int = Field(description="누적 출전 쿼터 수 (병합된 게스트 기록 포함)")
    position_distribution: dict[str, int] = Field(description="포지션 코드 → 그 포지션으로 뛴 쿼터 수")
    margin_trend: list[MarginPoint] = Field(description="회차 오름차순")
    recent_quarters: list[QuarterRecord] = Field(default=[], description="최근 쿼터 기록 (최신순, 최대 200개)")
    # --- 아래는 매니저/ADMIN 에게만 채워진다 ---
    skill_grade: str | None = None
    skill_overall: Decimal | None = Field(default=None, description="현재 종합 실력 (쿼터당 기여, 점)")
    prior_overall: Decimal | None = Field(default=None, description="사전값 (설문 + 매니저 정렬)")
    prior_source: str | None = None
    skill_confidence: Decimal | None = None
    cumulative_residual: Decimal | None = None
    skill_axes: dict[str, Decimal | None] = Field(default={})
    skill_axes_rank: dict[str, AxisRank] = Field(default={}, description="축별 팀 내 상대 위치 (설문 기준). 매니저/ADMIN 전용")
    manager_rank: RankInfo | None = None
    play_again_received: int | None = Field(default=None, description="'다음에 같이 뛰고 싶은 사람'으로 지목받은 횟수")
    play_again_mutual: int | None = Field(default=None, description="상호 지목 쌍 수")
    history: list[RatingChange] = Field(default=[], description="실력값 변동 이력 (최신순, 최대 200개)")


class CompatiblePlayer(BaseModel):
    """`GET /players/{id}/compatible` 의 items 원소 (S-17 "잘 맞는 참여자"). 투표 데이터만으로 만든다 (9.4절 F11)."""

    player: PlayerCard
    mutual_play_again: bool = Field(description="서로를 PLAY_AGAIN 으로 지목한 적이 있는지 (상호 선호 — 가장 강한 신호)")
    voted_me_best: int = Field(description="이 사람이 나를 BEST_PERFORMER 로 뽑은 횟수")
    i_voted_best: int = Field(description="내가 이 사람을 BEST_PERFORMER 로 뽑은 횟수")
    together_quarters: int = Field(description="같은 팀으로 함께 출전한 쿼터 수")


class LeaderboardEntry(BaseModel):
    """`GET /teams/{id}/stats/leaderboard` 의 items 원소."""

    rank: int = 0
    player: PlayerCard
    value: Decimal = Field(description="정렬 기준 값. attendance=참여율 0~1, quarters=쿼터 수, residual=잔차 누적(점)")
    detail: str = Field(default="", description="표시용 보조 문구. 예: 4/5회, 29쿼터")
