"""전술 추천 · 전술판 · 이름표 (docs/07 8.3절)."""

from pydantic import BaseModel, Field

from app.tactics.play import Defense, Play, Role


class PresetList(BaseModel):
    presets_version: int
    items: list[Play]


class SlotRecommendation(BaseModel):
    slot: int
    role: Role
    player_id: int
    display_name: str
    score: int = Field(description="이 역할 점수 0~100")
    matched_attrs: list[str]
    missing_attrs: list[str]
    alt_player_id: int | None = Field(description="교체 후보: 이 자리에 앉혔을 때 점수가 가장 높은 벤치 선수")
    alt_display_name: str | None
    alt_score: int | None


class PlayRecommendation(BaseModel):
    play_key: str
    name: str
    summary: str
    defense: Defense
    fit: float = Field(description="적합도 0~100: 앉힌 5명의 역할 점수 평균")
    slots: list[SlotRecommendation]


class SquadRecommendation(BaseModel):
    squad_no: int
    squad_name: str
    member_count: int
    items: list[PlayRecommendation] = Field(description="적합도 상위 3개. 팀이 5명 미만이면 비어 있다")


class TacticRecommendation(BaseModel):
    event_id: int
    zone: bool = Field(description="상대 지역 수비 토글. 켜면 zone·any 전술만, 끄면 man·any 전술만")
    presets_version: int
    squads: list[SquadRecommendation]


class SlotTag(BaseModel):
    slot: int
    player_id: int
    display_name: str


class SquadMember(BaseModel):
    player_id: int
    display_name: str
    is_guest: bool


class SquadTags(BaseModel):
    squad_no: int
    squad_name: str
    members: list[SquadMember]  # 이름표 고르기용 (그날 그 팀 전원)
    slots: list[SlotTag]  # 저장된 이름표 (없으면 빈 목록)


class EventPlayView(BaseModel):
    play_key: str
    play: Play
    can_edit: bool  # 매니저·ADMIN
    my_squad_no: int | None
    squads: list[SquadTags]


class SlotIn(BaseModel):
    slot: int = Field(ge=1, le=5)
    player_id: int


class SlotsIn(BaseModel):
    squad_no: int = Field(ge=1)
    slots: list[SlotIn] = Field(max_length=5, description="빈 목록이면 이 팀의 이름표를 지운다")


class SavedPlay(BaseModel):
    play_key: str
    name: str
    squad_no: int
    squad_name: str
    filled: int  # 채운 슬롯 수


class SavedPlays(BaseModel):
    event_id: int
    can_edit: bool
    my_squad_no: int | None
    items: list[SavedPlay]
