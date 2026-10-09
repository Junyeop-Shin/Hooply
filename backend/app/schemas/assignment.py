"""팀 배정 스키마 — 7.3절 "팀 배정(F5, F15, F16)" 엔드포인트의 요청/응답 (S-12 ~ S-14).

대상 엔드포인트:
- POST /events/{id}/assignments            배정 실행 → `AssignmentRunView` (후보안 3개)
- POST /events/{id}/assignments:validate   제약 실현가능성만 검사 → `ValidateResult`
- GET  /events/{id}/assignments            실행 이력, GET /assignments/runs/{run_id} 단건
- GET  /events/{id}/assignments/last-constraints   직전 회차 제약 → `ConstraintSet`
- PATCH /assignments/candidates/{id}       두 선수 교체 → 재계산된 `CandidateView`
- POST /assignments/candidates/{id}:adopt  확정, GET /events/{id}/assignment/adopted 확정 결과

용어 (9.5절·9.6절):
- run        : 배정 실행 1회. 같은 회차에서 재실행하면 run 이 하나 더 쌓인다 (이력 보존)
- candidate  : 전략(SKILL / CHEMISTRY / BALANCED)별 후보안. run 당 최대 3개, 확정은 1개
- squad      : 후보안 안의 팀 (블랙/화이트, 3팀이면 레드). squad_no 는 1부터
- constraint : 그 회차에만 적용되는 LOCK(묶기) / SEPARATE(갈라놓기) / PIN(미리 배치)
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import Strategy
from app.schemas.common import SquadView

MAX_GROUPS = 30  # 묶기 · 갈라놓기 그룹 수 상한
MAX_GROUP_SIZE = 30  # 그룹 하나의 인원 상한
MAX_PINS = 60  # 미리 배치 인원 상한


class PinConstraint(BaseModel):
    """미리 배치(PIN) 하나 — "이 사람은 squad_no 팀에 미리 꽂아둔다" (F16, 2순위).

    S-12 에서 참석자 칩을 팀 칸에 직접 드롭한 것. LOCK 과 달리 팀까지 지정한다.
    한 팀에 정원보다 많이 PIN 하면 422 SQUAD_OVERFLOW.
    """

    player_id: int
    squad_no: int = Field(ge=1, description="1부터 team_count까지. 1=블랙, 2=화이트 (기본 이름 기준)")


class ConstraintSet(BaseModel):
    """lock_groups·separate_groups는 페어가 아니라 그룹 배열 (9.6절).

    한 회차의 배정 제약 묶음. `AssignmentRunRequest.constraints` 로 보내고,
    `AssignmentRunView.constraints` / `GET .../last-constraints` 로 돌려받는다.
    값은 전부 `player_id` 이며 **그 회차에만** 적용된다 — 다음 회차 화면은 빈 상태로 시작하고
    "직전 회차 제약 불러오기"만 제공한다 (FR-18).

    LOCK 은 목적함수 페널티가 아니라 Union-Find 슈퍼노드로 처리되므로 어떤 전략을 골라도
    묶음이 깨지지 않는다 (FR-17). A-B, B-C 를 따로 묶으면 A-B-C 가 자동으로 한 그룹이 된다.
    """

    # 요청 크기 상한 — 한 회차 참석자는 많아야 수십 명이라 넉넉하다. 큰 본문으로 서버를 붙잡지 못하게
    lock_groups: list[Annotated[list[int], Field(max_length=MAX_GROUP_SIZE)]] = Field(
        default=[], max_length=MAX_GROUPS, description=f"각 안쪽 배열이 '반드시 같은 팀' 그룹 (2명 이상). 그룹 {MAX_GROUPS}개 · 그룹당 {MAX_GROUP_SIZE}명까지",
    )
    separate_groups: list[Annotated[list[int], Field(max_length=MAX_GROUP_SIZE)]] = Field(
        default=[], max_length=MAX_GROUPS, description=f"각 안쪽 배열이 '반드시 다른 팀' 그룹. 그룹 {MAX_GROUPS}개 · 그룹당 {MAX_GROUP_SIZE}명까지",
    )
    pins: list[PinConstraint] = Field(default=[], max_length=MAX_PINS, description=f"특정 팀에 고정할 인원 ({MAX_PINS}명까지)")


class AssignmentRunRequest(BaseModel):
    """배정 실행 / 검증 요청 — `POST /events/{id}/assignments`, `.../assignments:validate` (MANAGER 전용, FR-16).

    참석(ATTEND) 확정자 전원이 배정 대상이며 게스트도 포함된다. 참석자 < team_count × 5 면
    422 NOT_ENOUGH_PLAYERS, 제약이 실현 불가능하면 422 LOCK_* / CONSTRAINT_CONFLICT / SQUAD_OVERFLOW
    (어떤 그룹·선수가 문제인지 `details[]` 에 담긴다).
    """

    team_count: int = Field(
        default=2, ge=2, le=3,
        description="팀 수 2 또는 3. 2팀은 완전 탐색으로 최적해를 보장하고, 3팀(참석 16명 이상, 21명이면 7·7·7)은 지역 탐색이다 (13.1절 Q4, 9.7절)",
    )
    strategies: list[Strategy] = Field(
        default=[Strategy.SKILL, Strategy.CHEMISTRY, Strategy.BALANCED], min_length=1, max_length=3,
        description="후보안을 만들 전략 (1~3개, 중복은 하나로). 기본은 3종 전부 (실력 우선 / 친화도 우선 / 종합, 9.5절 가중치 표)",
    )
    constraints: ConstraintSet = Field(default=ConstraintSet(), description="이 회차의 제약. 비우면 제약 없음")

    @field_validator("strategies")
    @classmethod
    def _dedupe(cls, v: list[Strategy]) -> list[Strategy]:
        """같은 전략을 두 번 보내면 하나로 (순서는 처음 나온 대로)."""
        return list(dict.fromkeys(v))


class ConstraintViolation(BaseModel):
    """실현 불가능한 제약 하나. `ValidateResult.violations` 원소 (9.6절 사전 실현가능성 검사 표)."""

    code: str = Field(description="7.4절 에러 코드와 동일 (LOCK_GROUP_TOO_LARGE, CONSTRAINT_CONFLICT, ...)")
    message: str = Field(description="매니저에게 그대로 보여줄 문구. 예: '4명 그룹과 5명 그룹으로는 6명씩 두 팀을 만들 수 없어요'")
    player_ids: list[int] = Field(default=[], description="문제가 된 선수들. 프론트가 칩을 강조하는 데 쓴다")
    group_no: int | None = Field(default=None, description="문제가 된 LOCK/SEPARATE 그룹 번호 (요청 배열의 인덱스). 그룹과 무관하면 None")


class ValidateResult(BaseModel):
    """`POST /events/{id}/assignments:validate` 응답 — 실행 전 프리플라이트.

    S-12 는 제약을 바꿀 때마다 이걸 호출해, `feasible=false` 면 실행 버튼을 비활성화하고 인라인
    경고를 띄운다. 검사 없이 실행하면 알고리즘이 답을 못 찾거나 조용히 제약을 어긴다 (9.6절).
    """

    feasible: bool = Field(description="false면 배정 실행이 422로 막힌다")
    violations: list[ConstraintViolation] = Field(default=[], description="차단 사유. feasible=true면 비어 있다")
    warnings: list[str] = Field(default=[], description="차단은 아니지만 알려줄 것. 예: 빅맨 부족 (FR-34), 게스트 데이터 없음")


class CandidateMetrics(BaseModel):
    """후보안 지표의 권장 형태 — `CandidateView.metrics` (JSONB) 에 들어가는 키 설명.

    JSONB 라 `CandidateView.metrics` 는 `dict[str, Any]` 로 느슨하게 받지만, 실제 내용은 이 형태를
    따른다. 지표가 늘어나도 스키마 마이그레이션이 필요 없게 하려는 선택. S-13 팀별 카드의
    '평균 실력·편차·포지션 아이콘'이 여기서 나온다 (FR-21).
    """

    squad_avg_skill: list[Decimal] = Field(default=[], description="팀별 평균 실력. 인덱스 = squad_no − 1")
    skill_spread: Decimal | None = Field(default=None, description="팀 평균 실력의 최대−최소. 작을수록 균형")
    position_coverage: dict[str, Any] = Field(default={}, description="팀별 1번·5번 확보 여부 등 포지션 커버리지")
    guest_count_per_squad: list[int] = Field(default=[], description="팀별 게스트 수. 한쪽에 몰리지 않았는지 확인용 (w_guest)")


class CandidateView(BaseModel):
    """후보안 하나 — `AssignmentRunView.candidates` 원소, `PATCH /assignments/candidates/{id}` 응답 (S-13).

    MANAGER 시점이라 `squads[].avg_skill` 이 채워진다. 플레이어에게는 `AdoptedAssignment` 만 내려간다.
    """

    id: int = Field(description="assignment_candidates.id. swap / adopt 의 대상")
    strategy: Strategy = Field(description="SKILL(실력 우선) / CHEMISTRY(친화도 우선) / BALANCED(종합)")
    total_score: Decimal | None = Field(default=None, description="목적함수 J 값 (9.5절). 후보안끼리 상대 비교용")
    metrics: dict[str, Any] = Field(description="CandidateMetrics 형태의 지표")
    explanation: str | None = Field(
        default=None,
        description="규칙 기반 설명 문구 (매니저용, 수치 포함). 게스트가 있으면 '게스트 N명은 매니저 지정 등급으로 계산' 명시 (F6)",
    )
    is_adopted: bool = Field(description="확정된 후보안인지. run 안에서 최대 1개")
    squads: list[SquadView] = Field(description="squad_no 오름차순")


class AssignmentRunView(BaseModel):
    """배정 실행 1회 — `POST /events/{id}/assignments` 201 응답, `GET /assignments/runs/{id}`,
    `GET /events/{id}/assignments` 의 items 원소 (MANAGER 전용).

    재배정(노쇼·당일 인원 변동)하면 새 run 이 생기고 이전 run 은 이력으로 남는다 (5.4절).
    """

    id: int = Field(description="assignment_runs.id")
    event_id: int
    team_count: int
    created_at: datetime = Field(description="실행 시각")
    constraints: ConstraintSet = Field(description="이 run 에 적용된 제약 (last-constraints 의 원본)")
    candidates: list[CandidateView] = Field(description="전략별 후보안. 요청한 strategies 순서")
    warnings: list[str] = Field(default=[], description="빅맨·핸들러 부족 등 차단되지 않은 경고 (FR-34)")


class SwapPair(BaseModel):
    """교체할 두 선수. 서로 다른 팀에 있어야 한다."""

    player_id_a: int
    player_id_b: int


class MovePlayer(BaseModel):
    """한 명을 지정한 팀으로 일방 이동 (홀수 인원·한쪽이 부족할 때). 원래 팀에 최소 5명은 남아야 한다."""

    player_id: int
    to_squad_no: int = Field(ge=1)


class Exchange(BaseModel):
    """그룹 단위 교환 — 한쪽 팀의 a_player_ids 와 다른 팀의 b_player_ids 를 서로 상대 팀으로 보낸다.

    한쪽이 비어 있으면 일방 이동이다. 묶음(LOCK)에 속한 사람이 포함되면 묶음 전체가 자동으로 함께 움직이고,
    갈라놓기(SEPARATE)는 교환 뒤에도 서로 다른 팀이어야 한다. 미리 배치(PIN)는 옮길 수 없다.
    """

    a_player_ids: list[int] = Field(default=[], max_length=MAX_GROUP_SIZE, description="같은 팀에 있는 선수들 (상대 팀으로 이동)")
    b_player_ids: list[int] = Field(default=[], max_length=MAX_GROUP_SIZE, description="다른 팀에 있는 선수들 (a 쪽 팀으로 이동)")
    to_squad_no: int | None = Field(default=None, ge=1, description="한쪽만 보낼 때 옮길 팀 번호. 3팀이면 꼭 넣는다 (2팀은 상대 팀)")


class SwapRequest(BaseModel):
    """후보안 수동 수정 — `PATCH /assignments/candidates/{id}` (MANAGER 전용, S-13 드래그 swap, FR-22).

    교체 후 지표가 즉시 재계산되어 `CandidateView` 로 돌아온다. 같은 팀끼리, 후보안에 없는 선수,
    LOCK 그룹을 깨는 교체는 422 INVALID_SWAP. 교체된 슬롯은 `is_manual_override=true` 로 표시된다.
    swaps → moves → exchanges 를 차례로 적용하고 한 번에 저장한다 — 어느 하나라도 422 면 아무것도 바뀌지 않는다.
    """

    swaps: list[SwapPair] = Field(default=[], max_length=MAX_GROUPS, description="맞교체할 쌍 (Exchange 1:1 과 같음). 순서대로 적용")
    moves: list[MovePlayer] = Field(default=[], max_length=MAX_GROUPS, description="일방 이동 (Exchange 한쪽 비움과 같음). swaps 뒤에 적용")
    exchanges: list[Exchange] = Field(default=[], max_length=MAX_GROUPS, description="그룹 단위 교환. 묶음은 자동으로 통째로 움직인다. moves 뒤에 적용")


class AdoptedAssignment(BaseModel):
    """확정된 배정 — `POST /assignments/candidates/{id}:adopt` 응답, `GET /events/{id}/assignment/adopted`.

    **액터별로 마스킹**된다 (FR-23, FR-24):
    - MANAGER / ADMIN: `squads[].avg_skill` 포함
    - PLAYER: `avg_skill=None`, 팀원 카드는 등급만 (S-14 "내 팀 강조 카드")
    아직 확정 전이면 404 NOT_ADOPTED_YET, 두 번 확정하면 409 ALREADY_ADOPTED.
    """

    run_id: int
    candidate_id: int
    strategy: Strategy = Field(description="채택된 전략")
    squads: list[SquadView]
    explanation: str | None = Field(default=None, description="설명 문구. 플레이어에게는 포지션·조합 중심 문장")
    my_squad_no: int | None = Field(default=None, description="호출자가 속한 팀 번호. 참석자가 아니면 None")
    my_player_id: int | None = Field(default=None, description="호출자의 players.id (배정에 포함된 경우). 프론트가 '(나)' 표시에 쓴다")
    my_assigned_position: str | None = Field(default=None, description="호출자에게 배정된 포지션 (PG/SG/SF/PF/C). 없으면 None")
    adopted_at: datetime | None = None
    skill_spread: float | None = Field(default=None, description="가장 강한 팀과 가장 약한 팀의 예상 평균 실력 차이 (점/쿼터, 2팀이면 두 팀 차). 팀 단위 값이라 플레이어에게도 보여준다")
    total_score: float | None = Field(default=None, description="균형 점수 (낮을수록 균형). 목적함수 J")
