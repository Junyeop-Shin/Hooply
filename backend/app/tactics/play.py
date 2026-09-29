"""전술 데이터 모델과 재생 가능성 검사 (docs/07 FR-38, FR-39, FR-41).

전술은 좌표 궤적이 아니라 **동작의 순서**로 적는다. 시작 위치 5개와 공을 가진 슬롯에서 출발해,
단계마다 동시에 일어나는 동작을 늘어놓는다. 전술판은 단계 하나를 한 번에 보간해 재생한다.

동작별 필드
  move · dribble · cut   `to`            — 어디로 가는가
  screen                 `to`, `target`  — 어디에 서서 누구에게 스크린을 거는가
  pass · handoff         `target`        — 누구에게 넘기는가 (받은 슬롯이 다음 단계부터 공을 가진다)
  shot                   (없음)
"""

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.josa import substitute

Defense = Literal["man", "zone", "any"]
Situation = Literal["half_court", "inbound"]  # 인바운드는 골밑에서 공을 넣을 때만 쓰는 전술 — 오늘 추천에는 넣지 않는다
Role = Literal["ball_handler", "screener_roll", "screener_pop", "shooter", "cutter", "post", "spacer"]
ActionType = Literal["move", "dribble", "pass", "screen", "cut", "handoff", "shot"]

ROLES: tuple[Role, ...] = ("ball_handler", "screener_roll", "screener_pop", "shooter", "cutter", "post", "spacer")
BALL_ACTIONS: frozenset[str] = frozenset({"dribble", "pass", "handoff", "shot"})  # 공을 가진 슬롯만
_NEEDS_TO: frozenset[str] = frozenset({"move", "dribble", "cut", "screen"})
_NEEDS_TARGET: frozenset[str] = frozenset({"pass", "handoff", "screen"})

ACTION_LABEL: dict[str, str] = {
    "move": "이동", "dribble": "드리블", "pass": "패스", "screen": "스크린",
    "cut": "컷", "handoff": "핸드오프", "shot": "슛",
}

Slot = int  # 1~5


OOB_Y = -0.08  # 베이스라인 뒤(코트 밖). 인바운드에서 공을 넣는 사람이 선다


class Point(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=OOB_Y, le=1)  # 0 = 베이스라인, 음수는 베이스라인 뒤 (인바운드)


class Action(BaseModel):
    type: ActionType
    slot: Slot = Field(ge=1, le=5)  # 동작하는 슬롯
    to: Point | None = None
    target: Slot | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def _fields_match_type(self) -> Self:
        if self.type in _NEEDS_TO and self.to is None:
            raise ValueError(f"{self.type} 에는 도착 위치(to)가 필요해요")
        if self.type not in _NEEDS_TO and self.to is not None:
            raise ValueError(f"{self.type} 에는 도착 위치(to)를 넣지 않아요")
        if self.type in _NEEDS_TARGET and self.target is None:
            raise ValueError(f"{self.type} 에는 대상 슬롯(target)이 필요해요")
        if self.type not in _NEEDS_TARGET and self.target is not None:
            raise ValueError(f"{self.type} 에는 대상 슬롯(target)을 넣지 않아요")
        if self.target is not None and self.target == self.slot:
            raise ValueError(f"{self.slot}번이 자기 자신에게 {ACTION_LABEL[self.type]}할 수 없어요")
        return self


class Step(BaseModel):
    caption: str = Field(min_length=1, max_length=80)  # 전술판 아래 단계 설명 한 줄
    actions: list[Action] = Field(min_length=1)


