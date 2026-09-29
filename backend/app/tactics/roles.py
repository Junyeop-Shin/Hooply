"""선수별 역할 점수 (docs/07 FR-43, 7절).

설문 값을 0~1 항(term)으로 바꾼 뒤 역할마다 가중합한다. 키는 **그 일정 참석자 안의 백분위**라서
같은 사람도 그날 누가 왔느냐에 따라 값이 달라진다.

설문이 없는 사람(게스트, 설문 전 회원)은 설문 항을 **그 일정 참석자 중 설문이 있는 사람의 평균**으로
채운다. 채운 항은 점수에는 들어가지만 "충족 속성"으로는 말하지 않는다 — 그 사람에 대해 아는 것이 아니므로.
키와 가능 포지션은 게스트도 자기 값이 있어 그대로 쓴다.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from statistics import mean
from typing import TYPE_CHECKING

from app.tactics.play import ROLES, Role

if TYPE_CHECKING:  # survey_service 는 DB 모델을 불러오므로 타입 확인 때만
    from app.services.survey_service import SurveyFeatures

B1_CODES: tuple[str, ...] = (
    "CATCH_SHOOT", "PULLUP", "DRIVE_FINISH", "PNR_HANDLER", "PNR_ROLL_POP", "POST_UP", "OFFBALL_CUT", "PUTBACK",
)
GUARDS = frozenset({"PG", "SG"})
FORWARDS = frozenset({"SF", "PF"})
CENTERS = frozenset({"C"})

MATCH_THRESHOLD = 0.5  # 항의 값이 이 이상이면 충족 속성, 가장 큰 항이 이 미만이면 미충족 속성

# 역할별 (항, 가중치). 가중치 합은 1. 데이터가 쌓이면 여기만 고친다 (명세 O4)
ROLE_WEIGHTS: dict[Role, tuple[tuple[str, float], ...]] = {
    "ball_handler": (("handle", 0.40), ("B1:PNR_HANDLER", 0.30), ("pos:G", 0.15), ("pass", 0.15)),
    "screener_roll": (("height", 0.35), ("B1:PNR_ROLL_POP", 0.25), ("finish", 0.20), ("pos:CF", 0.20)),
    "screener_pop": (("height", 0.35), ("B1:PNR_ROLL_POP", 0.25), ("range", 0.40)),
    "shooter": (("range", 0.50), ("B1:CATCH_SHOOT", 0.35), ("pos:GF", 0.15)),
    "cutter": (("B1:OFFBALL_CUT", 0.45), ("B1:DRIVE_FINISH", 0.35), ("stamina", 0.20)),
    "post": (("height", 0.40), ("B1:POST_UP", 0.45), ("pos:CF", 0.15)),
    "spacer": (("range", 0.70), ("B1:CATCH_SHOOT", 0.30)),
}

# 충족·미충족 속성으로 화면과 LLM 에 보여 줄 이름
TERM_LABEL: dict[str, str] = {
    "handle": "볼 운반",
    "pass": "패스",
    "height": "키",
    "range": "슛 거리",
    "stamina": "체력",
    "finish": "골밑 마무리",
    "pos:G": "가드 포지션",
    "pos:CF": "빅맨·포워드 포지션",
    "pos:GF": "가드·포워드 포지션",
    "B1:CATCH_SHOOT": "캐치앤슛",
    "B1:DRIVE_FINISH": "돌파 마무리",
    "B1:PNR_HANDLER": "픽앤롤 핸들러",
    "B1:PNR_ROLL_POP": "픽앤롤 롤·팝",
    "B1:POST_UP": "포스트업",
    "B1:OFFBALL_CUT": "오프볼 컷",
}

NO_SURVEY = "설문 없음"
NO_SURVEY_GUEST = "설문 없음(게스트)"


@dataclass
class RoleInput:
    """한 선수의 역할 점수 재료. 설문 값은 모두 0~1, 설문이 없으면 `has_survey=False` 로 두고 비운다.

    `b1` 공격 옵션(B1) 에서 고른 코드 · `shot_range` B2 · `handle` B3 · `passing`·`stamina` 기존 6축 / 10.
    """

    player_id: int
    height_cm: int | None = None
    positions: frozenset[str] = frozenset()  # 가능 포지션 PG/SG/SF/PF/C
    is_guest: bool = False
    has_survey: bool = False
    b1: frozenset[str] = frozenset()
    shot_range: float | None = None
    handle: float | None = None
    passing: float | None = None
    stamina: float | None = None


@dataclass
class PlayerRoles:
    player_id: int
    scores: dict[Role, float]  # 역할 → 0~1
    terms: dict[str, float]  # 항 → 0~1 (채운 값 포함)
    imputed: frozenset[str] = field(default_factory=frozenset)  # 참석자 평균으로 채운 항
    notes: tuple[str, ...] = ()  # 역할과 무관하게 붙는 미충족 속성 ("설문 없음(게스트)")

    def matched_attrs(self, role: Role) -> list[str]:
        """이 역할의 항 중 값이 기준 이상이고, 본인 데이터로 확인된 것 (가중치 큰 순)."""
        return [
            TERM_LABEL[t] for t, _ in ROLE_WEIGHTS[role]
            if t not in self.imputed and self.terms[t] >= MATCH_THRESHOLD
        ]

    def missing_attrs(self, role: Role) -> list[str]:
        """설문 없음 표시 + 이 역할에서 가중치가 가장 큰 항이 기준 미만이면 그 항."""
        out = list(self.notes)
        top, _ = ROLE_WEIGHTS[role][0]
        if top not in self.imputed and self.terms[top] < MATCH_THRESHOLD:
            out.append(TERM_LABEL[top])
        return out


def _height_percentiles(inputs: list[RoleInput]) -> dict[int, float]:
    """참석자 안의 키 백분위 0~1. 자기보다 작은 사람 + 같은 사람의 절반을 나머지 인원으로 나눈다.

    키가 없는 사람은 0.5 (가운데). 비교 대상이 없으면 모두 0.5.
    """
    known = [i.height_cm for i in inputs if i.height_cm is not None]
    out: dict[int, float] = {}
    for i in inputs:
        if i.height_cm is None or len(known) < 2:
            out[i.player_id] = 0.5
            continue
        lower = sum(1 for h in known if h < i.height_cm)
        same = sum(1 for h in known if h == i.height_cm) - 1  # 본인 제외
        out[i.player_id] = (lower + 0.5 * same) / (len(known) - 1)
    return out


def _survey_terms(i: RoleInput) -> dict[str, float]:
    """설문에서만 나오는 항. 설문이 없으면 빈 dict (평균으로 채운다)."""
    if not i.has_survey:
        return {}
    b1 = {f"B1:{c}": float(c in i.b1) for c in B1_CODES}
    return {
        **b1,
        "handle": i.handle or 0.0,
        "range": i.shot_range or 0.0,
        "pass": i.passing or 0.0,
        "stamina": i.stamina or 0.0,
        "finish": max(b1["B1:PUTBACK"], b1["B1:DRIVE_FINISH"]),
    }


def _position_terms(i: RoleInput) -> dict[str, float]:
    p = i.positions
    return {
        "pos:G": float(bool(p & GUARDS)),
        "pos:CF": float(bool(p & (CENTERS | FORWARDS))),
        "pos:GF": float(bool(p & (GUARDS | FORWARDS))),
    }


def _weighted(terms: dict[str, float], role: Role) -> float:
    return sum(w * terms[t] for t, w in ROLE_WEIGHTS[role])


def compute_role_scores(inputs: Iterable[RoleInput]) -> dict[int, PlayerRoles]:
    """그 일정 참석자 전원(블랙+화이트)을 한꺼번에 넣는다. 키 백분위와 설문 평균의 기준이 참석자 전체다."""
    inputs = list(inputs)
    heights = _height_percentiles(inputs)
    surveyed = {i.player_id: _survey_terms(i) for i in inputs if i.has_survey}
    survey_keys = next(iter(surveyed.values())).keys() if surveyed else _survey_terms(
        RoleInput(player_id=0, has_survey=True)
    ).keys()
    # 설문이 한 명도 없으면 설문 항은 모두 0 — 키·포지션만으로 순위가 갈린다
    avg = {k: mean(t[k] for t in surveyed.values()) if surveyed else 0.0 for k in survey_keys}

    out: dict[int, PlayerRoles] = {}
    for i in inputs:
        own = surveyed.get(i.player_id)
        terms = {**(own if own is not None else avg), **_position_terms(i), "height": heights[i.player_id]}
        imputed = frozenset() if own is not None else frozenset(avg)
        notes: tuple[str, ...] = () if own is not None else ((NO_SURVEY_GUEST,) if i.is_guest else (NO_SURVEY,))
        out[i.player_id] = PlayerRoles(
            player_id=i.player_id,
            scores={r: round(_weighted(terms, r), 4) for r in ROLES},
            terms=terms,
            imputed=imputed,
            notes=notes,
        )
    return out


def role_input_from_features(
    player_id: int, features: "SurveyFeatures | None", *, height_cm: int | None, positions: Iterable[str],
    is_guest: bool,
) -> RoleInput:
    """survey_service.SurveyFeatures → RoleInput. 설문이 없으면 features=None."""
    base = RoleInput(player_id=player_id, height_cm=height_cm, positions=frozenset(positions), is_guest=is_guest)
    if features is None:
        return base
    base.has_survey = True
    base.b1 = frozenset(features.b1_codes)
    base.shot_range = features.shot_range
    base.handle = features.handle
    base.passing = features.axes.get("passing", 0.0) / 10
    base.stamina = features.axes.get("stamina", 0.0) / 10
    return base
