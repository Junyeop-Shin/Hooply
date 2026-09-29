"""전술 추천 · 전술판 · 이름표 (docs/07 8.3절)."""

from pydantic import BaseModel, Field

from app.tactics.play import Defense, Play, Role


class PresetList(BaseModel):
    presets_version: int
    items: list[Play]


class SlotPlayer(BaseModel):
    player_id: int
    display_name: str


class SlotLineup(BaseModel):
    slot: int
    role: Role
    player_id: int
    display_name: str
    backups: list[SlotPlayer] = Field(description="예비: 같은 전술판 5명 중 이 역할도 잘 맞는 사람 (점수 높은 순, 최대 2명)")
    # 아래는 매니저·ADMIN 에게만 채운다 (설문에서 나온 개인 특성). 팀원에게는 null / 빈 목록
    score: int | None = Field(default=None, description="이 역할 점수 0~100 (매니저만)")
    matched_attrs: list[str] = []
    missing_attrs: list[str] = []
    alt_player_id: int | None = Field(default=None, description="교체 후보: 이 자리에 가장 잘 맞는 벤치 선수 (매니저만)")
    alt_display_name: str | None = None


class PlayLineup(BaseModel):
    play_key: str
    name: str
    summary: str
    defense: Defense
    fit: float = Field(description="적합도 0~100: 전술판 5명의 역할 점수 평균")
    manual: bool = Field(description="매니저가 자리를 바꿔 저장한 배치면 true, 추천 배치면 false")
    counter: str = Field(default="", description="막혔을 때의 대안 — 그날 배치의 선수 이름으로 바꾼 문장")
    slots: list[SlotLineup]


class SquadRecommendation(BaseModel):
    squad_no: int
    squad_name: str
    member_count: int
    items: list[PlayLineup] = Field(description="적합도 기준을 넘은 전술 중 상위 3개. 없으면 빈 목록")


class TacticRecommendation(BaseModel):
    event_id: int
    zone: bool = Field(description="상대 지역 수비 보기. 켜면 zone·any 전술만, 끄면 man·any 전술만")
    fit_min: float = Field(description="추천 기준 적합도. 이 값 이상인 전술만 추천한다")
    presets_version: int
    can_edit: bool
    my_squad_no: int | None
    squads: list[SquadRecommendation]


class SquadMember(BaseModel):
    player_id: int
    display_name: str
    is_guest: bool


class SquadBoard(BaseModel):
    squad_no: int
    squad_name: str
    members: list[SquadMember]  # 자리 바꾸기용 (그날 그 팀 전원)
    lineup: PlayLineup | None  # 팀이 5명 미만이면 None


class EventPlayView(BaseModel):
    play_key: str
    play: Play
    can_edit: bool  # 매니저·ADMIN
    my_squad_no: int | None
    squads: list[SquadBoard]


class SlotIn(BaseModel):
    slot: int = Field(ge=1, le=5)
    player_id: int


class SlotsIn(BaseModel):
    squad_no: int = Field(ge=1)
    slots: list[SlotIn] = Field(max_length=5, description="다섯 자리를 모두 보낸다. 빈 목록이면 추천 배치로 되돌린다")