class Play(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,30}$")  # play_key 는 "preset:<key>"
    name: str = Field(min_length=1, max_length=30)
    summary: str = Field(min_length=1, max_length=80)  # 목록 카드의 한 줄 설명
    defense: Defense  # 이 전술이 노리는 상대 수비
    situation: Situation = "half_court"
    # 막혔을 때의 대안 한두 문장. 자리는 {1}~{5} 로 적는다 — 그날 배치가 있으면 선수 이름, 없으면 "5번" 으로 바꿔 보여 준다
    counter: str = Field(default="", max_length=120)
    start: list[Point] = Field(min_length=5, max_length=5)  # start[i] = 슬롯 i+1 의 시작 위치
    ball: Slot = Field(ge=1, le=5)  # 처음 공을 가진 슬롯
    roles: list[Role] = Field(min_length=5, max_length=5)  # roles[i] = 슬롯 i+1 의 역할
    steps: list[Step] = Field(min_length=1)

    def role_of(self, slot: Slot) -> Role:
        return self.roles[slot - 1]


COUNTER_REF = re.compile(r"\{([1-5])\}")


def render_counter(text: str, names: list[str] | None = None) -> str:
    """"{5}의 롤이 막히면 {3}이" → "서장훈의 롤이 막히면 허재가" (names 없으면 "5번의 … 3번이"). 조사는 받침에 맞춘다."""
    return substitute(text, r"\{([1-5])\}", lambda k: names[int(k) - 1] if names else f"{k}번")


def playability_errors(play: Play) -> list[str]:
    """재생할 수 없는 곳을 "N단계: …" 문장으로 모두 돌려준다. 빈 목록이면 통과.

    규칙
      1. 공은 한 번에 한 명만 가진다 — 한 단계에 공 동작(드리블·패스·핸드오프·슛)은 하나뿐
      2. 공 동작은 그 단계를 시작할 때 공을 가진 슬롯만 할 수 있다
      3. 공을 가진 슬롯은 드리블로만 움직인다 (move·cut 은 트래블링)
      4. 한 슬롯은 한 단계에 동작 하나만 한다 (동시에 재생되므로)
      5. 패스·핸드오프를 받은 슬롯이 다음 단계부터 공을 가진다
      6. 슛 뒤에는 단계가 없고, 마지막 단계는 슛 또는 패스로 끝난다
    """
    errors: list[str] = []
    holder: Slot | None = play.ball
    last = len(play.steps)
    for no, step in enumerate(play.steps, start=1):
        seen: set[Slot] = set()
        ball_actions = [a for a in step.actions if a.type in BALL_ACTIONS]
        if holder is None:
            errors.append(f"{no}단계: 앞 단계에서 슛을 해 공이 없어요")
            break
        if len(ball_actions) > 1:
            errors.append(f"{no}단계: 공 동작은 한 단계에 하나만 할 수 있어요")
        for a in step.actions:
            label = ACTION_LABEL[a.type]
            if a.slot in seen:
                errors.append(f"{no}단계: {a.slot}번이 동작을 두 개 해요. 단계를 나눠 주세요")
            seen.add(a.slot)
            if a.type in BALL_ACTIONS and a.slot != holder:
                errors.append(f"{no}단계: {a.slot}번은 공이 없어 {label}할 수 없어요 (공은 {holder}번)")
            if a.type in ("move", "cut") and a.slot == holder:
                errors.append(f"{no}단계: 공을 가진 {a.slot}번은 {label} 대신 드리블로 움직여요")
        next_holder = holder
        for a in ball_actions:
            if a.slot != holder:
                continue
            if a.type in ("pass", "handoff"):
                next_holder = a.target
            elif a.type == "shot":
                next_holder = None
        if no == last and not any(a.type in ("shot", "pass") for a in ball_actions):
            errors.append(f"{no}단계: 마지막 단계는 슛이나 패스로 끝나야 해요")
        holder = next_holder
    return errors


def holders(play: Play) -> list[Slot | None]:
    """단계마다 시작할 때 공을 가진 슬롯 (len = 단계 수 + 1, 마지막은 끝난 뒤). 검사를 통과한 전술에만 쓴다."""
    out: list[Slot | None] = [play.ball]
    for step in play.steps:
        h = out[-1]
        for a in step.actions:
            if a.slot == h and a.type in ("pass", "handoff"):
                h = a.target
            elif a.slot == h and a.type == "shot":
                h = None
        out.append(h)
    return out
