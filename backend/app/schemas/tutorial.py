"""시작 안내(튜토리얼) — `GET/PUT /me/tutorial`.

가입 직후 홈 체크리스트(며칠 안에 끝나는 준비만)와, 배정·경기 기록처럼 나중에 열리는 기능에 처음 들어갔을 때
한 번 뜨는 안내(tips)로 나뉜다. 체크리스트 단계는 서버가 실제 데이터로 판정한다 — 남의 행동(팀원 모집·일정 등록)이
필요한 단계는 WAITING 과 이유를 내려 준다.
"""

from typing import Literal

from pydantic import BaseModel, Field


class TutorialStep(BaseModel):
    key: str = Field(description="JOIN_TEAM · SURVEY · SELF_RANK · FIRST_RSVP · CREATE_TEAM · INVITE · FIRST_EVENT")
    title: str
    status: Literal["DONE", "TODO", "WAITING"] = Field(description="WAITING = 다른 사람의 행동이 먼저 필요해 아직 할 수 없음")
    hint: str = Field(description="지금 할 일 또는 기다리는 이유")
    link: str | None = Field(default=None, description="눌렀을 때 갈 화면 (TODO 일 때)")
    action: str | None = Field(default=None, description="버튼 문구")


class TutorialView(BaseModel):
    state: str
    path: str | None
    tips_seen: list[str]
    steps: list[TutorialStep] = Field(default=[], description="경로를 고르기 전이면 빈 목록")
    all_done: bool = False


class TutorialUpdate(BaseModel):
    """보낸 것만 바꾼다. state=ACTIVE 만 보내면 경로 선택부터 다시 시작한다 (도움말의 '시작 안내 다시 보기')."""

    state: Literal["ACTIVE", "CLOSED", "DONE", "DECLINED"] | None = None
    path: Literal["PLAYER", "MANAGER"] | None = None
    tip_seen: str | None = Field(default=None, description="닫은 기능별 첫 안내 id (assign · quarters · vote · adopted · records)")
