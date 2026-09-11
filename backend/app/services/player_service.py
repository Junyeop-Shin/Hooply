"""`Player` ORM 객체 → API 응답 카드 변환 (설계서 7.2절 공통 스키마 · FR-24 · FR-28).

이 모듈은 DB를 건드리지 않는 **순수 변환 계층**이다. 하는 일은 두 가지:

1. 실력 수치를 5등급(`SkillGrade` A~E)으로 요약한다.
2. 호출자(액터)에 따라 **무엇을 보여줄지** 결정한다 — 마스킹 규칙.

마스킹 규칙 (3.3절 권한 매트릭스 · 9.2절 "표시 정책"):
- `PlayerCard` — **플레이어에게 보이는 뷰.** 등급(`skill_grade`)과 포지션, 신뢰도만
  담는다. `skill_overall` 같은 숫자 필드 자체가 스키마에 없으므로 실수로 새어 나갈
  수 없다.
- `PlayerCardDetailed` — **매니저/관리자 전용.** `PlayerCard`를 상속해 `skill_overall`,
  `prior_overall`, 6축 세부 점수, 평균 마진, 출전 쿼터 수를 추가한다.
  매니저가 배정 결과를 판단하려면 근거 수치가 필요하다는 판단(13.1절 Q3)에 따른다.

어느 변환기를 쓸지는 라우터가 요청자의 역할을 보고 고른다
(`teams.py`: `to_card_detailed if detailed else to_card`). 이 모듈은 권한을 검사하지
않는다 — 잘못된 변환기를 고르면 그대로 노출되므로, 새 엔드포인트를 추가할 때는
"플레이어 요청이면 반드시 `to_card`"를 지켜야 한다.

수치를 숨기는 이유: 동호회에서 실력 점수가 공개되면 갈등이 생기고(10장 "실력 점수
공개로 인한 갈등"), 매 쿼터 흔들리는 숫자는 신뢰를 잃는다. 등급은 8쿼터 단위로만
갱신 표시하는 것이 원칙이나, 그 주기 제어는 아직 구현 전이다.
"""

from decimal import Decimal

from app.models import Player
from app.models.enums import PlayerKind, Position
from app.schemas.common import PlayerCard, PlayerCardDetailed, SkillGrade


def skill_grade_of(skill: Decimal | None) -> SkillGrade | None:
    """실력 수치(쿼터당 득실 기여, 점)를 5등급으로 변환한다 (FR-28).

    현재 경계값은 **임시 절대 구간**이다:
        A ≥ +2 · B ≥ +1 · C ≥ −1 · D ≥ −2 · E < −2
    9.2절에서 개인 실력 표준편차를 약 2점으로 가정하므로, 대략 "±1σ 안이 C, 그 밖이
    B/D, ±2σ 밖이 A/E"에 해당하도록 잡은 값이다.

    이 절대 구간은 **클럽 내 분위수로 교체할 예정**이다. 설계 전체가 "절대 실력이 아니라
    동호회 내 상대 순위"를 다루기 때문(8.1절)이고, 실력이 전반적으로 높은 클럽에서는
    모두가 A, 낮은 클럽에서는 모두가 E가 되는 문제를 피하기 위해서다. 그때는 이 함수가
    팀의 실력 분포(예: 상위 10% → A)를 인자로 받는 형태로 바뀔 것이다.

    입력: `Decimal` 또는 None (프로필이 없거나 사전값·실측값이 아직 없는 경우).
    출력: `SkillGrade` 또는 None. None은 UI에서 "데이터 부족" 배지로 표시된다
    (5.4절 "신규·게스트 데이터 부족").
    """
    if skill is None:
        return None
    if skill >= 2:
        return SkillGrade.A
    if skill >= 1:
        return SkillGrade.B
    if skill >= -1:
        return SkillGrade.C
    if skill >= -2:
        return SkillGrade.D
    return SkillGrade.E


def _positions(player: Player) -> tuple[list[Position], Position | None]:
    """`player.positions`(player_positions 1:N)에서 (가능 포지션 목록, 주 포지션)을 뽑는다.

    - 가능 포지션: `can_play=True`인 행의 포지션 전부 (D1 문항 결과).
    - 주 포지션: `preference_rank`가 있는 행 중 순위가 가장 작은 것 (D1 첫 선택).
      선호를 하나도 매기지 않았으면 None.

    `player.positions`가 lazy load라면 여기서 쿼리가 나갈 수 있으므로, 목록 응답을 만들 때는
    라우터에서 `selectinload` 등으로 미리 적재하는 편이 좋다.
    """
    order = list(Position)
    rows = [p for p in player.positions if p.can_play]
    ranked = sorted((p for p in rows if p.preference_rank is not None), key=lambda p: p.preference_rank)
    rest = sorted((p for p in rows if p.preference_rank is None), key=lambda p: order.index(p.position))
    playable = [p.position for p in ranked + rest]  # 선호 순서 먼저, 나머지는 PG→C
    return playable, (ranked[0].position if ranked else None)


def to_card(player: Player, *, include_grade: bool = False) -> PlayerCard:
    """플레이어용 카드 (`PlayerCard`). 실력은 **등급으로만** 노출한다.

    등급 계산에 쓰는 값의 우선순위:
    1. `skill_overall` — 쿼터 잔차로 갱신된 실측값 (9.2절 층 1 Elo).
    2. 없으면 `prior_overall` — 설문·매니저 정렬·게스트 등급에서 온 사전값 (8.4절).
    3. 둘 다 없으면 None → `skill_grade=None`.
    즉 데이터가 쌓이기 전에는 사전값 기준 등급이 보이고, 경기 기록이 붙으면 실측 기준으로
    자연스럽게 넘어간다.

    `skill_confidence`(0~1)는 숫자이지만 "실력"이 아니라 "얼마나 믿을 만한가"이므로
    플레이어에게도 보여 준다. 0.3 미만이면 UI가 "데이터 부족" 배지를 붙인다.
    `profile`이 None인 방어 분기는 `_add_member`가 항상 프로필을 만들어 주므로 실제로는
    거의 타지 않지만, 게스트 등록 경로 등에서 누락될 가능성에 대비한 것이다.

    부수 효과: 없음.
    """
    playable, primary = _positions(player)
    profile = player.profile
    skill = profile.skill_overall if profile and profile.skill_overall is not None else (
        profile.prior_overall if profile else None
    )
    return PlayerCard(
        id=player.id,
        user_id=player.user_id,
        kind=player.kind,
        display_name=player.display_name,
        role=player.role,
        profile_image_url=player.user.profile_image_url if player.user else None,
        height_cm=player.height_cm if player.kind == PlayerKind.GUEST else (player.user.height_cm if player.user else None),
        skill_grade=skill_grade_of(skill) if include_grade else None,  # 등급은 매니저/ADMIN 에게만 (사용자 결정)
        primary_position=primary,
        playable_positions=playable,
        skill_confidence=profile.skill_confidence if profile else None,
    )


def to_card_detailed(player: Player, *, attended_events: int = 0) -> PlayerCardDetailed:
    """매니저/관리자용 카드 (`PlayerCardDetailed`). `to_card` 결과에 원시 수치를 덧붙인다.

    추가 필드:
    - `skill_overall` / `prior_overall` — 실측값과 사전값을 둘 다 준다. 매니저가
      "설문으로는 B인데 실제로는 D로 나온다" 같은 괴리를 볼 수 있게 하기 위함.
    - `skill_axes` — 6축 세부 점수(슛·볼핸들링·패스·수비·골밑·체력). 8.4절의 세부 축
      매핑 결과이며, 포지션 매칭과 설명 문구 생성(F6)의 재료다.
    - `avg_margin` — 표시용 파생값 `avg_margin_per_quarter`. **원시 마진**이라 실력
      지표가 아니다 (9.1절: 원시 마진은 0으로 수렴). 참고 표시 용도.
    - `quarters_played` — 표본 크기. 프로필이 없으면 0.

    `base.model_dump()`로 부모 필드를 그대로 펼쳐 넣으므로, `PlayerCard`에 필드를
    추가하면 여기도 자동으로 따라온다.

    **이 함수를 플레이어 요청에 쓰면 안 된다.** 호출 전 역할 검사는 라우터 책임이다.
    부수 효과: 없음.
    """
    base = to_card(player, include_grade=True)
    profile = player.profile
    axes = {}
    if profile:
        axes = {
            "shooting": profile.skill_shooting,
            "ball_handling": profile.skill_ball_handling,
            "passing": profile.skill_passing,
            "defense": profile.skill_defense,
            "rebound_post": profile.skill_rebound_post,
            "stamina": profile.skill_stamina,
        }
    return PlayerCardDetailed(
        **base.model_dump(),
        skill_overall=profile.skill_overall if profile else None,
        prior_overall=profile.prior_overall if profile else None,
        skill_axes=axes,
        avg_margin=profile.avg_margin_per_quarter if profile else None,
        quarters_played=profile.quarters_played if profile else 0,
        attended_events=attended_events,
    )
